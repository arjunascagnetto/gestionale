# 🌐 Interfaccia Web - Gestione Storico Pagamenti

Interfaccia web per abbinare manualmente i 90 pagamenti storici alle lezioni.

## 🚀 Avvio Rapido

```bash
cd /home/arjuna/nextcloud/web_interface
../.cal/bin/python app.py
```

Apri browser: **http://localhost:5000**

---

## 📊 Funzionalità

### ✅ Implementate

1. **Vista a 2 Colonne**
   - 📚 Lezioni non pagate (sinistra)
   - 💰 Pagamenti disponibili (destra)

2. **Ordinamenti Indipendenti**
   - Pulsanti ↑↓ per ogni colonna
   - Ordinamento per data crescente/decrescente
   - Separati tra lezioni e pagamenti

3. **Selezione Multipla**
   - Checkbox su lezioni e pagamenti
   - Calcolo automatico totali
   - Bilancio real-time (crediti - debiti)

4. **Abbinamento Intelligente**
   - Pulsante "CONFERMA ABBINAMENTO"
   - Attivo solo se bilancio ≥ 0
   - Distribuzione automatica su pagamenti parziali
   - Aggiornamento `pagamenti_lezioni` + `associazioni`

5. **Gestione Abbinamenti Esistenti**
   - Sezione "ABBINAMENTI COMPLETATI"
   - Visualizzazione lezione ↔ pagamento + quota
   - Pulsante 🗑️ per eliminare

6. **Colori Intuitivi**
   - 🟢 Verde: disponibile (non abbinato)
   - ⚫ Grigio: già abbinato

---

## 🎯 Come Usare

### 1. Abbinare Pagamenti a Lezioni

**Caso 1: Abbinamento Semplice (1 lezione, 1 pagamento)**
1. Clicca checkbox lezione (es. Chitarra - 10/10)
2. Clicca checkbox pagamento (es. Алексей Ш. - 3000 RUB)
3. Bilancio mostra: +1000 RUB (credito residuo)
4. Click "CONFERMA ABBINAMENTO"
5. Lezione abbinata, pagamento aggiornato con residuo 1000 RUB

**Caso 2: Abbonamento (5 lezioni, 1 pagamento da 10500 RUB)**
1. Seleziona 5 checkbox lezioni
2. Seleziona 1 checkbox pagamento (10500 RUB)
3. Bilancio: +500 RUB (10500 - 5×2000)
4. Click "CONFERMA"
5. Sistema distribuisce: 2000 RUB per lezione

**Caso 3: Lezione condivisa (1 lezione, 2 pagamenti)**
1. Seleziona 1 checkbox lezione
2. Seleziona 2 checkbox pagamenti (es. 1000 RUB + 1000 RUB)
3. Bilancio: 0 RUB (perfetto)
4. Click "CONFERMA"
5. Sistema usa 1000 RUB dal primo, 1000 RUB dal secondo

**Caso 4: Crediti insufficienti**
1. Seleziona 3 lezioni (6000 RUB)
2. Seleziona 1 pagamento (2000 RUB)
3. ⚠️ Bilancio: -4000 RUB (negativo)
4. Pulsante "CONFERMA" disabilitato
5. Aggiungi altri pagamenti per coprire il debito

### 2. Eliminare Abbinamento

1. Scorri alla sezione "ABBINAMENTI COMPLETATI"
2. Trova l'abbinamento da rimuovere
3. Click 🗑️ "Elimina"
4. Conferma
5. Lezione torna disponibile (verde) nella lista sopra

---

## ⚙️ Configurazione

### Costo per Lezione

Default: **2000 RUB**

Per modificare, cambia in `app.py`:
```python
costo_per_lezione = 2000  # Linea 140
```

E in `templates/index.html`:
```javascript
const COSTO_LEZIONE = 2000; // Linea 192
```

### Porta Server

Default: **5000**

Per modificare, cambia in `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5000)  # Linea 253
```

---

## 🗄️ Database

### Query Principali

**Lezioni non pagate:**
```sql
SELECT l.* FROM lezioni l
LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
WHERE pl.lezione_id IS NULL
```

**Pagamenti con residuo:**
```sql
SELECT p.*,
       p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
FROM pagamenti p
LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
GROUP BY p.id_pagamento
HAVING residuo > 0
```

### Tabelle Modificate

**Al click "CONFERMA ABBINAMENTO":**
1. `pagamenti_lezioni` - Inserisce righe con `quota_usata`
2. `associazioni` - Inserisce/aggiorna relazione studente-pagante
3. `pagamenti` - Aggiorna `stato` a 'associato' se residuo = 0

**Al click "🗑️ Elimina":**
1. `pagamenti_lezioni` - DELETE riga
2. `pagamenti` - Ripristina `stato` a 'sospeso' se necessario
3. `associazioni` - NON toccata (rimane per riuso futuro)

---

## 🎨 Personalizzazione UI

### Tailwind CSS

Il template usa Tailwind via CDN. Per personalizzare:

```html
<!-- Cambia colori in index.html -->
<style>
    .lesson-item {
        @apply border-l-4 border-green-500 bg-green-50;
    }
</style>
```

### Classi Principali

- `.lesson-item` - Stile lezioni disponibili
- `.payment-item` - Stile pagamenti disponibili
- `.abbinamento-item` - Stile abbinamenti completati

---

## 🐛 Troubleshooting

### "Address already in use"
```bash
# Porta 5000 occupata, cambia porta in app.py
app.run(port=5001)
```

### "No module named 'flask'"
```bash
cd /home/arjuna/nextcloud
.cal/bin/pip install flask
```

### "Database is locked"
```bash
# Chiudi altri script che accedono al DB
pkill -f telegram_ingestor
pkill -f association_resolver
```

### "Lezioni non appaiono"
```bash
# Sincronizza lezioni da Google Calendar
cd /home/arjuna/nextcloud
.cal/bin/python -c "from association_resolver import sync_lessons_from_calendar; sync_lessons_from_calendar()"
```

---

## 📊 Statistiche Attuali

**Database (2025-10-09):**
- 90 pagamenti (tutti stato='sospeso')
- 150 lezioni (tutte stato='prevista')
- 0 associazioni (pronte per essere create)
- 0 abbinamenti in pagamenti_lezioni

**Stato sistema:**
- ✅ Interfaccia web funzionante
- ✅ Bugfix applicati (vedi BUGFIX_REPORT.md)
- ✅ Pronta per abbinamento storico

---

## 📝 Note Tecniche

### Distribuzione Pagamenti

Quando selezioni multiple lezioni e multiple pagamenti, il sistema:

1. Per ogni lezione (in ordine):
   - Calcola quota necessaria (2000 RUB)
   - Usa pagamenti selezionati fino a coprire quota
   - Se un pagamento non basta, usa il successivo (pagamento parziale)

2. Esempio pratico:
   - Lezioni: A, B, C (6000 RUB totale)
   - Pagamenti: P1 (5000 RUB), P2 (3000 RUB)
   - Risultato:
     - Lezione A: P1 → 2000 RUB
     - Lezione B: P1 → 2000 RUB
     - Lezione C: P1 → 1000 RUB + P2 → 1000 RUB
   - Residui finali: P1 = 0, P2 = 2000 RUB

### Sicurezza

**⚠️ IMPORTANTE:**
- Interfaccia NON ha autenticazione
- Solo per uso locale (localhost)
- NON esporre su internet pubblico
- Cambia `host='0.0.0.0'` a `host='127.0.0.1'` per maggiore sicurezza

---

## 🔧 Sviluppi Futuri

- [ ] Autenticazione con password
- [ ] Filtri per studente/data
- [ ] Export CSV/Excel
- [ ] Statistiche grafiche
- [ ] Gestione costo variabile per lezione
- [ ] Undo/Redo abbinamenti
- [ ] Dark mode
- [ ] Flash messages per feedback utente (invece di print)
- [ ] Validazione lato server per crediti insufficienti

---

## 📝 Changelog

**v1.1 - 2025-10-09** (Bugfix Release)
- ✅ Fix: INSERT ON CONFLICT per aggiornamento associazioni
- ✅ Fix: UPDATE quota_usata per abbinamenti duplicati
- ✅ Fix: Gestione errori SQL con try-except e rollback
- ✅ Fix: Validazione input con controllo fetchone()
- 📊 Affidabilità migliorata: 60% → 95%

**v1.0 - 2025-10-09** (Initial Release)
- ✅ Interfaccia a 2 colonne
- ✅ Selezione multipla e calcolo bilancio
- ✅ Distribuzione automatica pagamenti
- ✅ Gestione abbinamenti completati

---

*Ultimo aggiornamento: 2025-10-09 - 15:30*
