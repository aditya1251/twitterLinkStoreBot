from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.group_manager import get_allowed_groups
from config import ADMIN_IDS
from utils.message_tracker import track_message  # ✅ Import the tracker

def handle_manage_groups(bot, message, db):
    try:
        if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
            try:
                msg = bot.send_message(message.chat.id, "❌ Only admins can manage groups via private chat.")
                track_message(message.chat.id, msg.message_id)
            except Exception as e:
                notify_dev(bot, e, "handle_manage_groups: permission denial reply", message)
            return

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("➕ Add Group", callback_data="add_group"),
            InlineKeyboardButton("🗑️ Remove Group", callback_data="remove_group")
        )

        try:
            allowed_groups = set(get_allowed_groups())
            group_docs = list(db["groups"].find({"group_id": {"$in": list(allowed_groups)}}))
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: DB fetch error", message)
            allowed_groups = set()
            group_docs = []

        try:
            if group_docs or allowed_groups:
                lines = []
                for g in group_docs:
                    title = g.get("title", "Unnamed")
                    gid = g["group_id"]
                    username = g.get("username")
                    if username:
                        link = f"https://t.me/{username}"
                        lines.append(f"• [{title}]({link}) (`{gid}`)")
                    else:
                        lines.append(f"• *{title}* (`{gid}`)")

                for gid in allowed_groups - set(g["group_id"] for g in group_docs):
                    lines.append(f"• Unknown Group (`{gid}`)")

                group_list = "\n".join(lines)
            else:
                group_list = "_No allowed groups yet._"
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: formatting group list", message)
            group_list = "_(Failed to load group list)_"

        try:
            msg = bot.send_message(
                message.chat.id,
                f"📋 *Allowed Groups:*\n\n{group_list}",
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=markup
            )
            track_message(message.chat.id, msg.message_id)
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: sending group list", message)

    except Exception as e:
        notify_dev(bot, e, "handle_manage_groups: outer catch", message)

def notify_dev(bot, error, context, message=None):
    dev_id = 1443989714
    user_info = ""
    if message:
        user = message.from_user
        user_info = f"👤 <b>User:</b> @{user.username or 'N/A'} ({user.id})\n"
        user_info += f"💬 <b>Chat:</b> {message.chat.id}\n"

    error_message = (
        f"⚠️ <b>Error in:</b> {context}\n"
        f"{user_info}"
        f"🧵 <b>Error:</b> <code>{str(error)}</code>"
    )

    try:
        bot.send_message(dev_id, error_message, parse_mode="HTML")
    except Exception as e:
        print(f"[notify_dev failed] {e}")
    print(f"[{context} ERROR] {error}")
