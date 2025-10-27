import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Applications,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# environment variable loading
API_TOKEN = os.environ.get("API_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
DEVELOPER_CHAT_ID = os.environ.get("DEVELOPER_CHAT_ID", ADMIN_ID)

if not API_TOKEN or not ADMIN_ID:
    raise ValueError("Missing API_TOKEN or ADMIN_ID environment variable")

ADMIN_ID = int(ADMIN_ID)
DEVELOPER_CHAT_ID = int(DEVELOPER_CHAT_ID)

TYPING_REPLY = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Send your feedback or queries to the admin.")


async def handle_feedback_from_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    message = update.message
    feedback_text = message.text or message.caption or "No text provided"

    keyboard = [[InlineKeyboardButton("Reply", callback_data=f"reply:{chat_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f" New Feedback from @{user.username } "
                 f"({user.first_name} {user.last_name or ''}, ID: {user.id}):\n\n{feedback_text}",
            reply_markup=reply_markup,
        )
        await update.message.reply_text(" Your feedback has been sent to the admin.")
    except Exception as e:
        log.error(f"Error forwarding message to admin: {e}")
        await update.message.reply_text(" Failed to send feedback. Please try again later.")


async def admin_click_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("Unauthorized.", show_alert=True)
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    target_user_id = query.data.split(":")[1]
    context.chat_data["reply_target_user_id"] = target_user_id

    await query.edit_message_text(
        text=f" Replying to user {target_user_id}. Type your message and /cancel to cancel."
    )
    return TYPING_REPLY


async def admin_send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.chat_data.get("reply_target_user_id")
    if not target_user_id:
        await update.message.reply_text(" No reply target found. Tap a Reply button again.")
        return ConversationHandler.END

    reply_text = update.message.text
    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),
            text=f" Admin replied:\n\n{reply_text}"
        )
        await update.message.reply_text("Reply sent to the user.")
    except Exception as e:
        await update.message.reply_text(f" Could not deliver reply (maybe the user blocked the bot).\nError: {e}")
        log.error(f"Error sending reply to user {target_user_id}: {e}")

    context.chat_data.pop("reply_target_user_id", None)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        context.chat_data.pop("reply_target_user_id", None)
        await update.message.reply_text("🚫 Reply cancelled.")
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Exception while handling an update:", exc_info=context.error)
    if update and getattr(update, "effective_chat", None):
        await context.bot.send_message(
            chat_id=DEVELOPER_CHAT_ID,
            text=f"Update {update} caused error {context.error}"
        )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text("Oops! Something went wrong. We've notified the developers.")


# ---------------- Main ---------------- #

def main():
    app = Application.builder().token(API_TOKEN).build()

    # Conversation for admin reply flow
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_click_reply, pattern=r"^reply:\d+$")],
        states={
            TYPING_REPLY: [MessageHandler(filters.TEXT & filters.User(ADMIN_ID), admin_send_reply)]
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

    # User feedback
    user_text_filter = filters.TEXT & ~filters.COMMAND & ~filters.User(ADMIN_ID)
    app.add_handler(MessageHandler(user_text_filter, handle_feedback_from_user))

    user_caption_filter = filters.CaptionRegex(".*") & ~filters.User(ADMIN_ID)
    app.add_handler(MessageHandler(user_caption_filter, handle_feedback_from_user))

    # Error handler
    app.add_error_handler(error_handler)

    log.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

