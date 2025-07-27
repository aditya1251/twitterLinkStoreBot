import os
from flask import Flask, request
import telebot
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Example: https://your-app.onrender.com/webhook

if not TOKEN or not WEBHOOK_URL:
    raise EnvironmentError("Missing TELEGRAM_BOT_TOKEN or WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
webhook_set = False

def handle_update(update):
    if update.message:
        text = update.message.text
        chat_id = update.message.chat.id
        if text == '/start':
            print(f"🔔 Received /start from {chat_id}")
            bot.send_message(chat_id, "👋 Hello! I'm your bot running on Render with manual handlers.")
        elif text == '/help':
            bot.send_message(chat_id, "ℹ️ Available commands:\n/start - Welcome message\n/help - Command list")
        else:
            bot.send_message(chat_id, "❓ Unknown command. Try /start or /help.")

# Webhook endpoint
@app.route("/webhook", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        print(f"📩 Received update: {update}")
        handle_update(update)
        return '', 200
    return 'Invalid content type', 403

# Root route: auto-sets webhook
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
