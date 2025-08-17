from telebot.types import (
    Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from config import settings
from utils import db
from bson.objectid import ObjectId
from utils.telegram import manager
import re
from telebot.apihelper import ApiTelegramException

TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")

# in-memory state for simple wizard flows
pending_add_token = {}  # {admin_id: chat_id}

BOTS_PER_PAGE = 5  # how many bots per page


# === SAFE EDIT WRAPPER ===
def safe_edit(chat_id, message_id, text, reply_markup=None, parse_mode="Markdown"):
    try:
        manager.admin_bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            # ignore harmless error
            return
        else:
            raise


# === MAIN MENU ===
def show_main_menu(chat_id, message_id=None):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("➕ Add Bot", callback_data="cmd_addbot"),
        InlineKeyboardButton("📋 List Bots", callback_data="cmd_listbots:0"),
    )
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="cmd_help"))

    text = "👋 *Admin Dashboard*\n\nSelect an action below:"
    if message_id:
        safe_edit(chat_id, message_id, text, kb)
    else:
        manager.admin_bot.send_message(
            chat_id, text, parse_mode="Markdown", reply_markup=kb
        )


# === ENTRYPOINT ===
def handle_admin_update(update: Update):
    if update.callback_query:
        return handle_admin_callback(update.callback_query)

    if not update.message:
        return

    message: Message = update.message
    text = message.text or ""

    if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
        manager.admin_bot.reply_to(message, "❌ Not authorized.")
        return

    # Handle wizard "waiting for token"
    if message.from_user.id in pending_add_token:
        token = text.strip()
        pending_add_token.pop(message.from_user.id, None)
        return process_new_bot_token(message, token)

    if text.startswith("/start"):
        show_main_menu(message.chat.id)


# === CALLBACK HANDLER ===
def handle_admin_callback(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
        manager.admin_bot.answer_callback_query(call.id, "❌ Not authorized.")
        return

    cmd = call.data

    if cmd == "cmd_help":
        help_text = (
            "🤖 *Admin Bot Help*\n\n"
            "➕ Add Bot — Register a new child bot\n"
            "📋 List Bots — Show all child bots\n"
            "▶️ Enable Bot — Enable bot & set webhook\n"
            "⏸️ Disable Bot — Disable bot\n"
            "🗑️ Remove Bot — Delete bot\n"
        )
        safe_edit(call.message.chat.id, call.message.message_id, help_text, back_btn())

    elif cmd == "cmd_addbot":
        pending_add_token[call.from_user.id] = call.message.chat.id
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            "➕ Please send me the *bot token* now:",
            back_btn(),
        )

    elif cmd.startswith("cmd_listbots:") or cmd.startswith("page:"):
        page = int(cmd.split(":")[1])
        show_bot_list(call.message.chat.id, call.message.message_id, page)

    elif cmd.startswith("listpage:"):
        _, page = cmd.split(":")
        show_bot_list(call.message.chat.id, call.message.message_id, int(page))

    elif cmd.startswith("info:"):
        _, bid, page = cmd.split(":")
        show_bot_info(call, bid, int(page))

    elif cmd.startswith("enable:"):
        _, bid, page = cmd.split(":")
        enable_bot(call, bid, int(page))

    elif cmd.startswith("disable:"):
        _, bid, page = cmd.split(":")
        disable_bot(call, bid, int(page))

    elif cmd.startswith("remove:"):
        _, bid, page = cmd.split(":")
        remove_bot(call, bid, int(page))

    elif cmd == "back_main":
        show_main_menu(call.message.chat.id, call.message.message_id)

    else:
        manager.admin_bot.answer_callback_query(call.id, "❓ Unknown action.")

    manager.admin_bot.answer_callback_query(call.id)

def escape_markdown(text: str) -> str:
    # Escape characters that Telegram MarkdownV2 treats specially
    return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\]").replace("`", "\\`")



# === BOT LIST ===
def show_bot_list(chat_id, message_id, page=0):
    docs = db.list_bots()
    total = len(docs)

    if total == 0:
        safe_edit(chat_id, message_id, "ℹ️ No child bots yet.", back_btn())
        return

    # paginate
    start = page * BOTS_PER_PAGE
    end = start + BOTS_PER_PAGE
    docs_page = docs[start:end]

    text = f"📋 *Child Bots Panel* (page {page+1}/{(total-1)//BOTS_PER_PAGE+1})\n\n"

    text += "\n".join(
    f"🤖 @{escape_markdown(d.get('name') or 'Unnamed')} ({d.get('status', 'unknown')})"
    for d in docs_page
)

    kb = InlineKeyboardMarkup(row_width=1)

    for d in docs_page:
        bid = str(d["_id"])
        status = d.get("status", "unknown")
        name = d.get("name") or "Unnamed"

        kb.add(InlineKeyboardButton(f"🤖 {name} ({status})", callback_data=f"info:{bid}:{page}"))

        row = []
        if status == "enabled":
            row.append(InlineKeyboardButton("⏸️ Disable", callback_data=f"disable:{bid}:{page}"))
        else:
            row.append(InlineKeyboardButton("▶️ Enable", callback_data=f"enable:{bid}:{page}"))
        row.append(InlineKeyboardButton("🗑️ Remove", callback_data=f"remove:{bid}:{page}"))
        kb.row(*row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page-1}"))
    if end < total:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"page:{page+1}"))
    if nav_row:
        kb.row(*nav_row)

    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))

    safe_edit(chat_id, message_id, text, kb)


# === BOT INFO ===
def show_bot_info(call: CallbackQuery, bid: str, page: int):
    d = db.get_bot_by_id(bid)
    if not d:
        manager.admin_bot.answer_callback_query(call.id, "❌ Bot not found.")
        return

    text = (
        f"🤖 *Bot Info*\n\n"
        f"🆔 ID: `{d['_id']}`\n"
        f"📛 Name: {d.get('name') or 'Unnamed'}\n"
        f"📡 Status: {d.get('status', 'unknown')}\n"
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Back to list", callback_data=f"listpage:{page}"))

    safe_edit(call.message.chat.id, call.message.message_id, text, kb)


# === PROCESS NEW BOT ===
def process_new_bot_token(message: Message, token: str):
    if not TOKEN_PATTERN.match(token):
        manager.admin_bot.send_message(
            message.chat.id,
            "❌ Invalid bot token format.\nExample: `123456:ABCdefGhIJKlmnoPQR`",
            parse_mode="Markdown",
        )
        show_main_menu(message.chat.id)
        return

    existing = db.get_bot_by_token(token)
    if existing:
        manager.admin_bot.send_message(
            message.chat.id,
            f"⚠️ Bot already exists with id `{existing['_id']}`",
            parse_mode="Markdown",
        )
        show_main_menu(message.chat.id)
        return

    bot_id = db.create_bot_doc(token)
    url = f"{settings.BASE_URL.rstrip('/')}/webhook/{bot_id}"
    ok = manager.set_child_webhook(bot_id, url)
    if ok:
        manager.admin_bot.send_message(
            message.chat.id,
            f"✅ Bot added and webhook set!\n🆔 `{bot_id}`",
            parse_mode="Markdown",
        )
    else:
        manager.admin_bot.send_message(message.chat.id, "❌ Failed to set webhook.")

    show_main_menu(message.chat.id)


# === ENABLE BOT ===
def enable_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_status(bid, "enabled")
        url = f"{settings.BASE_URL.rstrip('/')}/webhook/{bid}"
        manager.set_child_webhook(bid, url)
        manager.admin_bot.answer_callback_query(call.id, f"▶️ Bot {bid} enabled.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === DISABLE BOT ===
def disable_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_status(bid, "disabled")
        manager.delete_child_webhook(bid)
        manager.admin_bot.answer_callback_query(call.id, f"⏸️ Bot {bid} disabled.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === REMOVE BOT ===
def remove_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_webhook(bid, None)
        db.bots_collection().delete_one({"_id": ObjectId(bid)})
        manager.child_bots.pop(bid, None)
        manager.admin_bot.answer_callback_query(call.id, f"🗑️ Bot {bid} removed.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === HELPERS ===
def back_btn():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    return kb
