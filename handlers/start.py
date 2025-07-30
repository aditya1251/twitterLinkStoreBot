from telebot.types import Message
from utils.telegram import is_user_admin
from utils.group_session import start_group_session, stop_group_session, get_group_phase
from utils.message_tracker import track_message  # ✅ Import tracker


from telebot.types import ChatPermissions


def handle_start_group(bot, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if is_user_admin(bot, chat_id, user_id):

        already_started = get_group_phase(chat_id)
        if already_started:
            msg = bot.send_message(chat_id, "Group already started!")
            track_message(chat_id, msg.message_id)
            return

        # ✅ Start group session logic
        start_group_session(chat_id)

        # ✅ Set group permissions for all users
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        )
        bot.set_chat_permissions(chat_id, permissions)

        # ✅ Media and text messages
        msg = bot.send_video(chat_id, open("gifs/start.mp4", "rb"))
        track_message(chat_id, msg.message_id)
        msg = bot.send_message(chat_id, "🚀 Start dropping your links!")
        track_message(chat_id, msg.message_id)

    else:
        msg = bot.send_message(
            chat_id, "❌ Only group admins can start session.")
        track_message(chat_id, msg.message_id)


def handle_cancel_group(bot, message: Message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if is_user_admin(bot, chat_id, user_id):
        data = stop_group_session(chat_id)
        db["LinksData"].update_one(
            {"chat_id": chat_id},
            {"$push": {"data": data}},
            upsert=True
        )

        # ✅ Try to restrict group permissions
        try:
            restricted_permissions = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
            bot.set_chat_permissions(chat_id, restricted_permissions)
        except Exception:
            pass  # Silently ignore if permission change fails

        # ✅ Send closing media and message
        try:
            msg = bot.send_video(chat_id, open("gifs/close.mp4", "rb"))
            track_message(chat_id, msg.message_id)
        except Exception:
            pass  # In case the video file is missing or invalid

        msg = bot.send_message(
            chat_id, "Tracking has been stopped. All data cleared.")
        track_message(chat_id, msg.message_id)

    else:
        msg = bot.send_message(
            chat_id, "❌ Only group admins can stop session.")
        track_message(chat_id, msg.message_id)


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

    msg = bot.send_message(chat_id, welcome_text, parse_mode="Markdown")
    track_message(chat_id, msg.message_id)  # ✅
