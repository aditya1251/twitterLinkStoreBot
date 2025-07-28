from telebot.types import Message
from utils.telegram import is_user_admin
from utils.group_session import start_group_session, stop_group_session

def handle_start_group(bot, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    print(f"Group start: {user_id}")
    if is_user_admin(bot, chat_id, user_id):
        start_group_session(chat_id)
        print(f"Group started: {chat_id}")
        bot.send_message(
                    chat_id,
                    "👋 Hello! I'm your group management bot\n\n"
                    "I encrypt all links shared in the GC using advanced encryption\n"
                    "techniques to ensure your account remains safe, preventing\n"
                    "flagging or demonetization.\n\n"
                    "So please start sharing your post links!"
        )
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
        bot.send_message(chat_id, "Tracking has been stopped. All data cleared.")
        bot.reply_to(message, "Catch you later I'm off to snoozeville! \nZzz... See ya soon!")
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
