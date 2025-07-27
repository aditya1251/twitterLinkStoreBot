import os
from flask import Flask, request
import telebot
import requests
from dotenv import load_dotenv
from handlers.commands import handle_command
from utils.db import init_db

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TOKEN or not WEBHOOK_URL:
    raise EnvironmentError("Missing required environment variables.")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
db = init_db()  
webhook_set = False

# Manual dispatcher
def handle_update(update):
    if update.message and update.message.text:
        handle_command(bot, update.message, db)

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
