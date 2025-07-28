from threading import Lock
from config import ADMIN_IDS
from telegram import Message

active_groups = {}  
group_messages = {}  
sr_requested_users = {}  
lock = Lock()


def start_group_session(group_id):
    with lock:
        active_groups[group_id] = "collecting"
        group_messages[group_id] = []
        sr_requested_users[group_id] = set()


def stop_group_session(group_id):
    with lock:
        active_groups.pop(group_id, None)
        sr_requested_users.pop(group_id, None)
        return group_messages.pop(group_id, [])


def set_verification_phase(group_id):
    with lock:
        if group_id in active_groups:
            active_groups[group_id] = "verifying"


def get_group_phase(group_id):
    return active_groups.get(group_id)


def is_group_verifying(group_id):
    return active_groups.get(group_id) == "verifying"


def add_group_message(group_id, message_data: dict):
    with lock:
        group_messages.setdefault(group_id, []).append(message_data)


def get_group_messages(group_id):
    return group_messages.get(group_id, [])


# SR (screen recording) management
def request_sr(group_id, user_id):
    with lock:
        sr_requested_users.setdefault(group_id, set()).add(user_id)


def get_sr_users(group_id):
    return sr_requested_users.get(group_id, set())

def store_group_message(group_id, user_id, username, link, x_username=None):
    with lock:
        if group_id not in group_messages:
            group_messages[group_id] = []
        
        if not link.startswith("https://x.com"):
            return

        x_username = link.split("/")[3]

        group_messages[group_id].append({
            "user_id": user_id,
            "username": username,
            "link": link,
            "x_username": x_username,
            "check": False,
        })

def mark_user_verified(group_id, user_id):
    with lock:
        if group_id not in group_messages:
            return None

        for msg in group_messages[group_id]:
            if msg["user_id"] == user_id and not msg["check"]:
                msg["check"] = True
                return msg["x_username"]
        
        return None
    
def get_users_with_multiple_links(group_id):
    from collections import defaultdict

    user_links = defaultdict(list)

    for msg in group_messages.get(group_id, []):
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
    seen = set()
    unverified_users = []

    for msg in group_messages.get(group_id, []):
        user_id = msg["user_id"]
        if not msg["check"] and user_id not in seen:
            seen.add(user_id)
            username = msg.get("username")
            name_display = f"@{username}" if username else msg.get("first_name", "Unknown")
            unverified_users.append(name_display)

    return unverified_users

def get_unverified_users_full(group_id):
    seen = set()
    users = []

    for msg in group_messages.get(group_id, []):
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
    chat_id = message.chat.id
    from_id = message.from_user.id

    # Ensure only admins can use
    if from_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can use this command.")
        return

    # Must be a reply to someone's message
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
        return

    target_user = message.reply_to_message.from_user
    user_id = target_user.id
    username = target_user.username or target_user.first_name or "Unknown"

    links = []
    for entry in group_messages.get(chat_id, []):
        if entry["user_id"] == user_id and "link" in entry:
            links.append(entry["link"])

    if not links:
        bot.reply_to(message, f"❌ No links found for @{username}.")
        return

    link_lines = "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    bot.reply_to(
        message,
        f"🔗 *Links shared by @{username}:*\n{link_lines}",
        parse_mode="Markdown"
    )

def handle_sr_command(bot, message: Message):
    chat_id = message.chat.id
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
        f"📹 @{user.username or user.first_name}, please send a *screen recording* of your likes to the admin in DM.",
        parse_mode="Markdown"
    )

def handle_srlist_command(bot, message: Message):
    chat_id = message.chat.id

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
            mentions.append(f"• @{name} (ID: `{entry['user_id']}`)")

    if not mentions:
        mentions = [f"• User ID: `{uid}`" for uid in sr_users]

    bot.send_message(
        chat_id,
        "*📋 Users asked to submit screen recording:*\n" + "\n".join(mentions),
        parse_mode="Markdown"
    )
