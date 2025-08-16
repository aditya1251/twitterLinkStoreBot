# keep your old init_db
from pymongo import MongoClient, ReturnDocument
import os
from bson import ObjectId
from config import settings

_client = None
_db = None

def init_db():
    global _client, _db
    if not _client:
        uri = os.getenv("MONGODB_URI") or settings.MONGO_URI
        if not uri:
            raise Exception("MONGODB_URI is missing.")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _db = _client.get_database()
    return _db

# === New multi-bot stuff ===
def create_bot_doc(token: str, name: str = "", description: str = "", status: str = "enabled") -> str:
    db = init_db()
    res = db["bots"].insert_one({
        "token": token.strip(),
        "name": name.strip(),
        "description": description.strip(),
        "status": status,
        "webhook_url": None,
    })
    return str(res.inserted_id)

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
