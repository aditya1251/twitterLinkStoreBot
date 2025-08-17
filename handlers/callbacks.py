from telebot.types import CallbackQuery
from utils.group_manager import add_group, remove_group
from utils.message_tracker import track_message
from handlers.admin import notify_dev
from config import settings
pending_action = {}


def handle_callback(bot, bot_id: str, call: CallbackQuery, db=None):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        if not user_id in settings.ADMIN_IDS:
            bot.answer_callback_query(call.id, "Not authorized.")
            return

        if call.data == "add_group":
            pending_action[user_id] = "add"
            msg = bot.send_message(chat_id, "📥 Send the group ID to *add*.", parse_mode="Markdown")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            bot.answer_callback_query(call.id, "Waiting for group ID...")

        elif call.data == "remove_group":
            pending_action[user_id] = "remove"
            msg = bot.send_message(chat_id, "📤 Send the group ID to *remove*.", parse_mode="Markdown")
            track_message(chat_id, msg.message_id, bot_id=bot_id)
            bot.answer_callback_query(call.id, "Waiting for group ID...")

    except Exception as e:
        notify_dev(bot, e, "handle_callback outer", call.message)
        try:
            bot.answer_callback_query(call.id, "⚠️ Something went wrong.")
        except:
            pass
