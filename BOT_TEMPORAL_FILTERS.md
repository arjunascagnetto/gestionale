# 🕒 Filtri Temporali Bot Telegram

**Data**: 2025-10-10
**File modificato**: `association_resolver.py`
**Versione**: 1.2 (filtri temporali)

---

## 🎯 Obiettivo Modifiche

Modificare il bot Telegram per processare **SOLO pagamenti e lezioni di OGGI** (stesso giorno dell'esecuzione).

### Motivazione
- Il bot deve essere usato per associazioni **immediate** e **quotidiane**
- Tutto il resto (storico, abbinamenti passati) gestito via **interfaccia web**
- **MAI nel futuro**, **MAI nel passato** (nemmeno ieri)
- **SOLO OGGI**: se oggi è 10/10/2025, mostra solo pagamenti e lezioni del 10/10/2025

---

## 🔧 Modifiche Implementate

### 1. Filtro Pagamenti (linee 239-306)

**Funzione**: `get_unassociated_payments()`

**Modifiche applicate**:
```python
# Calcola SOLO data di oggi
today = datetime.now().date()

# Aggiunto filtro date in entrambe le query SQL
WHERE p.stato = 'sospeso'
    AND p.giorno = ?
```

**Risultato**:
- ✅ Solo pagamenti di OGGI (stesso giorno)
- ✅ Esclude automaticamente pagamenti storici (anche di ieri)
- ✅ Esclude automaticamente pagamenti futuri

---

### 2. Filtro Lezioni (linee 180-186)

**Funzione**: `process_payment()`

**PRIMA** (range ±3 giorni):
```python
cursor.execute('''
    SELECT id_lezione, nome_studente, giorno, ora
    FROM lezioni
    WHERE giorno BETWEEN date(?, '-3 days') AND date(?, '+3 days')
    ORDER BY giorno ASC, ora ASC
''', (payment_date, payment_date))
```

**DOPO** (solo stesso giorno):
```python
cursor.execute('''
    SELECT id_lezione, nome_studente, giorno, ora
    FROM lezioni
    WHERE giorno = ?
    ORDER BY ora ASC
''', (payment_date,))
```

**Risultato**:
- ✅ Solo lezioni dello **stesso giorno** del pagamento
- ✅ Ordinamento per ora (non più per giorno + ora)
- ✅ Nessuna lezione passata oltre il giorno del pagamento
- ✅ Nessuna lezione futura

---

### 3. Messaggi Utente Aggiornati

**Modifiche ai messaggi Telegram**:

**Nessuna lezione trovata**:
```python
# PRIMA
f"Non ci sono lezioni nel range ±3 giorni.\n"

# DOPO
f"Non ci sono lezioni per questo giorno.\n"
```

**Titolo lista lezioni**:
```python
# PRIMA
f"\n📚 <b>Lezioni vicine (±3 giorni):</b>\n"

# DOPO
f"\n📚 <b>Lezioni di oggi:</b>\n"
```

**Log messaggi**:
```python
# PRIMA
logger.info(f"Trovate {len(lessons_in_range)} lezioni nel range ±3 giorni")

# DOPO
logger.info(f"Trovate {len(lessons_in_range)} lezioni per il giorno {payment_date}")
```

---

## 📊 Statistiche Modifiche

| Componente | Prima | Dopo |
|------------|-------|------|
| Range pagamenti | Tutti | **SOLO OGGI** |
| Range lezioni | ±3 giorni | **SOLO OGGI** (stesso giorno pagamento) |
| Pagamenti processabili | Storici inclusi | Solo di oggi |
| Lezioni mostrate | 7 giorni totali | Solo di oggi |

---

## 🧪 Test Effettuati

### Verifica Dati Disponibili
```bash
# Pagamenti OGGI (2025-10-10): 3 trovati
# Lezioni OGGI (2025-10-10): 4 trovate
```

### Test Avvio Bot
```
✅ Bot avviato correttamente (process ID: 6d5637)
✅ Sincronizzate 145 lezioni da Google Calendar
✅ Application started - in ascolto
```

### Test Funzionale Manuale
**Requisiti per test utente**:
1. Invia `/process` al bot
2. Verifica che vengano mostrati SOLO pagamenti di oggi/ieri (max 6)
3. Verifica che per ogni pagamento vengano mostrate SOLO lezioni dello stesso giorno
4. Conferma che NON appaiano pagamenti storici (es. 1 settimana fa)

---

## 🔍 Comportamento Atteso

### Scenario 1: Pagamento di Oggi + Lezione di Oggi
```
✅ Bot mostra il pagamento
✅ Bot mostra le lezioni dello stesso giorno
✅ Associazione possibile
```

### Scenario 2: Pagamento di Ieri (09/10/2025) + Lezione di Ieri
```
❌ Bot NON mostra il pagamento (non è oggi)
→ Gestisci via interfaccia web
```

### Scenario 3: Pagamento di 3 Giorni Fa
```
❌ Bot NON mostra il pagamento
→ Gestisci via interfaccia web
```

### Scenario 4: Pagamento di Oggi + Lezione di Ieri
```
✅ Bot mostra il pagamento (di oggi)
❌ Bot NON mostra lezione (di ieri, giorno diverso)
⚠️  Messaggio: "Non ci sono lezioni per questo giorno"
→ Skip e gestisci via web
```

### Scenario 5: Pagamento di Oggi + Lezione Futura
```
✅ Bot mostra il pagamento (di oggi)
❌ Bot NON mostra lezione futura
⚠️  Messaggio: "Non ci sono lezioni per questo giorno"
→ Skip e gestisci via web
```

---

## 🆚 Confronto Bot vs Web Interface

| Funzionalità | Bot Telegram | Interfaccia Web |
|--------------|--------------|-----------------|
| Range temporale | **SOLO OGGI** | Tutto lo storico |
| Tipo associazioni | Immediate/quotidiane | Storiche + correzioni |
| Flessibilità date | Nessuna (fisso a oggi) | Completa |
| Filtri personalizzati | NO | SÌ |
| Pagamenti multipli | 1 alla volta | Batch/ricerca |
| Editing abbinamenti | NO | SÌ |

**Conclusione**: Bot per **routine giornaliera**, Web per **gestione completa**.

---

## 📝 Compatibilità

- ✅ **Backward compatible**: Non rompe associazioni esistenti
- ✅ **Schema DB**: Nessuna migrazione necessaria
- ✅ **API Google Calendar**: Nessun cambio
- ✅ **API Telegram**: Nessun cambio nelle callback
- ✅ **Sintassi Python**: Verificata con `py_compile` ✅

---

## 🚀 Deployment

### Update su Produzione (Linode)
```bash
# SSH al server
ssh lezioni-russo@your-linode-ip

# Update codice
cd ~/lezioni-russo
git pull  # o rsync dal PC locale

# Restart bot service
sudo systemctl restart lezioni-russo-bot

# Verifica logs
sudo journalctl -u lezioni-russo-bot -f
```

---

## 🔄 Rollback (se necessario)

Se i nuovi filtri causano problemi, ecco come tornare indietro:

### 1. Ripristina Range Pagamenti
In `get_unassociated_payments()`:
```python
# Rimuovi queste linee:
today = datetime.now().date()
yesterday = today - timedelta(days=1)

# Rimuovi dai WHERE:
AND p.giorno >= ?
AND p.giorno <= ?

# Rimuovi dai parametri:
, (str(yesterday), str(today))
```

### 2. Ripristina Range Lezioni ±3 Giorni
In `process_payment()`:
```python
cursor.execute('''
    SELECT id_lezione, nome_studente, giorno, ora
    FROM lezioni
    WHERE giorno BETWEEN date(?, '-3 days') AND date(?, '+3 days')
    ORDER BY giorno ASC, ora ASC
''', (payment_date, payment_date))
```

### 3. Ripristina Messaggi
```python
f"Non ci sono lezioni nel range ±3 giorni.\n"
f"\n📚 <b>Lezioni vicine (±3 giorni):</b>\n"
logger.info(f"Trovate {len(lessons_in_range)} lezioni nel range ±3 giorni")
```

---

## 📞 Note Importanti

1. **Sync Google Calendar**: Il comando `/sync` continua a sincronizzare ultimi 60 giorni fino a OGGI (nessun futuro)
2. **Pagamenti skipped**: Il filtro "SOLO OGGI" si applica anche ai pagamenti skipped (`/suspended`)
3. **Abbonamenti**: Funzionalità abbonamenti (3/5/10 lezioni) NON modificata, continua a funzionare
4. **Web Interface**: NON modificata, continua a mostrare tutto lo storico
5. **Comportamento**: Se oggi è 10/10/2025, il bot mostra SOLO pagamenti e lezioni del 10/10/2025. I pagamenti del 09/10 vanno gestiti via web.

---

## 🎯 Riepilogo Finale

**Oggi è**: 10 ottobre 2025

**Bot mostra**:
- Pagamenti: `WHERE giorno = '2025-10-10'` → **3 pagamenti**
- Lezioni: `WHERE giorno = '2025-10-10'` → **4 lezioni**

**Bot NON mostra**:
- Pagamenti del 9 ottobre (ieri)
- Lezioni del 9 ottobre
- Qualsiasi data passata o futura

**Per gestire tutto il resto**: Usa interfaccia web su `http://localhost:5000`

---

## 👨‍💻 Autore Modifiche

**Claude Code** - 2025-10-10
Modifiche applicate su richiesta esplicita utente per limitare bot a solo operazioni giornaliere.

---

## 📋 Riferimenti

- **Bug Fix Precedente**: `BUGFIX_REPORT_BOT.md` (IntegrityError duplicati)
- **Deployment Guide**: `DEPLOYMENT_LINODE.md`
- **Web Interface**: `web_interface/README.md`
- **File modificato**: `association_resolver.py` (linee 239-306, 180-186, 199-217, 535-539)

---

*Report creato: 2025-10-10 - 21:25*
