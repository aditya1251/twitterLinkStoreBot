from telebot.types import Message, ChatPermissions
from utils.telegram import is_user_admin
from utils.group_session import start_group_session, stop_group_session, get_group_phase
from utils.message_tracker import track_message
from handlers.admin import notify_dev

def handle_start_group(bot, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        if is_user_admin(bot, chat_id, user_id):
            already_started = get_group_phase(chat_id)
            if already_started:
                try:
                    msg = bot.send_message(chat_id, "Group already started!")
                    track_message(chat_id, msg.message_id)
                except Exception as e:
                    notify_dev(bot, e, "start_group: already started msg", message)
                return

            # ✅ Start session
            start_group_session(chat_id)

            # ✅ Set group permissions
            try:
                permissions = ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                )
                bot.set_chat_permissions(chat_id, permissions)
            except Exception as e:
                notify_dev(bot, e, "start_group: set permissions", message)

            # ✅ Send start video
            try:
                msg = bot.send_video(chat_id, open("gifs/start.mp4", "rb"))
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "start_group: send start.mp4", message)

            try:
                msg = bot.send_message(chat_id, "🚀 Start dropping your links!")
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "start_group: send start text", message)

        else:
            try:
                msg = bot.send_message(chat_id, "❌ Only group admins can start session.")
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "start_group: non-admin warning", message)

    except Exception as e:
        notify_dev(bot, e, "handle_start_group outer", message)


def handle_cancel_group(bot, message: Message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        if is_user_admin(bot, chat_id, user_id):
            try:
                data = stop_group_session(chat_id)
                db["LinksData"].update_one(
                    {"chat_id": chat_id},
                    {"$push": {"data": data}},
                    upsert=True
                )
            except Exception as e:
                notify_dev(bot, e, "cancel_group: session stop or DB update", message)

            # ✅ Restrict group
            try:
                restricted = ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                )
                bot.set_chat_permissions(chat_id, restricted)
            except Exception as e:
                notify_dev(bot, e, "cancel_group: restrict permissions", message)

            # ✅ Close video
            try:
                msg = bot.send_video(chat_id, open("gifs/close.mp4", "rb"))
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "cancel_group: send close.mp4", message)

            try:
                msg = bot.send_message(chat_id, "Tracking has been stopped. All data cleared.")
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "cancel_group: send final text", message)

        else:
            try:
                msg = bot.send_message(chat_id, "❌ Only group admins can stop session.")
                track_message(chat_id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "cancel_group: non-admin warning", message)

    except Exception as e:
        notify_dev(bot, e, "handle_cancel_group outer", message)


def handle_start(bot, message):
    chat_id = message.chat.id

    try:
        welcome_text = (
            "👋 *Welcome!*\n\n"
            "I'm your Telegram group management bot designed to help manage link sharing and keep your groups safe.\n\n"
            "✅ I encrypt and track shared Twitter/X links\n"
            "✅ Help prevent account flags \n"
            "✅ Mute or warn users who don’t follow rules\n\n"
            "Type /help to see what I can do!"
        )
        msg = bot.send_message(chat_id, welcome_text, parse_mode="Markdown")
        track_message(chat_id, msg.message_id)
    except Exception as e:
        notify_dev(bot, e, "handle_start", message)
