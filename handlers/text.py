from telebot.types import Message
from handlers.callbacks import pending_action
from utils.group_manager import add_group, remove_group
from config import ADMIN_IDS
from utils.group_session import store_group_message, get_group_phase, mark_user_verified

def handle_text(bot, message: Message, db):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if message.chat.type == "private" and user_id in pending_action:
        action = pending_action.pop(user_id)
        try:
            group_id = int(text)
            if action == "add":
                add_group(group_id)
                bot.send_message(chat_id, f"✅ Group `{group_id}` added.", parse_mode="Markdown")
            elif action == "remove":
                remove_group(group_id)
                bot.send_message(chat_id, f"🗑️ Group `{group_id}` removed.", parse_mode="Markdown")
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid group ID.")
    else:
        bot.send_message(chat_id, "🤖 I didn’t understand that. Use /help.")


def handle_group_text(bot, message, db):
    chat = message.chat
    user = message.from_user

    group_id = chat.id
    phase = get_group_phase(group_id)

    if phase == "collecting":
        store_group_message(
            group_id,
            user.id,
            user.username or user.first_name,
            message.text,
            None  # you can extract x_username if needed
        )

    elif phase == "verifying":
        done_keywords = ["done", "all done", "ad", "all dn"]
        if message.text.lower().strip() in done_keywords:
            if x_username := mark_user_verified(group_id, user.id):
                bot.reply_to(message, f"@{user.username or user.first_name}'s X account: {x_username}.")
            else:
                bot.send_message(chat.id, f"⚠️ @{user.username or user.first_name} already verified or no links sent.")
