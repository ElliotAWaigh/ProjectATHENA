from Tools import login
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Get the API token from your login module
API_TOKEN = login.telegram_login()

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Hello! I am ATHENA. How can I assist you today?')

async def handle_message(update: Update, context: CallbackContext) -> None: 
    from bot import process_input_from_telegram
    text = update.message.text
    print("text sent is", text)
    response = process_input_from_telegram(text)
    await update.message.reply_text(response)

def run_telegram_bot(bot_instance):
    application = Application.builder().token(API_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()
