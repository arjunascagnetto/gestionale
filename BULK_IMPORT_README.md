# 📥 Import Completo Dati Storici

## Panoramica

Questo documento descrive gli script per l'importazione completa dei dati storici dal **1 agosto 2024 a oggi**:

- **Pagamenti** da Telegram (messaggi SMS bancari)
- **Lezioni** da Google Calendar

---

## 🎯 Script Disponibili

### 1. `telegram_bulk_ingestor.py`
**Scarica TUTTI i pagamenti da Telegram (nessun limite)**

Differenze rispetto a `telegram_ingestor.py`:
- ✅ Nessun limite di 100 messaggi
- ✅ Range di date configurabile (1 agosto → oggi)
- ✅ **Paginazione automatica** - scarica a batch di 100 messaggi
- ✅ **Rate limiting** - pausa 3 secondi tra batch (rispetta limite Telegram 20 req/sec)
- ✅ **Gestione FloodWait** - attende automaticamente se Telegram lo richiede
- ✅ Statistiche dettagliate
- ✅ Report totale importo e numero pagamenti

**Uso:**
```bash
.cal/bin/python telegram_bulk_ingestor.py
```

**Output:**
- Scarica tutti i messaggi dal canale Telegram
- Filtra solo SMS bancari con pagamenti
- Applica whitelist studenti
- Inserisce nel DB con deduplicazione
- Mostra riepilogo: messaggi, pagamenti inseriti, totale importo

---

### 2. `gcal_bulk_sync.py`
**Sincronizza TUTTE le lezioni da Google Calendar**

Differenze rispetto a `sync_lessons_from_calendar()`:
- ✅ Range di date configurabile (1 agosto → oggi)
- ✅ Statistiche per studente
- ✅ Report dettagliato lezioni per studente
- ✅ Esclusione automatica eventi "prova" (lezioni gratis)

**Uso:**
```bash
.cal/bin/python gcal_bulk_sync.py
```

**Output:**
- Scarica tutti gli eventi dal calendario
- Filtra solo lezioni (esclude "prova")
- Normalizza nomi studenti
- Inserisce/aggiorna nel DB con deduplicazione
- Mostra statistiche per studente

---

### 3. `bulk_import_all.py` ⭐
**Script MASTER - esegue tutto in automatico**

Esegue in sequenza:
1. Scaricamento pagamenti da Telegram
2. Sincronizzazione lezioni da Google Calendar

**Uso:**
```bash
.cal/bin/python bulk_import_all.py
```

**Vantaggi:**
- ✅ Un solo comando per tutto
- ✅ Gestione errori automatica
- ✅ Output in tempo reale
- ✅ Riepilogo finale

---

## 🚀 Quick Start

### Opzione A: Import completo automatico (CONSIGLIATO)

```bash
# Esegui tutto in un colpo
.cal/bin/python bulk_import_all.py
```

Questo script:
1. Verifica che tutto sia configurato correttamente
2. Scarica tutti i pagamenti da Telegram
3. Sincronizza tutte le lezioni da Google Calendar
4. Mostra statistiche dettagliate

### Opzione B: Import manuale (step by step)

```bash
# Step 1: Scarica pagamenti
.cal/bin/python telegram_bulk_ingestor.py

# Step 2: Sincronizza lezioni
.cal/bin/python gcal_bulk_sync.py
```

---

## 📊 Configurazione

### Range di Date

**Default:** 1 agosto 2024 → oggi

Per cambiare il range, modifica le variabili nei file:

**telegram_bulk_ingestor.py:**
```python
START_DATE = datetime(2024, 8, 1)  # Cambia qui
END_DATE = datetime.now()
```

**gcal_bulk_sync.py:**
```python
START_DATE = datetime(2024, 8, 1)  # Cambia qui
END_DATE = datetime.now()
```

### Rate Limiting (Telegram)

**Default:** 100 messaggi/batch, 3 secondi tra batch

Per modificare (se ricevi FloodWait frequenti):

**telegram_bulk_ingestor.py:**
```python
BATCH_SIZE = 100  # Riduci a 50 se hai problemi
DELAY_BETWEEN_BATCHES = 3  # Aumenta a 5-10 se necessario
```

**Limiti Telegram API:**
- Max 20 richieste al secondo
- FloodWait può essere richiesto se troppi messaggi in poco tempo
- Lo script gestisce automaticamente FloodWait, ma puoi ridurre BATCH_SIZE per prevenire

---

## 🔍 Cosa Succede Durante l'Import

### Pagamenti (Telegram)

1. **Connessione** a Telegram tramite Telethon (User API)
2. **Scaricamento** di TUTTI i messaggi dal canale nel range di date
   - **Paginazione:** scarica a batch di 100 messaggi
   - **Rate limiting:** pausa 3s tra batch (max 20 req/sec Telegram)
   - **FloodWait:** se Telegram richiede attesa, lo script si mette in pausa automaticamente
3. **Parsing** con regex per estrarre:
   - Nome pagante
   - Data e ora
   - Importo
4. **Filtro** whitelist (solo studenti validi)
5. **Inserimento** nel DB con deduplicazione (fonte_msg_id)
6. **Report** finale con statistiche

### Lezioni (Google Calendar)

1. **Connessione** a Google Calendar tramite Service Account
2. **Scaricamento** di TUTTI gli eventi dal calendario nel range di date
3. **Filtro** eventi "prova" (lezioni gratis)
4. **Normalizzazione** nomi studenti (es. "dmitry1" → "dmitry")
5. **Inserimento** nel DB con deduplicazione (nextcloud_event_id)
6. **Report** finale con statistiche per studente

---

## ⚙️ Prerequisiti

### Credenziali Telegram (.env)
```bash
API_ID=...
API_HASH=...
CHANNEL_ID=...
PHONE_NUMBER=...
TELEGRAM_PASSWORD=...
```

### Credenziali Google Calendar (.env)
```bash
GCAL_CALENDAR_ID=...
GCAL_SERVICE_ACCOUNT_FILE=fresh-electron-318314-*.json
```

### Whitelist Studenti
File `mittenti_whitelist.csv`:
```csv
nome_pagante,studente
Anna,1
Boris,1
Carlo,0
```

---

## 🗄️ Database

Gli script popolano le tabelle:

**`pagamenti`**
- `id_pagamento` (PK)
- `nome_pagante` (TEXT)
- `giorno` (DATE)
- `ora` (TIME)
- `somma` (NUMERIC)
- `valuta` (TEXT, default 'RUB')
- `stato` (TEXT, default 'sospeso')
- `fonte_msg_id` (TEXT, UNIQUE) ← deduplicazione

**`lezioni`**
- `id_lezione` (PK)
- `nome_studente` (TEXT)
- `giorno` (DATE)
- `ora` (TIME)
- `durata_min` (INTEGER, default 60)
- `nextcloud_event_id` (TEXT, UNIQUE) ← deduplicazione
- `stato` (TEXT, default 'prevista')
- `costo` (NUMERIC, default 2000)

---

## 📈 Output Esempio

### telegram_bulk_ingestor.py

```
============================================================
SCARICAMENTO COMPLETO PAGAMENTI DA TELEGRAM
============================================================
Canale: -1002452167729
Database: pagamenti.db
Range date: 01/08/2024 → 10/10/2024
============================================================

✅ Whitelist caricata: 20 studenti validi

🔐 Autenticazione Telegram in corso...
✅ Client Telegram connesso

📥 Recupero TUTTI i messaggi dal canale -1002452167729
   Range: 2024-08-01 → 2024-10-10
   (NESSUN LIMITE - scaricamento completo)

   📊 Scaricati 50 messaggi...
   📊 Scaricati 100 messaggi...
   ...

✅ Trovati 250 messaggi con testo nel range di date

📝 Processamento messaggi...

✅ Inserito: Anna - 2000₽ - 2024-08-05 14:30:00
✅ Inserito: Boris - 6600₽ - 2024-08-12 18:45:00
🚫 Filtrato: Marco - 1500₽ (non è studente)
...

============================================================
RIEPILOGO SCARICAMENTO COMPLETO
============================================================
Range date: 01/08/2024 → 10/10/2024
Messaggi trovati: 250
Pagamenti inseriti: 145
Già esistenti (saltati): 10
Filtrati (non studenti): 85
Errori di parsing: 10
------------------------------------------------------------
TOTALE nel database: 155 pagamenti
TOTALE importo: 310,000.00 RUB
============================================================
```

### gcal_bulk_sync.py

```
============================================================
SINCRONIZZAZIONE COMPLETA LEZIONI DA GOOGLE CALENDAR
============================================================
Service Account: fresh-electron-318314-050d19bd162e.json
Database: pagamenti.db
Range date: 01/08/2024 → 10/10/2024
============================================================

✅ Connessione al Google Calendar API stabilita

✅ Calendario trovato: Lezioni Russo
   Timezone: Europe/Moscow

📥 Sincronizzazione lezioni da Google Calendar
   Range: 2024-08-01 → 2024-10-10
   Calendario: 5e7ecd0336fee20b4ae7b132634044396c0ba...

🔍 Recupero eventi dal calendario...
✅ Trovati 320 eventi totali

📝 Processamento eventi...

   Processati 50/320 eventi...
   Processati 100/320 eventi...
   ...

✅ Sincronizzato: Anna - 2024-08-05 14:00:00
✅ Sincronizzato: Boris - 2024-08-12 18:00:00
🎁 Lezione gratis (prova): prova Yana - 2024-08-01
...

============================================================
RIEPILOGO SINCRONIZZAZIONE LEZIONI
============================================================
Eventi trovati: 320
Lezioni sincronizzate: 280
Lezioni gratis (prova): 35
Errori: 5
------------------------------------------------------------
TOTALE nel database: 280 lezioni
============================================================

📊 LEZIONI PER STUDENTE:
------------------------------------------------------------
   Anna................................ 45 lezioni
   Boris............................... 38 lezioni
   Carlo............................... 32 lezioni
   Dmitry.............................. 28 lezioni
   Elena............................... 25 lezioni
   ...
------------------------------------------------------------
   TOTALE.............................. 280 lezioni
   Studenti attivi.....................  18
============================================================
```

---

## 🛠️ Troubleshooting

### Errore: "Session file not found"
**Soluzione:** Il file `telegram_session.session` non esiste. Verrà creato automaticamente al primo login.

### Errore: "Calendar not found"
**Soluzione:** Verifica di aver condiviso il calendario con il service account:
```
calendar-service-account@fresh-electron-318314.iam.gserviceaccount.com
```

### Errore: "API rate limit" o "FloodWaitError"
**Soluzione:**
- Lo script gestisce automaticamente i FloodWait di Telegram
- Se ricevi un errore persistente, attendi 5-10 minuti e riprova
- Puoi ridurre `BATCH_SIZE` o aumentare `DELAY_BETWEEN_BATCHES` nel file .py

### Nessun pagamento inserito
**Cause possibili:**
1. Whitelist troppo restrittiva → verifica `mittenti_whitelist.csv`
2. Regex non matcha i messaggi → verifica formato SMS
3. Messaggi già importati → normale, deduplicazione attiva

---

## 📝 Note Importanti

### Deduplicazione
- **Pagamenti:** Basata su `fonte_msg_id` (es. "tg_-1002452167729_12345")
- **Lezioni:** Basata su `nextcloud_event_id` (ID evento Google Calendar)

**Conseguenza:** Puoi eseguire gli script più volte senza duplicare i dati.

### Eventi "prova" (Lezioni Gratis)
Gli eventi con titolo che inizia con "prova" vengono **automaticamente esclusi** perché sono lezioni di prova gratis (non richiedono pagamento).

### Normalizzazione Nomi
I nomi studenti vengono normalizzati:
- "dmitry1" → "dmitry"
- "YanaVasilisa" → "YanaVasilisa" (mantiene CamelCase se presente)

Puoi aggiungere altre regole di normalizzazione nel codice.

---

## 🎯 Prossimi Passi (dopo l'import)

1. **Verifica dati:**
   ```bash
   sqlite3 pagamenti.db "SELECT COUNT(*) FROM pagamenti;"
   sqlite3 pagamenti.db "SELECT COUNT(*) FROM lezioni;"
   ```

2. **Avvia bot per abbinamenti:**
   ```bash
   .cal/bin/python association_resolver.py
   # Poi usa /process su Telegram
   ```

3. **Oppure usa interfaccia web:**
   ```bash
   cd web_interface
   ../.cal/bin/python app.py
   # Apri http://localhost:5000
   ```

---

## 📞 Supporto

Per problemi o domande, controlla:
- `project-status.md` - Stato generale del progetto
- `to-do-list.txt` - Task list completa
- Log files: `association_resolver.log`

---

**Ultimo aggiornamento:** 2024-10-10
**Versione:** 1.0
