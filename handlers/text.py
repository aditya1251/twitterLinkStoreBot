# handlers/text.py
from telebot.types import Message
from utils.group_manager import add_group, remove_group
from utils.group_session import (
    store_group_message,
    get_group_phase,
    mark_user_verified,
    get_sr_users,
    remove_sr_request,
)
from utils.message_tracker import track_message
from utils.telegram import is_user_admin
from handlers.admin import notify_dev
from utils import wizard_state, db


def handle_text(bot, bot_id: str, message: Message, db):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    try:
        if message.chat.type == "private":
            action = wizard_state.pop_pending_action(user_id)
            if action:

                try:
                    group_id = int(text)
                    if action == "add":
                        add_group(bot_id, group_id)
                        msg = bot.send_message(chat_id, f"✅ Group `{group_id}` added.", parse_mode="Markdown")
                        track_message(chat_id, msg.message_id, bot_id=bot_id)
                    elif action == "remove":
                        remove_group(bot_id, group_id)
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

        # ignore admins
        if is_user_admin(bot, chat.id, user.id):
            return
        
        if message and getattr(message, "sender_chat", None):
            sender = message.sender_chat
            if sender.id == chat.id:  # Anonymous Admin sends as the group itself
                return True

        # unify link/content extraction: prefer text, fallback to caption
        link_or_content = (getattr(message, "text", None) or getattr(message, "caption", None) or "")

        if phase == "collecting":
            try:
                # store the link (works for text messages and captioned media)
                store_group_message(
                    bot,
                    bot_id,
                    message,
                    group_id,
                    user.id,
                    user.username,
                    link_or_content,
                    None,
                    user.first_name
                )
            except Exception as e:
                notify_dev(bot, e, "handle_group_text: collecting phase", message)

        elif phase == "verifying":
            try:
                done_keywords = ["done", "all done", "ad", "all dn"]
                content = link_or_content.lower().strip()

                if content in done_keywords or content.startswith("ad"):
                    x_username, status = mark_user_verified(bot_id, group_id, user.id)
                    if x_username:
                        msg = bot.reply_to(message, f"𝕏 ID @{x_username}\n\n profile 🔗: https://x.com/{x_username}")
                        track_message(chat.id, msg.message_id, bot_id=bot_id)
                    else:
                        if status is None:
                            return
                        msg = bot.send_message(chat.id, f"{status}")
                        track_message(chat.id, msg.message_id, bot_id=bot_id)

                    if getattr(message, "caption", None):
                        sr_users = get_sr_users(bot_id, group_id)
                        if user.id in sr_users:
                            remove_sr_request(bot_id, group_id, user.id)

                elif link_or_content.startswith("https://x.com/") or link_or_content.startswith("https://twitter.com/"):
                    try:
                        warn = bot.send_message(
                            chat.id,
                            f"<a href='tg://user?id={user.id}'>{message.from_user.first_name}</a>Invalid Link! Join next session.",
                            parse_mode="HTML"
                        )
                        track_message(chat.id, warn.message_id, bot_id=bot_id)
                    except Exception:
                        pass
                    try:
                        bot.delete_message(chat.id, message.message_id)
                    except Exception:
                        pass

            except Exception as e:
                notify_dev(bot, e, "handle_group_text: verifying phase", message)

    except Exception as e:
        notify_dev(bot, e, "handle_group_text outer", message)
