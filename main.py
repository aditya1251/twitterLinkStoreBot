import traceback
from flask import Flask, request, abort
from telebot import types
from config import settings
from utils.telegram import manager, manual_dispatch
from utils import db
from utils.db import init_db
from handlers.admin_multi import handle_admin_update

app = Flask(__name__)

# === Initialize Mongo ===
init_db()
from utils.db import ensure_indexes
ensure_indexes()

# === Webhook for Admin Bot ===
@app.route("/webhook/admin", methods=["POST"])
def webhook_admin():
    try:
        update = types.Update.de_json(request.data.decode("utf-8"))
        if not update:
            return "OK", 200

        # 🚀 Use manual handler instead of process_new_updates
        handle_admin_update(update)
    except Exception:
        traceback.print_exc()
        abort(400)
    return "OK", 200




# === Webhook for Child Bots ===
@app.route("/webhook/<string:bot_id>", methods=["POST"])
def webhook_child(bot_id: str):
    
    bot = manager.create_or_get_child(bot_id)
    if not bot:
        abort(404)
    try:
        update = types.Update.de_json(request.data.decode("utf-8"))
        # Child bot already uses its own bot_id
        manual_dispatch(bot, bot_id, update, db._db)
    except Exception:
        traceback.print_exc()
        abort(400)
    return "OK", 200


# === Health Check ===
@app.get("/")
def health():
    return {"ok": True}, 200


# === List All Bots (without tokens) ===
@app.get("/bots")
def list_bots():
    docs = db.list_bots()
    for d in docs:
        d["_id"] = str(d["_id"])
        d.pop("token", None)  # don’t leak tokens in API
    return {"bots": docs}, 200
    

