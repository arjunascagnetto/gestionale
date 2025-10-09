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
- [x] Schema completo con indici e trigger

#### 2. Componente 1: Ingestore Pagamenti
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
- 90 pagamenti nel DB
- 20 studenti validi
- Totale: 184,800₽

#### 3. Google Calendar Integration
- [x] Service Account creato su Google Cloud Console
- [x] API Google Calendar abilitata
- [x] Credenziali JSON scaricate (`fresh-electron-318314-050d19bd162e.json`)
- [x] Calendario "Lezioni Russo" condiviso con service account
- [x] **Script di test**: `gcal_connect_test.py`
- [x] Accesso verificato, 50+ eventi letti
- [x] Timezone: Europe/Moscow

---

### 🚧 In Corso / Da Completare

#### Componente 2: Sincronizzatore Lezioni
- [ ] Creare script per leggere eventi da Google Calendar
- [ ] Estrarre nome studente dal titolo evento
- [ ] Inserire/aggiornare lezioni nel DB
- [ ] Gestire deduplicazione via `nextcloud_event_id`
- [ ] Gestire eventi ricorrenti

#### Componente 3: Risolutore Associazioni
- [ ] Logica di matching automatico nomi
- [ ] Interfaccia Telegram per conferma associazioni
- [ ] Sistema di inline keyboard
- [ ] Callback handlers
- [ ] Salvataggio associazioni nel DB

#### Componente 4: Associatore Pagamenti-Lezioni
- [ ] Algoritmo di matching pagamenti ↔ lezioni
- [ ] Gestione pagamenti parziali/multipli
- [ ] Aggiornamento stati (pagamenti e lezioni)
- [ ] Notifiche Telegram per discrepanze
- [ ] Report periodici via Telegram

#### Infrastruttura
- [ ] Logging strutturato per tutti i componenti
- [ ] Unit tests
- [ ] Script di orchestrazione (esecuzione in sequenza)
- [ ] Scheduler automatico (cron/systemd)
- [ ] Backup automatico database
- [ ] Gestione errori e retry

---

## 📁 Struttura File del Progetto

```
/home/arjuna/nextcloud/
├── .env                                    # Credenziali (gitignored)
├── .gitignore
├── to-do-list.txt                          # Task list dettagliata
├── project-status.md                       # Questo file
│
├── pagamenti.db                            # Database SQLite
├── telegram_session.session                # Session Telegram salvata
│
├── mittenti_whitelist.csv                  # Whitelist studenti
├── fresh-electron-318314-*.json            # Credenziali Google Service Account
│
├── db_create_schema.py                     # Schema DB + setup
├── db_connect_test.py                      # Test connessione DB
│
├── telegram_ingestor.py                    # ✅ Componente 1 - Ingestore Pagamenti
├── get_channel_id.py                       # Utility per ID canale Telegram
├── get_channel_id_forward.py               # Utility alternativa
│
├── gcal_connect_test.py                    # ✅ Test Google Calendar
├── nextcloud_connect_test.py               # Test vecchio (Nextcloud, deprecato)
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

1. **Completare Componente 2**: Sincronizzatore Lezioni
   - Creare `gcal_lesson_sync.py`
   - Leggere eventi da Google Calendar
   - Inserire nel DB tabella `lezioni`

2. **Implementare Matching Nomi**
   - Logica fuzzy matching tra nome_studente e nome_pagante
   - Gestire variazioni (es. "Ekaterina" vs "Екатерина А.")

3. **Bot Telegram per Associazioni**
   - Creare bot interattivo per confermare associazioni
   - Inline keyboard con opzioni multiple

4. **Orchestrazione**
   - Script master che esegue i componenti in sequenza
   - Gestione errori e logging

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

- **Linee di codice**: ~800 (python)
- **Tabelle database**: 4
- **Script funzionanti**: 3
- **Test eseguiti**: 5+
- **Pagamenti tracciati**: 90
- **Studenti attivi**: 20
- **Eventi calendario**: 50+

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

*Ultimo aggiornamento: 2025-10-09*
