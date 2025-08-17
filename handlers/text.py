from telebot.types import Message
from handlers.callbacks import pending_action
from utils.group_manager import add_group, remove_group
from utils.group_session import store_group_message, get_group_phase, mark_user_verified
from utils.message_tracker import track_message
from utils.telegram import is_user_admin
from handlers.admin import notify_dev


def handle_text(bot, bot_id: str, message: Message, db):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    try:
        if message.chat.type == "private" and user_id in pending_action:
            action = pending_action.pop(user_id)
            try:
                group_id = int(text)
                if action == "add":
                    add_group(bot_id, group_id)
                    msg = bot.send_message(chat_id, f"✅ Group `{group_id}` added.", parse_mode="Markdown")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                elif action == "remove":
                    remove_group(db, bot_id, group_id)
                    msg = bot.send_message(chat_id, f"🗑️ Group `{group_id}` removed.", parse_mode="Markdown")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
            except ValueError:
                msg = bot.send_message(chat_id, "❌ Invalid group ID.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "handle_text: add/remove group", message)
        else:
            msg = bot.send_message(chat_id, "🤖 I didn’t understand that. Use /help.")
            track_message(chat_id, msg.message_id, bot_id=bot_id)

    except Exception as e:
        notify_dev(bot, e, "handle_text outer", message)


def handle_group_text(bot, bot_id: str, message: Message, db):
    try:
        chat = message.chat
        user = message.from_user
        group_id = chat.id
        phase = get_group_phase(bot_id, group_id)

        if is_user_admin(bot, chat.id, user.id):
            return

        if phase == "collecting":
            try:
                store_group_message(
                    bot,
                    bot_id,
                    message,
                    group_id,
                    user.id,
                    user.username or user.first_name,
                    message.text,
                    None,
                    user.first_name
                )
            except Exception as e:
                notify_dev(bot, e, "handle_group_text: collecting phase", message)

        elif phase == "verifying":
            try:
                done_keywords = ["done", "all done", "ad", "all dn"]
                if message.text.lower().strip() in done_keywords:
                    x_username = mark_user_verified(bot_id, group_id, user.id)
                    if x_username:
                        msg = bot.reply_to(message, f"𝕏 ID @{x_username}")
                        track_message(chat.id, msg.message_id, bot_id=bot_id)
                    else:
                        msg = bot.send_message(chat.id, "𝕏 already verified")
                        track_message(chat.id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "handle_group_text: verifying phase", message)

    except Exception as e:
        notify_dev(bot, e, "handle_group_text outer", message)
