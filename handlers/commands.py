import handlers.start as start
import handlers.admin as admin
from utils.telegram import is_user_admin, set_cached_admins, mute_user
from utils.group_session import get_users_with_multiple_links, get_unverified_users,get_unverified_users_full,handle_link_command, handle_sr_command, handle_srlist_command,set_verification_phase


def handle_command(bot, message, db):
    chat_id = message.chat.id
    text = message.text.strip()

    if "@" in text:
        text = text.split("@")[0]

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
        start.handle_start(bot, message)
    elif text == "/help":
        help_text = (
    "🤖 <b>Bot Help Menu</b>\n\n"
    "👤 <b>General Commands:</b>\n"
    "/start — Start the bot\n"
    "/help — Show this help menu\n\n"

    "👥 <b>Group Commands:</b>\n"
    "/start — Activate group features\n"
    "/refresh_admins — Refresh admin list (admin only)\n"
    "/verify — Start verifying mode (admin only)\n"
    "/multi — Show users with multiple links (admin only)\n"
    "/unsafe — List unverified users (admin only)\n"
    "/muteunsafe — Mute all unverified users for 3 days (admin only)\n"
    "/link — (Reply) Get all links shared by a user (admin only)\n"
    "/sr — (Reply) Ask a user to submit screen recording in DM (admin only)\n"
    "/srlist — List users asked to submit screen recordings (admin only)\n\n"

    "🛠️ <b>Admin Panel:</b>\n"
    "/managegroups — Manage allowed groups (admin only in private chat)"
)

        bot.send_message(chat_id, help_text, parse_mode="HTML")


    elif text == "/managegroups":
        admin.handle_manage_groups(bot, message, db)
    else:
        bot.send_message(chat_id, "🤔 Unknown command. Use /help.")

def handle_group_command(bot, message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    if "@" in text:
        text = text.split("@")[0]

    print(f"Group command: {text} by {user_id}")
    
    if text == "/start":
        print(f"Group command: /start by {user_id}")
        start.handle_start_group(bot, message)
    elif text == "/close":
        print(f"Group command: /close by {user_id}")
        start.handle_cancel_group(bot, message,db)
    elif text == "/refresh_admins":
        if is_user_admin(bot, chat_id, message.from_user.id):
            try:
                admins = bot.get_chat_administrators(chat_id)
                set_cached_admins(chat_id, [admin.user.id for admin in admins])
                bot.send_message(chat_id, "✅ Admin list refreshed.")
            except Exception:
                bot.send_message(chat_id, "⚠️ Failed to refresh admins.")
    elif text == "/verify":
        if is_user_admin(bot, chat_id, message.from_user.id):
            set_verification_phase(chat_id)
            bot.send_message(chat_id, "Ad tracking has started! I will track 'ad', 'all done', 'all dn', 'done' messages.")
        else:
            bot.send_message(chat_id, "❌ Only admins can enable verification.")
    elif text == "/multi":
        if not is_user_admin(bot, chat_id, user_id):
            bot.send_message(chat_id, "❌ Only admins can use this command.")
            return

        users = get_users_with_multiple_links(chat_id)

        if not users:
            bot.send_message(chat_id, "ℹ️ No users with multiple links.")
            return

        response = "📊 *Users with Multiple Links:*\n\n"
        for user in users:
            response += f"👤 `{user['username']}` — {user['count']} links\n"
            for idx, link in enumerate(user["links"], start=1):
                response += f"{idx}. `{link}`\n"
            response += "\n\n"


        bot.send_message(chat_id, response, parse_mode="Markdown")
    elif text == "/unsafe":
        if not is_user_admin(bot, chat_id, user_id):
            bot.send_message(chat_id, "❌ Only admins can use this command.")
            return

        users = get_unverified_users(chat_id)

        if user == "notVerifyingphase":
            bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
            return

        if not users:
            bot.send_message(chat_id, "✅ All users are verified.")
        else:
            msg = "⚠️ *Unverified Users:*\n" + "\n".join([f"• {u}" for u in users])
            bot.send_message(chat_id, msg, parse_mode="Markdown")
    elif text == "/muteunsafe":
        if not is_user_admin(bot, chat_id, user_id):
            bot.send_message(chat_id, "❌ Only admins can use this command.")
            return

        unverified = get_unverified_users_full(chat_id)

        if unverified == "notVerifyingphase":
            bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
            return

        if not unverified:
            bot.send_message(chat_id, "✅ No unverified users to mute.")
            return

        success_log = []
        failed = []
        for user in unverified:
            uid = user["user_id"]
            uname = user.get("username")
            fname = user.get("first_name", "Unknown")

            if mute_user(bot, chat_id, uid):
                name_display = f"@{uname}" if uname else fname
                success_log.append(f"{name_display} (ID: {uid})")
            else:
                failed.append(uname or fname)

        msg = "🔇 *Muted the following unverified users for 3 days:*\n\n"
        msg += "\n".join(success_log)

        if failed:
            msg += "\n\n⚠️ *Failed to mute:*\n" + "\n".join(f"• {u}" for u in failed)

        bot.send_message(chat_id, msg, parse_mode="Markdown")
    elif text.startswith("/link"):
        handle_link_command(bot, message)
    elif text.startswith("/sr "):  # or just "/sr"
        handle_sr_command(bot, message)
    elif text == "/srlist":
        handle_srlist_command(bot, message)