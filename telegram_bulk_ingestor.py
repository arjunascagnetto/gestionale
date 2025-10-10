#!/usr/bin/env python
"""
Scaricamento COMPLETO dei pagamenti da Telegram
Scarica TUTTI i messaggi dal canale Telegram dal 1 agosto a oggi (nessun limite)
e popola il database pagamenti.

Differenze rispetto a telegram_ingestor.py:
- Rimuove il limite di 100 messaggi
- Supporta range di date personalizzato
- Ottimizzato per import storico completo
"""
import os
import re
import sqlite3
import csv
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from tqdm import tqdm
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import asyncio
import time

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

# Range di date per il recupero (1 agosto 2025 - oggi)
START_DATE = datetime(2025, 8, 1, tzinfo=timezone.utc)  # 1 agosto 2025 (UTC aware)
END_DATE = datetime.now(timezone.utc)  # Oggi (UTC aware)

# Rate limiting configuration
BATCH_SIZE = 100  # Scarica 100 messaggi alla volta
DELAY_BETWEEN_BATCHES = 3  # Pausa 3 secondi tra batch (max 20 req/sec = safe con 3s ogni 100 msg)

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


async def fetch_all_channel_messages(client, channel_id, start_date, end_date):
    """
    Recupera TUTTI i messaggi da un canale in un range di date con rate limiting.

    Gestisce:
    - Paginazione automatica (scarica a batch di BATCH_SIZE)
    - Rate limiting (delay tra batch)
    - FloodWait errors di Telegram

    Args:
        client: TelegramClient instance
        channel_id: ID del canale
        start_date: Data inizio (datetime)
        end_date: Data fine (datetime)

    Returns:
        Lista di messaggi
    """
    print(f"📥 Recupero TUTTI i messaggi dal canale {channel_id}")
    print(f"   Range: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"   Rate limiting: {BATCH_SIZE} msg/batch, {DELAY_BETWEEN_BATCHES}s delay\n")

    try:
        messages = []
        message_count = 0
        batch_count = 0
        offset_id = 0  # Inizia dall'ultimo messaggio

        while True:
            batch_count += 1
            batch_start = time.time()

            print(f"   📦 Batch #{batch_count}: scaricamento fino a {BATCH_SIZE} messaggi...")

            try:
                # Scarica un batch di messaggi
                batch_messages = []
                async for message in client.iter_messages(
                    channel_id,
                    limit=BATCH_SIZE,  # Limita a BATCH_SIZE per batch
                    offset_id=offset_id,  # Continua da dove ci siamo fermati
                    reverse=False  # Dal più recente al più vecchio
                ):
                    # Verifica range di date
                    if message.date < start_date:
                        # Troppo vecchio, fermiamo tutto
                        print(f"   ⏹️  Raggiunta data minima ({start_date.strftime('%Y-%m-%d')}), stop.")
                        batch_messages = []  # Svuota batch, usciamo
                        break

                    if message.date > end_date:
                        # Troppo recente, salta ma continua
                        continue

                    if message.text:
                        batch_messages.append(message)
                        offset_id = message.id  # Aggiorna offset per prossimo batch

                # Se batch vuoto, abbiamo finito
                if not batch_messages:
                    print(f"   ✅ Nessun altro messaggio da scaricare.")
                    break

                # Aggiungi batch ai messaggi totali
                messages.extend(batch_messages)
                message_count += len(batch_messages)

                print(f"   ✅ Batch #{batch_count}: {len(batch_messages)} messaggi (totale: {message_count})")

                # Se il batch è più piccolo di BATCH_SIZE, abbiamo finito
                if len(batch_messages) < BATCH_SIZE:
                    print(f"   ✅ Ultimo batch ricevuto (parziale), scaricamento completo.")
                    break

                # Rate limiting: pausa tra batch
                batch_duration = time.time() - batch_start
                if batch_duration < DELAY_BETWEEN_BATCHES:
                    sleep_time = DELAY_BETWEEN_BATCHES - batch_duration
                    print(f"   ⏳ Pausa {sleep_time:.1f}s (rate limiting)...")
                    await asyncio.sleep(sleep_time)

            except FloodWaitError as e:
                # Telegram ci chiede di aspettare
                wait_time = e.seconds
                print(f"   ⚠️  FloodWait: attendo {wait_time}s come richiesto da Telegram...")
                await asyncio.sleep(wait_time)
                continue  # Riprova questo batch

            except Exception as e:
                print(f"   ❌ Errore nel batch #{batch_count}: {e}")
                # Continua con il prossimo batch invece di fallire completamente
                continue

        print(f"\n✅ Scaricamento completato: {len(messages)} messaggi in {batch_count} batch")
        return messages

    except Exception as e:
        print(f"❌ Errore fatale nel recuperare messaggi: {e}")
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
    print("SCARICAMENTO COMPLETO PAGAMENTI DA TELEGRAM")
    print("="*60)
    print(f"Canale: {CHANNEL_ID}")
    print(f"Database: {DB_PATH}")
    print(f"Range date: {START_DATE.strftime('%d/%m/%Y')} → {END_DATE.strftime('%d/%m/%Y')}")
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

    # Recupera TUTTI i messaggi nel range di date
    messages = await fetch_all_channel_messages(client, CHANNEL_ID, START_DATE, END_DATE)

    if not messages:
        print("\n⚠️  Nessun messaggio disponibile nel range di date specificato.")
        await client.disconnect()
        conn.close()
        return

    # Processa messaggi
    inserted_count = 0
    skipped_count = 0
    error_count = 0
    filtered_count = 0

    print("\n📝 Processamento messaggi...\n")

    # Progress bar con tqdm
    pbar = tqdm(messages, desc="📝 Elaborazione DB", unit=" msg", ncols=100)

    for msg in pbar:
        # Parsing del messaggio
        payment_data = parse_payment_message(msg.text, msg.date)

        if not payment_data:
            error_count += 1
            # Aggiorna descrizione progress bar
            pbar.set_postfix({
                'Inseriti': inserted_count,
                'Filtrati': filtered_count,
                'Duplicati': skipped_count,
                'Errori': error_count
            }, refresh=True)
            continue

        # Filtra mittenti non validi (se whitelist è attiva)
        if valid_senders is not None and payment_data['nome_pagante'] not in valid_senders:
            filtered_count += 1
            # Aggiorna descrizione progress bar
            pbar.set_postfix({
                'Inseriti': inserted_count,
                'Filtrati': filtered_count,
                'Duplicati': skipped_count,
                'Errori': error_count
            }, refresh=True)
            continue

        # Inserimento nel database
        record_id = insert_payment(cursor, payment_data, msg.id)

        if record_id:
            inserted_count += 1
        else:
            skipped_count += 1

        # Aggiorna descrizione progress bar
        pbar.set_postfix({
            'Inseriti': inserted_count,
            'Filtrati': filtered_count,
            'Duplicati': skipped_count,
            'Errori': error_count
        }, refresh=True)

    pbar.close()
    print()  # Newline dopo progress bar

    # Commit delle modifiche
    conn.commit()

    # Verifica totale nel database
    cursor.execute("SELECT COUNT(*) FROM pagamenti")
    total_in_db = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(somma) FROM pagamenti WHERE valuta='RUB'")
    total_amount = cursor.fetchone()[0] or 0

    conn.close()

    # Disconnetti client
    await client.disconnect()

    # Riepilogo
    print("\n" + "="*60)
    print("RIEPILOGO SCARICAMENTO COMPLETO")
    print("="*60)
    print(f"Range date: {START_DATE.strftime('%d/%m/%Y')} → {END_DATE.strftime('%d/%m/%Y')}")
    print(f"Messaggi trovati: {len(messages)}")
    print(f"Pagamenti inseriti: {inserted_count}")
    print(f"Già esistenti (saltati): {skipped_count}")
    print(f"Filtrati (non studenti): {filtered_count}")
    print(f"Errori di parsing: {error_count}")
    print("-"*60)
    print(f"TOTALE nel database: {total_in_db} pagamenti")
    print(f"TOTALE importo: {total_amount:,.2f} RUB")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
