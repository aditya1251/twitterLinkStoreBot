import handlers.start as start
import handlers.admin as admin
from utils.telegram import is_user_admin, set_cached_admins, mute_user
from utils.group_session import (
    get_users_with_multiple_links,
    get_unverified_users,
    get_unverified_users_full,
    handle_link_command,
    handle_sr_command,
    handle_srlist_command,
    set_verification_phase,
    get_all_links_count,
    handle_close_group,
    handle_add_to_ad_command
)
from utils.message_tracker import track_message ,delete_tracked_messages



def handle_command(bot, message, db):
    chat_id = message.chat.id
    text = message.text.strip()

    if "@" in text:
        text = text.split("@")[0]

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
        msg = bot.send_message(chat_id, help_text, parse_mode="HTML")
        track_message(chat_id, msg.message_id)  # ✅

    elif text == "/managegroups":
        admin.handle_manage_groups(bot, message, db)
    else:
        msg = bot.send_message(chat_id, "🤔 Unknown command. Use /help.")
        track_message(chat_id, msg.message_id)  # ✅


def handle_group_command(bot, message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    if "@" in text:
        text = text.split("@")[0]

    if text in ["/start", "/starts"]:
        start.handle_start_group(bot, message)

    elif text == "/close":
        handle_close_group(bot, message)

    elif text in ["/end", "/stop"]:
        start.handle_cancel_group(bot, message, db)

    elif text == "/refresh_admins":
        if is_user_admin(bot, chat_id, user_id):
            try:
                admins = bot.get_chat_administrators(chat_id)
                set_cached_admins(chat_id, [admin.user.id for admin in admins])
                msg = bot.send_message(chat_id, "✅ Admin list refreshed.")
                track_message(chat_id, msg.message_id)  # ✅
            except Exception:
                msg = bot.send_message(chat_id, "⚠️ Failed to refresh admins.")
                track_message(chat_id, msg.message_id)  # ✅

    elif text in ["/verify", "/track", "/check"]:
        if is_user_admin(bot, chat_id, user_id):
            set_verification_phase(chat_id)
            msg = bot.send_message(chat_id, "✅ Ad tracking has started! I will track 'ad', 'all done', 'all dn', 'done' messages.")
            track_message(chat_id, msg.message_id)  # ✅
        else:
            msg = bot.send_message(chat_id, "❌ Only admins can enable verification.")
            track_message(chat_id, msg.message_id)  # ✅

    elif text == "/count":
        if not is_user_admin(bot, chat_id, user_id):
            msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id)  # ✅
            return
        count = get_all_links_count(chat_id)
        msg = bot.send_message(chat_id, f"📊 Total Users: {count}")
        track_message(chat_id, msg.message_id)  # ✅

    elif text == "/multi":
        if not is_user_admin(bot, chat_id, user_id):
            msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        users = get_users_with_multiple_links(chat_id)

        if not users:
            msg = bot.send_message(chat_id, "ℹ️ No users with multiple links.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        response = "<b>📊 Users with Multiple Links:</b>\n\n"
        for user in users:
            name_display = f"@{user['username']}" if user.get("username") else f"ID: <code>{user['user_id']}</code>"
            response += f"👤 <b>{name_display}</b> — {user['count']} links\n"
            for idx, link in enumerate(user["links"], start=1):
                response += f"{idx}. {link}\n"
            response += "\n"

        msg = bot.send_message(chat_id, response, parse_mode="HTML")
        track_message(chat_id, msg.message_id)  # ✅

    elif text == "/list":
        from utils.group_session import get_formatted_user_link_list

        if not is_user_admin(bot, chat_id, user_id):
            msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        result, count = get_formatted_user_link_list(chat_id)

        if not result:
            msg = bot.send_message(chat_id, "ℹ️ No users have submitted X links yet.")
            track_message(chat_id, msg.message_id)  # ✅
        else:
            msg = bot.send_message(chat_id, f"<b>📄 🚨 USERS LIST 🚨: {count}</b>\n\n{result}", parse_mode="HTML")
            track_message(chat_id, msg.message_id)  # ✅

    elif text == "/unsafe":
        if not is_user_admin(bot, chat_id, user_id):
            msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        users = get_unverified_users(chat_id)

        if users == "notVerifyingphase":
            msg = bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        if not users:
            msg = bot.send_message(chat_id, "✅ All users are verified.")
            track_message(chat_id, msg.message_id)  # ✅
        else:
            msg_text = "<b>⚠️ Unverified Users:</b>\n"
            for user in users:
                msg_text += f"\n• {user}"  # Already formatted HTML
            msg = bot.send_message(chat_id, msg_text, parse_mode="HTML")
            track_message(chat_id, msg.message_id)  # ✅

    elif text in ["/muteunsafe","/muteall"]:
        if not is_user_admin(bot, chat_id, user_id):
            msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        unverified = get_unverified_users_full(chat_id)

        if unverified == "notVerifyingphase":
            msg = bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        if not unverified:
            msg = bot.send_message(chat_id, "✅ No unverified users to mute.")
            track_message(chat_id, msg.message_id)  # ✅
            return

        success_log = []
        failed = []
        for user in unverified:
            uid = user["user_id"]
            fname = user.get("first_name", "User")
            if mute_user(bot, chat_id, uid):
                mention = f'<a href="tg://user?id={uid}">{fname}</a>'
                success_log.append(f"• {mention} (ID: <code>{uid}</code>)")
            else:
                failed.append(fname)

        msg_text = "<b>🔇 Muted the following unverified users for 3 days:</b>\n\n"
        msg_text += "\n".join(success_log)

        if failed:
            msg_text += "\n\n⚠️ <b>Failed to mute:</b>\n" + "\n".join(f"• {u}" for u in failed)

        msg = bot.send_message(chat_id, msg_text, parse_mode="HTML")
        track_message(chat_id, msg.message_id)  # ✅

    elif text.startswith("/link"):
        handle_link_command(bot, message)

    elif text == "/add_to_ad":
        handle_add_to_ad_command(bot, message)

    elif text == "/sr":
        handle_sr_command(bot, message)

    elif text == "/srlist":
        handle_srlist_command(bot, message)
    elif text == "/clear":
        delete_tracked_messages(bot, message.chat_id)
