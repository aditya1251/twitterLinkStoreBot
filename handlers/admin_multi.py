from telebot.types import Message
from utils import db
from config import settings
from utils.telegram import manager
from bson.objectid import ObjectId

def register_admin_handlers(bot):
    """
    Register management commands for the Admin bot only.
    """

    @bot.message_handler(commands=["addbot"])
    def add_bot_cmd(message: Message):
        if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            bot.reply_to(message, "❌ Not authorized.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Usage: /addbot <BOT_TOKEN>")
            return

        token = args[1].strip()
        existing = db.get_bot_by_token(token)
        if existing:
            bot.reply_to(message, f"⚠️ Bot already exists with id `{existing['_id']}`", parse_mode="Markdown")
            return

        bot_id = db.create_bot_doc(token)
        url = f"{settings.BASE_URL.rstrip('/')}/webhook/{bot_id}"
        ok = manager.set_child_webhook(bot_id, url)
        if ok:
            bot.reply_to(message, f"✅ Bot added and webhook set!\nID: `{bot_id}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Failed to set webhook.")

    @bot.message_handler(commands=["listbots"])
    def list_bots_cmd(message: Message):
        if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            bot.reply_to(message, "❌ Not authorized.")
            return

        docs = db.list_bots()
        if not docs:
            bot.reply_to(message, "ℹ️ No child bots yet.")
            return

        lines = []
        for d in docs:
            status = d.get("status", "unknown")
            lines.append(f"• `{d['_id']}` — {d.get('name') or 'Unnamed'} ({status})")
        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

    @bot.message_handler(commands=["disablebot"])
    def disable_bot_cmd(message: Message):
        if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            bot.reply_to(message, "❌ Not authorized.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Usage: /disablebot <BOT_ID>")
            return

        try:
            bid = str(ObjectId(args[1].strip()))
        except Exception:
            bot.reply_to(message, "❌ Invalid bot id.")
            return

        db.set_bot_status(bid, "disabled")
        manager.delete_child_webhook(bid)
        bot.reply_to(message, f"⏸️ Bot `{bid}` disabled.", parse_mode="Markdown")

    @bot.message_handler(commands=["enablebot"])
    def enable_bot_cmd(message: Message):
        if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            bot.reply_to(message, "❌ Not authorized.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Usage: /enablebot <BOT_ID>")
            return

        try:
            bid = str(ObjectId(args[1].strip()))
        except Exception:
            bot.reply_to(message, "❌ Invalid bot id.")
            return

        db.set_bot_status(bid, "enabled")
        url = f"{settings.BASE_URL.rstrip('/')}/webhook/{bid}"
        ok = manager.set_child_webhook(bid, url)
        if ok:
            bot.reply_to(message, f"▶️ Bot `{bid}` enabled and webhook set.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"⚠️ Bot `{bid}` enabled but webhook failed.", parse_mode="Markdown")

    @bot.message_handler(commands=["removebot"])
    def remove_bot_cmd(message: Message):
        if message.from_user.id != settings.ADMIN_TELEGRAM_USER_ID:
            bot.reply_to(message, "❌ Not authorized.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Usage: /removebot <BOT_ID>")
            return

        try:
            bid = str(ObjectId(args[1].strip()))
        except Exception:
            bot.reply_to(message, "❌ Invalid bot id.")
            return

        # Delete DB doc and webhook
        db.set_bot_webhook(bid, None)
        db.bots.delete_one({"_id": ObjectId(bid)})
        manager.child_bots.pop(bid, None)
        bot.reply_to(message, f"🗑️ Bot `{bid}` removed.", parse_mode="Markdown")
