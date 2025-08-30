"""
utils/group_session.py

DB-backed, low-bandwidth session manager for the Telegram bot.
Drop-in replacement for an in-memory implementation. Persists minimal
state to MongoDB and keeps hot in-memory caches for performance.

Usage:
    from utils.group_session import start_group_session, store_group_message, request_sr

Call ensure_indexes() once on startup (or run the included function)
so necessary indexes are created.

This file intentionally keeps a small API surface that matches the
previous in-repo expectations (so handlers don't need changes).

Key functions provided:
- ensure_indexes()
- start_group_session(bot_id, group_id)
- stop_group_session(bot_id, group_id)
- set_verification_phase(bot_id, group_id)
- get_group_phase(bot_id, group_id)
- store_group_message(bot, bot_id, message, group_id, user_id, username, link, x_username=None, first_name=None)
- get_group_messages(bot_id, group_id, limit=1000)
- request_sr(bot_id, group_id, user_id)
- remove_sr_request(bot_id, group_id, user_id)
- get_sr_users(bot_id, group_id)

Notes:
- This module expects a function `init_db()` in `utils.db` returning a
  connected `pymongo` Database object.
- Where helpful, it will call `handlers.admin.notify_dev` (if available)
  to surface errors during DB operations. If that import fails it will
  fall back to logging to `print()`.

"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

# These imports assume your repo already has them. We try/except to
# provide graceful fallbacks during unit testing.
try:
    from telebot.types import Message, ChatPermissions
except Exception:  # pragma: no cover - telebot may not be installed in tests
    Message = Any
    ChatPermissions = Any

try:
    from utils.db import init_db
except Exception:
    # Provide a helpful error at runtime if DB helper is missing
    def init_db():
        raise RuntimeError("utils.db.init_db() not found — please provide an init_db() that returns a pymongo Database")

try:
    from utils.message_tracker import track_message
except Exception:
    def track_message(*_args, **_kwargs):
        # No-op fallback; keeps behavior safe if tracker missing
        return None

# Optional admin notifier used for reporting unexpected exceptions
try:
    from handlers.admin import notify_dev
except Exception:
    def notify_dev(bot, exc, context=""):
        # Best-effort reporting fallback
        print("[notify_dev]", context, str(exc))

# Module-level in-memory caches (hot caches, safe to evict)
_lock = threading.RLock()
_sessions: Dict[str, Dict[str, Any]] = {}

# Constants
_DEFAULT_MESSAGE_LOAD = 1000


def _ns(bot_id: str) -> Dict[str, Any]:
    """Return the per-bot namespace (initialize lazily)."""
    if bot_id not in _sessions:
        _sessions[bot_id] = {
            "active_groups": {},         # group_id -> phase (collecting|verifying)
            "group_messages": {},        # group_id -> list[small message docs]
            "sr_requested_users": {},    # group_id -> set(user_id)
            "unique_x_usernames": {},    # group_id -> set(x_username)
        }
    return _sessions[bot_id]


def normalize_gid(group_id: Any) -> str:
    return str(group_id)


# ---------------- DB helpers ----------------

def _db():
    return init_db()


def ensure_indexes():
    """Create recommended indexes. Call once at app startup.

    Safe to call multiple times.
    """
    db = _db()
    try:
        db["sessions"].create_index([("bot_id", 1), ("group_id", 1)], unique=True)
        db["session_messages"].create_index([("bot_id", 1), ("group_id", 1), ("x_username", 1)])
        db["session_messages"].create_index([("bot_id", 1), ("group_id", 1), ("user_id", 1)])
        db["session_messages"].create_index([("bot_id", 1), ("group_id", 1), ("message_id", 1)])
        db["sr_requests"].create_index([("bot_id", 1), ("group_id", 1), ("user_id", 1)], unique=True)
        db["tracked_messages"].create_index([("bot_id", 1), ("chat_id", 1)])
    except Exception as e:
        notify_dev(None, e, "ensure_indexes")


def _ensure_session_doc(bot_id: str, group_id: Any):
    db = _db()
    try:
        db["sessions"].update_one(
            {"bot_id": bot_id, "group_id": group_id},
            {
                "$setOnInsert": {
                    "bot_id": bot_id,
                    "group_id": group_id,
                    "phase": "collecting",
                    "started_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
    except Exception as e:
        notify_dev(None, e, "_ensure_session_doc")


# ---------------- Session lifecycle ----------------

def start_group_session(bot_id: str, group_id: Any):
    """Mark a group's session as started (in-memory + persisted meta).

    Idempotent.
    """
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    with _lock:
        ns["active_groups"][gid] = "collecting"
        ns["group_messages"].setdefault(gid, [])
        ns["unique_x_usernames"].setdefault(gid, set())
        ns["sr_requested_users"].setdefault(gid, set())

    try:
        _ensure_session_doc(bot_id, group_id)
    except Exception as exc:
        notify_dev(None, exc, "start_group_session: persist")


def stop_group_session(bot_id: str, group_id: Any) -> List[Dict[str, Any]]:
    """Stop a session and return any cached messages (if desired).

    This clears the in-memory caches for the group but does not delete
    persisted messages — those are retained in `session_messages`.
    """
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    with _lock:
        cached = ns["group_messages"].pop(gid, [])
        ns["active_groups"].pop(gid, None)
        ns["sr_requested_users"].pop(gid, None)
        ns["unique_x_usernames"].pop(gid, None)
    # Optional: mark session ended in DB
    try:
        db = _db()
        db["sessions"].update_one({"bot_id": bot_id, "group_id": group_id}, {"$set": {"ended_at": datetime.utcnow()}}, upsert=False)
    except Exception as exc:
        notify_dev(None, exc, "stop_group_session: mark ended")
    return cached


def set_verification_phase(bot_id: str, group_id: Any):
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    with _lock:
        if gid in ns["active_groups"]:
            ns["active_groups"][gid] = "verifying"
    try:
        db = _db()
        db["sessions"].update_one(
            {"bot_id": bot_id, "group_id": group_id},
            {"$set": {"phase": "verifying", "phase_changed_at": datetime.utcnow()}},
            upsert=True,
        )
    except Exception as exc:
        notify_dev(None, exc, "set_verification_phase: persist")


def get_group_phase(bot_id: str, group_id: Any) -> Optional[str]:
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    return ns["active_groups"].get(gid)


# ---------------- Message handling ----------------

def store_group_message(
    bot,
    bot_id: str,
    message: Message,#type: ignore
    group_id: Any,
    user_id: int,
    username: Optional[str],
    link: str,
    x_username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> bool:
    """Persist a single group message and return True if a fraud alert
    was triggered (duplicate x_username), otherwise False.

    This function intentionally performs a small number of targeted DB
    operations (one find_one and one insert_one) and updates the
    in-memory caches for hot access.
    """
    if not link:
        return False

    # we only care about X/Twitter-like links — adapt predicate as needed
    if "x.com" not in link and "twitter.com" not in link:
        return False

    gid = normalize_gid(group_id)
    db = _db()

    # Try to derive x_username if not supplied
    if not x_username:
        try:
            # naive extraction: https://x.com/username/... or /username
            parts = link.rstrip("/\n\r").split("/")
            # username should be after host, e.g., ['https:', '', 'x.com', 'username', ...]
            if len(parts) >= 4:
                x_username = parts[3]
            else:
                x_username = None
        except Exception:
            x_username = None

    if not x_username:
        # we can't check duplicates reliably without a username
        # still persist message (optional) — but here we'll return False
        return False

    # 1) Check if another message with same x_username exists in this session
    try:
        existing = db["session_messages"].find_one(
            {"bot_id": bot_id, "group_id": group_id, "x_username": x_username},
            projection={"user_id": 1, "first_name": 1, "message_id": 1, "_id": 0},
        )
    except Exception as exc:
        notify_dev(bot, exc, "store_group_message: find_one")
        existing = None

    # Build the document to insert (small, explicit fields)
    msg_doc = {
        "bot_id": bot_id,
        "group_id": group_id,
        "message_id": getattr(message, "message_id", None),
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "link": link,
        "x_username": x_username,
        "check": False,
        "created_at": datetime.utcnow(),
    }

    # 2) Insert the message doc (append-only). If insert fails, report and
    # continue to update in-memory caches to avoid losing state locally.
    try:
        db["session_messages"].insert_one(msg_doc)
    except Exception as exc:
        notify_dev(bot, exc, "store_group_message: insert_one")

    # 3) Update in-memory caches for hot access
    ns = _ns(bot_id)
    with _lock:
        ns["group_messages"].setdefault(gid, []).append(msg_doc)
        ns["unique_x_usernames"].setdefault(gid, set()).add(x_username)

    # 4) If an existing record was found, fetch small offender list and alert
    if existing:
        try:
            offender_cursor = db["session_messages"].find(
                {"bot_id": bot_id, "group_id": group_id, "x_username": x_username},
                projection={"user_id": 1, "first_name": 1, "_id": 0},
            )
            offenders = list(offender_cursor)
        except Exception as exc:
            notify_dev(bot, exc, "store_group_message: fetch_offenders")
            offenders = []

        # Build mention tags for alert (avoid loading large profile info)
        tags = []
        for u in offenders:
            uid = u.get("user_id")
            name = u.get("first_name") or "User"
            if uid:
                tags.append(f'<a href="tg://user?id={uid}">{name}</a>')

        tags_str = ", ".join(sorted(set(tags))) if tags else "(unknown users)"
        alert = (
            f"⚠️ <b>Fraud Alert</b>\n"
            f"Multiple users are sharing the same X account link: <code>{x_username}</code>\n"
            f"Suspicious users: {tags_str}"
        )
        # Try to reply to the message — handlers expect bot-like behavior
        try:
            # Some codebases use bot.reply_to, others use bot.send_message —
            # attempt reply_to, fallback to send_message if missing
            if hasattr(bot, "reply_to"):
                bot.reply_to(message, text=alert, parse_mode="HTML")
            else:
                bot.send_message(getattr(message.chat, "id", None) or getattr(message, "chat", {}).get("id"), alert, parse_mode="HTML")

            # Track the generated bot message so admin commands can act on it
            track_message(getattr(message.chat, "id", None) or getattr(message, "chat", {}).get("id"), getattr(message, "message_id", None), bot_id=bot_id)
        except Exception as exc:
            notify_dev(bot, exc, "store_group_message: send fraud alert")

        return True

    return False


def get_group_messages(bot_id: str, group_id: Any, limit: int = _DEFAULT_MESSAGE_LOAD) -> List[Dict[str, Any]]:
    """Return cached messages for a group; if missing, load from DB (limited).

    Returns a list of small dicts (projection) suitable for iteration.
    """
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    with _lock:
        cache = ns["group_messages"].get(gid)
        if cache:
            # return a shallow copy for safety
            return list(cache)

    # Fallback: load the last `limit` messages from DB ordered by created_at
    db = _db()
    try:
        docs = list(
            db["session_messages"].find(
                {"bot_id": bot_id, "group_id": group_id},
                projection={"_id": 0, "message_id": 1, "user_id": 1, "username": 1, "first_name": 1, "link": 1, "x_username": 1, "check": 1},
            ).sort("created_at", 1).limit(limit)
        )
    except Exception as exc:
        notify_dev(None, exc, "get_group_messages: db load")
        return []

    with _lock:
        ns["group_messages"][gid] = docs
    return docs


# ---------------- SR (special request) handling ----------------

def request_sr(bot_id: str, group_id: Any, user_id: int):
    gid = normalize_gid(group_id)
    db = _db()
    try:
        db["sr_requests"].update_one(
            {"bot_id": bot_id, "group_id": group_id, "user_id": user_id},
            {"$set": {"status": "requested", "requested_at": datetime.utcnow()}, "$unset": {"cleared_at": ""}},
            upsert=True,
        )
    except Exception as exc:
        notify_dev(None, exc, "request_sr: persist")

    with _lock:
        _ns(bot_id)["sr_requested_users"].setdefault(gid, set()).add(user_id)

    # mark user's messages as unchecked (so verifier will re-check them)
    try:
        db["session_messages"].update_many({"bot_id": bot_id, "group_id": group_id, "user_id": user_id}, {"$set": {"check": False}})
    except Exception as exc:
        notify_dev(None, exc, "request_sr: update_messages")


def remove_sr_request(bot_id: str, group_id: Any, user_id: int):
    gid = normalize_gid(group_id)
    db = _db()
    try:
        db["sr_requests"].update_one({"bot_id": bot_id, "group_id": group_id, "user_id": user_id}, {"$set": {"status": "cleared", "cleared_at": datetime.utcnow()}})
    except Exception as exc:
        notify_dev(None, exc, "remove_sr_request: persist")

    with _lock:
        _ns(bot_id)["sr_requested_users"].setdefault(gid, set()).discard(user_id)


def get_sr_users(bot_id: str, group_id: Any) -> Set[int]:
    gid = normalize_gid(group_id)
    ns = _ns(bot_id)
    with _lock:
        cached = ns["sr_requested_users"].get(gid)
        if cached:
            return set(cached)

    # fallback: query DB
    db = _db()
    try:
        docs = db["sr_requests"].find({"bot_id": bot_id, "group_id": group_id, "status": "requested"}, projection={"user_id": 1, "_id": 0})
        users = {d["user_id"] for d in docs}
    except Exception as exc:
        notify_dev(None, exc, "get_sr_users: db")
        users = set()

    with _lock:
        ns["sr_requested_users"][gid] = users
    return users


# ---------------- Utilities ----------------

def clear_cache_for_group(bot_id: str, group_id: Any):
    gid = normalize_gid(group_id)
    with _lock:
        ns = _ns(bot_id)
        ns["group_messages"].pop(gid, None)
        ns["sr_requested_users"].pop(gid, None)
        ns["unique_x_usernames"].pop(gid, None)


def load_session_into_cache(bot_id: str, group_id: Any, limit: int = _DEFAULT_MESSAGE_LOAD):
    """Explicitly load a session's last `limit` messages into the in-memory cache.

    Useful for warming caches on restart for active groups.
    """
    docs = get_group_messages(bot_id, group_id, limit=limit)
    with _lock:
        _ns(bot_id)["group_messages"][normalize_gid(group_id)] = docs


# Expose a small __all__ for clarity
__all__ = [
    "ensure_indexes",
    "start_group_session",
    "stop_group_session",
    "set_verification_phase",
    "get_group_phase",
    "store_group_message",
    "get_group_messages",
    "request_sr",
    "remove_sr_request",
    "get_sr_users",
    "clear_cache_for_group",
    "load_session_into_cache",
]

# ---------------- Group closing & verification ----------------
def handle_close_group(bot, bot_id: str, message):
    gid = normalize_gid(message.chat.id)
    s = _ns(bot_id)
    with _lock:
        s["active_groups"][gid] = "closed"

    try:
        restricted_permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        )
        bot.set_chat_permissions(message.chat.id, restricted_permissions)
    except Exception:
        pass  

    try:
        msg = bot.send_video(message.chat.id, open("gifs/stop.mp4", "rb"))
        track_message(message.chat.id, msg.message_id, bot_id=bot_id)
    except Exception:
        pass

def mark_user_verified(bot_id: str, group_id, user_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    x_usernames = set()
    found_any = False

    with _lock:
        if gid not in s["group_messages"]:
            return None, "no_group"

        for msg in s["group_messages"][gid]:
            if msg["user_id"] == user_id:
                found_any = True
                if not msg["check"]:
                    msg["check"] = True
                    x_usernames.add(msg["x_username"])

        if not found_any:
            return None, "No 𝕏 Link Found"
        elif not x_usernames:
            return None, "𝕏 already verified"
        else:
            return list(x_usernames)[0], "verified"

def get_users_with_multiple_links(bot_id: str, group_id):
    from collections import defaultdict
    s = _ns(bot_id)
    gid = normalize_gid(group_id)

    user_links = defaultdict(list)
    for msg in s["group_messages"].get(gid, []):
        user_links[msg["user_id"]].append(msg)

    result = []
    for user_id, msgs in user_links.items():
        if len(msgs) > 1:
            result.append({
                "user_id": user_id,
                "username": msgs[0].get("username", "Unknown"),
                "count": len(msgs),
                "links": [m["link"] for m in msgs]
            })
    return result

def get_formatted_user_link_list(bot_id: str, group_id):
    from collections import defaultdict
    s = _ns(bot_id)
    gid = normalize_gid(group_id)

    grouped = defaultdict(lambda: {"x_username": None, "first_name": None, "links": []})

    for msg in s["group_messages"].get(gid, []):
        uid = msg["user_id"]
        grouped[uid]["x_username"] = msg["x_username"]
        grouped[uid]["first_name"] = msg.get("first_name", "User")
        grouped[uid]["links"].append(msg["link"])

    if not grouped:
        return None, 0

    result = []
    for i, (uid, data) in enumerate(grouped.items(), start=1):
        name = f'<a href="tg://user?id={uid}">{data["first_name"]}</a>'
        x_username = data["x_username"]
        block = f"{i}. {name} ✦ (𝕏 ID <a href=\"https://x.com/{x_username}\">{x_username}</a>)"
        result.append(block)

    return "\n".join(result), len(result)

def get_unverified_users(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    seen = set()
    unverified_users = []

    phase = get_group_phase(bot_id, gid)
    if phase != "verifying":
        return 'notVerifyingphase'

    for msg in s["group_messages"].get(gid, []):
        user_id = msg["user_id"]
        number = msg["number"]
        if not msg["check"] and user_id not in seen:
            seen.add(user_id)
            unverified_users.append(f'{number}. <a href="tg://user?id={user_id}">{msg.get("first_name", "User")}</a> 𝕏 <code>@{msg["x_username"]}</code>')

    return unverified_users

def get_all_links_count(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    unique_users = set(msg["user_id"] for msg in s["group_messages"].get(gid, []))
    return len(unique_users)

def get_unverified_users_full(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    seen = set()
    users = []

    phase = get_group_phase(bot_id, gid)
    if phase != "verifying":
        return 'notVerifyingphase'

    for msg in s["group_messages"].get(gid, []):
        uid = msg["user_id"]
        if not msg["check"] and uid not in seen:
            seen.add(uid)
            users.append({
                "user_id": uid,
                "username": msg.get("username"),
                "first_name": msg.get("first_name", "Unknown")
            })
    return users
