#!/usr/bin/env python
"""
Script VELOCE per aggiornare Google Calendar in batch:
1. Rinomina titoli con nomi standardizzati
2. Colora di BLU (colorId=9) le lezioni completamente pagate
"""
import os
import sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configurazione
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
DB_PATH = Path(__file__).parent / "pagamenti.db"
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Colori
COLOR_PAID = '9'  # BLU (Blueberry)

# Date per filtrare eventi (1 agosto - oggi)
START_DATE = datetime(2025, 8, 1)
END_DATE = datetime.now()


def get_calendar_service():
    """Crea servizio Google Calendar."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def get_lessons_map(db_path):
    """
    Recupera mappa: event_id -> {nome, is_paid}

    Returns:
        dict: {event_id: {'nome': str, 'is_paid': bool}}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            l.nextcloud_event_id,
            l.nome_studente,
            l.costo,
            COALESCE(SUM(pl.quota_usata), 0) as quota_pagata
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.nextcloud_event_id IS NOT NULL
        GROUP BY l.id_lezione
    ''')

    lessons_map = {}
    for row in cursor.fetchall():
        event_id, nome, costo, quota_pagata = row
        lessons_map[event_id] = {
            'nome': nome,
            'is_paid': (quota_pagata >= costo)
        }

    conn.close()
    return lessons_map


def update_events_batch(service, calendar_id, lessons_map, start_date, end_date):
    """
    Aggiorna eventi in batch.

    Returns:
        dict: Statistiche
    """
    stats = {
        'total': 0,
        'renamed': 0,
        'colored': 0,
        'unchanged': 0,
        'errors': 0
    }

    print(f"\n📥 Recupero eventi da Google Calendar...")
    print(f"   Range: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}\n")

    try:
        # Recupera TUTTI gli eventi in un colpo solo
        time_min = start_date.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        time_max = end_date.replace(hour=23, minute=59, second=59).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=2500
        ).execute()

        events = events_result.get('items', [])
        print(f"✅ Trovati {len(events)} eventi\n")
        print("🔄 Aggiornamento in corso...\n")

        for event in events:
            stats['total'] += 1
            event_id = event['id']

            # Salta se non è nelle nostre lezioni
            if event_id not in lessons_map:
                continue

            lesson = lessons_map[event_id]
            nome_atteso = lesson['nome']
            is_paid = lesson['is_paid']

            # Determina aggiornamenti necessari
            needs_update = False
            current_title = event.get('summary', '')
            current_color = event.get('colorId', None)

            # Titolo
            if current_title != nome_atteso:
                event['summary'] = nome_atteso
                needs_update = True
                stats['renamed'] += 1
                print(f"  ✏️  '{current_title}' → '{nome_atteso}'")

            # Colore (solo se pagato)
            if is_paid and current_color != COLOR_PAID:
                event['colorId'] = COLOR_PAID
                needs_update = True
                stats['colored'] += 1
                print(f"  🔵 Colorato BLU: {nome_atteso}")

            # Applica update se necessario
            if needs_update:
                try:
                    service.events().update(
                        calendarId=calendar_id,
                        eventId=event_id,
                        body=event
                    ).execute()
                except HttpError as e:
                    stats['errors'] += 1
                    print(f"  ❌ Errore {event_id}: {e}")
            else:
                stats['unchanged'] += 1

    except HttpError as error:
        print(f"❌ Errore nell'accesso al calendario: {error}")
        return None

    return stats


def print_stats(stats):
    """Stampa statistiche."""
    print("\n" + "="*60)
    print("RIEPILOGO AGGIORNAMENTO")
    print("="*60)
    print(f"Eventi processati: {stats['total']}")
    print(f"Titoli rinominati: {stats['renamed']}")
    print(f"Eventi colorati BLU: {stats['colored']}")
    print(f"Eventi non modificati: {stats['unchanged']}")
    print(f"Errori: {stats['errors']}")
    print("="*60)


def main():
    """Funzione principale."""
    print("="*60)
    print("AGGIORNAMENTO VELOCE GOOGLE CALENDAR")
    print("="*60)
    print(f"Database: {DB_PATH.name}")
    print(f"Range: {START_DATE.strftime('%d/%m/%Y')} → {END_DATE.strftime('%d/%m/%Y')}")
    print("="*60)

    # Verifica file
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"\n❌ File Service Account non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    if not DB_PATH.exists():
        print(f"\n❌ Database non trovato: {DB_PATH}")
        return

    # Crea service
    print("\n🔐 Autenticazione Google Calendar...")
    service = get_calendar_service()
    print("✅ Autenticato")

    # Carica lezioni dal DB
    print("\n📖 Caricamento lezioni dal database...")
    lessons_map = get_lessons_map(DB_PATH)
    paid_count = sum(1 for l in lessons_map.values() if l['is_paid'])
    print(f"✅ {len(lessons_map)} lezioni caricate")
    print(f"   - Pagate: {paid_count}")
    print(f"   - Non pagate: {len(lessons_map) - paid_count}")

    # Aggiorna eventi
    stats = update_events_batch(service, CALENDAR_ID, lessons_map, START_DATE, END_DATE)

    if stats:
        print_stats(stats)
        print("\n✅ Aggiornamento completato!\n")


if __name__ == "__main__":
    main()
