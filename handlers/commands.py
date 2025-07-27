def handle_command(bot, message, db):
    chat_id = message.chat.id
    text = message.text.strip()

    # Save or update user
    db["users"].update_one(
        {"chat_id": chat_id},
        {"$set": {
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name
        }},
        upsert=True
    )

    if text == "/start":
        bot.send_message(chat_id, "👋 Hello! I'm alive and connected to MongoDB.")
    elif text == "/help":
        bot.send_message(chat_id, "ℹ️ Commands:\n/start - Start bot\n/help - Help menu")
    else:
        bot.send_message(chat_id, "🤔 Unknown command. Use /help.")
