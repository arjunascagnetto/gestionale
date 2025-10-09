#!/usr/bin/env python
"""
Script per recuperare l'ID di un canale tramite forward di un messaggio.
Inoltra un messaggio dal canale al bot in privato, e lo script ti dirà l'ID.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import asyncio

# Carica variabili d'ambiente
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce messaggi inoltrati e mostra l'ID del canale di origine."""
    message = update.message

    if message.forward_origin:
        origin = message.forward_origin

        print("\n" + "="*50)
        print("MESSAGGIO INOLTRATO RICEVUTO!")
        print("="*50)

        # Controlla il tipo di origine
        if hasattr(origin, 'chat'):
            # Inoltrato da un canale
            chat = origin.chat
            print(f"\nCanale di origine:")
            print(f"  Titolo: {chat.title}")
            print(f"  ID: {chat.id}")
            print(f"  Username: @{chat.username}" if chat.username else "  Username: (privato)")
            print(f"  Tipo: {chat.type}")

            # Salva nel .env
            channel_id = str(chat.id)
            print(f"\n✅ ID DEL CANALE DA SALVARE: {channel_id}")

            await message.reply_text(
                f"✅ Canale trovato!\n\n"
                f"Titolo: {chat.title}\n"
                f"ID: {channel_id}\n\n"
                f"Aggiungi questa riga al file .env:\n"
                f"CHANNEL_ID={channel_id}"
            )
        else:
            print("\nMessaggio inoltrato da un utente, non da un canale")
            await message.reply_text("⚠️ Inoltra un messaggio DAL CANALE, non da un utente.")
    else:
        print("\nMessaggio normale ricevuto (non inoltrato)")
        await message.reply_text(
            "👋 Ciao! Per trovare l'ID del canale:\n"
            "1. Apri il canale 'entrate_agts'\n"
            "2. Scegli un messaggio qualsiasi\n"
            "3. Inoltralo (forward) a questo bot\n"
            "4. Ti dirò l'ID del canale"
        )

async def main():
    if not BOT_TOKEN:
        print("ERRORE: BOT_TOKEN non trovato nel file .env")
        return

    print("="*50)
    print("BOT IN ASCOLTO")
    print("="*50)
    print("\nIstruzioni:")
    print("1. Apri Telegram")
    print("2. Vai sul canale 'entrate_agts'")
    print("3. Scegli un messaggio qualsiasi")
    print("4. Inoltralo (forward) a @justarj003_bot")
    print("5. Il bot ti dirà l'ID del canale")
    print("\nPremere Ctrl+C per terminare")
    print("="*50 + "\n")

    # Crea l'applicazione
    app = Application.builder().token(BOT_TOKEN).build()

    # Handler per tutti i messaggi
    app.add_handler(MessageHandler(filters.ALL, handle_forward))

    # Avvia il bot
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Mantieni il bot in esecuzione
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n\nBot terminato.")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
