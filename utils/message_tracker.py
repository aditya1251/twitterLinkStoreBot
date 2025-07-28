# message_tracker.py

from collections import defaultdict

# In-memory message ID store: { "chat_id": [msg_id1, msg_id2, ...] }
messages_by_chat = defaultdict(list)

def track_message(chat_id: int, message_id: int):
    """
    Track a message ID sent by the bot in a specific chat.
    """
    messages_by_chat[str(chat_id)].append(message_id)

def get_tracked_messages(chat_id: int):
    """
    Get a list of message IDs tracked for a given chat.
    """
    return messages_by_chat.get(str(chat_id), [])

def clear_tracked_messages(chat_id: int):
    """
    Clear all tracked message IDs for a given chat.
    """
    messages_by_chat[str(chat_id)] = []

def delete_tracked_messages(bot, chat_id: int):
    """
    Delete all messages tracked for a given chat using the bot.
    """
    chat_key = str(chat_id)
    for msg_id in messages_by_chat.get(chat_key, []):
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass  # You can log the error here if needed
    messages_by_chat[chat_key] = []

def delete_last_message(bot, chat_id: int):
    """
    Delete the last tracked message in a given chat.
    """
    chat_key = str(chat_id)
    if messages_by_chat[chat_key]:
        last_msg_id = messages_by_chat[chat_key].pop()
        try:
            bot.delete_message(chat_id, last_msg_id)
        except Exception:
            pass
