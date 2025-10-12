# Sistema di Gestione Pagamenti e Lezioni Russo

Sistema automatizzato per la gestione e riconciliazione dei pagamenti delle lezioni di russo. Il sistema integra Telegram, Google Calendar e database SQLite per tracciare pagamenti, lezioni e abbinamenti automatici.

## Caratteristiche Principali

- **Import automatico pagamenti** da notifiche SMS bancarie via Telegram
- **Sincronizzazione lezioni** da Google Calendar
- **Bot Telegram interattivo** per abbinamento guidato pagamenti-lezioni
- **Interfaccia Web** per gestione manuale abbinamenti storici
- **Supporto abbonamenti** (3/5/10 lezioni) e pagamenti parziali
- **Sistema di associazioni** studente-pagante con fuzzy matching

## Architettura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                     FLUSSO DEL SISTEMA                       │
└─────────────────────────────────────────────────────────────┘

1. INGESTORE PAGAMENTI (telegram_ingestor.py)
   ├─ Legge messaggi dal canale Telegram
   ├─ Estrae: nome_pagante, data, ora, somma
   ├─ Filtra usando whitelist studenti
   └─ Inserisce in DB con stato='sospeso'

2. SINCRONIZZATORE LEZIONI (gcal_bulk_sync.py / bot /sync)
   ├─ Legge eventi da Google Calendar "Lezioni Russo"
   ├─ Estrae: nome_studente, data, ora, durata
   └─ Inserisce/aggiorna in DB con stato='prevista'

3. BOT TELEGRAM (association_resolver.py)
   ├─ Mostra SOLO pagamenti e lezioni di OGGI
   ├─ Sync automatico lezioni oggi ad ogni /process
   ├─ Inline keyboard per selezione lezioni
   ├─ Rilevamento automatico abbonamenti
   └─ Salvataggio associazioni studente-pagante

4. INTERFACCIA WEB (web_interface/app.py)
   ├─ Vista dual: lezioni non pagate | pagamenti disponibili
   ├─ Selezione multipla con checkbox
   ├─ Calcolo real-time bilancio crediti-debiti
   ├─ Distribuzione automatica su pagamenti multipli
   └─ Gestione abbinamenti completi e storico
```

## Installazione

### Prerequisiti

- Python 3.10+
- SQLite3
- Account Telegram (User API + Bot API)
- Google Cloud Service Account con accesso Google Calendar

### Setup Ambiente

```bash
# Clona il repository
git clone https://github.com/arjunascagnetto/gestionale.git
cd gestionale

# Crea virtual environment
python3 -m venv .cal
source .cal/bin/activate  # Linux/Mac
# oppure
.cal\Scripts\activate  # Windows

# Installa dipendenze
pip install python-telegram-bot telethon python-dotenv \
            google-api-python-client google-auth-httplib2 \
            google-auth-oauthlib flask
```

### Configurazione

1. **Crea file `.env`** nella root del progetto:

```bash
# Telegram Bot (receiver)
BOT_TOKEN=your_bot_token_here

# Telegram User API (Telethon)
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+1234567890
TELEGRAM_PASSWORD=your_telegram_password
CHANNEL_ID=-100xxxxxxxxxxxx

# Google Calendar
GCAL_CALENDAR_ID=your_calendar_id@group.calendar.google.com
GCAL_SERVICE_ACCOUNT_FILE=your-service-account.json
```

2. **Configura Google Service Account:**
   - Vai su Google Cloud Console
   - Crea un nuovo Service Account
   - Abilita Google Calendar API
   - Scarica il file JSON delle credenziali
   - Condividi il calendario "Lezioni Russo" con l'email del service account

3. **Crea whitelist studenti** (`mittenti_whitelist.csv`):

```csv
nome_studente
Иван
Мария
Сергей
```

4. **Inizializza database:**

```bash
python db_create_schema.py
```

## Utilizzo

### Import Dati Storici

```bash
# Import pagamenti da Telegram (ultimi 60 giorni)
python telegram_bulk_ingestor.py

# Import lezioni da Google Calendar
python gcal_bulk_sync.py
```

### Bot Telegram Interattivo

```bash
# Avvia bot per abbinamenti di OGGI
python association_resolver.py
```

**Comandi bot:**
- `/process` - Processa pagamenti di oggi (non-skipped)
- `/suspended` - Riprocessa pagamenti skippati
- `/sync` - Sincronizza lezioni da Google Calendar

**Nota:** Il bot mostra SOLO pagamenti e lezioni del giorno corrente. Per gestire storico/futuro usa l'interfaccia web.

### Interfaccia Web

```bash
# Avvia server Flask
cd web_interface
python app.py
```

Accedi a `http://localhost:5000` per:
- Abbinare manualmente pagamenti storici
- Gestire abbonamenti multipli
- Visualizzare abbinamenti completati
- Eliminare abbinamenti errati

### Monitor Pagamenti Real-time

```bash
# Monitora nuovi pagamenti in arrivo
python payment_monitor.py
```

## Struttura Database

### Tabella `pagamenti`
- `id_pagamento` (PK)
- `nome_pagante` (TEXT)
- `giorno`, `ora` (DATE, TIME)
- `somma` (NUMERIC)
- `stato` ('sospeso', 'associato', 'usato')
- `fonte_msg_id` (UNIQUE) - per deduplicazione

### Tabella `lezioni`
- `id_lezione` (PK)
- `nome_studente` (TEXT)
- `giorno`, `ora` (DATE, TIME)
- `durata_min` (INTEGER)
- `nextcloud_event_id` (UNIQUE) - ID Google Calendar
- `stato` ('prevista', 'svolta', 'pagata')

### Tabella `associazioni`
- `id_assoc` (PK)
- `nome_studente` (UNIQUE)
- `nome_pagante` (TEXT)
- `note` (TEXT)

### Tabella `pagamenti_lezioni`
- `pagamento_id` (FK)
- `lezione_id` (FK)
- `quota_usata` (NUMERIC)
- UNIQUE constraint su (pagamento_id, lezione_id)

## Statistiche Progetto

- **Linee di codice:** ~2733 Python
- **Script funzionanti:** 15+
- **Pagamenti tracciati:** 90+
- **Lezioni sincronizzate:** 150+
- **Studenti attivi:** 20

## Deployment

Guida completa disponibile in `DEPLOYMENT_LINODE.md` per deploy su VPS con:
- Servizi systemd (bot + web)
- Nginx reverse proxy
- SSL con Let's Encrypt
- Cron job per sync automatico

## Documentazione Completa

- `project-status.md` - Stato dettagliato del progetto
- `to-do-list.txt` - Task list e versioni release
- `SISTEMA_PAGAMENTI.md` - Architettura sistema dual (Bot + Web)
- `BULK_IMPORT_README.md` - Import dati storici
- `BOT_TEMPORAL_FILTERS.md` - Comportamento filtri temporali bot
- `DEPLOYMENT_LINODE.md` - Guida deployment produzione
- `web_interface/README.md` - Documentazione interfaccia web

## Sicurezza

- File `.env` con credenziali (gitignored)
- Service account JSON (gitignored)
- Database SQLite locale (gitignored)
- Session Telegram (gitignored)

**IMPORTANTE:** Non committare mai file contenenti credenziali nel repository.

## Versioni

**v2.1 (Current)** - Filtri temporali bot
- Bot mostra SOLO dati di oggi
- Sync automatico lezioni oggi
- Storico/futuro via web interface

**v2.0** - Import bulk e normalizzazione
- Import storico completo
- Normalizzazione nomi studenti
- Sync incrementale Calendar

**v1.1** - Bugfix
- Gestione IntegrityError duplicati
- UPDATE quota per abbinamenti esistenti

**v1.0** - Sistema base
- Import pagamenti/lezioni
- Bot Telegram + Web interface

## Contatti

**Autore:** Arjuna Scagnetto
**Repository:** https://github.com/arjunascagnetto/gestionale
**Service Account Google:** `calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com`

## Licenza

Progetto privato per uso personale.

---

*Ultimo aggiornamento: 2025-10-12*
