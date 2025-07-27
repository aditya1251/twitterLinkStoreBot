from pymongo import MongoClient

def init_db(uri):
    client = MongoClient(uri)
    db = client.get_database()  # Uses DB from the URI
    return db
