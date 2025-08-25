# Schema chiaro di tutto il processo

## Panoramica (flusso dati)
SMS → Bot Telegram (post) → **Ingestore Pagamenti** → DB  
Calendario “lezioni” (Nextcloud) → **Risolutore Associazioni** → DB  
DB (pagamenti+associazioni) + Calendario “lezioni” (giorno −1) → **Sincronizzatore Calendari** → Calendario “pagate”

---

## Componenti/Programmi

### 1) Ingestore Pagamenti (h 08:00 MSK)
- Legge i **nuovi post** nel canale Telegram.
- Effettua parsing del testo (`nome_pagante`, `giorno`, `ora`, `somma`).
- Inserisce/aggiorna in **DB.pagamenti** come `stato='sospeso'`.
- Deduplica per id messaggio / hash contenuto.

### 2) Risolutore di Associazioni (h 08:00 MSK, subito dopo)
- Legge le **lezioni** (giorno −1 o finestra desiderata) da Nextcloud “lezioni”.
- Per ogni `nome_studente`:
  - Cerca in `DB.associazioni`.  
  - Se **manca**:
    - Estrae **pagamenti sospesi** recenti e genera una **scelta multipla su Telegram** (inline keyboard).
    - Alla selezione:
      - Crea/aggiorna `associazioni (nome_studente ↔ nome_pagante)`.
      - Imposta `pagamenti.stato='associato'` e collega alla/e lezione/i (tabella ponte).
    - Opzioni: “Inserisci a mano”, “Salta”.

### 3) Sincronizzatore Calendari (h 08:00 MSK, per ultimo)
- Legge eventi del giorno −1 da **Nextcloud “lezioni”**.
- Per ogni evento con `nome_studente`:
  - Verifica esistenza di `associazione` e di pagamenti **associati/consumabili** coerenti (importo/periodo).
  - Sposta (o copia+chiudi) l’evento nel calendario **“pagate”**.
  - Marca i pagamenti coinvolti come `usato/consumato` (se 1→1) o aggiorna il residuo (se 1→N).
- Gestisce mismatch (tagga “in attesa” e notifica su Telegram).

---

## Schema Database (minimo robusto)

- **pagamenti**
  - `id_pagamento` (PK)
  - `nome_pagante` (TEXT)
  - `giorno` (DATE)
  - `ora` (TIME)
  - `somma` (NUMERIC(10,2))
  - `valuta` (TEXT, opz.)
  - `stato` (ENUM: `sospeso` | `associato` | `usato`)
  - `fonte_msg_id` (TEXT, unico per dedup)
  - `created_at`, `updated_at`

- **lezioni**
  - `id_lezione` (PK)
  - `nome_studente` (TEXT)
  - `giorno` (DATE)
  - `ora` (TIME)
  - `nextcloud_event_id` (TEXT, unico)
  - `durata_min` (INT, opz.)
  - `stato` (ENUM: `prevista` | `svolta` | `pagata`)

- **associazioni**
  - `id_assoc` (PK)
  - `nome_studente` (TEXT, unique) → `nome_pagante` (TEXT)
  - `note` (TEXT)
  - `valid_from`, `valid_to` (opz.)

- **pagamenti_lezioni** (tabella ponte per 1↔N)
  - `id` (PK)
  - `pagamento_id` (FK → pagamenti)
  - `lezione_id` (FK → lezioni)
  - `quota_usata` (NUMERIC(10,2)) — per gestire pacchetti / parziali

**Indici utili:**  
`pagamenti (stato, giorno)`, `lezioni (giorno, nome_studente)`, `associazioni (nome_studente)`

---

## Regole di matching (per proporre i candidati)
- Pagamenti **recenti** (es. ultimi 7–14 giorni).
- Vicinanza temporale alla lezione (stesso giorno o ±1).
- Importo “tipico” per la durata (es. 60’ = €X).
- Se più candidati: ordina per **scarto di orario** e **stessa somma**.

---

## Stati & Transizioni (pagamenti)
`sospeso` → (associato a studente) → `associato` → (usato su lezione/i) → `usato`  
(Per pacchetti: rimane `associato` finché la **quota residua** > 0; poi `usato`.)

---

## Pianificazione
- 08:00 MSK: **Ingestore Pagamenti**
- 08:02 MSK: **Risolutore Associazioni** (invio scelte su Telegram)
- 08:05 MSK: **Sincronizzatore Calendari** (sposta su “pagate”)
> Nota: se il server non è su fuso MSK, configurare il timezone del job o usare un orchestratore che gestisca TZ.

---

## Messaggio Telegram (esempio pronto all’uso)
Testo:  
«Nessuna associazione per *Ivan Petrov* (lezione 22/08 18:00). Scegli il pagante:»

Inline keyboard (etichetta → `callback_data`):
- «Mario Rossi • €25 • 22/08 17:40» → `assoc|stud:123|pay:987`
- «Elena Bianchi • €25 • 22/08 19:05» → `assoc|stud:123|pay:992`
- «Altro / Inserisci a mano» → `assoc|stud:123|manual`
- «Salta» → `assoc|stud:123|skip`

**Effetti alla scelta:**
- Crea/aggiorna `associazioni (Ivan Petrov ↔ Mario Rossi)`.
- `pagamenti.id=987 → stato='associato'`.
- Inserisce in `pagamenti_lezioni (987, id_lezione=...)`.
- (Opz.) risponde con conferma e link all’evento Nextcloud.

---

## Log & controllo qualità (consigli)
- Log strutturati (INFO per flusso, WARN per ambiguità, ERROR per parsing).
- Dashboard minima: #pagamenti sospesi, #lezioni non abbinate, ritardi di sincronizzazione.
- Normalizzazione nomi (trim, lower, rimozione emoji) prima del confronto.
- Retry idempotenti e dedup su `fonte_msg_id` e `nextcloud_event_id`.
