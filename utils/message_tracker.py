import time
from telebot.apihelper import ApiTelegramException
from collections import defaultdict

# Structure: { bot_id: { chat_id: [msg_ids...] } }
messages_by_chat = defaultdict(lambda: defaultdict(list))

__all__ = [
    "track_message",
    "get_tracked_messages",
    "clear_tracked_messages",
    "delete_tracked_messages",
    "delete_last_message",
]

def track_message(chat_id: int, message_id: int, bot_id: str = "default"):
    """Store a sent message so it can be bulk-deleted later."""
    messages_by_chat[bot_id][str(chat_id)].append(message_id)

def get_tracked_messages(chat_id: int, bot_id: str = "default"):
    """Return all tracked message IDs for a given chat."""
    return messages_by_chat[bot_id].get(str(chat_id), [])

def clear_tracked_messages(chat_id: int, bot_id: str = "default"):
    """Clear the tracked messages for a given chat."""
    messages_by_chat[bot_id][str(chat_id)] = []

def delete_tracked_messages(bot, chat_id: int, bot_id: str = "default"):
    """
    Delete all tracked messages in a chat for this bot_id.
    Handles rate limits gracefully.
    """
    chat_key = str(chat_id)
    tracked = messages_by_chat[bot_id].get(chat_key, [])

    for msg_id in tracked:
        try:
            bot.delete_message(chat_id, msg_id)
            time.sleep(0.05)  # avoid hitting rate limit
        except ApiTelegramException as e:
            if e.error_code == 429:
                retry_after = getattr(e, "retry_after", 3)
                time.sleep(retry_after)
        except Exception:
            pass

    messages_by_chat[bot_id][chat_key] = []

def delete_last_message(bot, chat_id: int, bot_id: str = "default"):
    """Delete the last tracked message in this chat."""
    chat_key = str(chat_id)
    if messages_by_chat[bot_id][chat_key]:
        last_msg_id = messages_by_chat[bot_id][chat_key].pop()
        try:
            bot.delete_message(chat_id, last_msg_id)
        except Exception:
            pass
