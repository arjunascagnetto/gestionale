# Sistema Gestione Pagamenti Lezioni Russo

## 📋 Panoramica

Sistema duale per gestire pagamenti e lezioni:
- **Bot Telegram**: Gestione pagamenti FUTURI in tempo reale
- **Interfaccia Web** (da implementare): Gestione STORICO pagamenti

---

## 🤖 Bot Telegram - Pagamenti Futuri

### Componenti

#### 1. `payment_monitor.py`
**Funzione**: Monitora nuovi pagamenti ogni ora
- Esegue `telegram_ingestor.py` per importare nuovi SMS
- Rileva pagamenti ricevuti nell'ultima ora
- Invia notifica Telegram con lezioni dello STESSO GIORNO
- Permette associazione immediata o archiviazione

**Esecuzione**:
```bash
.cal/bin/python payment_monitor.py
```

**Funzionamento**:
1. Ogni ora legge il canale Telegram
2. Trova nuovi pagamenti (non ancora notificati)
3. Per ogni pagamento:
   - Cerca lezioni dello stesso giorno
   - Invia messaggio con pulsanti interattivi
   - Aspetta risposta utente

#### 2. `association_resolver.py`
**Funzione**: Bot Telegram interattivo
- Gestisce callback da `payment_monitor.py`
- Salva associazioni pagamento→lezione
- Gestisce archivio per pagamenti da processare via web

**Callback supportati**:
- `newpay_{payment_id}_{lesson_id}` - Associa pagamento a lezione
- `archive_{payment_id}` - Archivia per gestione web

**Comandi**:
- `/start` - Info bot
- `/sync` - Sincronizza lezioni da Google Calendar

---

## 🗄️ Database

### Nuove Colonne

**Tabella `pagamenti`**:
- `notificato` (INTEGER) - 0=non notificato, 1=notificato via Telegram
- `stato` - Valori: `sospeso`, `associato`, `archivio`

### Stati Pagamento

| Stato | Significato |
|-------|-------------|
| `sospeso` | Pagamento importato, non ancora processato |
| `associato` | Pagamento associato a lezione/i |
| `archivio` | Pagamento da gestire via interfaccia web |

---

## 📊 Workflow Nuovo Pagamento

```
1. SMS arriva su canale Telegram
   ↓
2. payment_monitor.py legge canale (ogni ora)
   ↓
3. telegram_ingestor.py importa in DB
   ↓
4. payment_monitor.py rileva nuovo pagamento
   ↓
5. Cerca lezioni dello STESSO GIORNO
   ↓
6. Invia notifica Telegram con pulsanti
   ↓
7. OPZIONI UTENTE:

   A) Clicca su lezione
      → Salva in pagamenti_lezioni
      → Crea associazione pagante→studente
      → Stato = 'associato'

   B) Clicca "Archivia"
      → Stato = 'archivio'
      → Da gestire via web
```

---

## 🌐 Interfaccia Web (Da Implementare)

### Funzionalità Richieste

1. **Visualizzazione Storico**
   - Tabella pagamenti archiviati
   - Filtri per data, studente, importo
   - Ricerca per nome pagante

2. **Gestione Associazioni**
   - Cerca lezioni in range date (±7 giorni)
   - Associazione manuale pagamento→lezioni
   - Supporto abbonamenti multipli
   - Gestione quote parziali

3. **Statistiche**
   - Pagamenti per studente
   - Lezioni pagate vs non pagate
   - Abbonamenti attivi

4. **Export**
   - CSV/Excel storico
   - Report mensili

### Tecnologie Suggerite
- **Framework**: Flask o FastAPI
- **DB**: SQLite esistente
- **Frontend**: HTML + Bootstrap + HTMX (lightweight)
- **Autenticazione**: Password singola (ambiente domestico)

---

## 🚀 Avvio Sistema

### 1. Bot Telegram (sempre attivo)
```bash
# In un terminale separato
cd /home/arjuna/nextcloud
.cal/bin/python association_resolver.py
```

### 2. Payment Monitor (sempre attivo)
```bash
# In un altro terminale
cd /home/arjuna/nextcloud
.cal/bin/python payment_monitor.py
```

### 3. Opzionale: Sincronizza lezioni manualmente
Via bot Telegram: `/sync`

---

## 📁 File Principali

| File | Scopo |
|------|-------|
| `payment_monitor.py` | Monitor pagamenti (ogni ora) |
| `telegram_ingestor.py` | Import SMS da Telegram |
| `association_resolver.py` | Bot interattivo Telegram |
| `pagamenti.db` | Database SQLite |
| `utils/name_matcher.py` | Fuzzy matching nomi (non usato attualmente) |

---

## 🔧 Configurazione

File `.env`:
```bash
BOT_TOKEN=...              # Bot Telegram receiver
ADMIN_CHAT_ID=...          # Tuo chat ID
CHANNEL_ID=...             # Canale SMS Telegram
API_ID=...                 # Telethon API ID
API_HASH=...               # Telethon API Hash
PHONE_NUMBER=...           # Numero telefono
TELEGRAM_PASSWORD=...      # Password 2FA
GCAL_CALENDAR_ID=...       # ID calendario Google
GCAL_SERVICE_ACCOUNT_FILE=...  # JSON service account
```

---

## 📝 Note Importanti

1. **Storico**: I 90 pagamenti esistenti sono in stato `sospeso`
   - NON verranno notificati da `payment_monitor` (solo nuovi pagamenti)
   - Verranno gestiti tramite interfaccia web

2. **Timing**: `payment_monitor` controlla ogni ora
   - Puoi ridurre/aumentare l'intervallo modificando `asyncio.sleep(3600)`

3. **Lezioni stesso giorno**: Mostra SOLO lezioni della stessa data del pagamento
   - Nessun range ±3 giorni per pagamenti futuri
   - Semplifica l'associazione

4. **Archivio**: Pagamenti archiviati rimangono in `pagamenti.db`
   - `stato = 'archivio'`
   - Accessibili via query SQL o interfaccia web

---

## 🛠️ Prossimi Sviluppi

- [ ] Interfaccia web per storico
- [ ] Dashboard statistiche
- [ ] Sistema di backup automatico
- [ ] Notifiche per lezioni senza pagamento
- [ ] Report mensili automatici
