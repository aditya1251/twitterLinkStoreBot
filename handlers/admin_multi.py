from utils import wizard_state, db
from telebot.types import (
    Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from telebot.apihelper import ApiTelegramException
from bson.objectid import ObjectId
from config import settings
from utils import db, wizard_state
from utils.db import ALL_MAIN_COMMANDS, get_bot_commands
from utils.telegram import manager
from handlers.admin import notify_dev
import re

# === CONSTANTS ===
TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
BOTS_PER_PAGE = 5  # Number of bots shown per page


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
            return
        else:
            raise


# === MAIN MENU ===
def show_main_menu(chat_id, message_id=None):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Bot", callback_data="cmd_addbot"),
        InlineKeyboardButton("📋 List Bots", callback_data="cmd_listbots:0"),
    )
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="cmd_help"))

    text = (
        "👋 *Admin Dashboard*\n\n"
        "Welcome to your control panel. Choose an action below:"
    )
    if message_id:
        safe_edit(chat_id, message_id, text, kb)
    else:
        manager.admin_bot.send_message(
            chat_id, text, parse_mode="Markdown", reply_markup=kb)


# === HANDLE ADMIN UPDATE ===
def handle_admin_update(update: Update):
    if update.callback_query:
        return handle_admin_callback(update.callback_query)

    if not update.message:
        return

    message: Message = update.message
    if message.video or message.animation or message.photo:
        media_action = wizard_state.pop_pending_media(message.from_user.id)
        if media_action:
            try:
                key, bid, page = media_action.split(":")

                bot = manager.create_or_get_child(bid)
                if not bot:
                    manager.admin_bot.send_message(
                        message.from_user.id, "❌ Bot not found."
                    )
                    return

                media_type = (
                    "video" if message.video else
                    "gif" if message.animation else
                    "image"
                )
                file_id = (
                    message.video.file_id if message.video else
                    message.animation.file_id if message.animation else
                    message.photo[-1].file_id
                )
                caption = message.caption or ""

                # --- 🔥 Step 1: Download file from admin bot ---
                file_info = manager.admin_bot.get_file(file_id)
                file_bytes = manager.admin_bot.download_file(
                    file_info.file_path)

                # --- 🔥 Step 2: Upload to target bot ---
                if media_type == "video":
                    sent = bot.send_video(
                        message.from_user.id,  # you can send it to admin user to upload
                        file_bytes,
                        caption=caption,
                    )
                    new_file_id = sent.video.file_id
                elif media_type == "gif":
                    sent = bot.send_animation(
                        message.from_user.id,
                        file_bytes,
                        caption=caption,
                    )
                    new_file_id = sent.animation.file_id
                else:
                    sent = bot.send_photo(
                        message.from_user.id,
                        file_bytes,
                        caption=caption,
                    )
                    new_file_id = sent.photo[-1].file_id

                # --- 🔥 Step 3: Save new file_id in DB ---
                db.set_bot_media(bid, key, media_type, new_file_id, caption)

                # --- Notify admin ---
                manager.admin_bot.send_message(
                    message.from_user.id,
                    f"✅ {key.capitalize()} media saved successfully!",
                    parse_mode="Markdown"
                )

                show_bot_manage_panel(call=None, bid=bid, page=int(page))
                return

            except Exception as e:
                notify_dev(manager.admin_bot, e,
                           "handle_admin_update: media upload", message)
                manager.admin_bot.send_message(
                    message.from_user.id, "❌ Failed to save media."
                )
                return
    
    if not message.text:
        return

    text = message.text.strip() if message.text else ""

    if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
        manager.admin_bot.reply_to(message, "❌ Not authorized.")
        return

    # Handle add bot wizard
    chat_id = wizard_state.pop_pending_add_token(message.from_user.id)
    if chat_id:
        return process_new_bot_token(message, text)

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Handle custom commands and verification text
    try:
        action = wizard_state.pop_pending_action(user_id)
        if action:
            if action.startswith("addcustom:"):
                _, bid, page = action.split(":")
                wizard_state.set_pending_action(
                    user_id, f"addcustomreply:{bid}:/{text}:{page}")
                manager.admin_bot.send_message(
                    chat_id, f"📩 Now send the *reply text* for command /{text}", parse_mode="Markdown")
                return

            elif action.startswith("addcustomreply:"):
                _, bid, command, page = action.split(":")
                db.set_bot_custom_command(bid, command, text)
                manager.admin_bot.send_message(
                    chat_id, f"✅ Custom command {command} saved.")
                return

            elif action.startswith("addverifytext:"):
                _, bid, page = action.split(":")
                db.set_bot_verification_text(bid, text)
                manager.admin_bot.send_message(
                    chat_id, "✅ Verification text saved.")
                return

                # === Handle media uploads (for custom start/close/end) ===

    except Exception as e:
        notify_dev(manager.admin_bot, e,
                   "handle_admin_callback: custom command", message)

    bid = wizard_state.pop_pending_rules(message.from_user.id)
    if bid:
        return process_new_rule(message, bid)

    # Handle /start
    if text.startswith("/start"):
        show_main_menu(chat_id)


# === CALLBACK HANDLER ===
def handle_admin_callback(call: CallbackQuery):
    try:
        if call.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            manager.admin_bot.answer_callback_query(
                call.id, "❌ Not authorized.")
            return

        cmd = call.data

        # Help
        if cmd == "cmd_help":
            help_text = (
                "🤖 *Admin Bot Help*\n\n"
                "• ➕ Add Bot — Register a new child bot\n"
                "• 📋 List Bots — Show all bots\n"
                "• ▶️ Enable Bot — Activate webhook\n"
                "• ⏸️ Disable Bot — Stop bot\n"
                "• 🗑️ Remove Bot — Delete permanently"
            )
            safe_edit(call.message.chat.id, call.message.message_id,
                      help_text, back_btn())
            return

        # Add bot
        if cmd == "cmd_addbot":
            wizard_state.set_pending_add_token(
                call.from_user.id, call.message.chat.id)
            safe_edit(call.message.chat.id, call.message.message_id,
                      "➕ Please send me the *bot token* now:", back_btn())
            return

        # List bots & pagination
        if cmd.startswith(("cmd_listbots:", "page:", "listpage:")):
            page = int(cmd.split(":")[1])
            show_bot_list(call.message.chat.id, call.message.message_id, page)
            return

        # Info, enable, disable, remove
        if cmd.startswith("info:"):
            _, bid, page = cmd.split(":")
            show_bot_info(call, bid, int(page))
            return

        if cmd.startswith("enable:"):
            _, bid, page = cmd.split(":")
            enable_bot(call, bid, int(page))
            return

        if cmd.startswith("disable:"):
            _, bid, page = cmd.split(":")
            disable_bot(call, bid, int(page))
            return

        if cmd.startswith("remove:"):
            _, bid, page = cmd.split(":")
            remove_bot(call, bid, int(page))
            return

        if cmd.startswith("setmedia:"):
            _, key, bid, page = cmd.split(":")
            wizard_state.set_pending_media(
                call.from_user.id, f"{key}:{bid}:{page}")
            safe_edit(
                call.message.chat.id,
                call.message.message_id,
                f"🎞 Send a *GIF / image / video* for `{key}` phase.\n"
                "You can include a caption too.",
                back_btn()
            )
            manager.admin_bot.answer_callback_query(
                call.id, "Waiting for media upload...")
            return

        # Commands / Rules / Custom / Verify Text
        if cmd.startswith("commands:"):
            _, bid, page = cmd.split(":")
            show_bot_commands(call, bid, int(page))
            return

        if cmd.startswith("togglecmd:"):
            _, bid, command, page = cmd.split(":")
            enabled = set(db.get_bot_commands(bid))
            enabled.remove(
                command) if command in enabled else enabled.add(command)
            db.set_bot_commands(bid, list(enabled))
            show_bot_commands(call, bid, int(page))
            return

        if cmd.startswith("rules:"):
            _, bid, page = cmd.split(":")
            show_bot_rules(call, bid, int(page))
            return

        if cmd.startswith("media:"):
            _, bid, page = cmd.split(":")
            show_bot_media_settings(call, bid, int(page))
            return

        if cmd.startswith("newrules:"):
            _, bid, page = cmd.split(":")
            set_bot_rules(call, bid, int(page))
            return

        if cmd.startswith("verifytext:"):
            _, bid, page = cmd.split(":")
            show_bot_verification_text(call, bid, int(page))
            return

        if cmd.startswith("newverifytext:"):
            _, bid, page = cmd.split(":")
            set_bot_verification_text(call, bid, int(page))
            return

        if cmd.startswith("customcmds:"):
            _, bid, page = cmd.split(":")
            show_custom_commands(call, bid, int(page))
            return

        if cmd.startswith("newcustom:"):
            _, bid, page = cmd.split(":")
            ask_new_custom_command(call, bid, int(page))
            return

        if cmd.startswith("delcustom:"):
            _, bid, command, page = cmd.split(":")
            db.delete_custom_command(bid, command)
            show_custom_commands(call, bid, int(page))
            return
        if cmd.startswith("manage:"):
            _, bid, page = cmd.split(":")
            show_bot_manage_panel(call, bid, int(page))
            return

        if cmd == "back_main":
            show_main_menu(call.message.chat.id, call.message.message_id)
            return

        manager.admin_bot.answer_callback_query(call.id, "❓ Unknown action.")
    except Exception as e:
        notify_dev(manager.admin_bot, e, "handle_admin_callback", call.message)


# === HELPERS ===
def back_btn():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    return kb


def escape_md(text: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


# === BOT LIST (visual improvement) ===
def show_bot_list(chat_id, message_id, page=0):
    bots = db.list_bots()
    total = len(bots)
    if not bots:
        safe_edit(chat_id, message_id, "ℹ️ No child bots yet.", back_btn())
        return

    start, end = page * BOTS_PER_PAGE, (page + 1) * BOTS_PER_PAGE
    bots_page = bots[start:end]
    total_pages = (total - 1) // BOTS_PER_PAGE + 1

    text = f"📋 *Child Bots Panel* (Page {page+1}/{total_pages})\n\n"
    kb = InlineKeyboardMarkup(row_width=1)

    for bot in bots_page:
        bid = str(bot["_id"])
        name = bot.get("name") or "Unnamed"
        status = bot.get("status", "unknown")
        icon = "🟢" if status == "enabled" else "🔴"
        text += f"{icon} [@{escape_md(name)}](https://t.me/{name}) — *{status}*\n"
        kb.add(InlineKeyboardButton(
            f"🧩 Manage {name}", callback_data=f"manage:{bid}:{page}"))

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "⬅️ Prev", callback_data=f"page:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(
            "➡️ Next", callback_data=f"page:{page+1}"))
    if nav:
        kb.row(*nav)

    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    safe_edit(chat_id, message_id, text, kb)


def show_bot_manage_panel(call: CallbackQuery, bid: str, page: int):
    bot = db.get_bot_by_id(bid)
    if not bot:
        manager.admin_bot.answer_callback_query(call.id, "❌ Bot not found.")
        return

    name = bot.get("name") or "Unnamed"
    status = bot.get("status", "unknown")
    icon = "🟢" if status == "enabled" else "🔴"

    text = (
        f"🧩 *Manage Bot: @{escape_md(name)}*\n\n"
        f"📡 Status: {icon} *{status}*\n"
    )

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            "⚙️ Commands", callback_data=f"commands:{bid}:{page}"),
        InlineKeyboardButton("📜 Rules", callback_data=f"rules:{bid}:{page}")
    )
    kb.add(
        InlineKeyboardButton(
            "📝 Custom Cmds", callback_data=f"customcmds:{bid}:{page}"),
        InlineKeyboardButton(
            "🛡 Verify Text", callback_data=f"verifytext:{bid}:{page}")
    )
    kb.add(
        InlineKeyboardButton("🎞 Media", callback_data=f"media:{bid}:{page}")
    )

    kb.row(
        InlineKeyboardButton(
            "⏸ Disable" if status == "enabled" else "▶️ Enable",
            callback_data=f"{'disable' if status=='enabled' else 'enable'}:{bid}:{page}"
        ),
        InlineKeyboardButton("🗑 Remove", callback_data=f"remove:{bid}:{page}")
    )
    kb.add(InlineKeyboardButton("⬅️ Back to List",
           callback_data=f"listpage:{page}"))

    safe_edit(call.message.chat.id, call.message.message_id, text, kb)


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
    kb.add(InlineKeyboardButton("⬅️ Back to list",
           callback_data=f"listpage:{page}"))

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
        # Save only main commands in DB (aliases will still work)
        db.set_bot_commands(bot_id, ALL_MAIN_COMMANDS)
        manager.admin_bot.send_message(
            message.chat.id,
            f"✅ Bot added and webhook set!\n🆔 `{bot_id}`",
            parse_mode="Markdown",
        )
    else:
        manager.admin_bot.send_message(
            message.chat.id, "❌ Failed to set webhook."
        )

    show_main_menu(message.chat.id)

# === ENABLE BOT ===


def enable_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_status(bid, "enabled")
        url = f"{settings.BASE_URL.rstrip('/')}/webhook/{bid}"
        manager.set_child_webhook(bid, url)
        manager.admin_bot.answer_callback_query(
            call.id, f"▶️ Bot {bid} enabled.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === DISABLE BOT ===
def disable_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_status(bid, "disabled")
        manager.delete_child_webhook(bid)
        manager.admin_bot.answer_callback_query(
            call.id, f"⏸️ Bot {bid} disabled.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === REMOVE BOT ===
def remove_bot(call: CallbackQuery, bid: str, page: int):
    try:
        db.set_bot_webhook(bid, None)
        db.bots_collection().delete_one({"_id": ObjectId(bid)})
        manager.child_bots.pop(bid, None)
        manager.admin_bot.answer_callback_query(
            call.id, f"🗑️ Bot {bid} removed.")
    except Exception:
        manager.admin_bot.answer_callback_query(call.id, "❌ Failed.")
    show_bot_list(call.message.chat.id, call.message.message_id, page)


# === HELPERS ===
def back_btn():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    return kb


def show_bot_commands(call: CallbackQuery, bid: str, page: int):
    enabled = set(get_bot_commands(bid))

    kb = InlineKeyboardMarkup(row_width=2)
    buttons = []

    for main_cmd in ALL_MAIN_COMMANDS:
        status = "✅" if main_cmd in enabled else "❌"
        buttons.append(
            InlineKeyboardButton(
                f"{status} {main_cmd}",
                callback_data=f"togglecmd:{bid}:{main_cmd}:{page}"
            )
        )

    # Add all command buttons (respects row_width)
    kb.add(*buttons)

    # Back button
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data=f"listpage:{page}"))

    text = f"⚙️ *Command Settings for Bot {bid}*"
    safe_edit(call.message.chat.id, call.message.message_id, text, kb)


def show_bot_rules(call: CallbackQuery, bid: str, page: int):
    rules = db.get_bot_doc(bid).get("rules")
    if not rules:
        rules = "📛 No rules set."

    text = f"📛 *Rules for Bot {bid}*\n\n{rules}"
    manager.admin_bot.send_message(call.message.chat.id, text)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ New Rules",
           callback_data=f"newrules:{bid}:{page}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data=f"listpage:{page}"))

    edit_text = "✅ Edit Rules"
    safe_edit(call.message.chat.id, call.message.message_id, edit_text, kb)


def set_bot_rules(call: CallbackQuery, bid: str, page: int):

    chat_id = call.message.chat.id
    # Ask for rules
    wizard_state.set_pending_rules(call.from_user.id, bid)
    manager.admin_bot.send_message(
        chat_id, "📛 Send the rules to *set*.", parse_mode="Markdown")
    manager.admin_bot.answer_callback_query(call.id, "Waiting for rules...")


def process_new_rule(message: Message, bid: str):
    chat_id = message.chat.id
    rules = message.text.strip()
    db.set_bot_rules(bid, rules)
    manager.admin_bot.send_message(
        chat_id, "✅ Rules set.", parse_mode="Markdown")


def show_custom_commands(call, bid: str, page: int):
    cmds = db.list_custom_commands(bid)
    if not cmds:
        text = f"📝 No custom commands for Bot {bid}."
    else:
        text = f"📝 *Custom Commands for Bot {bid}:*\n\n"
        for c, reply in cmds.items():
            text += f"{c} → {reply[:30]}...\n"

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("➕ Add Command",
           callback_data=f"newcustom:{bid}:{page}"))
    for c in cmds.keys():
        kb.add(InlineKeyboardButton(
            f"🗑 Remove {c}", callback_data=f"delcustom:{bid}:{c}:{page}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data=f"listpage:{page}"))

    safe_edit(call.message.chat.id, call.message.message_id, text, kb)


def ask_new_custom_command(call, bid: str, page: int):
    chat_id = call.message.chat.id
    wizard_state.set_pending_action(
        call.from_user.id, f"addcustom:{bid}:{page}")
    manager.admin_bot.send_message(
        chat_id, "✏️ Send the *command name* (e.g., `u`).", parse_mode="Markdown")
    manager.admin_bot.answer_callback_query(call.id, "Waiting for command...")


def show_bot_verification_text(call: CallbackQuery, bid: str, page: int):
    """
    Display current custom verification text for a bot, if any.
    """
    text_data = db.get_bot_verification_text(bid)
    if not text_data:
        display_text = "🛡 No custom verification text set."
    else:
        display_text = f"🛡 *Current Verification Text:*\n\n{text_data}"

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📝 Set New Text",
           callback_data=f"newverifytext:{bid}:{page}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data=f"listpage:{page}"))

    safe_edit(call.message.chat.id, call.message.message_id, display_text, kb)


def set_bot_verification_text(call: CallbackQuery, bid: str, page: int):
    """
    Start wizard to capture new verification text from admin.
    """
    chat_id = call.message.chat.id
    wizard_state.set_pending_action(
        call.from_user.id, f"addverifytext:{bid}:{page}")
    manager.admin_bot.send_message(
        chat_id, "📝 Send the *custom verification text* now.", parse_mode="Markdown")
    manager.admin_bot.answer_callback_query(
        call.id, "Waiting for verification text...")


def show_bot_media_settings(call: CallbackQuery, bid: str, page: int):
    bot = db.get_bot_by_id(bid)
    media = bot.get("custom_media", {})

    def display(key):
        entry = media.get(key)
        if not entry:
            return f"❌ No {key} media set"
        return f"✅ {entry['type']} ({entry.get('caption', '')})"

    text = (
        f"🎞 *Media Settings for Bot {bid}*\n\n"
        f"▶️ Start: {display('start')}\n"
        f"⏸ Close: {display('close')}\n"
        f"🏁 End: {display('end')}\n\n"
        "You can upload a new GIF/image/video to replace each one."
    )

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(
            "Set Start", callback_data=f"setmedia:start:{bid}:{page}"),
        InlineKeyboardButton(
            "Set Close", callback_data=f"setmedia:close:{bid}:{page}")
    )
    kb.add(
        InlineKeyboardButton(
            "Set End", callback_data=f"setmedia:end:{bid}:{page}")
    )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data=f"listpage:{page}"))
    safe_edit(call.message.chat.id, call.message.message_id, text, kb)
