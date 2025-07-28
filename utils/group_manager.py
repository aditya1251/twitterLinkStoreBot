from utils.db import init_db

ALLOWED_GROUPS_CACHE = None

def get_allowed_groups():
    global ALLOWED_GROUPS_CACHE
    if ALLOWED_GROUPS_CACHE is None:
        db = init_db()
        doc = db["settings"].find_one({"_id": "allowed_groups"}) or {"groups": []}
        ALLOWED_GROUPS_CACHE = doc["groups"]
    return ALLOWED_GROUPS_CACHE

def save_allowed_groups(groups):
    global ALLOWED_GROUPS_CACHE
    db = init_db()
    db["settings"].update_one(
        {"_id": "allowed_groups"},
        {"$set": {"groups": groups}},
        upsert=True
    )
    ALLOWED_GROUPS_CACHE = groups

def add_group(group_id):
    groups = get_allowed_groups()
    if group_id not in groups:
        groups.append(group_id)
        save_allowed_groups(groups)

def remove_group(group_id):
    groups = get_allowed_groups()
    if group_id in groups:
        groups.remove(group_id)
        save_allowed_groups(groups)

def save_group_metadata(db, chat):
    if chat.type in ["group", "supergroup"]:
        db["groups"].update_one(
            {"group_id": chat.id},
            {"$set": {
                "group_id": chat.id,
                "title": chat.title,
                "username": chat.username
            }},
            upsert=True
        )
