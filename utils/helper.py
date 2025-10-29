from handlers.admin import notify_dev

def send_media(bot, chat_id, media):
    try:
        caption = media.get("caption") or ""
        if media["type"] == "video":
            return bot.send_video(chat_id, media["file_id"], caption=caption)
        elif media["type"] == "gif":
            return bot.send_animation(chat_id, media["file_id"], caption=caption)
        elif media["type"] == "image":
            return bot.send_photo(chat_id, media["file_id"], caption=caption)
    except Exception as e:
        notify_dev(bot, e, "send_media")
