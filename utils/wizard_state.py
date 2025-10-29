# utils/wizard_state.py
from utils.redis_client import get_redis

r = get_redis()

# KEYS
PENDING_ADD_TOKEN = "wizard:pending_add_token"   # hash {admin_id: chat_id}
PENDING_RULES     = "wizard:pending_rules"       # hash {admin_id: bot_id}
PENDING_ACTION    = "wizard:pending_action"      # hash {user_id: action}
PENDING_MEDIA = "wizard:pending_media"  # hash {admin_id: "key:bot_id:page"}

# === Add Token ===
def set_pending_add_token(admin_id: int, chat_id: int):
    r.hset(PENDING_ADD_TOKEN, admin_id, chat_id)

def pop_pending_add_token(admin_id: int):
    chat_id = r.hget(PENDING_ADD_TOKEN, admin_id)
    if chat_id:
        r.hdel(PENDING_ADD_TOKEN, admin_id)
    return chat_id

# === Rules ===
def set_pending_rules(admin_id: int, bot_id: str):
    r.hset(PENDING_RULES, admin_id, bot_id)

def pop_pending_rules(admin_id: int):
    bot_id = r.hget(PENDING_RULES, admin_id)
    if bot_id:
        r.hdel(PENDING_RULES, admin_id)
    return bot_id

# === Action ===
def set_pending_action(user_id: int, action: str):
    r.hset(PENDING_ACTION, user_id, action)

def pop_pending_action(user_id: int):
    action = r.hget(PENDING_ACTION, user_id)
    if action:
        r.hdel(PENDING_ACTION, user_id)
    return action

# === Media ===
def set_pending_media(admin_id: int, action: str):
    r.hset(PENDING_MEDIA, admin_id, action)

def pop_pending_media(admin_id: int):
    action = r.hget(PENDING_MEDIA, admin_id)
    if action:
        r.hdel(PENDING_MEDIA, admin_id)
    return action
