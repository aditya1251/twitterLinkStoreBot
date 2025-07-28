from threading import Lock
from config import ADMIN_IDS
from telebot.types import Message

active_groups = {}          # group_id (str) -> phase
group_messages = {}         # group_id (str) -> list of messages
sr_requested_users = {}     # group_id (str) -> set of user_ids
lock = Lock()


def normalize_gid(group_id):
    return str(group_id)

def start_group_session(group_id):
    gid = normalize_gid(group_id)
    with lock:
        active_groups[gid] = "collecting"
        group_messages[gid] = []
        sr_requested_users[gid] = set()

def stop_group_session(group_id):
    gid = normalize_gid(group_id)
    with lock:
        active_groups.pop(gid, None)
        sr_requested_users.pop(gid, None)
        return group_messages.pop(gid, [])

def set_verification_phase(group_id):
    gid = normalize_gid(group_id)
    with lock:
        if gid in active_groups:
            active_groups[gid] = "verifying"

def get_group_phase(group_id):
    return active_groups.get(normalize_gid(group_id))

def is_group_verifying(group_id):
    return active_groups.get(normalize_gid(group_id)) == "verifying"

def add_group_message(group_id, message_data: dict):
    gid = normalize_gid(group_id)
    with lock:
        group_messages.setdefault(gid, []).append(message_data)

def get_group_messages(group_id):
    return group_messages.get(normalize_gid(group_id), [])

def request_sr(group_id, user_id):
    gid = normalize_gid(group_id)
    with lock:
        sr_requested_users.setdefault(gid, set()).add(user_id)

def get_sr_users(group_id):
    return sr_requested_users.get(normalize_gid(group_id), set())

def store_group_message(group_id, user_id, username, link, x_username=None):
    gid = normalize_gid(group_id)
    with lock:
        if gid not in group_messages:
            group_messages[gid] = []

        if not link.startswith("https://x.com"):
            return

        x_username = link.split("/")[3]

        group_messages[gid].append({
            "user_id": user_id,
            "username": username,
            "link": link,
            "x_username": x_username,
            "check": False,
        })

def mark_user_verified(group_id, user_id):
    gid = normalize_gid(group_id)
    x_usernames = set()

    with lock:
        if gid not in group_messages:
            return None

        for msg in group_messages[gid]:
            if msg["user_id"] == user_id and not msg["check"]:
                msg["check"] = True
                x_usernames.add(msg["x_username"])

        return list(x_usernames)[0] if x_usernames else None

def get_users_with_multiple_links(group_id):
    from collections import defaultdict
    gid = normalize_gid(group_id)

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

def get_unverified_users(group_id):
    gid = normalize_gid(group_id)
    seen = set()
    unverified_users = []

    phase = get_group_phase(gid)
    if phase != "verifying":
        return 'notVerifyingphase'

    for msg in group_messages.get(gid, []):
        user_id = msg["user_id"]
        if not msg["check"] and user_id not in seen:
            seen.add(user_id)
            username = msg.get("username")
            name_display = f"@{username}" if username else msg.get("first_name", "Unknown")
            unverified_users.append(name_display)

    return unverified_users

def get_unverified_users_full(group_id):
    gid = normalize_gid(group_id)
    seen = set()
    users = []

    phase = get_group_phase(gid)
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

def handle_link_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)
    from_id = message.from_user.id

    if from_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can use this command.")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
        return

    target_user = message.reply_to_message.from_user
    user_id = target_user.id
    username = target_user.username or target_user.first_name or "Unknown"

    links = [entry["link"] for entry in group_messages.get(chat_id, []) if entry["user_id"] == user_id]

    if not links:
        bot.reply_to(message, f"❌ No links found for @{username}.")
        return

    link_lines = "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    bot.reply_to(
        message,
        f"<b>🔗 Links shared by @{username}:</b>\n{link_lines}",
        parse_mode="HTML"
    )

def handle_sr_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)
    from_id = message.from_user.id

    if from_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can use this command.")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Reply to a user you want to request screen recording from.")
        return

    if not is_group_verifying(chat_id):
        bot.reply_to(message, "⚠️ This group is not in the verifying phase.")
        return

    user = message.reply_to_message.from_user
    request_sr(chat_id, user.id)

    bot.send_message(
        chat_id,
        f"📹 <b>@{user.username or user.first_name}</b>, please send a <b>screen recording</b> of your likes to the admin in DM.",
        parse_mode="HTML"
    )

def handle_srlist_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)

    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can use this command.")
        return

    sr_users = get_sr_users(chat_id)
    if not sr_users:
        bot.reply_to(message, "✅ No users asked for screen recording.")
        return

    mentions = []
    for entry in get_group_messages(chat_id):
        if entry["user_id"] in sr_users:
            name = entry.get("username") or f"User {entry['user_id']}"
            mentions.append(f"• @{name} (ID: <code>{entry['user_id']}</code>)")

    if not mentions:
        mentions = [f"• User ID: <code>{uid}</code>" for uid in sr_users]

    bot.send_message(
        chat_id,
        "<b>📋 Users asked to submit screen recording:</b>\n" + "\n".join(mentions),
        parse_mode="HTML"
    )
