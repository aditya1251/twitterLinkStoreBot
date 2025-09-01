# utils/group_manager.py
import json
import redis
from typing import List
from utils.db import init_db
from config import settings
from utils.redis_client import get_redis

# keep a tiny in-process fallback cache (optional)
ALLOWED_GROUPS_CACHE: dict = {}

_r = get_redis()

# Redis hash key where we store allowed groups for all bots
_ALLOWED_GROUPS_HASH = "allowed_groups"


def _redis_get_groups(bot_id: str):
    """Return list from redis or None if key missing or error."""
    try:
        raw = _r.hget(_ALLOWED_GROUPS_HASH, bot_id)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        # don't crash on redis error; fall back to DB
        print(f"[group_manager.redis_get] Redis error: {e}")
        return None


def _redis_set_groups(bot_id: str, groups: List[int]):
    """Persist list into redis (stringified)."""
    try:
        _r.hset(_ALLOWED_GROUPS_HASH, bot_id, json.dumps(list(groups)))
    except Exception as e:
        print(f"[group_manager.redis_set] Redis error: {e}")


def get_allowed_groups(bot_id: str) -> List[int]:
    """
    Return allowed groups for a bot. Uses Redis as the shared cache.
    Falls back to MongoDB if Redis misses or errors, and then populates Redis.
    """
    global ALLOWED_GROUPS_CACHE

    # 1) Try in-process cache (fast path)
    if bot_id in ALLOWED_GROUPS_CACHE:
        return ALLOWED_GROUPS_CACHE[bot_id]

    # 2) Try Redis
    groups = _redis_get_groups(bot_id)
    if groups is not None:
        ALLOWED_GROUPS_CACHE[bot_id] = groups
        return groups

    # 3) Fallback to DB
    try:
        db = init_db()
        doc = db["settings"].find_one({"_id": f"allowed_groups:{bot_id}"}) or {"groups": []}
        groups = doc.get("groups", [])
    except Exception as e:
        print(f"[group_manager.db_read] DB error while fetching allowed_groups for {bot_id}: {e}")
        groups = []

    # write back to redis for future fast reads (best-effort)
    try:
        _redis_set_groups(bot_id, groups)
    except Exception:
        pass

    ALLOWED_GROUPS_CACHE[bot_id] = groups
    return groups


def save_allowed_groups(bot_id: str, groups: List[int]):
    """
    Persist allowed groups list for a bot to MongoDB and Redis, and update local cache.
    """
    global ALLOWED_GROUPS_CACHE
    try:
        db = init_db()
        db["settings"].update_one(
            {"_id": f"allowed_groups:{bot_id}"},
            {"$set": {"groups": list(groups)}},
            upsert=True
        )
    except Exception as e:
        print(f"[group_manager.db_write] DB error while saving allowed_groups for {bot_id}: {e}")
        # continue to attempt Redis update even if DB fails

    # update Redis (best-effort)
    _redis_set_groups(bot_id, groups)

    # update local cache
    ALLOWED_GROUPS_CACHE[bot_id] = list(groups)


def add_group(bot_id: str, group_id: int):
    groups = get_allowed_groups(bot_id)
    if group_id not in groups:
        groups.append(group_id)
        save_allowed_groups(bot_id, groups)


def remove_group(bot_id: str, group_id: int):
    groups = get_allowed_groups(bot_id)
    if group_id in groups:
        groups.remove(group_id)
        save_allowed_groups(bot_id, groups)


def save_group_metadata(db, bot_id: str, chat):
    """
    Store/update group metadata for a given bot in MongoDB.
    (unchanged from original)
    """
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
