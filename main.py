import traceback
from flask import Flask, request, abort
from telebot import types
from config import settings
from utils.telegram import manager, manual_dispatch
from utils import db
from utils.db import init_db
from handlers import admin_multi

app = Flask(__name__)

# init mongo
init_db()
# register admin commands
admin_multi.register_admin_handlers(manager.admin_bot)

@app.route("/webhook/admin", methods=["POST"])
def webhook_admin():
    if settings.INGRESS_SECRET and request.headers.get("X-Ingress-Secret") != settings.INGRESS_SECRET:
        abort(401)
    try:
        update = types.Update.de_json(request.data.decode("utf-8"))
        manual_dispatch(manager.admin_bot, update, db._db)
    except Exception:
        traceback.print_exc()
        abort(400)
    return "OK", 200

@app.route("/webhook/<string:bot_id>", methods=["POST"])
def webhook_child(bot_id: str):
    if settings.INGRESS_SECRET and request.headers.get("X-Ingress-Secret") != settings.INGRESS_SECRET:
        abort(401)
    bot = manager.create_or_get_child(bot_id)
    if not bot:
        abort(404)
    try:
        update = types.Update.de_json(request.data.decode("utf-8"))
        manual_dispatch(bot, update, db._db)
    except Exception:
        traceback.print_exc()
        abort(400)
    return "OK", 200

@app.get("/health")
def health():
    return {"ok": True}, 200

@app.get("/bots")
def list_bots():
    docs = db.list_bots()
    for d in docs:
        d["_id"] = str(d["_id"])
        d.pop("token", None)
    return {"bots": docs}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
