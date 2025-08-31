# feedback_bot.py
# Requires: python-telegram-bot >= 20
# pip install python-telegram-bot==20.7

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
import logging
import os

# ================== CONFIG ==================
TOKEN = os.getenv("8261415169:AAEmkcwiagDzvIBMBWGXJ3tCpSiDsWy312g", "8261415169:AAEmkcwiagDzvIBMBWGXJ3tCpSiDsWy312g")
ADMIN_ID = int(os.getenv("7526659682", "7526659682"))  # <-- put your Telegram user ID here
# ============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

TYPING_REPLY = 1  # conversation state key


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id == ADMIN_ID:
        await update.message.reply_text("👋 Admin mode. I’ll forward users’ feedback here. Tap Reply to answer.")
    else:
        await update.message.reply_text("👋 Welcome! Send me your feedback; I’ll pass it to the admin.")


# ========== USERS: send feedback ==========
async def handle_feedback_from_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles feedback from any NON-admin user and forwards to the admin with a reply button."""
    msg = update.effective_message
    user = update.effective_user

    # Build a reply button carrying the user's id
    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("↩️ Reply to this user", callback_data=f"reply:{user.id}")
    )

    # Actual user name (not just @username)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else "(no username)"

    text = msg.text or msg.caption or ""
    payload = (
        "📩 New Feedback\n"
        f"👤 From: {full_name} {username}\n"
        f"🆔 ID: {user.id}\n\n"
        f"{text}"
    )

    # Forward to admin
    await context.bot.send_message(chat_id=ADMIN_ID, text=payload, reply_markup=kb)

    # Acknowledge user
    if msg.text:
        await msg.reply_text("✅ Your feedback was sent to the admin. Thanks!")
    else:
        await msg.reply_text("✅ Sent! (Note: admin sees text/caption; send text for best clarity.)")


# ========== ADMIN: clicks Reply button ==========
async def admin_click_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: Admin taps the inline button. Stores target user_id and asks for reply text."""
    query = update.callback_query
    await query.answer()

    # Only admin can use the button
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_reply_markup(None)
        await query.message.reply_text("⛔ Only the admin can use that button.")
        return ConversationHandler.END

    # Parse user id from callback data
    try:
        _, user_id_str = query.data.split(":")
        target_user_id = int(user_id_str)
    except Exception:
        await query.message.reply_text("⚠️ Invalid reply target.")
        return ConversationHandler.END

    # Store target in chat_data (scoped to admin chat)
    context.chat_data["reply_target_user_id"] = target_user_id

    # Prompt admin
    await query.message.reply_text(
        f"✍️ Type your reply for user ID {target_user_id}.\n"
        "Send text now. Use /cancel to abort."
    )
    return TYPING_REPLY


# ========== ADMIN: sends the reply text ==========
async def admin_send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin sends the actual reply message; bot delivers it only to the original user."""
    if update.effective_user.id != ADMIN_ID:
        # Safety: ignore if somehow reached by non-admin
        return ConversationHandler.END

    target_user_id = context.chat_data.get("reply_target_user_id")
    if not target_user_id:
        await update.message.reply_text("⚠️ No reply target found. Tap a Reply button again.")
        return ConversationHandler.END

    reply_text = update.message.text

    # Send to the specific user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Admin replied:\n\n{reply_text}"
        )
        await update.message.reply_text("✅ Reply sent to the user.")
    except Exception as e:
        await update.message.reply_text(f"❌ Could not deliver reply (maybe the user blocked the bot).\nError: {e}")

    # Clear target & end conversation
    context.chat_data.pop("reply_target_user_id", None)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        context.chat_data.pop("reply_target_user_id", None)
        await update.message.reply_text("🚫 Reply cancelled.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation for admin reply flow (button -> type message)
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_click_reply, pattern=r"^reply:\d+$")],
        states={
            TYPING_REPLY: [MessageHandler(filters.TEXT & filters.User(ADMIN_ID), admin_send_reply)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        per_chat=True,
        per_user=False,
        name="admin_reply_conv",
        persistent=False,
    )
    app.add_handler(reply_conv)

    # Commands
    app.add_handler(CommandHandler("start", start))

    # Admin-only messages outside the convo are ignored (so admin isn’t treated as a normal user)
    # Users’ feedback (text/caption) — EXCLUDE admin explicitly
    user_text_filter = filters.TEXT & ~filters.COMMAND & ~filters.User(ADMIN_ID)
    app.add_handler(MessageHandler(user_text_filter, handle_feedback_from_user))

    # Optional: support captions from media by catching non-text messages with captions
    user_caption_filter = filters.CaptionRegex(".*") & ~filters.User(ADMIN_ID)
    app.add_handler(MessageHandler(user_caption_filter, handle_feedback_from_user))

    log.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
