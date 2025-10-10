#!/usr/bin/env python
"""
Sincronizzazione COMPLETA delle lezioni da Google Calendar
Scarica TUTTE le lezioni dal calendario Google dal 1 agosto a oggi
e popola il database lezioni.

Differenze rispetto alla funzione sync_lessons_from_calendar():
- Range di date configurabile (dal 1 agosto a oggi)
- Statistiche dettagliate per studente
- Report completo del sincronizzamento
- Supporto lezioni gratis (eventi "prova")
"""
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
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

# Range di date per il recupero (1 agosto 2025 - oggi)
START_DATE = datetime(2025, 8, 1)  # 1 agosto 2025
END_DATE = datetime.now()  # Oggi (fine giornata)


def get_calendar_service():
    """
    Crea e restituisce un oggetto service per Google Calendar API.

    Returns:
        Google Calendar API service object
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)
    return service


def sync_all_lessons(service, calendar_id, start_date, end_date, db_path):
    """
    Sincronizza TUTTE le lezioni dal calendario nel database.

    Args:
        service: Google Calendar API service object
        calendar_id: ID del calendario Google
        start_date: Data inizio (datetime)
        end_date: Data fine (datetime)
        db_path: Path del database SQLite

    Returns:
        Dizionario con statistiche di sincronizzazione
    """
    print(f"📥 Sincronizzazione lezioni da Google Calendar")
    print(f"   Range: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"   Calendario: {calendar_id[:40]}...\n")

    # Imposta range di tempo
    # IMPORTANTE: finiamo a fine giornata di oggi
    time_min = start_date.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
    time_max = end_date.replace(hour=23, minute=59, second=59).isoformat() + 'Z'

    try:
        # Recupera TUTTI gli eventi (nessun limite maxResults)
        print("🔍 Recupero eventi dal calendario...")
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,  # Espande eventi ricorrenti
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"✅ Trovati {len(events)} eventi totali\n")

        if not events:
            print("⚠️  Nessun evento trovato nel range specificato.")
            return {
                'total_events': 0,
                'synced': 0,
                'skipped_prova': 0,
                'errors': 0,
                'students': {}
            }

        # Connessione database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Statistiche
        synced = 0
        skipped_prova = 0
        errors = 0
        students_stats = {}  # Dict: nome_studente → count lezioni

        print("📝 Processamento eventi...\n")

        for i, event in enumerate(events, 1):
            # Progresso ogni 50 eventi
            if i % 50 == 0:
                print(f"   Processati {i}/{len(events)} eventi...")

            event_id = event['id']
            summary = event.get('summary', '').strip()
            start = event['start'].get('dateTime', event['start'].get('date'))

            # Salta eventi senza titolo
            if not summary:
                errors += 1
                continue

            # Identifica eventi "prova" (lezioni gratis)
            is_prova = summary.lower().startswith('prova')

            if is_prova:
                skipped_prova += 1
                # print(f"🎁 Lezione gratis (prova): {summary} - {start}")
                continue

            # Parse date e time
            if 'T' in start:
                # Evento con orario
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                giorno = dt.strftime('%Y-%m-%d')
                ora = dt.strftime('%H:%M:%S')
            else:
                # Evento all-day
                giorno = start
                ora = '00:00:00'

            # Normalizza nome studente
            # Rimuovi varianti tipo "dmitry1" → "dmitry"
            nome_studente = summary.replace('dmitry1', 'dmitry').strip()

            # Statistiche per studente
            if nome_studente not in students_stats:
                students_stats[nome_studente] = 0
            students_stats[nome_studente] += 1

            # Insert or update nel database
            # Il costo di default (2000 RUB) viene impostato dalla tabella
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
                print(f"✅ Sincronizzato: {nome_studente} - {giorno} {ora}")

            except sqlite3.IntegrityError as e:
                errors += 1
                print(f"❌ Errore inserimento {event_id}: {e}")

        # Commit modifiche
        conn.commit()

        # Verifica totale nel database
        cursor.execute("SELECT COUNT(*) FROM lezioni WHERE stato='prevista'")
        total_in_db = cursor.fetchone()[0]

        conn.close()

        # Return statistiche
        return {
            'total_events': len(events),
            'synced': synced,
            'skipped_prova': skipped_prova,
            'errors': errors,
            'students': students_stats,
            'total_in_db': total_in_db
        }

    except HttpError as error:
        print(f"❌ Errore nell'accesso al calendario: {error}")
        return None
    except Exception as e:
        print(f"❌ Errore durante la sincronizzazione: {e}")
        return None


def print_statistics(stats):
    """
    Stampa statistiche di sincronizzazione.

    Args:
        stats: Dizionario con statistiche
    """
    if not stats:
        return

    print("\n" + "="*60)
    print("RIEPILOGO SINCRONIZZAZIONE LEZIONI")
    print("="*60)
    print(f"Eventi trovati: {stats['total_events']}")
    print(f"Lezioni sincronizzate: {stats['synced']}")
    print(f"Lezioni gratis (prova): {stats['skipped_prova']}")
    print(f"Errori: {stats['errors']}")
    print("-"*60)
    print(f"TOTALE nel database: {stats['total_in_db']} lezioni")
    print("="*60)

    # Statistiche per studente
    if stats['students']:
        print("\n📊 LEZIONI PER STUDENTE:")
        print("-"*60)

        # Ordina per numero di lezioni (decrescente)
        sorted_students = sorted(
            stats['students'].items(),
            key=lambda x: x[1],
            reverse=True
        )

        total_lessons = 0
        for nome_studente, count in sorted_students:
            print(f"   {nome_studente:.<40} {count:>3} lezioni")
            total_lessons += count

        print("-"*60)
        print(f"   {'TOTALE':.<40} {total_lessons:>3} lezioni")
        print(f"   {'Studenti attivi':.<40} {len(sorted_students):>3}")
        print("="*60)


def main():
    """Funzione principale."""
    print("="*60)
    print("SINCRONIZZAZIONE COMPLETA LEZIONI DA GOOGLE CALENDAR")
    print("="*60)
    print(f"Service Account: {SERVICE_ACCOUNT_FILE.name}")
    print(f"Database: {DB_PATH.name}")
    print(f"Range date: {START_DATE.strftime('%d/%m/%Y')} → {END_DATE.strftime('%d/%m/%Y')}")
    print("="*60 + "\n")

    # Verifica che il file delle credenziali esista
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ File credenziali non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    # Verifica che CALENDAR_ID sia configurato
    if not CALENDAR_ID:
        print("❌ GCAL_CALENDAR_ID non trovato nel file .env")
        return

    # Verifica database
    if not DB_PATH.exists():
        print(f"❌ Database non trovato: {DB_PATH}")
        return

    # Crea il service
    try:
        service = get_calendar_service()
        print("✅ Connessione al Google Calendar API stabilita\n")
    except Exception as e:
        print(f"❌ Errore nella creazione del service: {e}")
        return

    # Verifica accesso al calendario
    try:
        calendar = service.calendars().get(calendarId=CALENDAR_ID).execute()
        calendar_name = calendar['summary']
        timezone = calendar.get('timeZone', 'N/A')

        print(f"✅ Calendario trovato: {calendar_name}")
        print(f"   Timezone: {timezone}\n")
    except HttpError as error:
        print(f"❌ Errore nell'accesso al calendario: {error}")
        print("\nAssicurati di aver condiviso il calendario con:")
        print("calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com")
        return

    # Sincronizza lezioni
    stats = sync_all_lessons(service, CALENDAR_ID, START_DATE, END_DATE, DB_PATH)

    # Stampa statistiche
    print_statistics(stats)

    print("\n✅ Sincronizzazione completata!\n")


if __name__ == "__main__":
    main()
