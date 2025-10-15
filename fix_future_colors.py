#!/usr/bin/env python
"""
Script per RIMUOVERE il colore blu dagli eventi futuri su Google Calendar.

Questo script:
1. Recupera TUTTI gli eventi futuri (da domani in poi)
2. Rimuove il colore BLU (colorId=9) da eventi futuri
3. Lascia solo il colore default (Lavanda)

Uso: per correggere eventi che erano stati colorati erroneamente.
"""
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configurazione
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
SCOPES = ['https://www.googleapis.com/auth/calendar']

COLOR_BLUE = '9'  # Blueberry (da rimuovere da eventi futuri)
COLOR_DEFAULT = '1'  # Lavanda


def get_calendar_service():
    """Crea servizio Google Calendar."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def fix_future_events(service, calendar_id):
    """
    Rimuove colore blu da tutti gli eventi futuri.

    Returns:
        dict: Statistiche
    """
    # Date: da domani in poi (prossimi 6 mesi)
    domani = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    fine_range = (datetime.now() + timedelta(days=180)).replace(hour=23, minute=59, second=59)

    time_min = domani.isoformat() + 'Z'
    time_max = fine_range.isoformat() + 'Z'

    print(f"\n🔍 Ricerca eventi futuri da {domani.strftime('%Y-%m-%d')} a {fine_range.strftime('%Y-%m-%d')}...")

    try:
        # Recupera tutti gli eventi futuri
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=2500
        ).execute()

        events = events_result.get('items', [])
        print(f"✅ Trovati {len(events)} eventi futuri\n")

        if not events:
            return {'total': 0, 'fixed': 0, 'unchanged': 0, 'errors': 0}

        stats = {
            'total': len(events),
            'fixed': 0,
            'unchanged': 0,
            'errors': 0
        }

        print("🔧 Rimozione colori blu da eventi futuri...\n")

        for event in events:
            event_id = event['id']
            summary = event.get('summary', 'Senza titolo')
            current_color = event.get('colorId', None)

            # Se ha colore blu, rimuovilo
            if current_color == COLOR_BLUE:
                try:
                    # Imposta colore default (lavanda)
                    event['colorId'] = COLOR_DEFAULT

                    service.events().update(
                        calendarId=calendar_id,
                        eventId=event_id,
                        body=event
                    ).execute()

                    stats['fixed'] += 1

                    # Estrai data evento
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    if 'T' in start:
                        event_date = datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                    else:
                        event_date = start

                    print(f"  ✅ Rimosso colore BLU: {summary} ({event_date})")

                except HttpError as e:
                    stats['errors'] += 1
                    print(f"  ❌ Errore su {summary}: {e}")
            else:
                stats['unchanged'] += 1

        return stats

    except HttpError as error:
        print(f"❌ Errore API Google Calendar: {error}")
        return None
    except Exception as e:
        print(f"❌ Errore: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Funzione principale."""
    print("="*60)
    print("FIX COLORI EVENTI FUTURI - GOOGLE CALENDAR")
    print("="*60)
    print("Rimuove colore BLU da tutti gli eventi futuri")
    print("="*60)

    # Verifica file
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"\n❌ File Service Account non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    if not CALENDAR_ID:
        print("\n❌ CALENDAR_ID non trovato nel file .env")
        return

    # Crea service
    print("\n🔐 Autenticazione Google Calendar...")
    service = get_calendar_service()
    print("✅ Autenticato")

    # Fix eventi futuri
    stats = fix_future_events(service, CALENDAR_ID)

    if stats:
        print("\n" + "="*60)
        print("RIEPILOGO FIX COLORI FUTURI")
        print("="*60)
        print(f"Eventi futuri trovati: {stats['total']}")
        print(f"Colori BLU rimossi: {stats['fixed']}")
        print(f"Eventi già corretti: {stats['unchanged']}")
        print(f"Errori: {stats['errors']}")
        print("="*60)
        print("\n✅ Fix completato!\n")
    else:
        print("\n❌ Fix fallito\n")


if __name__ == "__main__":
    main()
