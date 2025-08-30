from handlers.admin import notify_dev
from telebot.types import Message
from utils.group_session import  get_sr_users,  remove_sr_request
from utils.telegram import is_user_admin
from utils.message_tracker import track_message
from utils.group_session import normalize_gid
from utils.group_session import mark_user_verified, _ns



def handle_add_to_ad_command(bot, bot_id: str, message):
    try:
        chat_id = normalize_gid(message.chat.id)

        if not is_user_admin(bot, chat_id, message.from_user.id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        reply_to_message = message.reply_to_message
        if not reply_to_message:
            msg = bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        user_id = reply_to_message.from_user.id
        display_name = f'<a href="tg://user?id={user_id}">{reply_to_message.from_user.first_name}</a>'

        for entry in _ns(bot_id)["group_messages"].get(chat_id, []):
            if entry["user_id"] == user_id:
                entry["check"] = True

        msg = bot.reply_to(message, f"{display_name} has been marked as AD.", parse_mode="HTML")
        track_message(chat_id, msg.message_id, bot_id=bot_id)
        users = get_sr_users(bot_id, chat_id)
        if user_id in users:
            remove_sr_request(bot_id, chat_id, user_id)
        

    except Exception as e:
        notify_dev(bot, e, "handle_add_to_ad_command", message)



def handle_done_keywords(bot, bot_id: str, message: Message, group_id):
    try:
        user = message.from_user
        done_keywords = ["done", "all done", "ad", "all dn"]
        if message.text.lower().strip() in done_keywords:
            x_username, status = mark_user_verified(bot_id, group_id, user.id)
            mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
            if status == "verified":
                msg = bot.reply_to(message, f"{mention}'s X account: {x_username}.", parse_mode="HTML")
            elif status == "already_verified":
                msg = bot.send_message(message.chat.id, f"⚠️ {mention} is already verified.", parse_mode="HTML")
            elif status == "no_messages":
                msg = bot.send_message(message.chat.id, f"⚠️ {mention} hasn't sent any links.", parse_mode="HTML")
            else:
                msg = bot.send_message(message.chat.id, f"⚠️ Unknown error or group not found.", parse_mode="HTML")
            track_message(message.chat.id, msg.message_id, bot_id=bot_id)
    except Exception as e:
        notify_dev(bot, e, "handle_done_keywords", message)



def handle_link_command(bot, bot_id: str, message: Message):
    try:
        chat_id = normalize_gid(message.chat.id)
        from_id = message.from_user.id

        if not is_user_admin(bot, chat_id, from_id):
            msg = bot.reply_to(message, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return False

        if not message.reply_to_message:
            msg = bot.reply_to(message, "↩️ Please reply to the user's message to get their links.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        target_user = message.reply_to_message.from_user
        user_id = target_user.id
        display_name = f'<a href="tg://user?id={user_id}">{target_user.first_name}</a>'

        links = [entry["link"] for entry in _ns(bot_id)["group_messages"].get(chat_id, []) if entry["user_id"] == user_id]

        if not links:
            msg = bot.reply_to(message, f"❌ No links found for {display_name}.", parse_mode="HTML")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            return

        link_lines = "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
        msg = bot.reply_to(
            message,
            f"<b>🔗 Links shared by {display_name}:</b>\n{link_lines}",
            parse_mode="HTML"
        )
        track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_link_command", message)

