#!/usr/bin/env python
"""
Script per aggiornare Google Calendar:
1. Normalizza nomi studenti negli eventi
2. Aggiunge nota "PAGATO" alle lezioni completamente pagate
3. Cambia colore a blu (colorId=9) per lezioni pagate
"""
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configurazione
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

DB_PATH = Path(__file__).parent / "pagamenti.db"
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Color IDs Google Calendar:
# 1 = Lavender, 2 = Sage, 3 = Grape, 4 = Flamingo, 5 = Banana
# 6 = Tangerine, 7 = Peacock, 8 = Graphite, 9 = Blueberry (BLU), 10 = Basil, 11 = Tomato
PAID_COLOR = '9'  # Blueberry (blu)


def get_calendar_service():
    """Ottiene il servizio Google Calendar autenticato con Service Account."""
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ File Service Account non trovato: {SERVICE_ACCOUNT_FILE}")
        return None

    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)
    return service


def get_paid_lessons():
    """
    Recupera lezioni completamente pagate dal database.

    Returns:
        Dict[str, dict]: nextcloud_event_id -> info lezione
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            l.nextcloud_event_id,
            l.nome_studente,
            l.giorno,
            l.ora,
            l.costo,
            COALESCE(SUM(pl.quota_usata), 0) as quota_pagata
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.nextcloud_event_id IS NOT NULL
            AND l.gratis = 0
        GROUP BY l.id_lezione
        HAVING quota_pagata >= l.costo
    ''')

    paid_lessons = {}
    for row in cursor.fetchall():
        paid_lessons[row['nextcloud_event_id']] = {
            'nome_studente': row['nome_studente'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'costo': row['costo'],
            'quota_pagata': row['quota_pagata']
        }

    conn.close()
    return paid_lessons


def get_all_lessons():
    """
    Recupera tutte le lezioni dal database.

    Returns:
        Dict[str, dict]: nextcloud_event_id -> info lezione
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            l.nextcloud_event_id,
            l.nome_studente,
            l.giorno,
            l.ora
        FROM lezioni l
        WHERE l.nextcloud_event_id IS NOT NULL
    ''')

    all_lessons = {}
    for row in cursor.fetchall():
        all_lessons[row['nextcloud_event_id']] = {
            'nome_studente': row['nome_studente'],
            'giorno': row['giorno'],
            'ora': row['ora']
        }

    conn.close()
    return all_lessons


def update_event(service, event_id, updates):
    """
    Aggiorna un evento su Google Calendar.

    Args:
        service: Google Calendar service
        event_id: ID dell'evento
        updates: Dict con campi da aggiornare

    Returns:
        bool: True se successo
    """
    try:
        # Recupera evento esistente
        event = service.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()

        # Applica aggiornamenti
        for key, value in updates.items():
            event[key] = value

        # Aggiorna su Google Calendar
        updated_event = service.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event
        ).execute()

        return True

    except Exception as e:
        print(f"    ❌ Errore aggiornamento evento {event_id}: {e}")
        return False


def main():
    """Funzione principale."""
    print("=" * 70)
    print("AGGIORNAMENTO GOOGLE CALENDAR - LEZIONI PAGATE")
    print("=" * 70)
    print()

    if not CALENDAR_ID:
        print("❌ CALENDAR_ID non trovato nel file .env")
        return

    # Autentica con Google Calendar
    print("🔐 Autenticazione Google Calendar...")
    service = get_calendar_service()
    if not service:
        print("❌ Autenticazione fallita")
        return
    print("✅ Autenticato\n")

    # Recupera lezioni dal database
    print("📊 Recupero lezioni dal database...")
    all_lessons = get_all_lessons()
    paid_lessons = get_paid_lessons()
    print(f"  Lezioni totali: {len(all_lessons)}")
    print(f"  Lezioni pagate: {len(paid_lessons)}")
    print()

    if not paid_lessons:
        print("✅ Nessuna lezione da aggiornare!")
        return

    # Info operazioni
    print("⚠️  Operazioni da eseguire:")
    print(f"  1. Normalizzare nomi studenti in {len(all_lessons)} eventi")
    print(f"  2. Aggiungere nota 'PAGATO' e colore blu a {len(paid_lessons)} lezioni pagate")
    print()
    print("🔄 Aggiornamento in corso...\n")

    # Step 1: Normalizza tutti i nomi
    print("📝 Step 1: Normalizzazione nomi studenti...")
    normalized_count = 0
    for event_id, lesson in all_lessons.items():
        current_name = lesson['nome_studente']

        try:
            # Recupera evento da Google Calendar
            event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
            event_summary = event.get('summary', '')

            # Se il nome è diverso, aggiorna
            if event_summary != current_name:
                updates = {'summary': current_name}
                if update_event(service, event_id, updates):
                    print(f"  ✅ '{event_summary}' → '{current_name}'")
                    normalized_count += 1

        except Exception as e:
            print(f"  ⚠️  Evento {event_id} non trovato o errore: {e}")

    print(f"\n  Totale nomi normalizzati: {normalized_count}\n")

    # Step 2: Marca lezioni pagate
    print("💰 Step 2: Aggiornamento lezioni pagate...")
    paid_count = 0
    for event_id, lesson in paid_lessons.items():
        try:
            # Recupera evento
            event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()

            current_description = event.get('description', '')
            current_color = event.get('colorId', '')

            # Prepara aggiornamenti
            updates = {}
            changed = []

            # Aggiungi "PAGATO" se non presente
            if 'PAGATO' not in current_description:
                new_description = f"PAGATO\n{current_description}" if current_description else "PAGATO"
                updates['description'] = new_description
                changed.append("nota")

            # Cambia colore a blu se non è già blu
            if current_color != PAID_COLOR:
                updates['colorId'] = PAID_COLOR
                changed.append("colore")

            # Applica aggiornamenti se necessario
            if updates:
                if update_event(service, event_id, updates):
                    print(f"  ✅ {lesson['nome_studente']} - {lesson['giorno']} {lesson['ora']}: {', '.join(changed)}")
                    paid_count += 1
            else:
                print(f"  ⏭️  {lesson['nome_studente']} - {lesson['giorno']} {lesson['ora']}: già aggiornato")

        except Exception as e:
            print(f"  ⚠️  Evento {event_id} non trovato o errore: {e}")

    print(f"\n  Totale lezioni pagate aggiornate: {paid_count}\n")

    # Riepilogo finale
    print("=" * 70)
    print("✅ AGGIORNAMENTO COMPLETATO")
    print("=" * 70)
    print(f"Nomi normalizzati: {normalized_count}")
    print(f"Lezioni pagate marcate: {paid_count}")
    print("=" * 70)


if __name__ == "__main__":
    main()
