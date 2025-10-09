#!/usr/bin/env python
"""
Componente 3: Risolutore di Associazioni
Gestisce l'associazione tra pagamenti e studenti tramite bot Telegram.
"""
import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, CommandHandler, filters, ContextTypes
import asyncio

from utils.name_matcher import get_match_with_confidence

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/arjuna/nextcloud/association_resolver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Carica variabili d'ambiente
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Configurazione
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
DB_PATH = Path(__file__).parent / "pagamenti.db"
GCAL_SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')
GCAL_CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Soglia per matching automatico
HIGH_CONFIDENCE_THRESHOLD = 95

# Storage temporaneo per le conversazioni (in produzione usare Redis)
pending_associations = {}


def get_students_from_calendar():
    """
    Recupera lista studenti unici dal Google Calendar.

    Returns:
        Set di nomi studenti
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(GCAL_SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)

    # Prendi eventi degli ultimi 60 giorni
    now = datetime.utcnow()
    time_min = (now - timedelta(days=60)).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId=GCAL_CALENDAR_ID,
            timeMin=time_min,
            maxResults=200,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Estrai nomi unici (pulendo da varianti)
        studenti = set()
        for event in events:
            summary = event.get('summary', '').strip()
            if summary and not summary.lower().startswith('prova'):
                # Pulisci nomi come "YanaVasilisa" → "Yana Vasilisa"
                # e rimuovi numeri/test
                clean_name = summary.replace('dmitry1', 'dmitry')
                studenti.add(clean_name)

        return sorted(studenti)

    except Exception as e:
        logger.error(f"❌ Errore recupero studenti da calendario: {e}")
        return []


def get_lessons_by_date_range(payment_date):
    """
    Recupera lezioni dal calendario in un range di ±3 giorni dalla data del pagamento.

    Args:
        payment_date: Data pagamento (string formato YYYY-MM-DD)

    Returns:
        Lista di dict con: nome_studente, data_lezione
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(GCAL_SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)

    # Parse payment date
    payment_dt = datetime.strptime(payment_date, '%Y-%m-%d')

    # Range ±3 giorni
    time_min = (payment_dt - timedelta(days=3)).isoformat() + 'Z'
    time_max = (payment_dt + timedelta(days=3)).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId=GCAL_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        lessons = []
        for event in events:
            summary = event.get('summary', '').strip()
            start = event['start'].get('dateTime', event['start'].get('date'))

            if summary and not summary.lower().startswith('prova'):
                # Parse date
                if 'T' in start:
                    event_date = datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                else:
                    event_date = start

                lessons.append({
                    'nome_studente': summary.replace('dmitry1', 'dmitry'),
                    'data_lezione': event_date
                })

        return lessons

    except Exception as e:
        logger.error(f"❌ Errore recupero lezioni per data {payment_date}: {e}")
        return []


def sync_lessons_from_calendar(days_back=60):
    """
    Sincronizza le lezioni da Google Calendar nel database.
    IMPORTANTE: Legge SOLO lezioni dal passato fino a OGGI (incluso).
    NON legge mai lezioni future.

    Args:
        days_back: Giorni nel passato da sincronizzare (default 60)

    Returns:
        Numero di lezioni sincronizzate
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(GCAL_SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)

    # Range di date: da days_back fa fino a OGGI (fine giornata)
    now = datetime.now()
    time_min = (now - timedelta(days=days_back)).isoformat() + 'Z'
    time_max = now.replace(hour=23, minute=59, second=59).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId=GCAL_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        synced = 0
        for event in events:
            event_id = event['id']
            summary = event.get('summary', '').strip()
            start = event['start'].get('dateTime', event['start'].get('date'))

            # Salta eventi "prova"
            if not summary or summary.lower().startswith('prova'):
                continue

            # Parse date e time
            if 'T' in start:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                giorno = dt.strftime('%Y-%m-%d')
                ora = dt.strftime('%H:%M:%S')
            else:
                giorno = start
                ora = '00:00:00'  # Default per eventi all-day

            # Normalizza nome studente
            nome_studente = summary.replace('dmitry1', 'dmitry').strip()

            # Insert or update
            try:
                cursor.execute('''
                    INSERT INTO lezioni (nextcloud_event_id, nome_studente, giorno, ora, stato)
                    VALUES (?, ?, ?, ?, 'prevista')
                    ON CONFLICT(nextcloud_event_id) DO UPDATE SET
                        nome_studente = excluded.nome_studente,
                        giorno = excluded.giorno,
                        ora = excluded.ora
                ''', (event_id, nome_studente, giorno, ora))
                synced += 1
            except sqlite3.IntegrityError as e:
                logger.warning(f"Errore inserimento lezione {event_id}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"✅ Sincronizzate {synced} lezioni da Google Calendar")
        return synced

    except Exception as e:
        logger.error(f"❌ Errore sincronizzazione lezioni: {e}")
        return 0


def get_unassociated_payments(include_skipped=False):
    """
    Recupera pagamenti che non sono completamente utilizzati.
    Un pagamento è "non associato" se la somma di quota_usata in pagamenti_lezioni < somma totale.

    Args:
        include_skipped: Se True, include anche i pagamenti skipped

    Returns:
        Lista di dict con dati pagamento e residuo disponibile
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Pagamenti con residuo disponibile (somma totale - quota già usata)
    if include_skipped:
        # Include anche i pagamenti skipped
        cursor.execute('''
            SELECT
                p.id_pagamento,
                p.nome_pagante,
                p.giorno,
                p.ora,
                p.somma,
                p.valuta,
                p.skipped,
                COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
                p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
            FROM pagamenti p
            LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
            WHERE p.stato = 'sospeso'
            GROUP BY p.id_pagamento
            HAVING residuo > 0
            ORDER BY p.giorno DESC, p.ora DESC
            LIMIT 10
        ''')
    else:
        # Escludi i pagamenti skipped
        cursor.execute('''
            SELECT
                p.id_pagamento,
                p.nome_pagante,
                p.giorno,
                p.ora,
                p.somma,
                p.valuta,
                p.skipped,
                COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
                p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
            FROM pagamenti p
            LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
            WHERE p.stato = 'sospeso' AND (p.skipped IS NULL OR p.skipped = 0)
            GROUP BY p.id_pagamento
            HAVING residuo > 0
            ORDER BY p.giorno DESC, p.ora DESC
            LIMIT 10
        ''')

    payments = []
    for row in cursor.fetchall():
        payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'skipped': row['skipped'] if row['skipped'] is not None else 0,
            'quota_utilizzata': row['quota_utilizzata'],
            'residuo': row['residuo']
        })

    conn.close()
    return payments


def get_skipped_payments():
    """
    Recupera solo i pagamenti skipped con residuo disponibile.

    Returns:
        Lista di dict con dati pagamento e residuo
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            p.id_pagamento,
            p.nome_pagante,
            p.giorno,
            p.ora,
            p.somma,
            p.valuta,
            COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
            p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
        FROM pagamenti p
        LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
        WHERE p.stato = 'sospeso' AND p.skipped = 1
        GROUP BY p.id_pagamento
        HAVING residuo > 0
        ORDER BY p.giorno DESC, p.ora DESC
    ''')

    payments = []
    for row in cursor.fetchall():
        payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'skipped': 1,
            'quota_utilizzata': row['quota_utilizzata'],
            'residuo': row['residuo']
        })

    conn.close()
    return payments


def save_association(nome_pagante, nome_studente, auto_matched=False, confidence_score=0):
    """
    Salva un'associazione nel database.

    Args:
        nome_pagante: Nome del pagante
        nome_studente: Nome dello studente
        auto_matched: Se è stato fatto matching automatico
        confidence_score: Score di confidenza del match
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO associazioni (nome_studente, nome_pagante, note, valid_from)
            VALUES (?, ?, ?, CURRENT_DATE)
        ''', (
            nome_studente,
            nome_pagante,
            f"Auto-matched: {auto_matched}, Score: {confidence_score:.1f}%" if auto_matched else "Manuale"
        ))

        conn.commit()
        logger.info(f"✅ Associazione salvata: {nome_pagante} → {nome_studente} (auto: {auto_matched}, score: {confidence_score:.1f}%)")

    except sqlite3.IntegrityError:
        logger.warning(f"⚠️  Associazione già esistente: {nome_pagante} → {nome_studente}")

    finally:
        conn.close()


def update_payment_status(payment_id, new_status='associato'):
    """
    Aggiorna lo stato di un pagamento.

    Args:
        payment_id: ID del pagamento
        new_status: Nuovo stato
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE pagamenti
        SET stato = ?
        WHERE id_pagamento = ?
    ''', (new_status, payment_id))

    conn.commit()
    conn.close()


def mark_payment_as_skipped(payment_id):
    """
    Marca un pagamento come skipped.

    Args:
        payment_id: ID del pagamento
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE pagamenti
        SET skipped = 1
        WHERE id_pagamento = ?
    ''', (payment_id,))

    conn.commit()
    conn.close()
    logger.info(f"Pagamento {payment_id} marcato come skipped")


async def process_payment(payment, bot):
    """
    Processa un singolo pagamento: mostra lezioni vicine e chiede associazione.
    Supporta abbonamenti e pagamenti parziali.

    Args:
        payment: Dict con dati pagamento (include 'residuo')
        bot: Bot Telegram
    """
    nome_pagante = payment['nome_pagante']
    payment_date = payment['giorno']
    residuo = payment['residuo']

    logger.info(f"Processamento pagamento: {nome_pagante} - {residuo}/{payment['somma']}{payment['valuta']} disponibile del {payment_date}")

    # Identifica tipo pagamento (abbonamento vs singolo)
    abbonamento_type = None
    num_lezioni = 1
    if residuo == 6600:
        abbonamento_type = "3 lezioni"
        num_lezioni = 3
    elif residuo == 10500:
        abbonamento_type = "5 lezioni"
        num_lezioni = 5
    elif residuo == 20000:
        abbonamento_type = "10 lezioni"
        num_lezioni = 10

    # Controlla se esiste già associazione pagante→studente
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT nome_studente FROM associazioni WHERE nome_pagante = ?', (nome_pagante,))
    existing = cursor.fetchone()

    nome_studente = None
    if existing:
        nome_studente = existing[0]
        logger.info(f"✅ Associazione esistente trovata: {nome_pagante} → {nome_studente}")

    # Recupera lezioni vicine dal DB (±3 giorni)
    cursor.execute('''
        SELECT id_lezione, nome_studente, giorno, ora
        FROM lezioni
        WHERE giorno BETWEEN date(?, '-3 days') AND date(?, '+3 days')
        ORDER BY giorno ASC, ora ASC
    ''', (payment_date, payment_date))

    lessons_in_range = []
    for row in cursor.fetchall():
        lessons_in_range.append({
            'id': row[0],
            'nome_studente': row[1],
            'giorno': row[2],
            'ora': row[3]
        })

    conn.close()

    if not lessons_in_range:
        logger.warning(f"Nessuna lezione trovata nel range ±3 giorni per {payment_date}")

        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"⚠️ <b>Nessuna lezione vicina</b>\n\n"
                 f"💰 {residuo}{payment['valuta']} da {nome_pagante}\n"
                 f"📅 {payment_date}\n\n"
                 f"Non ci sono lezioni nel range ±3 giorni.\n"
                 f"Salta questo pagamento per ora.",
            parse_mode='HTML'
        )
        return

    # Filtra lezioni per studente se c'è associazione
    if nome_studente:
        lessons_in_range = [l for l in lessons_in_range if l['nome_studente'] == nome_studente]

    logger.info(f"Trovate {len(lessons_in_range)} lezioni nel range ±3 giorni")

    # Prepara messaggio con lezioni
    msg = f"💰 <b>Pagamento</b>: {residuo}{payment['valuta']}"
    if payment['quota_utilizzata'] > 0:
        msg += f" (di {payment['somma']} totali, {payment['quota_utilizzata']} già usati)"
    msg += f"\n👤 Da: <b>{nome_pagante}</b>"
    if nome_studente:
        msg += f" → <b>{nome_studente}</b>"
    msg += f"\n📅 Data: {payment['giorno']} {payment['ora']}\n"

    if abbonamento_type:
        msg += f"\n🎫 <b>Abbonamento {abbonamento_type}</b>\n"
        msg += f"Seleziona {num_lezioni} lezioni da associare:\n\n"
    else:
        msg += f"\n📚 <b>Lezioni vicine (±3 giorni):</b>\n"

    keyboard = []
    for i, lesson in enumerate(lessons_in_range, 1):
        msg += f"{i}️⃣ {lesson['nome_studente']} - {lesson['giorno']} {lesson['ora']}\n"
        keyboard.append([
            InlineKeyboardButton(
                f"{i}. {lesson['nome_studente']} ({lesson['giorno']})",
                callback_data=f"lesson_{payment['id']}_{lesson['id']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("⏭️ Salta", callback_data=f"skip_{payment['id']}")])

    if abbonamento_type:
        msg += f"\n💡 Clicca su una lezione per associarla (puoi selezionarne {num_lezioni})"
    else:
        msg += "\nQuale lezione corrisponde a questo pagamento?"

    # Store payment data for callback
    payment_key = f"payment_{payment['id']}"
    pending_associations[payment_key] = {
        'payment': payment,
        'lessons': lessons_in_range,
        'abbonamento_type': abbonamento_type,
        'num_lezioni': num_lezioni,
        'selected_lessons': []  # Per abbonamenti multipli
    }

    reply_markup = InlineKeyboardMarkup(keyboard)

    await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=msg,
        parse_mode='HTML',
        reply_markup=reply_markup
    )


async def send_options(payment, match_result, bot):
    """
    Invia messaggio con opzioni multiple di associazione.

    Args:
        payment: Dict con dati pagamento
        match_result: Risultato del matching
        bot: Bot Telegram
    """
    msg = (
        f"❓ <b>SELEZIONA STUDENTE</b>\n\n"
        f"💰 Pagamento: {payment['somma']}{payment['valuta']}\n"
        f"👤 Da: <b>{payment['nome_pagante']}</b>\n\n"
        f"Candidati trovati:\n"
    )

    # Prendi top 3 match
    top_matches = match_result['all_matches'][:3]

    keyboard = []
    for i, (studente, score) in enumerate(top_matches, 1):
        msg += f"{i}️⃣ {studente} ({score:.0f}%)\n"
        keyboard.append([
            InlineKeyboardButton(
                f"{i}. {studente}",
                callback_data=f"select_{payment['id']}_{studente}"
            )
        ])

    # Aggiungi opzioni extra
    keyboard.append([
        InlineKeyboardButton("✏️ Altro nome", callback_data=f"manual_{payment['id']}"),
        InlineKeyboardButton("⏭️ Salta", callback_data=f"skip_{payment['id']}")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=msg,
        parse_mode='HTML',
        reply_markup=reply_markup
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gestisce i callback dai bottoni inline.
    Supporta selezione multipla per abbonamenti e quota_usata per lezioni condivise.
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split('_')
    action = parts[0]
    payment_id = int(parts[1])

    payment_key = f"payment_{payment_id}"

    if payment_key not in pending_associations:
        await query.edit_message_text("❌ Sessione scaduta. Riavvia lo script.")
        return

    payment_data = pending_associations[payment_key]
    payment = payment_data['payment']
    abbonamento_type = payment_data.get('abbonamento_type')
    num_lezioni = payment_data.get('num_lezioni', 1)
    selected_lessons = payment_data.get('selected_lessons', [])

    if action == "lesson":
        # Selezione lezione
        lezione_id = int(parts[2])

        # Trova la lezione selezionata
        lesson = next((l for l in payment_data['lessons'] if l['id'] == lezione_id), None)
        if not lesson:
            await query.answer("❌ Lezione non trovata", show_alert=True)
            return

        nome_studente = lesson['nome_studente']

        # Salva o aggiorna associazione pagante→studente
        save_association(
            payment['nome_pagante'],
            nome_studente,
            auto_matched=False,
            confidence_score=0
        )

        # Gestione abbonamenti (selezione multipla)
        if abbonamento_type and num_lezioni > 1:
            # Aggiungi lezione alla lista
            if lezione_id not in selected_lessons:
                selected_lessons.append(lezione_id)
                payment_data['selected_lessons'] = selected_lessons

            # Controlla se abbiamo selezionato abbastanza lezioni
            if len(selected_lessons) < num_lezioni:
                await query.answer(f"✅ Lezione aggiunta ({len(selected_lessons)}/{num_lezioni})")
                # Non fare nulla, aspetta altre selezioni
                return
            else:
                # Abbonamento completo, salva tutte le associazioni
                quota_per_lezione = payment['residuo'] / num_lezioni

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                for lid in selected_lessons:
                    cursor.execute('''
                        INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata)
                        VALUES (?, ?, ?)
                    ''', (payment_id, lid, quota_per_lezione))

                conn.commit()
                conn.close()

                logger.info(f"✅ Abbonamento {abbonamento_type} associato: {num_lezioni} lezioni per {payment['nome_pagante']}")

                await query.edit_message_text(
                    f"✅ <b>Abbonamento {abbonamento_type} salvato!</b>\n\n"
                    f"💰 Pagamento: {payment['somma']}{payment['valuta']}\n"
                    f"👤 Pagante: {payment['nome_pagante']} → <b>{nome_studente}</b>\n"
                    f"📚 {num_lezioni} lezioni associate ({quota_per_lezione:.0f} RUB ciascuna)\n\n"
                    f"Questa associazione verrà riutilizzata per i futuri pagamenti.",
                    parse_mode='HTML'
                )
        else:
            # Pagamento singolo o ultima lezione abbonamento
            # Chiedi quota_usata se non è un abbonamento
            quota_usata = payment['residuo']  # Default: usa tutto il residuo

            # Salva in pagamenti_lezioni
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata)
                VALUES (?, ?, ?)
            ''', (payment_id, lezione_id, quota_usata))

            conn.commit()
            conn.close()

            logger.info(f"✅ Pagamento-lezione associato: {payment['nome_pagante']} → {nome_studente}, quota: {quota_usata}")

            await query.edit_message_text(
                f"✅ <b>Associazione salvata!</b>\n\n"
                f"💰 Pagamento: {quota_usata}{payment['valuta']} (di {payment['somma']} totali)\n"
                f"👤 Pagante: {payment['nome_pagante']} → <b>{nome_studente}</b>\n"
                f"📚 Lezione: {lesson['giorno']} {lesson['ora']}\n\n"
                f"Residuo: {payment['residuo'] - quota_usata}{payment['valuta']}",
                parse_mode='HTML'
            )

        del pending_associations[payment_key]

        # Processa automaticamente il prossimo pagamento
        try:
            payments = get_unassociated_payments()

            if payments:
                next_payment = payments[0]
                logger.info(f"▶️ Auto-processamento prossimo pagamento: ID {next_payment['id']}")

                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📋 Prossimo pagamento ({len(payments)} rimanenti)...",
                    parse_mode='HTML'
                )

                await process_payment(next_payment, context.bot)
            else:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text="🎉 <b>Completato!</b>\n\nTutti i pagamenti sono stati processati.",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Errore auto-processamento prossimo: {e}")

    elif action == "skip":
        # Salta questo pagamento e marcalo come skipped
        mark_payment_as_skipped(payment_id)
        logger.info(f"⏭️ Pagamento saltato e marcato: {payment['nome_pagante']} - {payment['somma']}")

        await query.edit_message_text(
            f"⏭️ <b>Pagamento saltato</b>\n\n"
            f"{payment['nome_pagante']} - {payment['somma']}{payment['valuta']}\n\n"
            f"Marcato come sospeso.\n"
            f"Usa /suspended per riprocessarlo in futuro.",
            parse_mode='HTML'
        )

        del pending_associations[payment_key]

        # Processa automaticamente il prossimo pagamento (escludendo gli skipped)
        try:
            payments = get_unassociated_payments(include_skipped=False)

            if payments:
                next_payment = payments[0]
                logger.info(f"▶️ Auto-processamento prossimo pagamento: ID {next_payment['id']}")

                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📋 Prossimo pagamento ({len(payments)} rimanenti)...",
                    parse_mode='HTML'
                )

                await process_payment(next_payment, context.bot)
            else:
                # Controlla se ci sono skipped
                skipped = get_skipped_payments()
                if skipped:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"✅ <b>Completato!</b>\n\n"
                             f"Tutti i pagamenti processati.\n"
                             f"Hai {len(skipped)} pagamenti sospesi.\n\n"
                             f"Usa /suspended per riprocessarli.",
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text="🎉 <b>Completato!</b>\n\nTutti i pagamenti sono stati associati.",
                        parse_mode='HTML'
                    )
        except Exception as e:
            logger.error(f"Errore auto-processamento prossimo: {e}")

    elif action == "newpay":
        # Gestione nuovi pagamenti notificati dal monitor
        lezione_id = int(parts[2])

        # Recupera dati pagamento e lezione dal DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT nome_pagante, giorno, ora, somma, valuta FROM pagamenti WHERE id_pagamento = ?', (payment_id,))
        pay_row = cursor.fetchone()

        cursor.execute('SELECT nome_studente, giorno, ora FROM lezioni WHERE id_lezione = ?', (lezione_id,))
        les_row = cursor.fetchone()

        if not pay_row or not les_row:
            await query.edit_message_text("❌ Dati non trovati")
            conn.close()
            return

        nome_pagante = pay_row[0]
        nome_studente = les_row[0]
        quota_usata = pay_row[3]  # Usa l'intero importo

        # Salva associazione pagante→studente
        save_association(nome_pagante, nome_studente, auto_matched=False, confidence_score=0)

        # Salva in pagamenti_lezioni
        cursor.execute('''
            INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata)
            VALUES (?, ?, ?)
        ''', (payment_id, lezione_id, quota_usata))

        # Marca come associato
        cursor.execute('UPDATE pagamenti SET stato = ? WHERE id_pagamento = ?', ('associato', payment_id))

        conn.commit()
        conn.close()

        logger.info(f"✅ Nuovo pagamento associato: {nome_pagante} → {nome_studente}, {quota_usata} RUB")

        await query.edit_message_text(
            f"✅ <b>Pagamento associato!</b>\n\n"
            f"💰 {quota_usata} RUB da {nome_pagante}\n"
            f"📚 Lezione: {nome_studente} - {les_row[1]} {les_row[2]}\n\n"
            f"Associazione salvata.",
            parse_mode='HTML'
        )

    elif action == "archive":
        # Archivia pagamento per gestione via web
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE pagamenti SET stato = ? WHERE id_pagamento = ?', ('archivio', payment_id))
        cursor.execute('SELECT nome_pagante, somma, valuta FROM pagamenti WHERE id_pagamento = ?', (payment_id,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()

        logger.info(f"📦 Pagamento archiviato: {row[0]} - {row[1]}")

        await query.edit_message_text(
            f"📦 <b>Pagamento archiviato</b>\n\n"
            f"{row[0]} - {row[1]} {row[2]}\n\n"
            f"Gestiscilo tramite interfaccia web.",
            parse_mode='HTML'
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /start."""
    await update.message.reply_text(
        "🤖 <b>Bot Associazioni Pagamenti-Studenti</b>\n\n"
        "Comandi disponibili:\n"
        "• /process - Processa pagamenti non associati\n"
        "• /suspended - Riprocessa pagamenti saltati\n"
        "• /sync - Sincronizza lezioni da Google Calendar\n\n"
        "✨ <b>Funzionalità:</b>\n"
        "• Rilevamento automatico abbonamenti (3/5/10 lezioni)\n"
        "• Supporto pagamenti parziali per lezioni condivise\n"
        "• Associazione pagante→studente riutilizzabile\n"
        "• Calcolo automatico residuo disponibile",
        parse_mode='HTML'
    )


async def process_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /process - processa UN pagamento alla volta (esclusi skipped)."""
    if not update.message:
        return

    # Carica pagamenti non associati (ESCLUSI gli skipped)
    try:
        payments = get_unassociated_payments(include_skipped=False)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore caricamento pagamenti: {e}")
        return

    if not payments:
        # Controlla se ci sono skipped
        skipped = get_skipped_payments()
        if skipped:
            await update.message.reply_text(
                f"✅ Nessun pagamento da processare!\n\n"
                f"Hai {len(skipped)} pagamenti sospesi.\n"
                f"Usa /suspended per riprocessarli.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("✅ Nessun pagamento da processare!")
        return

    # Prendi solo il PRIMO pagamento
    payment = payments[0]

    logger.info(f"📋 Totale pagamenti da processare: {len(payments)}")
    logger.info(f"▶️ Processamento pagamento 1/{len(payments)}: ID {payment['id']}")

    await update.message.reply_text(
        f"📋 <b>Pagamenti da processare: {len(payments)}</b>\n\n"
        f"Invio il primo pagamento...",
        parse_mode='HTML'
    )

    # Processa SOLO il primo pagamento
    try:
        await process_payment(payment, context.bot)
    except Exception as e:
        logger.error(f"❌ Errore processamento pagamento {payment['id']}: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def suspended_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /suspended - processa pagamenti skipped."""
    if not update.message:
        return

    # Carica SOLO i pagamenti skipped
    try:
        payments = get_skipped_payments()
    except Exception as e:
        await update.message.reply_text(f"❌ Errore caricamento pagamenti skipped: {e}")
        return

    if not payments:
        await update.message.reply_text("✅ Nessun pagamento sospeso!")
        return

    # Prendi il primo skipped
    payment = payments[0]

    # Rimuovi flag skipped per permettere riprocessamento
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE pagamenti SET skipped = 0 WHERE id_pagamento = ?', (payment['id'],))
    conn.commit()
    conn.close()

    logger.info(f"📋 Totale pagamenti sospesi: {len(payments)}")
    logger.info(f"▶️ Riprocessamento pagamento sospeso: ID {payment['id']}")

    await update.message.reply_text(
        f"📋 <b>Pagamenti sospesi: {len(payments)}</b>\n\n"
        f"Riprocesso il primo...",
        parse_mode='HTML'
    )

    # Processa il pagamento skipped
    try:
        await process_payment(payment, context.bot)
    except Exception as e:
        logger.error(f"❌ Errore processamento pagamento {payment['id']}: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /sync - sincronizza lezioni da Google Calendar."""
    if not update.message:
        return

    await update.message.reply_text("🔄 Sincronizzazione lezioni da Google Calendar in corso...")

    try:
        synced = sync_lessons_from_calendar(days_back=60)
        await update.message.reply_text(
            f"✅ <b>Sincronizzazione completata!</b>\n\n"
            f"📚 {synced} lezioni sincronizzate dal calendario.\n"
            f"Range: ultimi 60 giorni fino a OGGI (incluso)",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"❌ Errore sincronizzazione lezioni: {e}")
        await update.message.reply_text(f"❌ Errore durante la sincronizzazione: {e}")


def main():
    """Funzione principale."""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN non trovato nel file .env")
        return

    if not ADMIN_CHAT_ID:
        print("❌ ADMIN_CHAT_ID non trovato nel file .env")
        print("   Per trovare il tuo chat ID, invia un messaggio a @userinfobot")
        return

    print("="*60)
    print("RISOLUTORE ASSOCIAZIONI - Bot Telegram")
    print("="*60)
    print(f"Bot Token: {BOT_TOKEN[:20]}...")
    print(f"Admin Chat ID: {ADMIN_CHAT_ID}")
    print("="*60 + "\n")

    # Sincronizza lezioni all'avvio
    print("🔄 Sincronizzazione lezioni da Google Calendar...")
    synced = sync_lessons_from_calendar(days_back=60)
    print(f"✅ {synced} lezioni sincronizzate (ultimi 60 giorni fino a oggi)\n")

    # Crea l'applicazione
    application = Application.builder().token(BOT_TOKEN).build()

    # Aggiungi handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("process", process_command))
    application.add_handler(CommandHandler("suspended", suspended_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Avvia il bot
    print("🤖 Bot avviato! Premi Ctrl+C per terminare.\n")
    print(f"📱 Invia /process al bot per elaborare i pagamenti.")
    print(f"📱 Usa /suspended per riprocessare i pagamenti sospesi.")

    application.run_polling()


if __name__ == "__main__":
    main()
