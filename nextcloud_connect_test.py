import os
import uuid
import time
import datetime as dt
from caldav import DAVClient
from caldav.elements import dav

# === CONFIG ===
NC_URL  = os.getenv("NC_URL",  "https://ustulcika.nextfiles.cloud/remote.php/dav")
NC_USER = os.getenv("NC_USER", "ustulcika")
NC_PASS = os.getenv("NC_PASS", "APP-PASSWORD")
CALENDAR_NAME = "Personale"   # <-- nome calendario target (hardcoded)

def display_name_of(cal):
    try:
        props = cal.get_properties([dav.DisplayName()])
        val = props.get(dav.DisplayName(), None) or props.get(dav.DisplayName, None) or props.get("displayname", None)
        if val:
            return str(val).strip()
    except Exception:
        pass
    return (getattr(cal, "name", None) or cal.url.path)

def find_calendar_by_name(principal, wanted_name):
    wl = wanted_name.strip().lower()
    for cal in principal.calendars():
        if display_name_of(cal).strip().lower() == wl:
            return cal
    return None

def main():
    client = DAVClient(url=NC_URL, username=NC_USER, password=NC_PASS)
    principal = client.principal()

    target_cal = find_calendar_by_name(principal, CALENDAR_NAME)
    if not target_cal:
        raise RuntimeError(f"Calendario '{CALENDAR_NAME}' non trovato")

    print(f"Uso calendario: {display_name_of(target_cal)}")

    # === CREA EVENTO DI TEST in UTC (aware) ===
    now_utc = dt.datetime.now(dt.timezone.utc)
    start = now_utc + dt.timedelta(minutes=2)
    end   = start + dt.timedelta(minutes=30)
    uid   = str(uuid.uuid4())

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Nextcloud CalDAV Test//EN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_utc.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Ping from Python
DESCRIPTION:Evento di test creato via CalDAV da script Python.
END:VEVENT
END:VCALENDAR
"""

    ev = target_cal.add_event(ics)
    print("Creato evento con UID:", uid)

    # Mini attesa: alcune istanze aggiornano l'indice con lieve ritardo
    time.sleep(1)

    # === 1) Verifica diretta dell'evento creato ===
    v = ev.vobject_instance.vevent
    print("Verifica immediata ->", v.summary.value, "| UID:", v.uid.value, "| DTSTART:", v.dtstart.value)

    # === 2) Ricerca consigliata con calendar.search(...) ===
    # Finestra ampia e expand=True per avere occorrenze "espanse"
    results = target_cal.search(
        start=start - dt.timedelta(hours=6),
        end=end + dt.timedelta(hours=6),
        event=True,
        expand=True
    )
    print(f"Risultati con calendar.search: {len(results)}")
    for r in results:
        vv = r.vobject_instance.vevent
        print("  ->", vv.summary.value, "| UID:", vv.uid.value, "| DTSTART:", vv.dtstart.value)

    # === 3) Fallback: elenco completo e match UID ===
    if not any(getattr(r.vobject_instance.vevent.uid, "value", None) == uid for r in results):
        all_events = target_cal.events()
        hits = []
        for r in all_events:
            try:
                vv = r.vobject_instance.vevent
                if getattr(vv.uid, "value", None) == uid:
                    hits.append(r)
            except Exception:
                pass
        print(f"Fallback match per UID nel calendario: {len(hits)}")
        for r in hits:
            vv = r.vobject_instance.vevent
            print("  ->", vv.summary.value, "| UID:", vv.uid.value, "| DTSTART:", vv.dtstart.value)

if __name__ == "__main__":
    main()
