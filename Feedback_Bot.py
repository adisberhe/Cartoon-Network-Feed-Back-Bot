import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

# Get environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))  # Ensure ADMIN_ID is an integer
DEVELOPER_CHAT_ID = int(os.environ.get("DEVELOPER_CHAT_ID", ADMIN_ID)) # Optional, defaults to ADMIN_ID if not set.


TYPING_REPLY = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Send your feedback or queries to the admin.")


async def handle_feedback_from_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    message = update.message
    feedback_text = message.text or message.caption or "No text provided"

    # Create Reply button inline
    keyboard = [
        [InlineKeyboardButton(text="Reply", callback_data=f"reply:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Forward the feedback to the admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💬 New Feedback from @{user.username} ({user.first_name} {user.last_name or ''}, ID: {user.id}):\n\n{feedback_text}",
            reply_markup=reply_markup,
        )
        await update.message.reply_text("✅ Your feedback has been sent to the admin.")
    except Exception as e:
        log.error(f"Error forwarding message to admin: {e}")
        await update.message.reply_text("❌ Failed to send feedback. Please try again later.")


async def admin_click_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        query = update.callback_query
        await query.answer()

        target_user_id = query.data.split(":")[1]  # Get the target user ID from the callback data
        context.chat_data["reply_target_user_id"] = target_user_id

        await query.edit_message_text(text=f"✍️ Replying to user {target_user_id}.  Type your message and /cancel to cancel.")
        return TYPING_REPLY
    else:
        await update.callback_query.answer("Unauthorized.", show_alert=True)
        return ConversationHandler.END

async def admin_send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.chat_data.get("reply_target_user_id")
    if not target_user_id:
        await update.message.reply_text("⚠️ No reply target found. Tap a Reply button again.")
        return ConversationHandler.END

    reply_text = update.message.text

    # Send to the specific user
    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),  # Ensure target_user_id is an integer
            text=f"💬 Admin replied:\n\n{reply_text}"
        )
        await update.message.reply_text("✅ Reply sent to the user.")
    except Exception as e:
        await update.message.reply_text(f"❌ Could not deliver reply (maybe the user blocked the bot).\nError: {e}")
        log.error(f"Error sending reply to user {target_user_id}: {e}")


    # Clear target & end conversation
    context.chat_data.pop("reply_target_user_id", None)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        context.chat_data.pop("reply_target_user_id", None)
        await update.message.reply_text("🚫 Reply cancelled.")
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    log.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # string!
    # the "effective chat" is the chat that is targeted by the update.
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=DEVELOPER_CHAT_ID, text=f"Update {update} caused error {context.error}"
        )
    # Finally, let the user know that something went wrong.
    await update.message.reply_text("Oops! Something went wrong. We've notified the developers.")


def main():
    app = Application.builder().token(TOKEN).build()

    # Add error handler
    app.add_error_handler(error_handler)

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



