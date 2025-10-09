#!/usr/bin/env python
"""
Script per recuperare l'ID di un canale Telegram.
Il bot deve essere già membro/amministratore del canale.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import asyncio

# Carica variabili d'ambiente
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def get_channel_info():
    """
    Recupera informazioni sui canali/chat accessibili al bot.
    """
    if not BOT_TOKEN:
        print("ERRORE: BOT_TOKEN non trovato nel file .env")
        return

    bot = Bot(token=BOT_TOKEN)

    print("Bot inizializzato. Recupero informazioni...\n")

    # Informazioni sul bot
    try:
        me = await bot.get_me()
        print(f"Bot username: @{me.username}")
        print(f"Bot ID: {me.id}")
        print(f"Bot name: {me.first_name}\n")
    except TelegramError as e:
        print(f"Errore nel recuperare info bot: {e}")
        return

    # Prova a ottenere gli aggiornamenti recenti
    print("Recupero ultimi messaggi/aggiornamenti...\n")
    try:
        updates = await bot.get_updates(limit=100)

        if not updates:
            print("Nessun aggiornamento trovato.")
            print("\nSuggerimenti:")
            print("1. Assicurati che il bot sia membro del canale 'entrate_agts'")
            print("2. Invia un messaggio al canale dopo aver aggiunto il bot")
            print("3. Oppure fornisci manualmente l'username del canale (es. @entrate_agts)")
            return

        # Raccogli info sui canali/chat
        channels = {}
        for update in updates:
            if update.channel_post:
                chat = update.channel_post.chat
                if chat.id not in channels:
                    channels[chat.id] = {
                        'title': chat.title,
                        'username': chat.username,
                        'type': chat.type
                    }

        if channels:
            print("Canali trovati:")
            for chat_id, info in channels.items():
                print(f"\nTitolo: {info['title']}")
                print(f"ID: {chat_id}")
                print(f"Username: @{info['username']}" if info['username'] else "Username: (privato)")
                print(f"Tipo: {info['type']}")
        else:
            print("Nessun canale trovato negli aggiornamenti recenti.")
            print("\nProva a:")
            print("1. Inviare un nuovo messaggio al canale")
            print("2. Verificare che il bot abbia i permessi corretti")

    except TelegramError as e:
        print(f"Errore: {e}")
        print("\nSe il canale è privato, prova a:")
        print("1. Aggiungere il bot come amministratore del canale")
        print("2. Inviare un messaggio di test dopo aver aggiunto il bot")

if __name__ == "__main__":
    asyncio.run(get_channel_info())
