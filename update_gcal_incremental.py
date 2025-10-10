#!/usr/bin/env python
"""
Script INCREMENTALE per aggiornare Google Calendar.
Aggiorna SOLO le lezioni che hanno cambiato stato di pagamento dall'ultimo aggiornamento.

Strategia:
1. Legge timestamp ultimo aggiornamento da file
2. Trova lezioni modificate dopo quel timestamp (updated_at)
3. Aggiorna solo gli eventi modificati
4. Salva nuovo timestamp
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
TIMESTAMP_FILE = Path(__file__).parent / ".gcal_last_update"
SCOPES = ['https://www.googleapis.com/auth/calendar']

COLOR_PAID = '9'  # BLU (Blueberry)
COLOR_DEFAULT = '1'  # Lavanda (default)


def get_calendar_service():
    """Crea servizio Google Calendar."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def get_last_update_timestamp():
    """Legge timestamp ultimo aggiornamento."""
    if TIMESTAMP_FILE.exists():
        try:
            with open(TIMESTAMP_FILE, 'r') as f:
                timestamp_str = f.read().strip()
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            print(f"⚠️  Errore lettura timestamp: {e}")
            return None
    return None


def save_update_timestamp():
    """Salva timestamp corrente."""
    with open(TIMESTAMP_FILE, 'w') as f:
        f.write(datetime.now().isoformat())


def get_modified_lessons(db_path, since_timestamp):
    """
    Recupera lezioni modificate dopo un certo timestamp.

    Args:
        db_path: Path del database
        since_timestamp: Timestamp da cui recuperare modifiche (None = tutte)

    Returns:
        dict: {event_id: {'nome': str, 'is_paid': bool, 'updated_at': str}}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if since_timestamp:
        # Query per lezioni modificate dopo timestamp
        query = '''
            SELECT
                l.nextcloud_event_id,
                l.nome_studente,
                l.costo,
                l.updated_at,
                COALESCE(SUM(pl.quota_usata), 0) as quota_pagata,
                MAX(COALESCE(l.updated_at, '1970-01-01'), COALESCE(pl.created_at, '1970-01-01')) as last_modified
            FROM lezioni l
            LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
            WHERE l.nextcloud_event_id IS NOT NULL
            GROUP BY l.id_lezione
            HAVING last_modified > ?
        '''
        cursor.execute(query, (since_timestamp.isoformat(),))
        print(f"\n🔍 Ricerca lezioni modificate dopo {since_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        # Prima esecuzione: processa tutte le lezioni
        query = '''
            SELECT
                l.nextcloud_event_id,
                l.nome_studente,
                l.costo,
                l.updated_at,
                COALESCE(SUM(pl.quota_usata), 0) as quota_pagata,
                MAX(COALESCE(l.updated_at, '1970-01-01'), COALESCE(pl.created_at, '1970-01-01')) as last_modified
            FROM lezioni l
            LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
            WHERE l.nextcloud_event_id IS NOT NULL
            GROUP BY l.id_lezione
        '''
        cursor.execute(query)
        print(f"\n🔍 Prima esecuzione: processamento di tutte le lezioni")

    lessons_map = {}
    for row in cursor.fetchall():
        event_id = row[0]
        nome = row[1]
        costo = row[2]
        updated_at = row[3]
        quota_pagata = row[4]
        last_modified = row[5]

        lessons_map[event_id] = {
            'nome': nome,
            'is_paid': (quota_pagata >= costo),
            'updated_at': updated_at,
            'last_modified': last_modified
        }

    conn.close()
    return lessons_map


def update_event_incremental(service, calendar_id, event_id, lesson_data):
    """
    Aggiorna un singolo evento in modo incrementale.

    Returns:
        dict: {'renamed': bool, 'colored': bool, 'unchanged': bool, 'error': str}
    """
    result = {
        'renamed': False,
        'colored': False,
        'unchanged': False,
        'error': None
    }

    try:
        # Recupera evento corrente
        event = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        nome_atteso = lesson_data['nome']
        is_paid = lesson_data['is_paid']

        # Determina aggiornamenti necessari
        needs_update = False
        current_title = event.get('summary', '')
        current_color = event.get('colorId', None)

        # 1. Verifica titolo
        if current_title != nome_atteso:
            event['summary'] = nome_atteso
            needs_update = True
            result['renamed'] = True

        # 2. Verifica colore
        target_color = COLOR_PAID if is_paid else COLOR_DEFAULT
        if current_color != target_color:
            event['colorId'] = target_color
            needs_update = True
            if is_paid:
                result['colored'] = True

        # Applica update se necessario
        if needs_update:
            service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
        else:
            result['unchanged'] = True

        return result

    except HttpError as e:
        if e.resp.status == 404:
            result['error'] = 'not_found'
        else:
            result['error'] = str(e)
        return result
    except Exception as e:
        result['error'] = str(e)
        return result


def main():
    """Funzione principale."""
    print("="*60)
    print("AGGIORNAMENTO INCREMENTALE GOOGLE CALENDAR")
    print("="*60)
    print(f"Database: {DB_PATH.name}")
    print("="*60)

    # Verifica file
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"\n❌ File Service Account non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    if not DB_PATH.exists():
        print(f"\n❌ Database non trovato: {DB_PATH}")
        return

    # Leggi timestamp ultimo aggiornamento
    last_update = get_last_update_timestamp()

    if last_update:
        print(f"📅 Ultimo aggiornamento: {last_update.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"📅 Prima esecuzione - processerò tutte le lezioni")

    # Crea service
    print("\n🔐 Autenticazione Google Calendar...")
    service = get_calendar_service()
    print("✅ Autenticato")

    # Carica lezioni modificate dal DB
    print("\n📖 Caricamento lezioni modificate dal database...")
    lessons_map = get_modified_lessons(DB_PATH, last_update)

    if not lessons_map:
        print("✅ Nessuna modifica da sincronizzare!")
        return

    print(f"✅ {len(lessons_map)} lezioni da aggiornare")

    paid_count = sum(1 for l in lessons_map.values() if l['is_paid'])
    print(f"   - Da colorare BLU: {paid_count}")
    print(f"   - Altre: {len(lessons_map) - paid_count}")

    # Aggiorna eventi modificati
    print("\n🔄 Aggiornamento eventi modificati...\n")

    stats = {
        'total': len(lessons_map),
        'renamed': 0,
        'colored': 0,
        'unchanged': 0,
        'not_found': 0,
        'errors': 0
    }

    for i, (event_id, lesson_data) in enumerate(lessons_map.items(), 1):
        nome = lesson_data['nome']
        is_paid = lesson_data['is_paid']

        # Progress ogni 10
        if i % 10 == 0:
            print(f"   📊 Processati {i}/{len(lessons_map)} eventi...")

        result = update_event_incremental(service, CALENDAR_ID, event_id, lesson_data)

        if result['error']:
            if result['error'] == 'not_found':
                stats['not_found'] += 1
                print(f"  ⚠️  Evento non trovato: {nome}")
            else:
                stats['errors'] += 1
                print(f"  ❌ Errore {nome}: {result['error']}")
        elif result['renamed']:
            stats['renamed'] += 1
            print(f"  ✏️  Rinominato: {nome}")
            if result['colored']:
                stats['colored'] += 1
                print(f"  🔵 Colorato BLU: {nome}")
        elif result['colored']:
            stats['colored'] += 1
            print(f"  🔵 Colorato BLU: {nome}")
        else:
            stats['unchanged'] += 1

    # Salva timestamp aggiornamento
    save_update_timestamp()

    # Stampa statistiche
    print("\n" + "="*60)
    print("RIEPILOGO AGGIORNAMENTO INCREMENTALE")
    print("="*60)
    print(f"Eventi processati: {stats['total']}")
    print(f"Titoli rinominati: {stats['renamed']}")
    print(f"Eventi colorati BLU: {stats['colored']}")
    print(f"Eventi non modificati: {stats['unchanged']}")
    print(f"Eventi non trovati: {stats['not_found']}")
    print(f"Errori: {stats['errors']}")
    print("="*60)
    print(f"\n✅ Timestamp salvato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n✅ Aggiornamento incrementale completato!\n")


if __name__ == "__main__":
    main()
