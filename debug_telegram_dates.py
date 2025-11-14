#!/usr/bin/env python
"""Script di debug per verificare le date dei messaggi Telegram"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient
import asyncio

# Configurazione
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
VERIFICATION_CODE = os.getenv('VERIFICATION_CODE')
TELEGRAM_PASSWORD = os.getenv('TELEGRAM_PASSWORD')
SESSION_NAME = Path(__file__).parent / 'telegram_session'

async def main():
    client = TelegramClient(str(SESSION_NAME), API_ID, API_HASH)

    await client.start(
        phone=PHONE_NUMBER,
        code_callback=lambda: VERIFICATION_CODE if VERIFICATION_CODE else input('Code: '),
        password=lambda: TELEGRAM_PASSWORD if TELEGRAM_PASSWORD else input('Password: ')
    )

    print("📅 Ultimi 20 messaggi con date:\n")

    count = 0
    async for message in client.iter_messages(CHANNEL_ID, limit=20):
        if message.text:
            # Mostra data in UTC e MSK
            date_utc = message.date
            date_msk = date_utc.astimezone()

            # Estratto breve del testo
            text_preview = message.text[:50].replace('\n', ' ')

            print(f"{count+1}. ID: {message.id}")
            print(f"   UTC: {date_utc.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   MSK: {date_msk.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   Text: {text_preview}...")
            print()

            count += 1

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
