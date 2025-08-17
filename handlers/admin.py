from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.group_manager import get_allowed_groups
from utils.message_tracker import track_message
from config import settings

def handle_manage_groups(bot, bot_id: str, message, db):
    """
    Admin-only command (in private chat) to list allowed groups
    and show inline buttons to add/remove groups.
    """
    try:
        # 🔑 Only allow in private chat
        if message.chat.type != "private":
            msg = bot.send_message(message.chat.id, "❌ Only private chat allowed for managing groups.")
            track_message(message.chat.id, msg.message_id, bot_id=bot_id)
            return

        # 🔑 Check if user is admin in DB (per bot)
        admin_doc = message.from_user.id in settings.ADMIN_IDS
        if not admin_doc:
            msg = bot.send_message(message.chat.id, "❌ You are not authorized to manage groups for this bot.")
            track_message(message.chat.id, msg.message_id, bot_id=bot_id)
            return

        # ✅ Inline buttons
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("➕ Add Group", callback_data="add_group"),
            InlineKeyboardButton("🗑️ Remove Group", callback_data="remove_group")
        )

        # ✅ Fetch groups from DB + config
        try:
            allowed_groups = set(get_allowed_groups(bot_id))
            group_docs = list(db["groups"].find({"group_id": {"$in": list(allowed_groups)}, "bot_id": bot_id}))
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: DB fetch error", message)
            allowed_groups = set()
            group_docs = []

        # ✅ Format group list
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

                # include any group IDs that are allowed but missing in docs
                for gid in allowed_groups - set(g["group_id"] for g in group_docs):
                    lines.append(f"• Unknown Group (`{gid}`)")

                group_list = "\n".join(lines)
            else:
                group_list = "_No allowed groups yet._"
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: formatting group list", message)
            group_list = "_(Failed to load group list)_"

        # ✅ Send result
        try:
            msg = bot.send_message(
                message.chat.id,
                f"📋 *Allowed Groups for this bot:*\n\n{group_list}",
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=markup
            )
            track_message(message.chat.id, msg.message_id, bot_id=bot_id)
        except Exception as e:
            notify_dev(bot, e, "handle_manage_groups: sending group list", message)

    except Exception as e:
        notify_dev(bot, e, "handle_manage_groups outer", message)


def notify_dev(bot, error, context, message=None):
    """
    Notify developer of errors via a fixed developer chat ID.
    """
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
