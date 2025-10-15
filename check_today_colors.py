#!/usr/bin/env python
"""
Script per verificare i colori degli eventi di OGGI su Google Calendar.
"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configurazione
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE')
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_calendar_service():
    """Crea servizio Google Calendar."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def check_today_events(service, calendar_id):
    """Verifica colori eventi di oggi."""
    oggi = datetime.now().date()
    time_min = oggi.isoformat() + 'T00:00:00Z'
    time_max = oggi.isoformat() + 'T23:59:59Z'

    print(f"\n📅 Verifica eventi del {oggi.strftime('%d/%m/%Y')}\n")

    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            print("Nessun evento oggi")
            return

        print(f"Trovati {len(events)} eventi:\n")
        print("-" * 80)

        color_map = {
            '1': 'Lavanda',
            '9': 'BLU (Blueberry)',
            None: 'Default (nessun colore)'
        }

        for event in events:
            summary = event.get('summary', 'Senza titolo')
            start = event['start'].get('dateTime', event['start'].get('date'))
            color_id = event.get('colorId', None)
            color_name = color_map.get(color_id, f'Colore {color_id}')

            # Estrai ora
            if 'T' in start:
                ora = datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%H:%M')
            else:
                ora = 'All-day'

            print(f"{ora:6} | {summary:30} | Colore: {color_name}")

        print("-" * 80)

    except Exception as e:
        print(f"❌ Errore: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Funzione principale."""
    print("=" * 80)
    print("VERIFICA COLORI EVENTI OGGI - GOOGLE CALENDAR")
    print("=" * 80)

    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"\n❌ File Service Account non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    if not CALENDAR_ID:
        print("\n❌ CALENDAR_ID non trovato nel file .env")
        return

    print("\n🔐 Autenticazione Google Calendar...")
    service = get_calendar_service()
    print("✅ Autenticato")

    check_today_events(service, CALENDAR_ID)
    print()


if __name__ == "__main__":
    main()
