from pymongo import MongoClient
import os

_client = None
_db = None

def init_db():
    global _client, _db
    if not _client:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise Exception("MONGODB_URI is missing.")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _db = _client.get_database()
    return _db
