import time
from telebot.apihelper import ApiTelegramException
from collections import defaultdict

# Scoped by bot_id
messages_by_chat = defaultdict(lambda: defaultdict(list))
# structure: { bot_id: { chat_id: [msg_ids...] } }

def track_message(chat_id: int, message_id: int, bot_id: str = "default"):
    messages_by_chat[bot_id][str(chat_id)].append(message_id)

def get_tracked_messages(chat_id: int, bot_id: str = "default"):
    return messages_by_chat[bot_id].get(str(chat_id), [])

def clear_tracked_messages(chat_id: int, bot_id: str = "default"):
    messages_by_chat[bot_id][str(chat_id)] = []

def delete_tracked_messages(bot, chat_id: int, bot_id: str = "default"):
    chat_key = str(chat_id)
    tracked = messages_by_chat[bot_id].get(chat_key, [])
    for msg_id in tracked:
        try:
            bot.delete_message(chat_id, msg_id)
            time.sleep(0.05)
        except ApiTelegramException as e:
            if e.error_code == 429:
                retry_after = getattr(e, 'retry_after', 3)
                time.sleep(retry_after)
        except Exception:
            pass
    messages_by_chat[bot_id][chat_key] = []

def delete_last_message(bot, chat_id: int, bot_id: str = "default"):
    chat_key = str(chat_id)
    if messages_by_chat[bot_id][chat_key]:
        last_msg_id = messages_by_chat[bot_id][chat_key].pop()
        try:
            bot.delete_message(chat_id, last_msg_id)
        except Exception:
            pass
