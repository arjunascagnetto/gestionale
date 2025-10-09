# Progetto: Sistema di Gestione Pagamenti e Lezioni Russo

## 📋 Descrizione del Progetto

Sistema automatizzato per la gestione e riconciliazione dei pagamenti delle lezioni di russo. Il sistema integra tre fonti di dati:

1. **Telegram** - Canale privato dove arrivano notifiche SMS bancarie dei pagamenti ricevuti
2. **Google Calendar** - Calendario "Lezioni Russo" con gli appuntamenti programmati
3. **Database SQLite** - Database locale per memorizzare pagamenti, lezioni e associazioni

### Obiettivi del Sistema

- Automatizzare l'ingestion dei pagamenti da Telegram
- Sincronizzare le lezioni dal calendario Google
- Associare automaticamente pagamenti ricevuti alle lezioni svolte
- Tracciare lo stato di pagamento di ogni lezione
- Ridurre al minimo l'intervento manuale

---

## 🏗️ Architettura del Sistema

### Componenti Principali

```
┌─────────────────────────────────────────────────────────────┐
│                     FLUSSO DEL SISTEMA                       │
└─────────────────────────────────────────────────────────────┘

1. INGESTORE PAGAMENTI (telegram_ingestor.py)
   ├─ Legge messaggi dal canale Telegram
   ├─ Estrae: nome_pagante, data, ora, somma
   ├─ Filtra usando whitelist studenti
   └─ Inserisce in DB con stato='sospeso'

2. SINCRONIZZATORE LEZIONI (da implementare)
   ├─ Legge eventi da Google Calendar
   ├─ Estrae: nome_studente, data, ora, durata
   └─ Inserisce/aggiorna in DB con stato='prevista'

3. RISOLUTORE ASSOCIAZIONI (da implementare)
   ├─ Cerca associazioni nome_studente ↔ nome_pagante
   ├─ Se non trovata, chiede conferma via Telegram
   └─ Salva associazione nel DB

4. ASSOCIATORE PAGAMENTI-LEZIONI (da implementare)
   ├─ Matcha pagamenti disponibili con lezioni svolte
   ├─ Aggiorna stati: lezione → 'pagata', pagamento → 'usato'
   └─ Notifica eventuali discrepanze via Telegram
```

---

## 🗄️ Schema Database (SQLite)

### Tabella: `pagamenti`
```sql
- id_pagamento (PK, AUTOINCREMENT)
- nome_pagante (TEXT)
- giorno (DATE)
- ora (TIME)
- somma (NUMERIC)
- valuta (TEXT, default 'RUB')
- stato (TEXT: 'sospeso', 'associato', 'usato')
- fonte_msg_id (TEXT, UNIQUE) -- per deduplicazione
- created_at, updated_at (TIMESTAMP)
```

### Tabella: `lezioni`
```sql
- id_lezione (PK, AUTOINCREMENT)
- nome_studente (TEXT)
- giorno (DATE)
- ora (TIME)
- durata_min (INTEGER, default 60)
- nextcloud_event_id (TEXT, UNIQUE) -- ID evento Google Calendar
- stato (TEXT: 'prevista', 'svolta', 'pagata')
- created_at, updated_at (TIMESTAMP)
```

### Tabella: `associazioni`
```sql
- id_assoc (PK, AUTOINCREMENT)
- nome_studente (TEXT, UNIQUE)
- nome_pagante (TEXT)
- note (TEXT)
- valid_from, valid_to (DATE)
- created_at, updated_at (TIMESTAMP)
```

### Tabella: `pagamenti_lezioni`
```sql
- id (PK, AUTOINCREMENT)
- pagamento_id (FK → pagamenti)
- lezione_id (FK → lezioni)
- quota_usata (NUMERIC)
- created_at (TIMESTAMP)
- UNIQUE(pagamento_id, lezione_id)
```

---

## 📊 Stato Attuale del Progetto

### ✅ Completato

#### 1. Setup e Configurazione
- [x] Ambiente Python con venv (`.cal/`)
- [x] Repository Git inizializzato
- [x] File `.env` con credenziali configurate
- [x] Database SQLite creato (`pagamenti.db`)
- [x] Schema completo con indici, trigger e foreign keys

#### 2. Componente 1: Ingestore Pagamenti ✅
- [x] **Script**: `telegram_ingestor.py`
- [x] Connessione Telethon User API
- [x] Autenticazione completa (API_ID, API_HASH, phone, password, 2FA)
- [x] Parsing regex SMS banca russa
- [x] Estrazione campi: nome, data, ora, somma
- [x] Deduplicazione via `fonte_msg_id`
- [x] Whitelist studenti (`mittenti_whitelist.csv`)
- [x] Filtro automatico non-studenti
- [x] Gestione importi con spazi (es. "10 000" → 10000)
- [x] Session file salvata (`telegram_session.session`)

**Statistiche attuali:**
- **90 pagamenti** nel DB (tutti stato='sospeso')
- **20 studenti** validi in whitelist
- **Totale**: 184,800₽

#### 3. Componente 2: Sincronizzatore Lezioni ✅
- [x] Funzione `sync_lessons_from_calendar()` in `association_resolver.py`
- [x] Lettura eventi da Google Calendar
- [x] Estrazione nome studente dal titolo evento
- [x] Inserimento/aggiornamento lezioni nel DB
- [x] Deduplicazione via `nextcloud_event_id` (UNIQUE)
- [x] Gestione eventi ricorrenti (singleEvents=True)
- [x] Filtraggio solo lezioni passate (fino a oggi, no futuro)
- [x] Integrato come comando `/sync` nel bot

**Statistiche attuali:**
- **150 lezioni** sincronizzate (tutte stato='prevista')
- Range: ultimi 60 giorni fino a oggi

#### 4. Componente 3: Risolutore Associazioni ✅
- [x] **Script**: `association_resolver.py` (~1035 righe)
- [x] Bot Telegram interattivo con comandi
- [x] `/process` - Processa pagamenti non-skipped
- [x] `/suspended` - Riprocessa pagamenti saltati
- [x] `/sync` - Sincronizza lezioni da Google Calendar
- [x] Inline keyboard per selezione lezioni
- [x] Callback handlers per gestione risposte utente
- [x] Sistema skip/suspended per evitare loop
- [x] Auto-avanzamento al prossimo pagamento
- [x] Salvataggio associazioni studente-pagante
- [x] Riuso automatico associazioni esistenti
- [x] Rilevamento automatico abbonamenti (3/5/10 lezioni)
- [x] Supporto pagamenti parziali per lezioni condivise
- [x] Logging su file (`association_resolver.log`)
- [x] Ricerca lezioni ±3 giorni dalla data pagamento

#### 5. Componente 4: Interfaccia Web ✅
- [x] **App Flask**: `web_interface/app.py`
- [x] Vista a 2 colonne (lezioni | pagamenti)
- [x] Ordinamento indipendente per data
- [x] Selezione multipla con checkbox
- [x] Calcolo real-time bilancio crediti-debiti
- [x] Pulsante CONFERMA ABBINAMENTO (con validazione)
- [x] Distribuzione automatica su pagamenti multipli
- [x] Gestione abbinamenti e pagamenti parziali
- [x] Sezione ABBINAMENTI COMPLETATI
- [x] Pulsante elimina con ripristino stato
- [x] Query calcolo residuo pagamenti
- [x] Aggiornamento automatico stato pagamenti
- [x] Gestione errori SQL con rollback
- [x] Template HTML con Tailwind CSS
- [x] Bugfix applicati (vedi `BUGFIX_REPORT.md`)

#### 6. Google Calendar Integration ✅
- [x] Service Account creato su Google Cloud Console
- [x] API Google Calendar abilitata
- [x] Credenziali JSON scaricate (`fresh-electron-318314-050d19bd162e.json`)
- [x] Calendario "Lezioni Russo" condiviso con service account
- [x] **Script di test**: `gcal_connect_test.py`
- [x] Accesso verificato e funzionante
- [x] Timezone: Europe/Moscow

---

### 🚧 In Corso / Da Completare

#### Attività Immediate
- [ ] Processare i 90 pagamenti storici tramite bot o interfaccia web
- [ ] Creare associazioni studente-pagante per i 20 studenti
- [ ] Abbinare pagamenti alle 150 lezioni sincronizzate

#### Infrastruttura e Miglioramenti
- [ ] Logging strutturato per telegram_ingestor
- [ ] Unit tests per tutti i componenti
- [ ] Script di orchestrazione (esecuzione in sequenza)
- [ ] Scheduler automatico (cron/systemd per deployment)
- [ ] Backup automatico database
- [ ] Autenticazione interfaccia web
- [ ] Filtri per studente/data nell'interfaccia web
- [ ] Gestione validità temporale associazioni (valid_from, valid_to)
- [ ] File requirements.txt consolidato
- [ ] Documentazione diagrammi di flusso aggiornati

---

## 📁 Struttura File del Progetto

```
/home/arjuna/nextcloud/
├── .env                                    # Credenziali (gitignored)
├── .gitignore
├── to-do-list.txt                          # Task list dettagliata (AGGIORNATA)
├── project-status.md                       # Questo file (AGGIORNATO)
│
├── pagamenti.db                            # Database SQLite (90 pagamenti, 150 lezioni)
├── telegram_session.session                # Session Telegram salvata
├── association_resolver.log                # Log del bot Telegram
│
├── mittenti_whitelist.csv                  # Whitelist studenti (20 studenti)
├── fresh-electron-318314-*.json            # Credenziali Google Service Account
│
├── db_create_schema.py                     # Schema DB + setup
├── db_connect_test.py                      # Test connessione DB
│
├── telegram_ingestor.py                    # ✅ Componente 1 - Ingestore Pagamenti
├── association_resolver.py                 # ✅ Componente 3 - Bot Telegram (1035 righe)
├── payment_monitor.py                      # Monitor pagamenti in tempo reale
├── test_bot.py                             # Test bot Telegram
│
├── get_channel_id.py                       # Utility per ID canale Telegram
├── get_channel_id_forward.py               # Utility alternativa
│
├── gcal_connect_test.py                    # ✅ Test Google Calendar
├── nextcloud_connect_test.py               # Test vecchio (Nextcloud, deprecato)
│
├── web_interface/                          # ✅ Interfaccia Web Flask
│   ├── app.py                              # App Flask principale
│   ├── templates/
│   │   └── index.html                      # Template HTML
│   ├── README.md                           # Documentazione web interface
│   └── BUGFIX_REPORT.md                    # Report correzioni bug
│
├── utils/                                  # Utility e helper functions
│   └── name_matcher.py                     # Fuzzy matching nomi (non usato ancora)
│
└── .cal/                                   # Virtual environment Python
    ├── bin/
    │   └── python
    └── lib/
        └── python3.10/site-packages/
```

---

## 🔐 Credenziali Configurate

### File `.env`
```bash
# Telegram Bot (receiver)
BOT_TOKEN=7762615672:AAFK0-ZcJIN2f27ePQaxhsL-kfwZqaFWsJo

# Telegram User API (Telethon)
API_ID=21581367
API_HASH=96c0f7df64d4422476f6a988f5dae600
PHONE_NUMBER=+79168231142
TELEGRAM_PASSWORD=j9099Wjkio
CHANNEL_ID=-1002452167729

# Google Calendar
GCAL_CALENDAR_ID=5e7ecd0336fee20b4ae7b132634044396c0babf455b22c35cbde6986392cccb1@group.calendar.google.com
GCAL_SERVICE_ACCOUNT_FILE=fresh-electron-318314-050d19bd162e.json

# Nextcloud (deprecato)
NC_PASS=gGPFk-fBHbm-p6tc2-bw6GF-HfmzQ
```

---

## 🔧 Dipendenze Python

### Installate
- `python-telegram-bot` - Bot API Telegram
- `telethon` - User API Telegram (per leggere messaggi canale)
- `caldav` - Accesso CalDAV (Nextcloud, deprecato)
- `python-dotenv` - Gestione variabili d'ambiente
- `google-api-python-client` - Google Calendar API
- `google-auth-httplib2` - Autenticazione Google
- `google-auth-oauthlib` - OAuth2 Google

---

## 🎯 Prossimi Passi Prioritari

### Fase 1: Abbinamento Storico (IN CORSO)
1. **Processare pagamenti storici**
   - Opzione A: Usare bot Telegram (`/process`) per abbinamenti interattivi
   - Opzione B: Usare interfaccia web per abbinamenti batch
   - Creare le 0→20+ associazioni studente-pagante

2. **Completare abbinamenti**
   - Abbinare i 90 pagamenti alle 150 lezioni
   - Verificare che tutti i pagamenti siano allocati correttamente
   - Controllare residui e crediti

### Fase 2: Testing e Validazione
3. **Test end-to-end**
   - Verificare workflow completo: ingestion → sync → abbinamento
   - Testare casi edge (abbonamenti, lezioni condivise, pagamenti parziali)
   - Controllare integrità dati nel database

4. **Monitoraggio in produzione**
   - Attivare `payment_monitor.py` per nuovi pagamenti
   - Testare notifiche in tempo reale
   - Verificare sincronizzazione automatica

### Fase 3: Automazione (FUTURO)
5. **Orchestrazione**
   - Script master per esecuzione in sequenza
   - Scheduler automatico (cron/systemd)
   - Gestione errori e retry

6. **Miglioramenti**
   - Autenticazione web interface
   - Filtri avanzati per ricerca
   - Dashboard statistiche
   - Export CSV/Excel

---

## 📝 Note Tecniche

### Formato SMS Banca Russa
```
СЧЁТ3185 20:18 Перевод 2000р от Сергей Х. Баланс: 15234р
```

Regex pattern:
```python
r'СЧЁТ\d+\s+(\d{1,2}):(\d{2})\s+Перевод.*?([\d\s]+)р\s+от\s+([А-ЯЁA-Za-zА-яё]+(?:\s+[А-ЯЁA-Za-zА-яё]\.?)?)'
```

### Timezone
- Calendario Google: `Europe/Moscow`
- Database: Date/time senza timezone (naive)
- Conversioni da gestire quando necessario

### Deduplicazione
- **Pagamenti**: `fonte_msg_id = "tg_{CHANNEL_ID}_{message_id}"`
- **Lezioni**: `nextcloud_event_id` (Google Calendar event ID)

---

## 🐛 Issues Noti

1. **Parsing SMS**: Ancora 1 messaggio su 100 che fallisce il parsing
   - Probabilmente formato SMS diverso o caratteri speciali

2. **Nomi Studenti**: Alcuni eventi hanno nomi non normalizzati
   - Es: "YanaVasilisa" vs "Yana Vasilisa"
   - Necessario preprocessing

3. **Eventi Ricorrenti**: Google Calendar restituisce istanze multiple
   - Event ID ha formato: `base_id_YYYYMMDDTHHMMSSZ`
   - Serve logica per gestire correttamente

---

## 📈 Metriche Progetto

- **Linee di codice**: ~2733 (python totale)
  - telegram_ingestor.py: ~250 righe
  - association_resolver.py: ~1035 righe
  - web_interface/app.py: ~260 righe
  - Altri script: ~1200 righe
- **Tabelle database**: 4 (pagamenti, lezioni, associazioni, pagamenti_lezioni)
- **Script funzionanti**: 8+ (ingestor, bot, web, tests, utilities)
- **Test eseguiti**: 10+
- **Pagamenti tracciati**: 90 (tutti in stato 'sospeso')
- **Lezioni sincronizzate**: 150 (tutte in stato 'prevista')
- **Studenti attivi**: 20 (in whitelist)
- **Abbinamenti**: 0 (pronti per essere creati)

---

## 🚀 Deployment (Futuro)

### Pianificazione Esecuzione
```
08:00 MSK - Componente 1: Ingestore Pagamenti
08:02 MSK - Componente 2: Sincronizzatore Lezioni
08:05 MSK - Componente 3: Risolutore Associazioni
08:10 MSK - Componente 4: Associatore Pagamenti-Lezioni
```

### Meccanismo
- Cron job / systemd timer
- Script bash orchestrator
- Logging su file rotazionali
- Notifiche errori via Telegram

---

## 👤 Contatti Service Account

**Email Service Account Google:**
```
calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com
```

Questo account ha accesso al calendario "Lezioni Russo" e può leggere/modificare gli eventi.

---

---

## 📝 Note di Versione

**v2.0 - 2025-10-09** (MAJOR UPDATE)
- ✅ Completato bot Telegram interattivo con 3 comandi
- ✅ Completata interfaccia web Flask
- ✅ Sincronizzatore lezioni integrato
- ✅ 150 lezioni sincronizzate da Google Calendar
- ✅ Sistema abbonamenti e pagamenti parziali
- ✅ Bugfix applicati all'interfaccia web
- 📊 Database: 90 pagamenti + 150 lezioni pronti per abbinamento

**v1.0 - 2025-08-25** (Initial Release)
- ✅ Ingestore pagamenti da Telegram
- ✅ Schema database completo
- ✅ 90 pagamenti storici importati
- ✅ Integrazione Google Calendar testata

---

*Ultimo aggiornamento: 2025-10-09 - 15:30*
