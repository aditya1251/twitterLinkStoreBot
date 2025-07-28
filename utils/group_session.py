from threading import Lock
from config import ADMIN_IDS
from telebot.types import Message
from utils.message_tracker import track_message  # ✅ Import the tracker

active_groups = {}
group_messages = {}
sr_requested_users = {}
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


def store_group_message(group_id, user_id, username, link, x_username=None, first_name=None):
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
            "first_name": first_name,
            "link": link,
            "x_username": x_username,
            "check": False,
        })


def handle_close_group(bot, message):
    gid = normalize_gid(message.chat.id)
    with lock:
        active_groups[gid] = "closed"
    msg = bot.send_video(message.chat.id, open("gifs/stop.mp4", "rb"))
    track_message(message.chat.id, msg.message_id)


def mark_user_verified(group_id, user_id):
    gid = normalize_gid(group_id)
    x_usernames = set()
    found_any = False

    with lock:
        if gid not in group_messages:
            return None, "no_group"

        for msg in group_messages[gid]:
            if msg["user_id"] == user_id:
                found_any = True
                if not msg["check"]:
                    msg["check"] = True
                    x_usernames.add(msg["x_username"])

        if not found_any:
            return None, "no_messages"
        elif not x_usernames:
            return None, "already_verified"
        else:
            return list(x_usernames)[0]


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


def get_formatted_user_link_list(group_id):
    gid = normalize_gid(group_id)
    from collections import defaultdict

    grouped = defaultdict(lambda: {"x_username": None, "first_name": None, "links": []})

    for msg in group_messages.get(gid, []):
        uid = msg["user_id"]
        grouped[uid]["x_username"] = msg["x_username"]
        grouped[uid]["first_name"] = msg.get("first_name", "User")
        grouped[uid]["links"].append(msg["link"])

    if not grouped:
        return None

    result = []
    for i, (uid, data) in enumerate(grouped.items(), start=1):
        name = f'<a href="tg://user?id={uid}">{data["first_name"]}</a>'
        x_username = data["x_username"]
        block = f"{i}. {name} ✦ (𝕏 ID <a href=\"https://x.com/{x_username}\">{x_username}</a>)"
        result.append(block)

    return "\n".join(result), len(result)


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
            unverified_users.append(f'<a href="tg://user?id={user_id}">{msg.get("first_name", "User")}</a>')

    return unverified_users


def get_all_links_count(group_id):
    gid = normalize_gid(group_id)
    return len(group_messages.get(gid, []))


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


def handle_add_to_ad_command(bot, message):
    chat_id = normalize_gid(message.chat.id)

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        msg = bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
        track_message(chat_id, msg.message_id)
        return

    user_id = reply_to_message.from_user.id
    display_name = f'<a href="tg://user?id={user_id}">{reply_to_message.from_user.first_name}</a>'

    for entry in group_messages.get(chat_id, []):
        if entry["user_id"] == user_id:
            entry["check"] = True

    msg = bot.reply_to(message, f"{display_name} have been marked as AD.", parse_mode="HTML")
    track_message(chat_id, msg.message_id)


def handle_link_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)
    from_id = message.from_user.id

    if from_id not in ADMIN_IDS:
        msg = bot.reply_to(message, "❌ Only admins can use this command.")
        track_message(chat_id, msg.message_id)
        return

    if not message.reply_to_message:
        msg = bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
        track_message(chat_id, msg.message_id)
        return

    target_user = message.reply_to_message.from_user
    user_id = target_user.id
    display_name = f'<a href="tg://user?id={user_id}">{target_user.first_name}</a>'

    links = [entry["link"] for entry in group_messages.get(chat_id, []) if entry["user_id"] == user_id]

    if not links:
        msg = bot.reply_to(message, f"❌ No links found for {display_name}.", parse_mode="HTML")
        track_message(chat_id, msg.message_id)
        return

    link_lines = "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    msg = bot.reply_to(
        message,
        f"<b>🔗 Links shared by {display_name}:</b>\n{link_lines}",
        parse_mode="HTML"
    )
    track_message(chat_id, msg.message_id)


def handle_sr_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)
    from_id = message.from_user.id

    if from_id not in ADMIN_IDS:
        msg = bot.reply_to(message, "❌ Only admins can use this command.")
        track_message(chat_id, msg.message_id)
        return

    if not message.reply_to_message:
        msg = bot.reply_to(message, "↩️ Reply to a user you want to request screen recording from.")
        track_message(chat_id, msg.message_id)
        return

    user = message.reply_to_message.from_user
    request_sr(chat_id, user.id)

    mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    msg = bot.send_message(
        chat_id,
        f"📹 {mention}, Please recheck your likes are missing and send a screen recording 'DM' Make sure your profile is visible too!",
        parse_mode="HTML"
    )
    track_message(chat_id, msg.message_id)


def handle_srlist_command(bot, message: Message):
    chat_id = normalize_gid(message.chat.id)

    if message.from_user.id not in ADMIN_IDS:
        msg = bot.reply_to(message, "❌ Only admins can use this command.")
        track_message(chat_id, msg.message_id)
        return

    sr_users = get_sr_users(chat_id)
    if not sr_users:
        msg = bot.reply_to(message, "✅ No users asked for screen recording.")
        track_message(chat_id, msg.message_id)
        return

    mentions = []
    for i, entry in enumerate(get_group_messages(chat_id), start=1):
        if entry["user_id"] in sr_users:
            first_name = entry.get("first_name", "User")
            uid = entry["user_id"]
            mentions.append(
                f"{i}. <a href=\"tg://user?id={uid}\">{first_name}</a>)"
            )

    if not mentions:
        mentions = [f"{i}. User ID: <code>{uid}</code>" for i, uid in enumerate(sr_users, start=1)]

    message_text = "<b>📋 Users asked to submit screen recording:</b>\n" + "\n".join(mentions)
    msg = bot.send_message(chat_id, message_text, parse_mode="HTML")
    track_message(chat_id, msg.message_id)


def handle_done_keywords(bot, message: Message, group_id):
    user = message.from_user
    done_keywords = ["done", "all done", "ad", "all dn"]
    if message.text.lower().strip() in done_keywords:
        x_username, status = mark_user_verified(group_id, user.id)
        mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        if status == "verified":
            msg = bot.reply_to(message, f"{mention}'s X account: {x_username}.", parse_mode="HTML")
        elif status == "already_verified":
            msg = bot.send_message(message.chat.id, f"⚠️ {mention} is already verified.", parse_mode="HTML")
        elif status == "no_messages":
            msg = bot.send_message(message.chat.id, f"⚠️ {mention} hasn't sent any links.", parse_mode="HTML")
        else:
            msg = bot.send_message(message.chat.id, f"⚠️ Unknown error or group not found.", parse_mode="HTML")
        track_message(message.chat.id, msg.message_id)
