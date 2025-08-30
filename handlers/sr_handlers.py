from handlers.admin import notify_dev
from telebot.types import Message
from utils.group_session import get_group_messages, get_sr_users, request_sr, remove_sr_request
from utils.telegram import is_user_admin
from utils.message_tracker import track_message
from utils.group_session import normalize_gid


def handle_sr_command(bot, bot_id: str, message: Message):
    try:
        chat_id = normalize_gid(message.chat.id)

        if not is_user_admin(bot, chat_id, message.from_user.id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        if not message.reply_to_message:
            msg = bot.reply_to(message, "↩️ Reply to a user you want to request screen recording from.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        user = message.reply_to_message.from_user
        request_sr(bot_id, chat_id, user.id)

        mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        msg = bot.send_message(
            chat_id,
            f"📹 {mention}, Please recheck your likes are missing and send a screen recording 'DM' Make sure your profile is visible too!",
            parse_mode="HTML"
        )
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
            msg = bot.reply_to(message, "✅ No users asked for screen recording.")
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
                    mentions.append(f"{num}. <a href=\"tg://user?id={uid}\">{first_name}</a>\n")
                seen_users.add(entry["user_id"])

        if not mentions:
            mentions = [f"User ID: <code>{uid}</code>" for uid in sr_users]

        message_text = (
            "📋 <b>These users <i>need</i> to recheck and "
            "<u>send a screen recording video</u> in this group with your own X/twitter profile visible in it must</b>‼️📛📛\n\n"
            "🚫 <b>If you guys ignore sending SR, you will be marked as a scammer and muted strictly from the group.</b> 🚫🚫\n\n"
        )
        message_text += "\n".join(mentions)

        msg = bot.send_message(chat_id, message_text, parse_mode="HTML", disable_web_page_preview=True)
        track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_srlist_command", message)
