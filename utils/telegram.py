# utils/admin_cache.py

from threading import Lock
from datetime import datetime, timedelta
from telebot import apihelper
import telebot.types

_admins_cache = {}
_lock = Lock()

def get_cached_admins(chat_id):
    with _lock:
        return _admins_cache.get(chat_id)

def set_cached_admins(chat_id, admin_ids):
    with _lock:
        _admins_cache[chat_id] = admin_ids

def clear_cached_admins(chat_id):
    with _lock:
        _admins_cache.pop(chat_id, None)

def is_user_admin_cached(chat_id, user_id):
    with _lock:
        admins = _admins_cache.get(chat_id)
        if admins is None:
            return None  # means not cached yet
        return user_id in admins



def is_user_admin(bot, chat_id, user_id):
    cached_result = is_user_admin_cached(chat_id, user_id)
    if cached_result is not None:
        return cached_result

    try:
        admins = bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        set_cached_admins(chat_id, admin_ids)
        return user_id in admin_ids
    except Exception as e:
        print(f"[AdminCheckError] {e}")
        return False
    

def mute_user(bot, chat_id, user_id, duration_days=3):
    until_date = datetime.utcnow() + timedelta(days=duration_days)
    permissions = telebot.types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    try:
        bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date
        )
        return True
    except apihelper.ApiTelegramException as e:
        print(f"Failed to mute {user_id} in {chat_id}: {e}")
        return False

