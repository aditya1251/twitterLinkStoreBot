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
telebot.apihelper.ENABLE_MIDDLEWARE = True
app = Flask(__name__)
webhook_set = False

# /start command
@bot.message_handler(commands=['start'])
def handle_start(message):
    print("✅ /start command received from", message.chat.id)
    bot.send_message(message.chat.id, "👋 Hello from webhook bot!")


# Optional: /help
@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(message.chat.id, "/start - Welcome\n/help - Info")

# Telegram webhook endpoint
@app.route("/webhook", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        print(bot.get_me())
        print(f"Received update: {update}")
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Invalid content type', 403
    
@bot.message_handler(func=lambda message: True)
def catch_all(message):
    print("⚠️ No specific handler matched this message:", message.text)


# Root route: sets webhook if not yet set
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

