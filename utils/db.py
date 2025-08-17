# keep your old init_db
from pymongo import MongoClient, ReturnDocument
import os
from bson import ObjectId
from config import settings
from telebot import TeleBot
_client = None
_db = None

COMMAND_GROUPS = {
    "/sr": ["/sr"],
    "/srlist": ["/srlist"],
    "/link": ["/link"],
    "/count": ["/count"],
    "/multi": ["/multi"],
    "/unsafe": ["/unsafe"],
    "/verify": ["/verify", "/track", "/check"],   # aliases
    "/close": ["/close", "/closes", "/stop"],     # aliases
    "/end": ["/end"],
    "/rule": ["/rule"],
    "/help": ["/help"],
    "/managegroups": ["/managegroups"],
    "/list": ["/list"],
    "/clear": ["/clear", "/clean"],               # aliases
    "/muteunsafe": ["/muteunsafe", "/muteall"],   # aliases
    "/refresh_admins": ["/refresh_admins"],
    "/add_to_ad": ["/add_to_ad"],
}

ALL_MAIN_COMMANDS = list(COMMAND_GROUPS.keys())

def init_db():
    global _client, _db
    if not _client:
        uri = os.getenv("MONGODB_URI") or settings.MONGO_URI
        if not uri:
            raise Exception("MONGODB_URI is missing.")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _db = _client[settings.MONGO_DB]
    return _db


# === New multi-bot stuff ===
def create_bot_doc(token: str, name: str = "", description: str = "", status: str = "enabled") -> str:
    db = init_db()

    # use telebot to get the bot name 
    bot = TeleBot(token)
    name = bot.get_me().username
    
    res = db["bots"].insert_one({
        "token": token.strip(),
        "name": name.strip(),
        "description": description.strip(),
        "status": status,
        "webhook_url": None,
    })
    return str(res.inserted_id)

def get_bot_by_token(token: str):
    db = init_db()
    return db["bots"].find_one({"token": token.strip()})

def get_bot_by_id(bot_id: str):
    db = init_db()
    return db["bots"].find_one({"_id": ObjectId(bot_id)})

def bots_collection():
    db = init_db()
    return db["bots"]

def set_bot_webhook(bot_id: str, url: str | None):
    """
    Update a bot's webhook URL in the database.
    """
    db = init_db()
    return db["bots"].find_one_and_update(
        {"_id": ObjectId(bot_id)},
        {"$set": {"webhook_url": url}},
        return_document=ReturnDocument.AFTER
    )


def get_bot_doc(bot_id: str):
    db = init_db()
    try:
        return db["bots"].find_one({"_id": ObjectId(bot_id)})
    except:
        return None

def list_bots():
    db = init_db()
    return list(db["bots"].find().sort([("_id", 1)]))

def set_bot_status(bot_id: str, status: str):
    db = init_db()
    return db["bots"].find_one_and_update(
        {"_id": ObjectId(bot_id)},
        {"$set": {"status": status}},
        return_document=ReturnDocument.AFTER
    )

def get_bot_commands(bot_id: str):
    db = init_db()
    doc = db["settings"].find_one({"_id": f"commands:{bot_id}"})
    return doc.get("enabled", []) if doc else []


def set_bot_commands(bot_id: str, commands: list[str]):
    db = init_db()
    db["settings"].update_one(
        {"_id": f"commands:{bot_id}"},
        {"$set": {"enabled": commands}},
        upsert=True
    )
    return commands


def is_command_enabled(bot_id: str, command: str) -> bool:
    """Check if a command or any of its aliases is enabled for a bot."""
    enabled = set(get_bot_commands(bot_id))

    for main_cmd, aliases in COMMAND_GROUPS.items():
        if command in aliases:       # match alias
            return main_cmd in enabled

    return False
