from telebot.types import CallbackQuery
from utils.group_manager import add_group, remove_group
from config import ADMIN_IDS
from utils.message_tracker import track_message  # ✅ Import tracker
from handlers.admin import notify_dev

pending_action = {}


def handle_callback(bot, call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        if user_id not in ADMIN_IDS:
            try:
                bot.answer_callback_query(call.id, "Not authorized.")
            except Exception as e:
                notify_dev(bot, e, "handle_callback: unauthorized answer_callback", call.message)
            return

        if call.data == "add_group":
            pending_action[user_id] = "add"
            try:
                msg = bot.send_message(chat_id, "📥 Send the group ID to *add*.", parse_mode="Markdown")
                track_message(chat_id, msg.message_id)
                bot.answer_callback_query(call.id, "Waiting for group ID...")
            except Exception as e:
                notify_dev(bot, e, "handle_callback: add_group response", call.message)
                bot.answer_callback_query(call.id, "⚠️ Error processing your request.")

        elif call.data == "remove_group":
            pending_action[user_id] = "remove"
            try:
                msg = bot.send_message(chat_id, "📤 Send the group ID to *remove*.", parse_mode="Markdown")
                track_message(chat_id, msg.message_id)
                bot.answer_callback_query(call.id, "Waiting for group ID...")
            except Exception as e:
                notify_dev(bot, e, "handle_callback: remove_group response", call.message)
                bot.answer_callback_query(call.id, "⚠️ Error processing your request.")

    except Exception as e:
        notify_dev(bot, e, "handle_callback: outer catch", call.message)
        try:
            bot.answer_callback_query(call.id, "⚠️ Something went wrong.")
        except:
            pass  # even fallback failed silently
