import json
from telebot.types import Message, ChatPermissions
from telebot import types
from utils.message_tracker import track_message
from handlers.admin import notify_dev
from config import settings
from utils.telegram import is_user_admin
from utils.redis_client import get_redis
from telebot.apihelper import ApiTelegramException
import time
ADMIN_IDS = settings.ADMIN_IDS

# === Redis Connection ===
r = get_redis()

# Helper: serialize/deserialize dict safely


def _get(bot_id: str, key: str, default):
    raw = r.hget(f"sessions:{bot_id}", key)
    if raw is None:
        return default
    return json.loads(raw)


def _set(bot_id: str, key: str, value):
    r.hset(f"sessions:{bot_id}", key, json.dumps(value))


def normalize_gid(group_id):
    return str(group_id)

# ---------------- Session Control ----------------


def start_group_session(bot_id: str, group_id):
    gid = normalize_gid(group_id)
    active_groups = _get(bot_id, "active_groups", {})
    group_messages = _get(bot_id, "group_messages", {})
    sr_requested_users = _get(bot_id, "sr_requested_users", {})
    unique_x_usernames = _get(bot_id, "unique_x_usernames", {})

    active_groups[gid] = "collecting"
    group_messages[gid] = []
    sr_requested_users[gid] = []
    unique_x_usernames[gid] = []

    _set(bot_id, "active_groups", active_groups)
    _set(bot_id, "group_messages", group_messages)
    _set(bot_id, "sr_requested_users", sr_requested_users)
    _set(bot_id, "unique_x_usernames", unique_x_usernames)


def stop_group_session(bot_id: str, group_id):
    gid = normalize_gid(group_id)
    active_groups = _get(bot_id, "active_groups", {})
    group_messages = _get(bot_id, "group_messages", {})
    sr_requested_users = _get(bot_id, "sr_requested_users", {})
    unique_x_usernames = _get(bot_id, "unique_x_usernames", {})

    active_groups.pop(gid, None)
    sr_requested_users.pop(gid, None)
    unique_x_usernames.pop(gid, None)
    msgs = group_messages.pop(gid, [])

    _set(bot_id, "active_groups", active_groups)
    _set(bot_id, "group_messages", group_messages)
    _set(bot_id, "sr_requested_users", sr_requested_users)
    _set(bot_id, "unique_x_usernames", unique_x_usernames)

    return msgs


def set_verification_phase(bot_id: str, group_id):
    gid = normalize_gid(group_id)
    active_groups = _get(bot_id, "active_groups", {})
    if gid in active_groups:
        active_groups[gid] = "verifying"
        _set(bot_id, "active_groups", active_groups)


def get_group_phase(bot_id: str, group_id):
    return _get(bot_id, "active_groups", {}).get(normalize_gid(group_id))


def is_group_verifying(bot_id: str, group_id):
    return get_group_phase(bot_id, group_id) == "verifying"

# ---------------- Messages ----------------


def add_group_message(bot_id: str, group_id, message_data: dict):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    group_messages.setdefault(gid, []).append(message_data)
    _set(bot_id, "group_messages", group_messages)


def get_group_messages(bot_id: str, group_id):
    return _get(bot_id, "group_messages", {}).get(normalize_gid(group_id), [])


def request_sr(bot_id: str, group_id, user_id):
    gid = normalize_gid(group_id)
    sr_users = _get(bot_id, "sr_requested_users", {})
    group_messages = _get(bot_id, "group_messages", {})

    sr_users.setdefault(gid, [])
    if user_id not in sr_users[gid]:
        sr_users[gid].append(user_id)

    for msg in group_messages.get(gid, []):
        if msg["user_id"] == user_id:
            msg["check"] = False

    _set(bot_id, "sr_requested_users", sr_users)
    _set(bot_id, "group_messages", group_messages)


def remove_sr_request(bot_id: str, group_id, user_id):
    gid = normalize_gid(group_id)
    sr_users = _get(bot_id, "sr_requested_users", {})
    if gid in sr_users and user_id in sr_users[gid]:
        sr_users[gid].remove(user_id)
        _set(bot_id, "sr_requested_users", sr_users)


def get_sr_users(bot_id: str, group_id):
    return set(_get(bot_id, "sr_requested_users", {}).get(normalize_gid(group_id), []))


def store_group_message(bot, bot_id: str, message: Message, group_id, user_id, username, link, x_username=None, first_name=None):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    unique_x_usernames = _get(bot_id, "unique_x_usernames", {})

    group_messages.setdefault(gid, [])
    unique_x_usernames.setdefault(gid, [])

    # ❌ Only allow x.com links
    if not link.startswith("https://x.com"):
        return

    x_username = link.split("/")[3]

    # 🚫 Prevent same TG user from sending more than one link
    already_sent = any(entry["user_id"] ==
                       user_id for entry in group_messages[gid])
    if already_sent:
        try:
            warn = bot.send_message(
                message.chat.id,
                f"❌ <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>You can only send one link.",
                parse_mode="HTML"
            )
            track_message(message.chat.id, warn.message_id, bot_id=bot_id)
        except Exception:
            pass

        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

        return

    # ✅ First time this X username appears
    if x_username not in unique_x_usernames[gid]:
        unique_x_usernames[gid].append(x_username)
        group_messages[gid].append({
            "number": len(group_messages[gid]) + 1,
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "link": link,
            "x_username": x_username,
            "check": False,
        })
        _set(bot_id, "group_messages", group_messages)
        _set(bot_id, "unique_x_usernames", unique_x_usernames)
        return

    # 🔎 Duplicate username found — collect offenders
    offenders = [
        entry for entry in group_messages[gid]
        if entry["x_username"] == x_username and entry["user_id"] != user_id
    ]
    if len(offenders) < 1:
        group_messages[gid].append({
            "number": len(group_messages[gid]) + 1,
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "link": link,
            "x_username": x_username,
            "check": False,
        })
        _set(bot_id, "group_messages", group_messages)
        return

    offenders.append({
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
    })

    # 🏷️ Create mention links
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
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    track_message(message.chat.id, msg.message_id, bot_id=bot_id)


# 🔹 Utility: Delete a user’s stored link from Redis
def delete_user_link(bot_id: str, group_id, user_id):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    unique_x_usernames = _get(bot_id, "unique_x_usernames", {})

    if gid not in group_messages:
        return False

    # Find the entry for this user
    entry = next(
        (e for e in group_messages[gid] if e["user_id"] == user_id), None)
    if not entry:
        return False

    x_username = entry["x_username"]

    # Remove from messages
    group_messages[gid] = [
        e for e in group_messages[gid] if e["user_id"] != user_id]

    # If no other user is using this x_username, remove it from unique list
    still_used = any(e["x_username"] ==
                     x_username for e in group_messages[gid])
    if not still_used and gid in unique_x_usernames:
        unique_x_usernames[gid] = [
            x for x in unique_x_usernames[gid] if x != x_username]

    # Save updates
    _set(bot_id, "group_messages", group_messages)
    _set(bot_id, "unique_x_usernames", unique_x_usernames)

    return True

# ---------------- Group closing & verification ----------------


def handle_close_group(bot, bot_id: str, message):
    if not is_user_admin(bot, message.chat.id, message.from_user.id):
        msg = bot.reply_to(message, "❌ Only admins can use this command.")
        track_message(message.chat.id, msg.message_id, bot_id=bot_id)
        return
    gid = normalize_gid(message.chat.id)
    active_groups = _get(bot_id, "active_groups", {})
    active_groups[gid] = "closed"
    _set(bot_id, "active_groups", active_groups)

    # ✅ Update group title → {old_name} | CLOSED
    try:
        chat_info = bot.get_chat(message.chat.id)
        old_title = chat_info.title or ""
        new_title = old_title

        if new_title.endswith(" | CLOSED"):
            pass  # already closed
        elif new_title.endswith(" | OPEN"):
            new_title = new_title.rsplit(" | OPEN", 1)[0] + " | CLOSED"
        else:
            new_title = new_title + " | CLOSED"

        if new_title != old_title:
            bot.set_chat_title(message.chat.id, new_title)

    except Exception:
        pass

    # ✅ Restrict group
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

    # ✅ Stop video
    try:
        msg = bot.send_video(message.chat.id, open("gifs/stop.mp4", "rb"))
        msg2 = bot.send_message(
            message.chat.id, "Time line is getting updated wait few mins.")
        track_message(message.chat.id, msg.message_id, bot_id=bot_id)
        track_message(message.chat.id, msg2.message_id, bot_id=bot_id)
    except Exception:
        pass


def mark_user_verified(bot_id: str, group_id, user_id):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    x_usernames = set()
    found_any = False

    if gid not in group_messages:
        return None, "no_group"

    for msg in group_messages[gid]:
        if msg["user_id"] == user_id:
            found_any = True
            if not msg["check"]:
                msg["check"] = True
                x_usernames.add(msg["x_username"])

    _set(bot_id, "group_messages", group_messages)

    if not found_any:
        return None, None
    elif not x_usernames:
        return None, "𝕏 already verified"
    else:
        return list(x_usernames)[0], "verified"


def get_users_with_multiple_links(bot_id: str, group_id):
    from collections import defaultdict
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})

    user_links = defaultdict(list)
    for msg in group_messages.get(gid, []):
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
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})

    grouped = defaultdict(
        lambda: {"x_username": None, "first_name": None, "links": []})
    for msg in group_messages.get(gid, []):
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
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    seen = set()
    unverified_users = []

    phase = get_group_phase(bot_id, gid)
    if phase != "verifying":
        return 'notVerifyingphase'

    for msg in group_messages.get(gid, []):
        user_id = msg["user_id"]
        number = msg["number"]
        if not msg["check"] and user_id not in seen:
            seen.add(user_id)
            unverified_users.append(
                f'{number}. 🅇 ᴵᴰ {msg["x_username"]}| ᵀᴳ '
                f'{ f'@{msg["username"]}' if msg.get("username") else f"<a href=\"tg://user?id={user_id}\">{msg.get("first_name", "User")}</a>" }'
            )

    return unverified_users

def notify_unverified_users(bot, bot_id: str, group_id: int, msg_id: int = None):
    """
    Sends personal DM to unverified users with a 'Verify Now' button linking back to the group.
    Handles Telegram rate limits.
    """
    gid = normalize_gid(group_id)
    unverified = get_unverified_users_full(bot_id, gid)

    if unverified == "notVerifyingphase":
        return "notVerifyingphase"
    if not unverified:
        return "allSafe"

    # Inline button back to group
    group_link = f"https://t.me/c/{gid[4:]}/{msg_id}"
    keyboard = types.InlineKeyboardMarkup()
    verify_button = types.InlineKeyboardButton("✅ Verify Now", url=group_link)
    keyboard.add(verify_button)

    for msg in unverified:
        user_id = msg["user_id"]
        try:
            warning_text = (
                "⚠️ You have not completed the verification in the group.\n\n"
                "Please return to the group and send 'ad' or 'all done' to finish verification."
            )
            bot.send_message(user_id, warning_text, reply_markup=keyboard)
            time.sleep(1)  # ⏳ safe delay to avoid flood (1s per user)
        except ApiTelegramException as e:
            if "Too Many Requests" in str(e):
                # Extract retry time if provided
                retry_after = getattr(e.result_json, "parameters", {}).get("retry_after", 5)
                print(f"⏳ Flood wait triggered, sleeping for {retry_after} seconds")
                time.sleep(retry_after)
                # retry once
                try:
                    bot.send_message(user_id, warning_text, reply_markup=keyboard)
                except Exception:
                    pass
            else:
                # user hasn’t started bot / blocked it
                pass
        except Exception:
            # other unexpected errors
            pass

    return "done"

def get_all_links_count(bot_id: str, group_id):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    unique_users = set(msg["user_id"] for msg in group_messages.get(gid, []))
    return len(unique_users)


def get_unverified_users_full(bot_id: str, group_id):
    gid = normalize_gid(group_id)
    group_messages = _get(bot_id, "group_messages", {})
    seen = set()
    users = []

    phase = get_group_phase(bot_id, gid)
    if phase != "verifying":
        return 'notVerifyingphase'

    for msg in group_messages.get(gid, []):
        uid = msg["user_id"]
        if not msg["check"] and uid not in seen:
            seen.add(uid)
            users.append({
                "user_id": uid,
                "username": msg.get("username"),
                "first_name": msg.get("first_name", "Unknown")
            })
    return users

# ---------------- Admin Handlers ----------------


def handle_add_to_ad_command(bot, bot_id: str, message):
    try:
        chat_id = normalize_gid(message.chat.id)

        if not is_user_admin(bot, chat_id, message.from_user.id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        reply_to_message = message.reply_to_message
        if not reply_to_message:
            msg = bot.reply_to(
                message, "↩️ Please reply to the user's message to get their links.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        user_id = reply_to_message.from_user.id
        display_name = f'<a href="tg://user?id={user_id}">{reply_to_message.from_user.first_name}</a>'

        group_messages = _get(bot_id, "group_messages", {})
        for entry in group_messages.get(chat_id, []):
            if entry["user_id"] == user_id:
                entry["check"] = True
        _set(bot_id, "group_messages", group_messages)

        msg = bot.reply_to(
            message, f"{display_name} has been marked as AD.", parse_mode="HTML")
        track_message(chat_id, msg.message_id, bot_id=bot_id)

        users = get_sr_users(bot_id, chat_id)
        if user_id in users:
            remove_sr_request(bot_id, chat_id, user_id)

    except Exception as e:
        notify_dev(bot, e, "handle_add_to_ad_command", message)


def handle_link_command(bot, bot_id: str, message: Message):
    try:
        chat_id = normalize_gid(message.chat.id)
        from_id = message.from_user.id

        if not is_user_admin(bot, chat_id, from_id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return False

        if not message.reply_to_message:
            msg = bot.reply_to(
                message, "↩️ Please reply to the user's message to get their links.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        target_user = message.reply_to_message.from_user
        user_id = target_user.id
        display_name = f'<a href="tg://user?id={user_id}">{target_user.first_name}</a>'

        links = [
            entry["link"]
            for entry in _get(bot_id, "group_messages", {}).get(chat_id, [])
            if entry["user_id"] == user_id
        ]

        if not links:
            msg = bot.reply_to(
                message, f"❌ No links found for {display_name}.", parse_mode="HTML")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        link_lines = "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
        msg = bot.reply_to(
            message, f"<b>🔗 Links shared by {display_name}:</b>\n{link_lines}", parse_mode="HTML")
        track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_link_command", message)


def handle_sr_command(bot, bot_id: str, message: Message):
    try:
        chat_id = normalize_gid(message.chat.id)

        if not is_user_admin(bot, chat_id, message.from_user.id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        if not message.reply_to_message:
            msg = bot.reply_to(
                message, "↩️ Reply to a user you want to request SR from.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        user_id = message.reply_to_message.from_user.id
        request_sr(bot_id, chat_id, user_id)

        display_name = f'<a href="tg://user?id={user_id}">{message.reply_to_message.from_user.first_name}</a>'
        msg = bot.reply_to(
            message, f"Please recheck {display_name} your likes are missing and send a screen recording 'DM' Make sure your profile is visible too! with TL profile mentioned or pinned as per post", parse_mode="HTML")
        track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_sr_command", message)


def handle_srlist_command(bot, bot_id: str, message: Message):
    try:
        chat_id = normalize_gid(message.chat.id)

        if not is_user_admin(bot, chat_id, message.from_user.id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        sr_users = get_sr_users(bot_id, chat_id)
        if not sr_users:
            msg = bot.reply_to(
                message, "✅ No users asked for screen recording.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        mentions = []
        seen_users = set()
        for entry in get_group_messages(bot_id, chat_id):
            if entry["user_id"] in sr_users and entry["user_id"] not in seen_users:
                username = entry.get("username")
                if username:
                    mentions.append(f"@{username}")
                else:
                    uid = entry["user_id"]
                    num = entry["number"]
                    first_name = entry.get("first_name", "User")
                    mentions.append(
                        f"{num}. <a href=\"tg://user?id={uid}\">{first_name}</a>\n")
                seen_users.add(entry["user_id"])

        if not mentions:
            mentions = [f"User ID: <code>{uid}</code>" for uid in sr_users]

        message_text = (
            " ⚠️ These users need to recheck and send a screen recording video"
            "in this group with your own X/twitter profile visible in it must ❗️\n\n"
            "If you guys ignore sending SR, you will be marked as a"
            "scammer and muted strictly from the group. 🚫🚫\n\n"
        )
        message_text += "\n".join(mentions)

        msg = bot.send_message(chat_id, message_text,
                               parse_mode="HTML", disable_web_page_preview=True)
        track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_srlist_command", message)


def handle_done_keywords(bot, bot_id: str, message: Message, group_id):
    try:
        user = message.from_user
        done_keywords = ["done", "all done", "ad", "all dn"]
        if message.text.lower().strip() in done_keywords:
            x_username, status = mark_user_verified(bot_id, group_id, user.id)
            mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
            if status == "verified":
                msg = bot.reply_to(
                    message, f"{mention}'s X account: {x_username}.", parse_mode="HTML")
            elif status == "already_verified":
                msg = bot.send_message(
                    message.chat.id, f"⚠️ {mention} is already verified.", parse_mode="HTML")
            elif status == "no_messages":
                msg = bot.send_message(
                    message.chat.id, f"⚠️ {mention} hasn't sent any links.", parse_mode="HTML")
            else:
                msg = bot.send_message(
                    message.chat.id, f"⚠️ Unknown error or group not found.", parse_mode="HTML")
            track_message(message.chat.id, msg.message_id, bot_id=bot_id)
    except Exception as e:
        notify_dev(bot, e, "handle_done_keywords", message)
