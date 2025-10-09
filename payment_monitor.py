#!/usr/bin/env python
"""
Payment Monitor - Controlla nuovi pagamenti ogni ora e notifica su Telegram.
Esegue telegram_ingestor.py e notifica solo i nuovi pagamenti con lezioni dello stesso giorno.
"""
import os
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv
from telegram import Bot
import subprocess
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/arjuna/nextcloud/payment_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Carica variabili d'ambiente
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
DB_PATH = Path(__file__).parent / "pagamenti.db"


def get_new_payments():
    """
    Recupera pagamenti inseriti nell'ultima ora che non sono ancora stati notificati.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Pagamenti inseriti nell'ultima ora, non ancora notificati
    cursor.execute('''
        SELECT id_pagamento, nome_pagante, giorno, ora, somma, valuta
        FROM pagamenti
        WHERE created_at >= datetime('now', '-1 hour')
        AND (notificato IS NULL OR notificato = 0)
        ORDER BY giorno DESC, ora DESC
    ''')

    payments = []
    for row in cursor.fetchall():
        payments.append({
            'id': row[0],
            'nome_pagante': row[1],
            'giorno': row[2],
            'ora': row[3],
            'somma': row[4],
            'valuta': row[5]
        })

    conn.close()
    return payments


def get_lessons_same_day(payment_date):
    """
    Recupera lezioni dello stesso giorno del pagamento.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id_lezione, nome_studente, giorno, ora
        FROM lezioni
        WHERE giorno = ?
        ORDER BY ora ASC
    ''', (payment_date,))

    lessons = []
    for row in cursor.fetchall():
        lessons.append({
            'id': row[0],
            'nome_studente': row[1],
            'giorno': row[2],
            'ora': row[3]
        })

    conn.close()
    return lessons


def mark_payment_as_notified(payment_id):
    """Marca un pagamento come notificato."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE pagamenti SET notificato = 1 WHERE id_pagamento = ?', (payment_id,))
    conn.commit()
    conn.close()


def mark_payment_as_archived(payment_id):
    """Marca un pagamento come archiviato (da gestire via web)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE pagamenti SET stato = ? WHERE id_pagamento = ?', ('archivio', payment_id))
    conn.commit()
    conn.close()


async def notify_new_payment(bot, payment):
    """
    Invia notifica Telegram per un nuovo pagamento con lezioni dello stesso giorno.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    payment_date = payment['giorno']
    lessons = get_lessons_same_day(payment_date)

    msg = (
        f"💰 <b>Nuovo pagamento ricevuto!</b>\n\n"
        f"👤 Da: <b>{payment['nome_pagante']}</b>\n"
        f"💵 Importo: {payment['somma']} {payment['valuta']}\n"
        f"📅 Data: {payment['giorno']} {payment['ora']}\n"
    )

    keyboard = []

    if lessons:
        msg += f"\n📚 <b>Lezioni dello stesso giorno ({payment_date}):</b>\n"
        for i, lesson in enumerate(lessons, 1):
            msg += f"{i}. {lesson['nome_studente']} - {lesson['ora']}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"{i}. {lesson['nome_studente']} ({lesson['ora']})",
                    callback_data=f"newpay_{payment['id']}_{lesson['id']}"
                )
            ])
        msg += "\nSeleziona la lezione corrispondente:"
    else:
        msg += f"\n⚠️ Nessuna lezione trovata per il {payment_date}"

    # Aggiungi pulsante "Archivia" (salta)
    keyboard.append([
        InlineKeyboardButton("📦 Archivia (gestisci via web)", callback_data=f"archive_{payment['id']}")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=msg,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

    mark_payment_as_notified(payment['id'])
    logger.info(f"✅ Notificato pagamento {payment['id']}: {payment['nome_pagante']} - {payment['somma']}")


async def check_and_notify():
    """
    Esegue telegram_ingestor, controlla nuovi pagamenti e notifica.
    """
    logger.info("🔄 Avvio controllo nuovi pagamenti...")

    # 1. Esegui telegram_ingestor per importare nuovi messaggi
    try:
        result = subprocess.run(
            ['.cal/bin/python', 'telegram_ingestor.py'],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=60
        )
        logger.info(f"telegram_ingestor output: {result.stdout}")
        if result.stderr:
            logger.warning(f"telegram_ingestor errors: {result.stderr}")
    except Exception as e:
        logger.error(f"Errore esecuzione telegram_ingestor: {e}")
        return

    # 2. Controlla nuovi pagamenti
    new_payments = get_new_payments()

    if not new_payments:
        logger.info("✅ Nessun nuovo pagamento da notificare")
        return

    logger.info(f"📋 Trovati {len(new_payments)} nuovi pagamenti")

    # 3. Invia notifiche
    bot = Bot(token=BOT_TOKEN)

    for payment in new_payments:
        try:
            await notify_new_payment(bot, payment)
        except Exception as e:
            logger.error(f"Errore notifica pagamento {payment['id']}: {e}")


async def run_periodic():
    """Esegue il controllo ogni ora."""
    while True:
        try:
            await check_and_notify()
        except Exception as e:
            logger.error(f"Errore nel ciclo periodico: {e}")

        # Attendi 1 ora
        logger.info("⏳ Prossimo controllo tra 1 ora...")
        await asyncio.sleep(3600)


if __name__ == "__main__":
    logger.info("🚀 Payment Monitor avviato - Controllo ogni ora")
    asyncio.run(run_periodic())
