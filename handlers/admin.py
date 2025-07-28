from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.group_manager import get_allowed_groups
from config import ADMIN_IDS
from utils.message_tracker import track_message  # ✅ Import the tracker

def handle_manage_groups(bot, message, db):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        msg = bot.send_message(message.chat.id, "❌ Only admins can manage groups via private chat.")
        track_message(message.chat.id, msg.message.id)  # ✅ Track the message
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("➕ Add Group", callback_data="add_group"),
        InlineKeyboardButton("🗑️ Remove Group", callback_data="remove_group")
    )

    allowed_groups = set(get_allowed_groups())
    group_docs = list(db["groups"].find({"group_id": {"$in": list(allowed_groups)}}))

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

        # Add groups that are allowed but not in the database
        for gid in allowed_groups - set(g["group_id"] for g in group_docs):
            lines.append(f"• Unknown Group (`{gid}`)")

        group_list = "\n".join(lines)
    else:
        group_list = "_No allowed groups yet._"

    msg = bot.send_message(
        message.chat.id,
        f"📋 *Allowed Groups:*\n\n{group_list}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=markup
    )
    track_message(message.chat.id, msg.message.id)  # ✅ Track the main response
