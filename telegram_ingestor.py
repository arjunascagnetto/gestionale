#!/usr/bin/env python
"""
Componente 1: Ingestore Pagamenti
Legge messaggi dal canale Telegram, estrae dati di pagamento e li inserisce nel database.
"""
import os
import re
import sqlite3
import csv
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
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
DB_PATH = Path(__file__).parent / "pagamenti.db"
SESSION_NAME = Path(__file__).parent / 'telegram_session'
WHITELIST_PATH = Path(__file__).parent / 'mittenti_whitelist.csv'

# Pattern regex per il parsing degli SMS dalla banca russa
# Formato: СЧЁТ3185 HH:MM Перевод [dettagli] XXXXр от NOME COGNOME Баланс: YYYYр
SMS_PATTERN = re.compile(
    r'СЧЁТ\d+\s+'  # Numero conto
    r'(\d{1,2}):(\d{2})\s+'  # Ora (gruppo 1, 2)
    r'Перевод.*?'  # "Перевод" con dettagli opzionali
    r'([\d\s]+)р\s+'  # Somma (gruppo 3) - può avere spazi nei numeri
    r'от\s+'  # "от"
    r'([А-ЯЁA-Za-zА-яё]+(?:\s+[А-ЯЁA-Za-zА-яё]\.?)?)'  # Nome pagante (gruppo 4)
)


def load_whitelist(whitelist_path):
    """
    Carica la whitelist dei mittenti validi dal file CSV.

    Args:
        whitelist_path: Path al file CSV

    Returns:
        Set di nomi paganti validi (studenti)
    """
    valid_senders = set()

    if not whitelist_path.exists():
        print(f"⚠️  File whitelist non trovato: {whitelist_path}")
        print("    Tutti i pagamenti verranno processati.")
        return None

    try:
        with open(whitelist_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Solo i mittenti con studente=1 sono validi
                if row.get('studente') == '1':
                    valid_senders.add(row['nome_pagante'])

        print(f"✅ Whitelist caricata: {len(valid_senders)} studenti validi")
        return valid_senders
    except Exception as e:
        print(f"❌ Errore caricamento whitelist: {e}")
        return None


def parse_payment_message(message_text, message_date):
    """
    Estrae i dati di pagamento da un messaggio SMS.

    Args:
        message_text: Testo del messaggio
        message_date: Data del messaggio (datetime object)

    Returns:
        dict con i dati estratti o None se il parsing fallisce
    """
    match = SMS_PATTERN.search(message_text)

    if not match:
        return None

    ora_hh = match.group(1)
    ora_mm = match.group(2)
    somma_str = match.group(3).strip()
    nome_pagante = match.group(4).strip()

    # Normalizza il nome (Title Case)
    nome_pagante = nome_pagante.title()

    # Costruisci data dal message_date
    giorno = message_date.strftime('%Y-%m-%d')
    ora = f"{ora_hh.zfill(2)}:{ora_mm}:00"

    # Rimuovi tutti gli spazi dalla somma (gestisce "10 000" -> "10000")
    somma_clean = somma_str.replace(' ', '').replace('\xa0', '')  # Rimuove spazi normali e non-breaking spaces

    try:
        somma = float(somma_clean)
    except ValueError:
        print(f"⚠️  Errore conversione somma: '{somma_str}' -> '{somma_clean}'")
        return None

    return {
        'nome_pagante': nome_pagante,
        'giorno': giorno,
        'ora': ora,
        'somma': somma,
        'valuta': 'RUB',
        'stato': 'sospeso'
    }


def insert_payment(cursor, payment_data, message_id):
    """
    Inserisce un pagamento nel database con deduplicazione basata su message_id.

    Args:
        cursor: Cursore SQLite
        payment_data: Dizionario con i dati del pagamento
        message_id: ID del messaggio Telegram (per deduplicazione)

    Returns:
        ID del record inserito/aggiornato o None se già esistente
    """
    fonte_msg_id = f"tg_{CHANNEL_ID}_{message_id}"

    try:
        cursor.execute('''
            INSERT INTO pagamenti
            (nome_pagante, giorno, ora, somma, valuta, stato, fonte_msg_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            payment_data['nome_pagante'],
            payment_data['giorno'],
            payment_data['ora'],
            payment_data['somma'],
            payment_data['valuta'],
            payment_data['stato'],
            fonte_msg_id
        ))
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Messaggio già processato (vincolo UNIQUE su fonte_msg_id)
        return None


async def fetch_channel_history(client, channel_id, limit=100):
    """
    Recupera lo storico messaggi da un canale usando Telethon.

    Args:
        client: TelegramClient instance
        channel_id: ID del canale
        limit: Numero massimo di messaggi da recuperare

    Returns:
        Lista di messaggi
    """
    print(f"📥 Recupero messaggi dal canale {channel_id}...")

    try:
        messages = []
        async for message in client.iter_messages(channel_id, limit=limit):
            if message.text:
                messages.append(message)

        print(f"✅ Trovati {len(messages)} messaggi con testo")
        return messages

    except Exception as e:
        print(f"❌ Errore nel recuperare messaggi: {e}")
        return []


async def main():
    """Funzione principale."""
    if not API_ID or not API_HASH:
        print("❌ API_ID o API_HASH non trovati nel file .env")
        return

    if not CHANNEL_ID:
        print("❌ CHANNEL_ID non trovato nel file .env")
        return

    print("="*60)
    print("INGESTORE PAGAMENTI - Componente 1")
    print("="*60)
    print(f"Canale: {CHANNEL_ID}")
    print(f"Database: {DB_PATH}")
    print("="*60 + "\n")

    # Carica whitelist
    valid_senders = load_whitelist(WHITELIST_PATH)
    print()

    # Connessione al database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Inizializza Telethon client
    client = TelegramClient(str(SESSION_NAME), API_ID, API_HASH)

    # Start con callback per autenticazione interattiva
    print("🔐 Autenticazione Telegram in corso...")
    print(f"    Numero di telefono: {PHONE_NUMBER}\n")

    await client.start(
        phone=PHONE_NUMBER,
        code_callback=lambda: VERIFICATION_CODE if VERIFICATION_CODE else input('Please enter the code you received: '),
        password=lambda: TELEGRAM_PASSWORD if TELEGRAM_PASSWORD else input('Please enter your password: ')
    )
    print("✅ Client Telegram connesso\n")

    # Recupera messaggi
    messages = await fetch_channel_history(client, CHANNEL_ID, limit=100)

    if not messages:
        print("\n⚠️  Nessun messaggio disponibile.")
        await client.disconnect()
        conn.close()
        return

    # Processa messaggi
    inserted_count = 0
    skipped_count = 0
    error_count = 0
    filtered_count = 0

    print("\n📝 Processamento messaggi...\n")

    for msg in messages:
        # Parsing del messaggio
        payment_data = parse_payment_message(msg.text, msg.date)

        if not payment_data:
            error_count += 1
            continue

        # Filtra mittenti non validi (se whitelist è attiva)
        if valid_senders is not None and payment_data['nome_pagante'] not in valid_senders:
            filtered_count += 1
            print(f"🚫 Filtrato: {payment_data['nome_pagante']} - {payment_data['somma']}₽ (non è studente)")
            continue

        # Inserimento nel database
        record_id = insert_payment(cursor, payment_data, msg.id)

        if record_id:
            inserted_count += 1
            print(f"✅ Inserito: {payment_data['nome_pagante']} - {payment_data['somma']}₽ - {payment_data['giorno']} {payment_data['ora']}")
        else:
            skipped_count += 1

    # Commit delle modifiche
    conn.commit()
    conn.close()

    # Disconnetti client
    await client.disconnect()

    # Riepilogo
    print("\n" + "="*60)
    print("RIEPILOGO")
    print("="*60)
    print(f"Messaggi trovati: {len(messages)}")
    print(f"Pagamenti inseriti: {inserted_count}")
    print(f"Già esistenti (saltati): {skipped_count}")
    print(f"Filtrati (non studenti): {filtered_count}")
    print(f"Errori di parsing: {error_count}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
