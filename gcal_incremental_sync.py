#!/usr/bin/env python
"""
Sincronizzazione INCREMENTALE delle lezioni da Google Calendar.

Scarica SOLO le lezioni nuove/modificate dall'ultimo sync, usando il timestamp
salvato nel database. Più efficiente di gcal_bulk_sync.py.

Features:
- Legge timestamp ultimo sync dal DB (tabella sync_status)
- Usa updatedMin parameter di Google Calendar API per scaricare solo modifiche
- Cancella lezioni rimosse dal calendario (eventi cancellati)
- Salva nuovo timestamp nel DB dopo sync
"""
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Carica variabili d'ambiente
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Configurazione
SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
DB_PATH = Path(__file__).parent / "pagamenti.db"
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_calendar_service():
    """Crea servizio Google Calendar API."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)
    return service


def ensure_sync_status_table(db_path):
    """
    Crea tabella sync_status se non esiste.

    Tabella per salvare timestamp ultimo sync di ogni fonte.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_status (
            source TEXT PRIMARY KEY,
            last_sync_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def get_last_sync_timestamp(db_path, source='google_calendar'):
    """
    Recupera timestamp ultimo sync dal database.

    Args:
        db_path: Path del database
        source: Nome della fonte (default: 'google_calendar')

    Returns:
        datetime object UTC o None se prima esecuzione
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT last_sync_at FROM sync_status WHERE source = ?
    ''', (source,))

    row = cursor.fetchone()
    conn.close()

    if row:
        # Parse timestamp ISO formato
        return datetime.fromisoformat(row[0])
    else:
        return None


def save_sync_timestamp(db_path, timestamp, source='google_calendar'):
    """
    Salva timestamp sync nel database.

    Args:
        db_path: Path del database
        timestamp: datetime object UTC
        source: Nome della fonte (default: 'google_calendar')
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # INSERT or UPDATE
    cursor.execute('''
        INSERT INTO sync_status (source, last_sync_at, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(source) DO UPDATE SET
            last_sync_at = excluded.last_sync_at,
            updated_at = CURRENT_TIMESTAMP
    ''', (source, timestamp.isoformat()))

    conn.commit()
    conn.close()


def sync_incremental_lessons(service, calendar_id, last_sync, db_path):
    """
    Sincronizza SOLO lezioni modificate/create dall'ultimo sync.

    Args:
        service: Google Calendar API service object
        calendar_id: ID del calendario Google
        last_sync: datetime dell'ultimo sync (None = prima esecuzione)
        db_path: Path del database SQLite

    Returns:
        dict con statistiche
    """
    print(f"📥 Sincronizzazione incrementale lezioni da Google Calendar")

    # Parametri query
    params = {
        'calendarId': calendar_id,
        'singleEvents': True,
        'orderBy': 'updated',  # Ordina per data modifica
        'showDeleted': True,   # Includi eventi cancellati
        'timeMax': datetime.now(timezone.utc).replace(hour=23, minute=59, second=59).isoformat(),  # Solo fino a oggi
    }

    if last_sync:
        # Sync incrementale: solo eventi modificati dopo last_sync
        # updatedMin richiede formato RFC3339 con Z
        updated_min = last_sync.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        params['updatedMin'] = updated_min
        print(f"   Modalità: INCREMENTALE (modifiche dopo {last_sync.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
    else:
        # Prima esecuzione: scarica tutto (ultimi 6 mesi per sicurezza)
        time_min = datetime.now().replace(month=max(1, datetime.now().month - 6)).isoformat() + 'Z'
        params['timeMin'] = time_min
        print(f"   Modalità: PRIMA ESECUZIONE (tutto dallo storico)")

    print(f"   Range temporale: SOLO passato e oggi (NO eventi futuri)")
    print()

    try:
        # Recupera eventi (con paginazione)
        print("🔍 Recupero eventi modificati dal calendario...")

        all_events = []
        page_token = None

        while True:
            if page_token:
                params['pageToken'] = page_token

            events_result = service.events().list(**params).execute()
            events = events_result.get('items', [])
            all_events.extend(events)

            page_token = events_result.get('nextPageToken')
            if not page_token:
                break

        print(f"✅ Trovati {len(all_events)} eventi modificati\n")

        if not all_events:
            print("✅ Nessuna modifica da sincronizzare!")
            return {
                'total_events': 0,
                'synced': 0,
                'deleted': 0,
                'skipped_prova': 0,
                'errors': 0,
            }

        # Connessione database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Statistiche
        synced = 0
        deleted = 0
        skipped_prova = 0
        errors = 0

        print("📝 Processamento eventi modificati...\n")

        for i, event in enumerate(all_events, 1):
            event_id = event['id']
            status = event.get('status', 'confirmed')
            summary = event.get('summary', '').strip()

            # Progresso ogni 50 eventi
            if i % 50 == 0:
                print(f"   Processati {i}/{len(all_events)} eventi...")

            # Eventi cancellati: rimuovi dal database
            if status == 'cancelled':
                try:
                    cursor.execute('''
                        DELETE FROM lezioni WHERE nextcloud_event_id = ?
                    ''', (event_id,))

                    if cursor.rowcount > 0:
                        deleted += 1
                        print(f"🗑️  Rimosso evento cancellato: {summary or event_id}")
                except Exception as e:
                    errors += 1
                    print(f"❌ Errore cancellazione {event_id}: {e}")

                continue

            # Salta eventi senza titolo
            if not summary:
                errors += 1
                continue

            # Identifica eventi "prova" (lezioni gratis)
            is_prova = any(keyword in summary.lower() for keyword in ['prova', 'пробный', 'trial'])

            if is_prova:
                skipped_prova += 1
                continue

            # Parse start time
            start = event['start'].get('dateTime', event['start'].get('date'))

            if 'T' in start:
                # Evento con orario
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                giorno = dt.strftime('%Y-%m-%d')
                ora = dt.strftime('%H:%M:%S')
            else:
                # Evento all-day
                giorno = start
                ora = '00:00:00'

            # FILTRO: SOLO dal 1 agosto 2025 a oggi (NO futuro, NO prima agosto)
            oggi = datetime.now().date().isoformat()
            if giorno > oggi or giorno < '2025-08-01':
                continue

            # Normalizza nome studente
            nome_studente = summary.strip()

            # Insert or update nel database
            try:
                cursor.execute('''
                    INSERT INTO lezioni (nextcloud_event_id, nome_studente, giorno, ora, stato)
                    VALUES (?, ?, ?, ?, 'prevista')
                    ON CONFLICT(nextcloud_event_id) DO UPDATE SET
                        nome_studente = excluded.nome_studente,
                        giorno = excluded.giorno,
                        ora = excluded.ora,
                        updated_at = CURRENT_TIMESTAMP
                ''', (event_id, nome_studente, giorno, ora))

                synced += 1
                print(f"✅ Sincronizzato: {nome_studente} - {giorno} {ora}")

            except sqlite3.IntegrityError as e:
                errors += 1
                print(f"❌ Errore inserimento {event_id}: {e}")

        # Commit modifiche
        conn.commit()

        # Verifica totale nel database
        cursor.execute("SELECT COUNT(*) FROM lezioni")
        total_in_db = cursor.fetchone()[0]

        conn.close()

        # Return statistiche
        return {
            'total_events': len(all_events),
            'synced': synced,
            'deleted': deleted,
            'skipped_prova': skipped_prova,
            'errors': errors,
            'total_in_db': total_in_db
        }

    except HttpError as error:
        print(f"❌ Errore API Google Calendar: {error}")
        return None
    except Exception as e:
        print(f"❌ Errore durante sincronizzazione: {e}")
        import traceback
        traceback.print_exc()
        return None


def print_statistics(stats):
    """Stampa statistiche di sincronizzazione."""
    if not stats:
        return

    print("\n" + "="*60)
    print("RIEPILOGO SINCRONIZZAZIONE INCREMENTALE")
    print("="*60)
    print(f"Eventi modificati: {stats['total_events']}")
    print(f"Lezioni sincronizzate: {stats['synced']}")
    print(f"Lezioni cancellate: {stats['deleted']}")
    print(f"Eventi prova (ignorati): {stats['skipped_prova']}")
    print(f"Errori: {stats['errors']}")
    print("-"*60)
    print(f"TOTALE nel database: {stats['total_in_db']} lezioni")
    print("="*60)


def main():
    """Funzione principale."""
    print("="*60)
    print("SINCRONIZZAZIONE INCREMENTALE LEZIONI - GOOGLE CALENDAR")
    print("="*60)
    print(f"Database: {DB_PATH.name}")
    print("="*60 + "\n")

    # Verifica file credenziali
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ File credenziali non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    # Verifica CALENDAR_ID
    if not CALENDAR_ID:
        print("❌ GCAL_CALENDAR_ID non trovato nel file .env")
        return

    # Verifica database
    if not DB_PATH.exists():
        print(f"❌ Database non trovato: {DB_PATH}")
        return

    # Crea tabella sync_status se non esiste
    print("🔧 Verifica tabella sync_status...")
    ensure_sync_status_table(DB_PATH)
    print("✅ Tabella sync_status pronta\n")

    # Leggi timestamp ultimo sync
    last_sync = get_last_sync_timestamp(DB_PATH)

    if last_sync:
        print(f"📅 Ultimo sync: {last_sync.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    else:
        print(f"📅 Prima esecuzione - scarico tutto lo storico")
    print()

    # Crea service Google Calendar
    try:
        print("🔐 Autenticazione Google Calendar...")
        service = get_calendar_service()
        print("✅ Autenticato\n")
    except Exception as e:
        print(f"❌ Errore autenticazione: {e}")
        return

    # Timestamp PRIMA del sync (per evitare race conditions)
    sync_start = datetime.now(timezone.utc)

    # Sincronizza lezioni
    stats = sync_incremental_lessons(service, CALENDAR_ID, last_sync, DB_PATH)

    if stats:
        # Salva timestamp sync
        save_sync_timestamp(DB_PATH, sync_start)
        print(f"\n✅ Timestamp salvato: {sync_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        # Stampa statistiche
        print_statistics(stats)

        print("\n✅ Sincronizzazione incrementale completata!\n")
    else:
        print("\n❌ Sincronizzazione fallita\n")


if __name__ == "__main__":
    main()
