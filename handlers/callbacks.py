from telebot.types import CallbackQuery
from utils.group_manager import add_group, remove_group
from config import ADMIN_IDS
from utils.message_tracker import track_message  # ✅ Import tracker

pending_action = {}

def handle_callback(bot, call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Not authorized.")
        return

    if call.data == "add_group":
        pending_action[user_id] = "add"
        msg = bot.send_message(chat_id, "📥 Send the group ID to *add*.", parse_mode="Markdown")
        track_message(chat_id, msg.message.id)  # ✅ Track
    elif call.data == "remove_group":
        pending_action[user_id] = "remove"
        msg = bot.send_message(chat_id, "📤 Send the group ID to *remove*.", parse_mode="Markdown")
        track_message(chat_id, msg.message.id)  # ✅ Track
