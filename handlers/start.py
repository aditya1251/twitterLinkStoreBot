from telebot.types import Message
from utils.telegram import is_user_admin
from utils.group_session import start_group_session, stop_group_session, get_group_phase

def handle_start_group(bot, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if is_user_admin(bot, chat_id, user_id):

        already_started = get_group_phase(chat_id)
        if already_started:
            bot.send_message(chat_id,"Group already started!")
            return
        start_group_session(chat_id)
        bot.send_video(chat_id, open("gifs/start.mp4", "rb"))
        bot.send_message(chat_id,"🚀 Start dropping your links!")
    else:
        bot.send_message(chat_id, "❌ Only group admins can start session.")

def handle_cancel_group(bot, message: Message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if is_user_admin(bot, chat_id, user_id):
        data = stop_group_session(chat_id)
        # upload to database
        db["LinksData"].update_one(
            {"chat_id": chat_id},
            {"$push": {"data": data}},
            upsert=True
        )
        bot.send_video(chat_id, open("gifs/close.mp4", "rb"))
        bot.send_message(chat_id, "Tracking has been stopped. All data cleared.")
    else:
        bot.send_message(chat_id, "�� Only group admins can stop session.")

def handle_start(bot, message):
    chat_id = message.chat.id

    welcome_text = (
        "👋 *Welcome!*\n\n"
        "I'm your Telegram group management bot designed to help manage link sharing and keep your groups safe.\n\n"
        "✅ I encrypt and track shared Twitter/X links\n"
        "✅ Help prevent account flags \n"
        "✅ Mute or warn users who don’t follow rules\n\n"
        "Type /help to see what I can do!"
    )

    bot.send_message(chat_id, welcome_text, parse_mode="Markdown")
