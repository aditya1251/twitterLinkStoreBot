from threading import Lock
from datetime import datetime, timedelta
from telebot import apihelper
import telebot.types
import re
from handlers.admin import notify_dev
import json
from utils.redis_client import get_redis

_admins_cache = {}
_lock = Lock()
_CACHE_TTL = 300  # 5 minutes

def normalize_gid(chat_id):
    return str(chat_id)

def _redis_key(chat_id):
    return f"admins_cache:{normalize_gid(chat_id)}"

def get_cached_admins(chat_id):
    gid = normalize_gid(chat_id)
    now = datetime.utcnow()

    with _lock:
        entry = _admins_cache.get(gid)
        if entry:
            admin_ids, expires_at = entry
            if now < expires_at:
                return admin_ids
            else:
                _admins_cache.pop(gid, None)

    try:
        r = get_redis()
        data = r.get(_redis_key(gid))
        if data:
            admin_ids = json.loads(data)
            with _lock:
                _admins_cache[gid] = (admin_ids, now + timedelta(seconds=_CACHE_TTL))
            return admin_ids
    except Exception as e:
        print(f"[WARN] Redis get_cached_admins failed: {e}")

    return None


def set_cached_admins(chat_id, admin_ids):
    gid = normalize_gid(chat_id)
    expires_at = datetime.utcnow() + timedelta(seconds=_CACHE_TTL)

    with _lock:
        _admins_cache[gid] = (admin_ids, expires_at)

    try:
        r = get_redis()
        r.setex(_redis_key(gid), _CACHE_TTL, json.dumps(admin_ids))
    except Exception as e:
        print(f"[WARN] Redis set_cached_admins failed: {e}")


def clear_cached_admins(chat_id):

    gid = normalize_gid(chat_id)

    with _lock:
        _admins_cache.pop(gid, None)

    try:
        r = get_redis()
        r.delete(_redis_key(gid))
    except Exception as e:
        print(f"[WARN] Redis clear_cached_admins failed: {e}")


def is_user_admin_cached(chat_id, user_id):
    gid = normalize_gid(chat_id)
    with _lock:
        admins = _admins_cache.get(gid)
        if admins is None:
            return None 
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

from typing import Dict, Optional
from telebot import TeleBot
from config import settings
from utils import db

# Import your existing handlers (child bots reuse these)
from handlers import commands, start, text as text_handler, callbacks
from utils.message_tracker import track_message
from utils.group_manager import get_allowed_groups, save_group_metadata

def manual_dispatch(bot, bot_id: str, update, db_conn):
    if update.callback_query:
        callbacks.handle_callback(bot, bot_id, update.callback_query)
        return

    if not update.message:
        return

    message = update.message
    track_message(message.chat.id, message.message_id, bot_id=bot_id)

    chat = message.chat

    # safe access to text/caption
    incoming_text = (getattr(message, "text", None) or "")  # prefer direct text
    caption_text = (getattr(message, "caption", None) or "")

    # PRIVATE: commands come from textual messages (most common). If no text, still pass to handler
    if chat.type == "private":
        if incoming_text.startswith("/"):
            commands.handle_command(bot, bot_id, message, db_conn)
        else:
            text_handler.handle_text(bot, bot_id, message, db_conn)
        return

    # GROUP / SUPERGROUP
    if chat.type in ["group", "supergroup"]:
        # store group metadata & check allowed groups
        save_group_metadata(db_conn, bot_id, message.chat)
        if chat.id not in get_allowed_groups(bot_id):
            return

        # command detection: only true text messages start with "/"
        if incoming_text.startswith("/"):
            commands.handle_group_command(bot, bot_id, message, db_conn)
        else:
            # non-command messages (including media captions) go to group text handler
            text_handler.handle_group_text(bot, bot_id, message, db_conn)

from telebot import TeleBot
from typing import Dict, Optional
from utils import db
from config import settings

class BotManager:
    """
    Holds the admin bot + all child bots.
    """
    def __init__(self):
        self.admin_bot: TeleBot = TeleBot(settings.ADMIN_BOT_TOKEN, parse_mode="HTML", threaded=False)
        self.child_bots: Dict[str, TeleBot] = {}

        @self.admin_bot.message_handler(commands=["ping"])
        def _ping(m):
            self.admin_bot.reply_to(m, "pong ✅")

    def get_child(self, bot_id: str) -> Optional[TeleBot]:
        return self.child_bots.get(bot_id)

    def create_or_get_child(self, bot_id: str) -> Optional[TeleBot]:
        if bot_id in self.child_bots:
            return self.child_bots[bot_id]

        doc = db.get_bot_doc(bot_id)
        if not doc or doc.get("status") != "enabled":
            return None

        token = doc["token"]
        bot = TeleBot(token, parse_mode="HTML", threaded=False)
        self.child_bots[bot_id] = bot
        return bot

    # === New methods for manual dispatch ===
    def set_child_webhook(self, bot_id: str, url: str) -> bool:
        """Set webhook for a child bot and store it in DB"""
        bot = self.create_or_get_child(bot_id)
        if not bot:
            return False
        try:
            bot.remove_webhook()
            bot.set_webhook(url)
            db.set_bot_webhook(bot_id, url)
            return True
        except Exception as e:
            print(f"Failed to set webhook for bot {bot_id}: {e}")
            return False

    def delete_child_webhook(self, bot_id: str):
        """Remove webhook for a child bot"""
        bot = self.get_child(bot_id)
        if bot:
            try:
                bot.remove_webhook()
            except Exception:
                pass
        db.set_bot_webhook(bot_id, None)


manager = BotManager()
