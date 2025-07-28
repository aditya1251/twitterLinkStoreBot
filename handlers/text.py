from telebot.types import Message
from handlers.callbacks import pending_action
from utils.group_manager import add_group, remove_group
from config import ADMIN_IDS
from utils.group_session import store_group_message, get_group_phase, mark_user_verified
from utils.message_tracker import track_message  # ✅ Import tracker
from utils.telegram import is_user_admin


def handle_text(bot, message: Message, db):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if message.chat.type == "private" and user_id in pending_action:
        action = pending_action.pop(user_id)
        try:
            group_id = int(text)
            if action == "add":
                msg = bot.send_message(chat_id, f"✅ Group `{group_id}` added.", parse_mode="Markdown")
                track_message(chat_id, msg.message_id)  # ✅
                add_group(group_id)
            elif action == "remove":
                msg = bot.send_message(chat_id, f"🗑️ Group `{group_id}` removed.", parse_mode="Markdown")
                track_message(chat_id, msg.message_id)  # ✅
                remove_group(group_id)
        except ValueError:
            msg = bot.send_message(chat_id, "❌ Invalid group ID.")
            track_message(chat_id, msg.message_id)  # ✅
    else:
        msg = bot.send_message(chat_id, "🤖 I didn’t understand that. Use /help.")
        track_message(chat_id, msg.message_id)  # ✅


def handle_group_text(bot, message, db):
    chat = message.chat
    user = message.from_user

    group_id = chat.id
    phase = get_group_phase(group_id)

    if is_user_admin(bot, chat.id, user.id):
        return

    if phase == "collecting":
        store_group_message(
            group_id,
            user.id,
            user.username or user.first_name,
            message.text,
            None,  # you can extract x_username if needed
            user.first_name
        )

    elif phase == "verifying":
        done_keywords = ["done", "all done", "ad", "all dn"]
        if message.text.lower().strip() in done_keywords:
            if x_username := mark_user_verified(group_id, user.id):
                bot.reply_to(message, f"𝕏 ID @{x_username}")
            else:
                msg = bot.send_message(chat.id, "𝕏 already verified")
                track_message(chat.id, msg.message_id)  # ✅
