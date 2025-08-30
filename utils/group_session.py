from threading import Lock
from telebot.types import Message, ChatPermissions
from utils.message_tracker import track_message
from handlers.admin import notify_dev
from config import settings
from utils.telegram import is_user_admin

ADMIN_IDS = settings.ADMIN_IDS
# === Per-bot in-memory state ===
_sessions = {}
_lock = Lock()

def _ns(bot_id: str):
    if bot_id not in _sessions:
        _sessions[bot_id] = {
            "active_groups": {},
            "group_messages": {},
            "sr_requested_users": {},
            "unique_x_usernames": {}
        }
    return _sessions[bot_id]

def normalize_gid(group_id):
    return str(group_id)

# ---------------- Session Control ----------------
def start_group_session(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        s["active_groups"][gid] = "collecting"
        s["group_messages"][gid] = []
        s["unique_x_usernames"][gid] = set()
        s["sr_requested_users"][gid] = set()

def stop_group_session(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        s["active_groups"].pop(gid, None)
        s["sr_requested_users"].pop(gid, None)
        s["unique_x_usernames"].pop(gid, None)
        return s["group_messages"].pop(gid, [])

def set_verification_phase(bot_id: str, group_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        if gid in s["active_groups"]:
            s["active_groups"][gid] = "verifying"

def get_group_phase(bot_id: str, group_id):
    return _ns(bot_id)["active_groups"].get(normalize_gid(group_id))

def is_group_verifying(bot_id: str, group_id):
    return get_group_phase(bot_id, group_id) == "verifying"

# ---------------- Messages ----------------
def add_group_message(bot_id: str, group_id, message_data: dict):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        s["group_messages"].setdefault(gid, []).append(message_data)

def get_group_messages(bot_id: str, group_id):
    return _ns(bot_id)["group_messages"].get(normalize_gid(group_id), [])

def request_sr(bot_id: str, group_id, user_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        s["sr_requested_users"].setdefault(gid, set()).add(user_id)
        for msg in s["group_messages"].get(gid, []):
            if msg["user_id"] == user_id:
                msg["check"] = False     

def remove_sr_request(bot_id: str, group_id, user_id):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        s["sr_requested_users"].setdefault(gid, set()).remove(user_id)

def get_sr_users(bot_id: str, group_id):
    return _ns(bot_id)["sr_requested_users"].get(normalize_gid(group_id), set())

def store_group_message(bot, bot_id: str, message: Message, group_id, user_id, username, link, x_username=None, first_name=None):
    s = _ns(bot_id)
    gid = normalize_gid(group_id)
    with _lock:
        if gid not in s["group_messages"]:
            s["group_messages"][gid] = []
            s["unique_x_usernames"][gid] = set()

        # only process x.com links
        if not link.startswith("https://x.com"):
            return

        x_username = link.split("/")[3]

        # First time this X username appears
        if x_username not in s["unique_x_usernames"][gid]:
            s["unique_x_usernames"][gid].add(x_username)
            s["group_messages"][gid].append({
                "number": len(s["group_messages"][gid]) + 1,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "link": link,
                "x_username": x_username,
                "check": False,
            })
            return

        # Duplicate detected — collect all users who shared this X username
        offenders = [
            entry for entry in s["group_messages"][gid]
            if entry["x_username"] == x_username and entry["user_id"] != user_id
        ]
        if len(offenders) < 1:
            s["group_messages"][gid].append({
                "number": len(s["group_messages"][gid]) + 1,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "link": link,
                "x_username": x_username,
                "check": False,
            })
            return
        offenders.append({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
        })

        # Create mention links
        tags = []
        for u in offenders:
            name = u.get("first_name") or "User"
            uid = u.get("user_id")
            if uid:
                tags.append(f'<a href="tg://user?id={uid}">{name}</a>')
        tags_str = ", ".join(sorted(set(tags)))

        alert = (
            f"⚠️ <b>Fraud Alert</b>\n"
            f"Multiple users are sharing the same X account link: <code>{x_username}</code>\n"
            f"Suspicious users: {tags_str}"
        )

        msg = bot.reply_to(message, text=alert, parse_mode="HTML")
        track_message(message.chat.id, msg.message_id, bot_id=bot_id)

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
