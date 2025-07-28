import os
from flask import Flask, request
import telebot
import requests
from dotenv import load_dotenv
from handlers.commands import handle_command, handle_group_command
from handlers.text import handle_text, handle_group_text
from utils.db import init_db
from utils.group_manager import get_allowed_groups , save_group_metadata
from handlers.callbacks import handle_callback

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(',')))

if not TOKEN or not WEBHOOK_URL:
    raise EnvironmentError("Missing required environment variables.")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
db = init_db()  
webhook_set = False

# Manual dispatcher
def handle_update(update):

    if update.callback_query:
        handle_callback(bot, update.callback_query)
        

    if not update.message:
        return

    message = update.message
    chat = message.chat
    if not message.text:
        return
    # Allow all private chats (admin management)
    if chat.type == "private":
        if message.text and message.text.startswith("/"):
            handle_command(bot, message, db)
        else:
            handle_text(bot, message, db)
        return

    # Allow only allowed groups
    if chat.type in ["group", "supergroup"]:
        save_group_metadata(db, message.chat)
        if not chat.id in get_allowed_groups():
            return  # Ignore message from unapproved group

        if message.text and message.text.startswith("/"):
            handle_group_command(bot, message, db)
        else:
            handle_group_text(bot, message, db)


@app.route("/webhook", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        handle_update(update)
        return '', 200
    return 'Invalid content type', 403

@app.route("/", methods=['GET'])
def index():
    global webhook_set
    if not webhook_set:
        res = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={'url': WEBHOOK_URL}
        )
        if res.status_code == 200 and res.json().get("ok"):
            webhook_set = True
            return "✅ Webhook set successfully"
        return f"❌ Failed to set webhook: {res.text}", 500
    return "✅ Webhook already set"