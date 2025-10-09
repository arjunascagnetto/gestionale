#!/usr/bin/env python
"""Test semplice del bot Telegram."""
import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Carica .env
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    await update.message.reply_text(
        f"✅ Bot funzionante!\n\n"
        f"Chat ID: {update.effective_chat.id}\n"
        f"User ID: {update.effective_user.id}\n"
        f"Username: @{update.effective_user.username}"
    )

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /test"""
    await update.message.reply_text(
        f"🧪 Test OK!\n"
        f"Admin configurato: {ADMIN_CHAT_ID}\n"
        f"Tuo ID: {update.effective_chat.id}"
    )

def main():
    print(f"Bot Token: {BOT_TOKEN[:20]}...")
    print(f"Admin Chat ID: {ADMIN_CHAT_ID}\n")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))

    print("🤖 Bot test avviato! Invia /start o /test")
    print("Premi Ctrl+C per terminare\n")

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
