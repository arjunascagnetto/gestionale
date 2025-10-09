#!/usr/bin/env python
"""
Script di test per la connessione a Google Calendar usando Service Account.
Verifica l'accesso al calendario e mostra gli eventi recenti.
"""
import os
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
SERVICE_ACCOUNT_FILE = Path(__file__).parent / os.getenv('GCAL_SERVICE_ACCOUNT_FILE', 'fresh-electron-318314-050d19bd162e.json')
CALENDAR_ID = os.getenv('GCAL_CALENDAR_ID')
SCOPES = ['https://www.googleapis.com/auth/calendar']


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


def list_calendars(service):
    """
    Elenca tutti i calendari accessibili al service account.

    Args:
        service: Google Calendar API service object
    """
    print("="*60)
    print("CALENDARI ACCESSIBILI")
    print("="*60)

    try:
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])

        if not calendars:
            print("Nessun calendario trovato.")
            print("\nAssicurati di aver condiviso il calendario con:")
            print("calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com")
            return None

        print(f"\nTrovati {len(calendars)} calendari:\n")
        for calendar in calendars:
            print(f"Nome: {calendar['summary']}")
            print(f"ID: {calendar['id']}")
            print(f"Colore: {calendar.get('backgroundColor', 'N/A')}")
            print(f"Ruolo: {calendar.get('accessRole', 'N/A')}")
            print("-" * 60)

        return calendars

    except HttpError as error:
        print(f"❌ Errore nell'accesso ai calendari: {error}")
        return None


def list_events(service, calendar_id, days_back=30, days_forward=30):
    """
    Elenca gli eventi del calendario in un intervallo di tempo.

    Args:
        service: Google Calendar API service object
        calendar_id: ID del calendario
        days_back: Giorni nel passato da considerare (default: 30)
        days_forward: Giorni nel futuro da considerare (default: 30)
    """
    print("\n" + "="*60)
    print("EVENTI NEL CALENDARIO")
    print("="*60)

    # Imposta intervallo di tempo
    now = datetime.utcnow()
    time_min = (now - timedelta(days=days_back)).isoformat() + 'Z'
    time_max = (now + timedelta(days=days_forward)).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            print(f"\nNessun evento trovato negli ultimi {days_back} giorni e prossimi {days_forward} giorni.")
            return

        print(f"\nTrovati {len(events)} eventi:\n")

        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '(Senza titolo)')
            event_id = event['id']

            # Estrai data/ora
            if 'T' in start:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted_start = dt.strftime('%Y-%m-%d %H:%M')
            else:
                formatted_start = start

            print(f"📅 {formatted_start} - {summary}")
            print(f"   ID: {event_id}")

            # Mostra descrizione se presente
            if 'description' in event:
                desc = event['description'][:100]
                print(f"   Descrizione: {desc}...")

            print()

    except HttpError as error:
        print(f"❌ Errore nel recuperare gli eventi: {error}")


def main():
    """Funzione principale."""
    print("="*60)
    print("TEST CONNESSIONE GOOGLE CALENDAR")
    print("="*60)
    print(f"Service Account: {SERVICE_ACCOUNT_FILE.name}")
    print()

    # Verifica che il file delle credenziali esista
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ File credenziali non trovato: {SERVICE_ACCOUNT_FILE}")
        return

    # Verifica che CALENDAR_ID sia configurato
    if not CALENDAR_ID:
        print("❌ GCAL_CALENDAR_ID non trovato nel file .env")
        return

    # Crea il service
    try:
        service = get_calendar_service()
        print("✅ Connessione al Google Calendar API stabilita\n")
    except Exception as e:
        print(f"❌ Errore nella creazione del service: {e}")
        return

    # Accedi direttamente al calendario configurato
    print("="*60)
    print("VERIFICA ACCESSO AL CALENDARIO")
    print("="*60)

    try:
        calendar = service.calendars().get(calendarId=CALENDAR_ID).execute()
        calendar_name = calendar['summary']
        timezone = calendar.get('timeZone', 'N/A')

        print(f"\n✅ Calendario trovato: {calendar_name}")
        print(f"   ID: {CALENDAR_ID}")
        print(f"   Timezone: {timezone}")
    except HttpError as error:
        print(f"❌ Errore nell'accesso al calendario: {error}")
        print("\nAssicurati di aver condiviso il calendario con:")
        print("calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com")
        return

    # Elenca gli eventi
    list_events(service, CALENDAR_ID)

    print("\n" + "="*60)
    print("TEST COMPLETATO")
    print("="*60)


if __name__ == "__main__":
    main()
