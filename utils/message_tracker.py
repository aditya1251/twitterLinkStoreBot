# utils/message_tracker.py
import json
from utils.redis_client import get_redis

_r = get_redis()

# Redis key pattern: tracked:{bot_id}:{chat_id}
# We use a Redis set to avoid duplicates, atomic ops to prevent race conditions

DEFAULT_TTL = 48 * 3600  # auto-expire in 24h


def track_message(chat_id: int, message_id: int, bot_id: str = None, ttl: int = DEFAULT_TTL):
    """
    Save a message ID in Redis for later deletion.
    """
    if not bot_id:
        bot_id = "default"
    key = f"tracked:{bot_id}:{chat_id}"
    try:
        _r.sadd(key, message_id)
        _r.expire(key, ttl)  # auto-clean after TTL
    except Exception as e:
        print(f"[track_message] Redis error: {e}")


def delete_tracked_messages(bot, chat_id: int, bot_id: str = None):
    """
    Delete all tracked messages for this chat.
    Works safely across multiple Gunicorn workers.
    """
    if not bot_id:
        bot_id = "default"
    key = f"tracked:{bot_id}:{chat_id}"

    try:
        while True:
            mid = _r.spop(key)  # atomic pop ensures no race condition
            if mid is None:
                break
            try:
                bot.delete_message(chat_id, int(mid))
            except Exception as e:
                # Ignore "message not found" or permission errors
                print(f"[delete_tracked_messages] Failed to delete {mid}: {e}")
    except Exception as e:
        print(f"[delete_tracked_messages] Redis error: {e}")

def delete_tracked_messages_with_progress(bot, chat_id: int, bot_id: str = None):
    """
    Delete tracked messages with a live progress bar.
    Updates one Telegram message as progress indicator.
    """
    if not bot_id:
        bot_id = "default"
    key = f"tracked:{bot_id}:{chat_id}"

    try:
        total = _r.scard(key)
        if total == 0:
            bot.send_message(chat_id, "ℹ️ No tracked messages to delete.")
            return

        progress_msg = bot.send_message(chat_id, f"🧹 Deleting {total} messages...\nProgress: 0% [░░░░░░░░░░]")

        deleted = 0
        bar_length = 10

        while True:
            mid = _r.spop(key)
            if mid is None:
                break
            try:
                bot.delete_message(chat_id, int(mid))
            except Exception:
                pass
            deleted += 1

            # Update progress every ~10% or last
            if deleted == total or deleted % max(1, total // bar_length) == 0:
                percent = int((deleted / total) * 100)
                filled = int(bar_length * deleted / total)
                bar = "█" * filled + "░" * (bar_length - filled)
                try:
                    bot.edit_message_text(
                        f"🧹 Deleting {total} messages...\nProgress: {percent}% [{bar}]",
                        chat_id,
                        progress_msg.message_id
                    )
                except Exception:
                    pass

        bot.edit_message_text(
            f"✅ Deleted {deleted}/{total} tracked messages.",
            chat_id,
            progress_msg.message_id
        )

    except Exception as e:
        print(f"[delete_tracked_messages_with_progress] Redis error: {e}")
        bot.send_message(chat_id, "⚠️ Failed to delete tracked messages.")


def clear_chat_tracking(chat_id: int, bot_id: str = None):
    """
    Just clear the Redis set without trying to delete messages.
    """
    if not bot_id:
        bot_id = "default"
    key = f"tracked:{bot_id}:{chat_id}"
    try:
        _r.delete(key)
    except Exception as e:
        print(f"[clear_chat_tracking] Redis error: {e}")
