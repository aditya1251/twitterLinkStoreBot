from utils.db import init_db

# In-memory cache, but keyed by bot_id
ALLOWED_GROUPS_CACHE = {}

def get_allowed_groups(bot_id: str):
    global ALLOWED_GROUPS_CACHE
    if bot_id not in ALLOWED_GROUPS_CACHE:
        db = init_db()
        doc = db["settings"].find_one({"_id": f"allowed_groups:{bot_id}"}) or {"groups": []}
        ALLOWED_GROUPS_CACHE[bot_id] = doc["groups"]
    return ALLOWED_GROUPS_CACHE[bot_id]

def save_allowed_groups(bot_id: str, groups):
    global ALLOWED_GROUPS_CACHE
    db = init_db()
    db["settings"].update_one(
        {"_id": f"allowed_groups:{bot_id}"},
        {"$set": {"groups": groups}},
        upsert=True
    )
    ALLOWED_GROUPS_CACHE[bot_id] = groups

def add_group(bot_id: str, group_id):
    groups = get_allowed_groups(bot_id)
    if group_id not in groups:
        groups.append(group_id)
        save_allowed_groups(bot_id, groups)

def remove_group(bot_id: str, group_id):
    groups = get_allowed_groups(bot_id)
    if group_id in groups:
        groups.remove(group_id)
        save_allowed_groups(bot_id, groups)

def save_group_metadata(db, bot_id: str, chat):
    if chat.type in ["group", "supergroup"]:
        db["groups"].update_one(
            {"bot_id": bot_id, "group_id": chat.id},
            {"$set": {
                "group_id": chat.id,
                "title": chat.title,
                "username": chat.username
            }},
            upsert=True
        )
