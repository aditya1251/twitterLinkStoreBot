from threading import Lock
from datetime import datetime, timedelta
from telebot import apihelper
import telebot.types
import re
from handlers.admin import notify_dev  # ✅ import notify_dev

_admins_cache = {}
_lock = Lock()

def normalize_gid(chat_id):
    return str(chat_id)

def get_cached_admins(chat_id):
    gid = normalize_gid(chat_id)
    with _lock:
        return _admins_cache.get(gid)

def set_cached_admins(chat_id, admin_ids):
    gid = normalize_gid(chat_id)
    with _lock:
        _admins_cache[gid] = admin_ids

def clear_cached_admins(chat_id):
    gid = normalize_gid(chat_id)
    with _lock:
        _admins_cache.pop(gid, None)

def is_user_admin_cached(chat_id, user_id):
    gid = normalize_gid(chat_id)
    with _lock:
        admins = _admins_cache.get(gid)
        if admins is None:
            return None  # Not cached yet
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
        # ✅ Notify dev
        context = "is_user_admin"
        notify_dev(bot, e, context, message=None)
        return False

def mute_user(bot, chat_id, user_id, duration=timedelta(days=3)):
    until_date = datetime.utcnow() + duration
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
        # ✅ Notify dev
        context = "mute_user"
        notify_dev(bot, e, context)
        return False
    except Exception as e:
        notify_dev(bot, e, "mute_user_general")
        return False

def parse_duration(duration_str):
    """
    Parses duration like "2d 10h 5m" into a timedelta.
    Supported units: d (days), h (hours), m (minutes)
    """
    pattern = r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?"
    match = re.match(pattern, duration_str.strip())
    if not match:
        return None

    days = int(match.group(1)) if match.group(1) else 0
    hours = int(match.group(2)) if match.group(2) else 0
    minutes = int(match.group(3)) if match.group(3) else 0

    return timedelta(days=days, hours=hours, minutes=minutes)