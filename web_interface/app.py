#!/usr/bin/env python
"""
Interfaccia Web - Gestione Storico Pagamenti e Lezioni
Flask app per abbinare manualmente pagamenti storici a lezioni.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "pagamenti.db"
DEFAULT_LESSON_COST = 2000
MIN_DATA_DATE = date(2025, 8, 1)
MIN_DATA_STR = MIN_DATA_DATE.isoformat()
SUBSCRIPTION_PLANS = {
    20000: 10,
    10500: 5,
    6600: 3
}
EXCLUDED_PAYMENT_STATUSES = ('rejected', 'pending_approval')


def ensure_trash_table():
    """Tabella di supporto per pagamenti cestinati (non visibili, ma senza cambiare stato)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamenti_cestinati (
                pagamento_id INTEGER PRIMARY KEY,
                trashed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    finally:
        conn.close()


ensure_trash_table()


def ensure_subscription_table():
    """Tabella per etichettare manualmente pagamenti come abbonamenti."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamenti_abbonamenti (
                pagamento_id INTEGER PRIMARY KEY,
                lezioni_totali INTEGER NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pagamento_id) REFERENCES pagamenti (id_pagamento) ON DELETE CASCADE
            )
        ''')
        conn.commit()
    finally:
        conn.close()


ensure_subscription_table()

def get_db():
    """Crea connessione database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_student_default_cost(nome_studente, conn=None):
    """Calcola il costo più probabile per uno studente basandosi sullo storico."""
    own_conn = False
    if conn is None:
        conn = get_db()
        own_conn = True

    cursor = conn.cursor()
    cursor.execute('''
        SELECT costo, COUNT(*) as cnt, MAX(giorno) as last_date
        FROM lezioni
        WHERE nome_studente = ?
            AND costo IS NOT NULL
            AND costo > 0
            AND gratis = 0
            AND giorno >= ?
        GROUP BY costo
        ORDER BY cnt DESC, last_date DESC
        LIMIT 1
    ''', (nome_studente, MIN_DATA_STR))
    row = cursor.fetchone()

    if own_conn:
        conn.close()

    return row['costo'] if row else None


def get_unassigned_lessons(order='DESC', filter_studenti=None, hide_paid=False, month_filter=None, min_date=MIN_DATA_STR):
    """
    Recupera TUTTE le lezioni, con flag per indicare se sono abbinate.

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
        filter_studenti: Lista di nomi studenti da filtrare (None = tutti)
        hide_paid: Se True, nasconde lezioni completamente pagate
        month_filter: Tupla (mese, anno) per filtrare per mese, None = tutti
        min_date: stringa ISO o date di inizio (default MIN_DATA_STR)
    """
    min_date_str = min_date if isinstance(min_date, str) else min_date.isoformat()
    conn = get_db()
    cursor = conn.cursor()

    # Base query
    query = '''
        SELECT
            l.id_lezione,
            l.nome_studente,
            l.giorno,
            l.ora,
            l.costo,
            l.gratis,
            COALESCE(SUM(pl.quota_usata), 0) as quota_pagata,
            CASE WHEN COALESCE(SUM(pl.quota_usata), 0) > 0 THEN 1 ELSE 0 END as is_abbinata,
            CASE WHEN COALESCE(SUM(pl.quota_usata), 0) >= l.costo THEN 1 ELSE 0 END as is_completamente_pagata
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
    '''

    # Aggiungi filtro studenti se specificato
    where_clauses = ['l.giorno >= ?']
    params = [min_date_str]

    if filter_studenti and len(filter_studenti) > 0:
        placeholders = ','.join(['?' for _ in filter_studenti])
        where_clauses.append(f'l.nome_studente IN ({placeholders})')
        params.extend(filter_studenti)

    # Filtro mese/anno
    if month_filter:
        month, year = month_filter
        where_clauses.append("strftime('%Y', l.giorno) = ? AND strftime('%m', l.giorno) = ?")
        params.extend([str(year), f'{month:02d}'])

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)

    query += f' GROUP BY l.id_lezione'

    # Aggiungi filtro HAVING per lezioni pagate
    if hide_paid:
        query += ' HAVING is_completamente_pagata = 0'

    query += f' ORDER BY l.giorno {order}, l.ora {order}'

    cursor.execute(query, params)
    rows = cursor.fetchall()

    lessons = []
    updates = []
    for row in rows:
        costo = row['costo']
        if row['gratis']:
            costo = costo or 0
        else:
            if costo is None or costo <= 0:
                suggested = get_student_default_cost(row['nome_studente'], conn)
                if suggested:
                    costo = suggested
                    updates.append((costo, row['id_lezione']))
                else:
                    costo = DEFAULT_LESSON_COST
                    updates.append((costo, row['id_lezione']))

        lessons.append({
            'id': row['id_lezione'],
            'studente': row['nome_studente'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'costo': costo,
            'gratis': row['gratis'],
            'is_abbinata': row['is_abbinata'],
            'quota_pagata': row['quota_pagata'],
            'is_completamente_pagata': row['is_completamente_pagata']
        })

    if updates:
        update_cursor = conn.cursor()
        update_cursor.executemany('UPDATE lezioni SET costo = ? WHERE id_lezione = ?', updates)
        conn.commit()

    conn.close()
    return lessons


def get_available_payments(order='DESC', filter_paganti=None, hide_used=False, month_filter=None, min_date=MIN_DATA_STR, include_residual_any_date=False):
    """
    Recupera TUTTI i pagamenti (inclusi quelli completamente utilizzati).

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
        filter_paganti: Lista di nomi paganti da filtrare (None = tutti)
        hide_used: Se True, nasconde pagamenti completamente usati
        month_filter: Tupla (mese, anno) per filtrare per mese, None = tutti
        min_date: stringa ISO o date di inizio (default MIN_DATA_STR)
        include_residual_any_date: Se True, mostra pagamenti con residuo anche se antecedenti a min_date
    """
    min_date_str = min_date if isinstance(min_date, str) else min_date.isoformat()
    conn = get_db()
    cursor = conn.cursor()

    # Base query - RIMOSSO il filtro "HAVING residuo > 0" per mostrare tutti
    query = '''
        SELECT
            p.id_pagamento,
            p.nome_pagante,
            p.giorno,
            p.ora,
            p.somma,
            p.valuta,
            p.stato,
            COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
            p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo,
            CASE WHEN COALESCE(SUM(pl.quota_usata), 0) > 0 THEN 1 ELSE 0 END as has_abbinamenti,
            CASE WHEN p.somma - COALESCE(SUM(pl.quota_usata), 0) = 0 THEN 1 ELSE 0 END as is_completamente_usato
        FROM pagamenti p
        LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
    '''

    # Aggiungi filtro paganti se specificato
    status_placeholders = ','.join(['?' for _ in EXCLUDED_PAYMENT_STATUSES])
    where_clauses = [
        f"p.stato NOT IN ({status_placeholders})",
        'p.id_pagamento NOT IN (SELECT pagamento_id FROM pagamenti_cestinati)'
    ]
    params = list(EXCLUDED_PAYMENT_STATUSES)

    if filter_paganti and len(filter_paganti) > 0:
        placeholders = ','.join(['?' for _ in filter_paganti])
        where_clauses.append(f'p.nome_pagante IN ({placeholders})')
        params.extend(filter_paganti)

    having_clauses = []
    if include_residual_any_date:
        having_clauses.append(
            "(p.giorno >= ?) OR (p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0)"
        )
        params.append(min_date_str)
    else:
        where_clauses.append('p.giorno >= ?')
        params.append(min_date_str)

    # Filtro mese/anno: mostra comunque i pagamenti con residuo > 0 anche se di mesi precedenti
    if month_filter:
        month, year = month_filter
        having_clauses.append(
            "(strftime('%Y', p.giorno) = ? AND strftime('%m', p.giorno) = ?) "
            "OR (p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0)"
        )
        params.extend([str(year), f'{month:02d}'])

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)

    query += f' GROUP BY p.id_pagamento'

    # Aggiungi filtri HAVING dopo il GROUP BY
    if hide_used:
        having_clauses.append('is_completamente_usato = 0')

    if having_clauses:
        query += ' HAVING ' + ' AND '.join([f'({clause})' for clause in having_clauses])

    query += f' ORDER BY p.giorno {order}, p.ora {order}'

    cursor.execute(query, params)

    payments = []
    for row in cursor.fetchall():
        payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'stato': row['stato'],
            'residuo': row['residuo'],
            'quota_utilizzata': row['quota_utilizzata'],
            'has_abbinamenti': row['has_abbinamenti'],
            'is_completamente_usato': row['is_completamente_usato']
        })

    conn.close()
    return payments


def get_existing_abbinamenti():
    """Recupera tutti gli abbinamenti esistenti."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            pl.id,
            pl.pagamento_id,
            pl.lezione_id,
            pl.quota_usata,
            l.nome_studente,
            l.giorno as lez_giorno,
            l.ora as lez_ora,
            p.nome_pagante,
            p.giorno as pag_giorno,
            p.ora as pag_ora,
            p.valuta
        FROM pagamenti_lezioni pl
        JOIN lezioni l ON pl.lezione_id = l.id_lezione
        JOIN pagamenti p ON pl.pagamento_id = p.id_pagamento
        WHERE l.giorno >= ?
        ORDER BY pl.id DESC
    ''', (MIN_DATA_STR,))

    abbinamenti = []
    for row in cursor.fetchall():
        abbinamenti.append({
            'id': row['id'],
            'lezione': f"{row['nome_studente']} - {row['lez_giorno']} {row['lez_ora']}",
            'pagamento': f"{row['nome_pagante']} - {row['pag_giorno']} {row['pag_ora']}",
            'quota': row['quota_usata'],
            'valuta': row['valuta']
        })

    conn.close()
    return abbinamenti


def get_payments_overview(order='DESC', filter_pagante=None, month_filter=None, day_filter=None):
    """
    Recupera pagamenti (anche completamente usati) con eventuali abbinamenti.

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
        filter_pagante: Nome pagante da filtrare (None = tutti)
        month_filter: Tupla (mese, anno) per filtrare, None = tutti
        day_filter: Data specifica (YYYY-MM-DD) per filtrare
    """
    conn = get_db()
    cursor = conn.cursor()

    query = '''
        SELECT
            p.id_pagamento,
            p.nome_pagante,
            p.giorno,
            p.ora,
            p.somma,
            p.valuta,
            p.stato,
            COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
            p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo,
            CASE WHEN p.somma - COALESCE(SUM(pl.quota_usata), 0) = 0 THEN 1 ELSE 0 END as is_completamente_usato
        FROM pagamenti p
        LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
    '''

    where_clauses = [
        f"p.stato NOT IN ({','.join(['?' for _ in EXCLUDED_PAYMENT_STATUSES])})",
        'p.giorno >= ?',
        'p.id_pagamento NOT IN (SELECT pagamento_id FROM pagamenti_cestinati)'
    ]
    params = list(EXCLUDED_PAYMENT_STATUSES) + [MIN_DATA_STR]

    if filter_pagante:
        where_clauses.append('p.nome_pagante = ?')
        params.append(filter_pagante)

    if day_filter:
        where_clauses.append('p.giorno = ?')
        params.append(day_filter)

    query += ' WHERE ' + ' AND '.join(where_clauses)
    query += ' GROUP BY p.id_pagamento'

    having_clauses = []
    if month_filter and not day_filter:
        month, year = month_filter
        having_clauses.append(
            "(strftime('%Y', p.giorno) = ? AND strftime('%m', p.giorno) = ?) "
            "OR (p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0)"
        )
        params.extend([str(year), f'{month:02d}'])

    if having_clauses:
        query += ' HAVING ' + ' AND '.join([f'({clause})' for clause in having_clauses])

    query += f' ORDER BY p.giorno {order}, p.ora {order}'

    cursor.execute(query, params)
    payments = []
    payment_ids = []
    for row in cursor.fetchall():
        payment_ids.append(row['id_pagamento'])
        payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'stato': row['stato'],
            'residuo': row['residuo'],
            'quota_utilizzata': row['quota_utilizzata'],
            'is_completamente_usato': row['is_completamente_usato'],
            'abbinamenti': []
        })

    if payment_ids:
        placeholders = ','.join(['?' for _ in payment_ids])
        cursor.execute(f'''
            SELECT
                pl.id,
                pl.pagamento_id,
                pl.lezione_id,
                pl.quota_usata,
                l.nome_studente,
                l.giorno,
                l.ora,
                l.costo,
                l.gratis
            FROM pagamenti_lezioni pl
            JOIN lezioni l ON pl.lezione_id = l.id_lezione
            WHERE pl.pagamento_id IN ({placeholders})
            ORDER BY l.giorno DESC, l.ora DESC
        ''', payment_ids)

        mapping = {p['id']: p for p in payments}
        for row in cursor.fetchall():
            mapping[row['pagamento_id']]['abbinamenti'].append({
                'id': row['id'],
                'lezione_id': row['lezione_id'],
                'studente': row['nome_studente'],
                'giorno': row['giorno'],
                'ora': row['ora'],
                'quota': row['quota_usata'],
                'costo': row['costo'],
                'gratis': row['gratis']
            })

    # Lista paganti per filtro
    cursor.execute('''
        SELECT DISTINCT nome_pagante
        FROM pagamenti
        WHERE stato NOT IN ({statuses}) AND giorno >= ?
        ORDER BY nome_pagante COLLATE NOCASE
    '''.format(statuses=','.join(['?' for _ in EXCLUDED_PAYMENT_STATUSES])), list(EXCLUDED_PAYMENT_STATUSES) + [MIN_DATA_STR])
    paganti_list = [row['nome_pagante'] for row in cursor.fetchall()]

    subscription_map = {}
    if payment_ids:
        placeholders = ','.join(['?' for _ in payment_ids])
        cursor.execute(f'''
            SELECT pagamento_id, lezioni_totali
            FROM pagamenti_abbonamenti
            WHERE pagamento_id IN ({placeholders})
        ''', payment_ids)
        subscription_map = {row['pagamento_id']: row['lezioni_totali'] for row in cursor.fetchall()}

    conn.close()
    return payments, paganti_list, subscription_map


def get_all_studenti():
    """Recupera lista unica di tutti gli studenti (da lezioni)."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT nome_studente
        FROM lezioni
        WHERE giorno >= ?
        ORDER BY nome_studente ASC
    ''', (MIN_DATA_STR,))

    studenti = [row['nome_studente'] for row in cursor.fetchall()]
    conn.close()
    return studenti


def get_all_paganti():
    """Recupera lista unica di TUTTI i paganti (inclusi quelli con residuo 0)."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT nome_pagante
        FROM pagamenti
        WHERE giorno >= ?
        ORDER BY nome_pagante ASC
    ''', (MIN_DATA_STR,))

    paganti = [row['nome_pagante'] for row in cursor.fetchall()]
    conn.close()
    return paganti


def get_suggested_abbinamenti():
    """
    Genera suggerimenti intelligenti di abbinamento basati su:
    1. Associazioni studente-pagante esistenti
    2. Lezioni non ancora completamente pagate
    3. Pagamenti con residuo disponibile
    4. Vicinanza temporale (±7 giorni)
    5. Esclude suggerimenti già rifiutati

    Returns:
        Lista di suggerimenti con lezione_id, pagamento_id, e dati per visualizzazione
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            l.id_lezione,
            l.nome_studente,
            l.giorno as lez_giorno,
            l.ora as lez_ora,
            l.costo,
            COALESCE(SUM(pl_existing.quota_usata), 0) as gia_pagato,
            l.costo - COALESCE(SUM(pl_existing.quota_usata), 0) as da_pagare,
            a.nome_pagante,
            p.id_pagamento,
            p.giorno as pag_giorno,
            p.ora as pag_ora,
            p.somma,
            p.valuta,
            p.somma - COALESCE(SUM(pl_residuo.quota_usata), 0) as residuo_pagamento,
            ABS(JULIANDAY(l.giorno) - JULIANDAY(p.giorno)) as giorni_distanza
        FROM lezioni l
        -- Join con associazioni per trovare il pagante corrispondente
        INNER JOIN associazioni a ON l.nome_studente = a.nome_studente
        -- Join con pagamenti del pagante associato che hanno residuo
        INNER JOIN pagamenti p ON a.nome_pagante = p.nome_pagante
        -- Calcola quanto già pagato per questa lezione
        LEFT JOIN pagamenti_lezioni pl_existing ON l.id_lezione = pl_existing.lezione_id
        -- Calcola residuo del pagamento
        LEFT JOIN pagamenti_lezioni pl_residuo ON p.id_pagamento = pl_residuo.pagamento_id
        -- Escludi suggerimenti già rifiutati
        LEFT JOIN suggerimenti_rifiutati sr ON l.id_lezione = sr.lezione_id AND p.id_pagamento = sr.pagamento_id
        WHERE p.stato IN ('sospeso', 'archivio')
            AND p.id_pagamento NOT IN (SELECT pagamento_id FROM pagamenti_cestinati)
            AND l.gratis = 0
            AND sr.id IS NULL
            AND l.giorno >= ?
            AND p.giorno >= ?
        GROUP BY l.id_lezione, p.id_pagamento
        HAVING
            da_pagare > 0
            AND residuo_pagamento > 0
            AND giorni_distanza <= 7
        ORDER BY
            giorni_distanza ASC,
            l.giorno DESC
        LIMIT 20
    ''', (MIN_DATA_STR, MIN_DATA_STR))

    suggestions = []
    for row in cursor.fetchall():
        suggestions.append({
            'lezione_id': row['id_lezione'],
            'pagamento_id': row['id_pagamento'],
            'studente': row['nome_studente'],
            'lez_giorno': row['lez_giorno'],
            'lez_ora': row['lez_ora'],
            'costo': row['costo'],
            'gia_pagato': row['gia_pagato'],
            'da_pagare': row['da_pagare'],
            'pagante': row['nome_pagante'],
            'pag_giorno': row['pag_giorno'],
            'pag_ora': row['pag_ora'],
            'pag_somma': row['somma'],
            'valuta': row['valuta'],
            'residuo': row['residuo_pagamento'],
            'giorni_distanza': int(row['giorni_distanza']),
            'quota_suggerita': min(row['da_pagare'], row['residuo_pagamento'])
        })

    conn.close()
    return suggestions


def save_association(cursor, nome_pagante, nome_studente):
    """
    Salva associazione pagante→studente usando il cursor della transazione corrente.

    Args:
        cursor: Cursor della connessione DB attiva
        nome_pagante: Nome del pagante
        nome_studente: Nome dello studente
    """
    try:
        # Usa INSERT OR REPLACE per aggiornare se lo studente ha già un'associazione
        cursor.execute('''
            INSERT INTO associazioni (nome_studente, nome_pagante, note, valid_from)
            VALUES (?, ?, 'Da interfaccia web', CURRENT_DATE)
            ON CONFLICT(nome_studente) DO UPDATE SET
                nome_pagante = excluded.nome_pagante,
                note = excluded.note,
                valid_from = CURRENT_DATE,
                updated_at = CURRENT_TIMESTAMP
        ''', (nome_studente, nome_pagante))
    except Exception as e:
        # Log l'errore ma continua (non blocca la transazione principale)
        print(f"⚠️ Errore salvataggio associazione {nome_studente} → {nome_pagante}: {e}")


@app.route('/')
def index():
    """Pagina principale."""
    lesson_order = request.args.get('lesson_order', 'DESC')
    payment_order = request.args.get('payment_order', 'DESC')

    # Gestione filtri studenti (può essere una lista)
    filter_studenti = request.args.getlist('studenti')
    if filter_studenti and len(filter_studenti) == 0:
        filter_studenti = None

    # Gestione filtri paganti (può essere una lista)
    filter_paganti = request.args.getlist('paganti')
    if filter_paganti and len(filter_paganti) == 0:
        filter_paganti = None

    # Filtri per nascondere lezioni/pagamenti completati
    hide_paid_lessons = request.args.get('hide_paid', '1') == '1'
    hide_used_payments = request.args.get('hide_used', '1') == '1'

    # Filtro mese/anno - default: includi mese corrente e precedente
    from datetime import datetime
    today_dt = datetime.now()
    today = today_dt.date()
    filter_month = request.args.get('month', str(today.month))
    filter_year = request.args.get('year', str(today.year))
    all_time_param = request.args.get('all_time')
    all_time = all_time_param == '1'

    first_of_current = today.replace(day=1)
    last_day_prev = first_of_current - timedelta(days=1)
    min_date_home = last_day_prev.replace(day=1)  # primo giorno del mese precedente

    has_custom_month = request.args.get('month') is not None or request.args.get('year') is not None
    if all_time:
        month_filter = None
        min_date_param = MIN_DATA_STR
        include_residual_any_date = True
    elif has_custom_month:
        month_filter = (int(filter_month), int(filter_year))
        min_date_param = MIN_DATA_STR
        include_residual_any_date = False
    else:
        # Default: mese corrente + mese precedente
        month_filter = None
        min_date_param = min_date_home
        include_residual_any_date = True

    lessons = get_unassigned_lessons(
        lesson_order,
        filter_studenti,
        hide_paid_lessons,
        month_filter,
        min_date=min_date_param
    )
    payments = get_available_payments(
        payment_order,
        filter_paganti,
        hide_used_payments,
        month_filter,
        min_date=min_date_param,
        include_residual_any_date=include_residual_any_date
    )

    subscription_payments = []
    regular_payments = []
    subscription_map = {}

    if payments:
        conn = get_db()
        cursor = conn.cursor()
        payment_ids = [p['id'] for p in payments]
        placeholders = ','.join(['?' for _ in payment_ids])
        cursor.execute(f'''
            SELECT pagamento_id, lezioni_totali
            FROM pagamenti_abbonamenti
            WHERE pagamento_id IN ({placeholders})
        ''', payment_ids)
        subscription_map = {row['pagamento_id']: row['lezioni_totali'] for row in cursor.fetchall()}
        conn.close()

    for payment in payments:
        amount = int(payment['somma'])
        lessons_count = subscription_map.get(payment['id']) or SUBSCRIPTION_PLANS.get(amount)
        if lessons_count:
            quota_per_lesson = amount / lessons_count if lessons_count else 0
            if quota_per_lesson.is_integer():
                quota_per_lesson = int(quota_per_lesson)
            lessons_left = int(max(0, payment['residuo'] // quota_per_lesson)) if quota_per_lesson else 0
            lessons_used = lessons_count - lessons_left
            payment = dict(payment)
            payment['subscription_lessons'] = lessons_count
            payment['subscription_lessons_left'] = lessons_left
            payment['subscription_lessons_used'] = lessons_used
            payment['subscription_value'] = quota_per_lesson
            subscription_payments.append(payment)
        else:
            regular_payments.append(payment)

    suggestions = get_suggested_abbinamenti()

    return render_template(
        'index.html',
        lessons=lessons,
        subscription_payments=subscription_payments,
        regular_payments=regular_payments,
        suggestions=suggestions,
        lesson_order=lesson_order,
        payment_order=payment_order,
        filter_studenti=filter_studenti or [],
        filter_paganti=filter_paganti or [],
        hide_paid_lessons=hide_paid_lessons,
        hide_used_payments=hide_used_payments,
        filter_month=filter_month,
        filter_year=filter_year,
        all_time=all_time,
        current_month=today.month,
        current_year=today.year,
        active_page='home'
    )


@app.route('/abbina', methods=['POST'])
def abbina():
    """Crea abbinamenti tra lezioni e pagamenti selezionati."""
    lesson_ids = request.form.getlist('lessons[]')
    payment_ids = request.form.getlist('payments[]')

    if not lesson_ids or not payment_ids:
        return redirect(url_for('index'))

    # Converti a int
    lesson_ids = [int(lid) for lid in lesson_ids]
    payment_ids = [int(pid) for pid in payment_ids]

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Per ogni lezione, distribuisci i pagamenti
        for lesson_id in lesson_ids:
            # Recupera studente e costo specifico della lezione
            cursor.execute('SELECT nome_studente, costo FROM lezioni WHERE id_lezione = ?', (lesson_id,))
            studente_row = cursor.fetchone()

            if not studente_row:
                print(f"Errore: Lezione {lesson_id} non trovata")
                continue

            studente = studente_row['nome_studente']
            costo_lezione = studente_row['costo'] or DEFAULT_LESSON_COST  # Default se NULL

            quota_residua = costo_lezione

            for payment_id in payment_ids:
                if quota_residua <= 0:
                    break

                # Recupera residuo pagamento
                cursor.execute('''
                    SELECT
                        p.nome_pagante,
                        p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
                    FROM pagamenti p
                    LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
                    WHERE p.id_pagamento = ?
                    GROUP BY p.id_pagamento
                ''', (payment_id,))

                pay_row = cursor.fetchone()
                if not pay_row or pay_row['residuo'] <= 0:
                    continue

                residuo_pagamento = pay_row['residuo']
                nome_pagante = pay_row['nome_pagante']

                # Calcola quanto usare di questo pagamento
                quota_da_usare = min(quota_residua, residuo_pagamento)

                # Controlla se abbinamento esiste già
                cursor.execute('''
                    SELECT id FROM pagamenti_lezioni
                    WHERE pagamento_id = ? AND lezione_id = ?
                ''', (payment_id, lesson_id))

                existing = cursor.fetchone()

                if existing:
                    # Aggiorna quota esistente invece di inserire duplicato
                    cursor.execute('''
                        UPDATE pagamenti_lezioni
                        SET quota_usata = quota_usata + ?
                        WHERE id = ?
                    ''', (quota_da_usare, existing['id']))
                else:
                    # Inserisci nuovo abbinamento
                    cursor.execute('''
                        INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata)
                        VALUES (?, ?, ?)
                    ''', (payment_id, lesson_id, quota_da_usare))

                # Salva associazione studente-pagante (aggiorna se esiste)
                save_association(cursor, nome_pagante, studente)

                quota_residua -= quota_da_usare

        # Aggiorna stato pagamenti completamente usati
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'associato'
            WHERE id_pagamento IN (
                SELECT p.id_pagamento
                FROM pagamenti p
                LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
                GROUP BY p.id_pagamento
                HAVING p.somma - COALESCE(SUM(pl.quota_usata), 0) = 0
            )
        ''')

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Errore durante abbinamento: {e}")
        # In produzione, usare flash message: flash(f'Errore: {e}', 'error')
    finally:
        conn.close()

    return redirect(url_for('index'))


@app.route('/update_cost/<int:lesson_id>', methods=['POST'])
def update_cost(lesson_id):
    """Aggiorna il costo di una lezione."""
    data = request.get_json()
    new_cost = data.get('costo')

    if new_cost is None or new_cost < 0:
        return jsonify({'success': False, 'error': 'Costo non valido'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('UPDATE lezioni SET costo = ? WHERE id_lezione = ?', (new_cost, lesson_id))
        conn.commit()
        return jsonify({'success': True, 'costo': new_cost})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/confirm_suggestion', methods=['POST'])
def confirm_suggestion():
    """Conferma un suggerimento di abbinamento."""
    data = request.get_json()
    lezione_id = data.get('lezione_id')
    pagamento_id = data.get('pagamento_id')
    quota = data.get('quota')

    if not lezione_id or not pagamento_id or not quota:
        return jsonify({'success': False, 'error': 'Dati mancanti'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Recupera nome studente e pagante per salvare associazione
        cursor.execute('SELECT nome_studente FROM lezioni WHERE id_lezione = ?', (lezione_id,))
        studente_row = cursor.fetchone()

        cursor.execute('SELECT nome_pagante FROM pagamenti WHERE id_pagamento = ?', (pagamento_id,))
        pagante_row = cursor.fetchone()

        if not studente_row or not pagante_row:
            return jsonify({'success': False, 'error': 'Lezione o pagamento non trovato'}), 404

        studente = studente_row['nome_studente']
        pagante = pagante_row['nome_pagante']

        # Controlla se abbinamento esiste già
        cursor.execute('''
            SELECT id FROM pagamenti_lezioni
            WHERE pagamento_id = ? AND lezione_id = ?
        ''', (pagamento_id, lezione_id))

        existing = cursor.fetchone()

        if existing:
            # Aggiorna quota esistente
            cursor.execute('''
                UPDATE pagamenti_lezioni
                SET quota_usata = quota_usata + ?
                WHERE id = ?
            ''', (quota, existing['id']))
        else:
            # Inserisci nuovo abbinamento
            cursor.execute('''
                INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata)
                VALUES (?, ?, ?)
            ''', (pagamento_id, lezione_id, quota))

        # Salva associazione studente-pagante
        save_association(cursor, pagante, studente)

        # Aggiorna stato pagamento se completamente usato
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'associato'
            WHERE id_pagamento = ?
            AND (SELECT p.somma - COALESCE(SUM(pl.quota_usata), 0)
                 FROM pagamenti p
                 LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
                 WHERE p.id_pagamento = ?) = 0
        ''', (pagamento_id, pagamento_id))

        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/reject_suggestion', methods=['POST'])
def reject_suggestion():
    """
    Rifiuta un suggerimento e lo salva nel DB per non riproporlo.
    """
    data = request.get_json()
    lezione_id = data.get('lezione_id')
    pagamento_id = data.get('pagamento_id')

    if not lezione_id or not pagamento_id:
        return jsonify({'success': False, 'error': 'Dati mancanti'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Salva il rifiuto nel database
        cursor.execute('''
            INSERT INTO suggerimenti_rifiutati (lezione_id, pagamento_id)
            VALUES (?, ?)
            ON CONFLICT(lezione_id, pagamento_id) DO NOTHING
        ''', (lezione_id, pagamento_id))

        conn.commit()
        return jsonify({'success': True, 'message': 'Suggerimento rifiutato e salvato'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/toggle_gratis/<int:lesson_id>', methods=['POST'])
def toggle_gratis(lesson_id):
    """Segna/desegna una lezione come gratis (lezione di prova)."""
    data = request.get_json()
    is_gratis = data.get('gratis', False)

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('UPDATE lezioni SET gratis = ? WHERE id_lezione = ?', (1 if is_gratis else 0, lesson_id))
        conn.commit()
        return jsonify({'success': True, 'gratis': is_gratis})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/get_payment_details/<int:payment_id>')
def get_payment_details(payment_id):
    """Recupera dettagli abbinamenti di un pagamento specifico."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            l.nome_studente,
            l.giorno,
            l.ora,
            pl.quota_usata
        FROM pagamenti_lezioni pl
        JOIN lezioni l ON pl.lezione_id = l.id_lezione
        WHERE pl.pagamento_id = ?
        ORDER BY l.giorno DESC, l.ora DESC
    ''', (payment_id,))

    abbinamenti = []
    for row in cursor.fetchall():
        abbinamenti.append({
            'studente': row['nome_studente'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'quota': row['quota_usata']
        })

    conn.close()
    return jsonify({'abbinamenti': abbinamenti})


@app.route('/get_lesson_abbinamenti/<int:lesson_id>')
def get_lesson_abbinamenti(lesson_id):
    """Recupera dettagli abbinamenti di una lezione specifica."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            p.nome_pagante,
            p.giorno,
            p.ora,
            pl.quota_usata,
            pl.id
        FROM pagamenti_lezioni pl
        JOIN pagamenti p ON pl.pagamento_id = p.id_pagamento
        WHERE pl.lezione_id = ?
        ORDER BY p.giorno DESC, p.ora DESC
    ''', (lesson_id,))

    abbinamenti = []
    for row in cursor.fetchall():
        abbinamenti.append({
            'id': row['id'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'quota': row['quota_usata']
        })

    conn.close()
    return jsonify({'abbinamenti': abbinamenti})


@app.route('/delete_lesson_abbinamenti/<int:lesson_id>', methods=['POST'])
def delete_lesson_abbinamenti(lesson_id):
    """Elimina TUTTI gli abbinamenti di una lezione."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Conta quanti abbinamenti stiamo eliminando
        cursor.execute('SELECT COUNT(*) FROM pagamenti_lezioni WHERE lezione_id = ?', (lesson_id,))
        deleted_count = cursor.fetchone()[0]

        # Elimina gli abbinamenti
        cursor.execute('DELETE FROM pagamenti_lezioni WHERE lezione_id = ?', (lesson_id,))

        # Ripristina stato pagamenti che erano completamente usati
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'sospeso'
            WHERE stato = 'associato'
            AND id_pagamento IN (
                SELECT p.id_pagamento
                FROM pagamenti p
                LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
                GROUP BY p.id_pagamento
                HAVING p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0
            )
        ''')

        conn.commit()
        return jsonify({'success': True, 'deleted_count': deleted_count})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/delete_lesson/<int:lesson_id>', methods=['POST'])
def delete_lesson(lesson_id):
    """Elimina una lezione e i suoi abbinamenti."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Rimuovi abbinamenti collegati alla lezione
        cursor.execute('DELETE FROM pagamenti_lezioni WHERE lezione_id = ?', (lesson_id,))

        # Elimina la lezione stessa
        cursor.execute('DELETE FROM lezioni WHERE id_lezione = ?', (lesson_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Lezione non trovata'}), 404

        # Ripristina stato dei pagamenti che ora hanno residuo
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'sospeso'
            WHERE stato = 'associato'
            AND id_pagamento IN (
                SELECT p.id_pagamento
                FROM pagamenti p
                LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
                GROUP BY p.id_pagamento
                HAVING p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0
            )
        ''')

        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/delete/<int:abbinamento_id>', methods=['POST'])
def delete_abbinamento(abbinamento_id):
    """Elimina un abbinamento esistente."""
    conn = get_db()
    cursor = conn.cursor()

    # Elimina da pagamenti_lezioni
    cursor.execute('DELETE FROM pagamenti_lezioni WHERE id = ?', (abbinamento_id,))

    # Ripristina stato pagamenti che erano completamente usati
    cursor.execute('''
        UPDATE pagamenti
        SET stato = 'sospeso'
        WHERE stato = 'associato'
        AND id_pagamento IN (
            SELECT p.id_pagamento
            FROM pagamenti p
            LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
            GROUP BY p.id_pagamento
            HAVING p.somma - COALESCE(SUM(pl.quota_usata), 0) > 0
        )
    ''')

    conn.commit()
    conn.close()

    next_url = request.args.get('next') or request.form.get('next')
    return redirect(next_url or url_for('index'))


@app.route('/payments/<int:payment_id>/delete_abbinamento/<int:abbinamento_id>', methods=['POST'])
def delete_payment_abbinamento(payment_id, abbinamento_id):
    """Elimina un abbinamento da un pagamento e riporta pagamento/lezione in stato libero."""
    next_url = request.form.get('next') or request.args.get('next')
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            DELETE FROM pagamenti_lezioni
            WHERE id = ? AND pagamento_id = ?
        ''', (abbinamento_id, payment_id))

        # Aggiorna stato pagamento in base al residuo attuale
        cursor.execute('''
            UPDATE pagamenti
            SET stato = CASE
                WHEN somma - COALESCE((
                    SELECT SUM(pl.quota_usata) FROM pagamenti_lezioni pl WHERE pl.pagamento_id = ?
                ), 0) = 0 THEN 'associato'
                ELSE 'sospeso'
            END
            WHERE id_pagamento = ?
              AND stato IN ('associato', 'sospeso')
        ''', (payment_id, payment_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Errore eliminazione abbinamento pagamento {payment_id}: {e}")
    finally:
        conn.close()

    return redirect(next_url or url_for('routines', tab='pagamenti'))


@app.route('/payments/<int:payment_id>/trash', methods=['POST'])
def trash_payment(payment_id):
    """Metti un pagamento nel cestino (tabella di appoggio) senza cambiare stato."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT 1 FROM pagamenti WHERE id_pagamento = ?', (payment_id,))
        if cursor.fetchone() is None:
            return jsonify({'success': False, 'error': 'Pagamento non trovato'}), 404

        cursor.execute('''
            INSERT OR REPLACE INTO pagamenti_cestinati (pagamento_id, trashed_at)
            VALUES (?, CURRENT_TIMESTAMP)
        ''', (payment_id,))

        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/manual_payment', methods=['POST'])
def api_manual_payment():
    """Crea un pagamento manuale (es. contanti) direttamente dal pannello web."""
    data = request.get_json(silent=True) or {}
    nome_pagante = (data.get('nome_pagante') or '').strip()
    giorno = (data.get('giorno') or '').strip() or date.today().isoformat()
    ora = (data.get('ora') or '').strip()
    valuta = (data.get('valuta') or 'RUB').strip().upper() or 'RUB'
    stato = (data.get('stato') or 'sospeso').strip()

    try:
        somma = float(data.get('somma'))
    except (TypeError, ValueError):
        somma = None

    # Validazioni base
    if not nome_pagante:
        return jsonify({'success': False, 'error': 'Nome pagante obbligatorio'}), 400
    if somma is None or somma <= 0:
        return jsonify({'success': False, 'error': 'Inserisci un importo valido'}), 400

    # Normalizza/valida data e ora
    try:
        datetime.strptime(giorno, '%Y-%m-%d')
    except ValueError:
        return jsonify({'success': False, 'error': 'Data non valida (YYYY-MM-DD)'}), 400

    if not ora:
        ora = datetime.now().strftime('%H:%M')
    else:
        try:
            datetime.strptime(ora, '%H:%M')
        except ValueError:
            return jsonify({'success': False, 'error': 'Ora non valida (HH:MM)'}), 400

    allowed_statuses = {'sospeso', 'pending_approval', 'rejected', 'associato', 'usato'}
    if stato not in allowed_statuses:
        stato = 'sospeso'

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO pagamenti (nome_pagante, giorno, ora, somma, valuta, stato, fonte_msg_id, skipped, notificato)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 0, 0)
        ''', (nome_pagante, giorno, ora, somma, valuta, stato))
        conn.commit()
        return jsonify({'success': True, 'id_pagamento': cursor.lastrowid})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/mark_subscription', methods=['POST'])
def api_mark_subscription():
    """Etichetta un pagamento come abbonamento impostando il numero di lezioni totali."""
    data = request.get_json(silent=True) or {}
    pagamento_id = data.get('pagamento_id')
    lezioni_totali = data.get('lezioni_totali')

    try:
        pagamento_id = int(pagamento_id)
        lezioni_totali = int(lezioni_totali)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Dati non validi'}), 400

    if lezioni_totali <= 0:
        return jsonify({'success': False, 'error': 'Lezioni totali deve essere > 0'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM pagamenti WHERE id_pagamento = ?', (pagamento_id,))
        if cursor.fetchone() is None:
            return jsonify({'success': False, 'error': 'Pagamento non trovato'}), 404

        cursor.execute('''
            INSERT INTO pagamenti_abbonamenti (pagamento_id, lezioni_totali, note)
            VALUES (?, ?, 'Etichettato da interfaccia web')
            ON CONFLICT(pagamento_id) DO UPDATE SET
                lezioni_totali = excluded.lezioni_totali,
                note = excluded.note
        ''', (pagamento_id, lezioni_totali))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/unmark_subscription', methods=['POST'])
def api_unmark_subscription():
    """Rimuove l'etichetta di abbonamento da un pagamento."""
    data = request.get_json(silent=True) or {}
    pagamento_id = data.get('pagamento_id')

    try:
        pagamento_id = int(pagamento_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Dati non validi'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM pagamenti_abbonamenti WHERE pagamento_id = ?', (pagamento_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/stats')
def stats():
    """Pagina statistiche."""
    stats_data = calculate_statistics()
    return render_template('stats.html', stats=stats_data, active_page='stats')


@app.route('/routines')
def routines():
    """Pagina per operazioni ricorrenti (abbinamenti completati e gestione)."""
    tab = request.args.get('tab', 'abbinamenti')
    now = datetime.now()

    abbinamenti = []
    iframe_src = None
    payments = []
    paganti_options = []
    filter_pagante = request.args.get('pagante') or None
    filter_day = request.args.get('day') or None
    filter_month = None
    filter_year = None
    payment_order = request.args.get('payment_order', 'DESC')
    all_time = request.args.get('all_time', '0') == '1'

    if tab == 'abbinamenti':
        abbinamenti = get_existing_abbinamenti()
    elif tab == 'pagamenti':
        filter_month = request.args.get('month', str(now.month))
        filter_year = request.args.get('year', str(now.year))
        month_filter = None if all_time or filter_day else (int(filter_month), int(filter_year))
        payments, paganti_options, subscription_map = get_payments_overview(
            payment_order,
            filter_pagante=filter_pagante,
            month_filter=month_filter,
            day_filter=filter_day
        )
        for payment in payments:
            if payment['id'] in subscription_map:
                payment['subscription_lessons'] = subscription_map[payment['id']]
        # Lezioni con debito > 0 per uso manuale
        lessons_raw = get_unassigned_lessons(order='DESC', filter_studenti=None, hide_paid=False, month_filter=None)
        lessons_for_manual = []
        for l in lessons_raw:
            remaining = max(0, (l['costo'] or 0) - (l['quota_pagata'] or 0))
            if l['gratis']:
                continue
            if remaining > 0:
                lessons_for_manual.append({
                    'id': l['id'],
                    'label': f"{l['studente']} - {l['giorno']} {l['ora']}",
                    'remaining': remaining,
                    'costo': l['costo']
                })
    elif tab == 'approva':
        iframe_src = url_for('approva_paganti', embedded=1)
    elif tab == 'normalizza':
        iframe_src = url_for('normalizza', embedded=1)
    elif tab == 'rifiutati':
        iframe_src = url_for('rifiutati', embedded=1)
    else:
        return redirect(url_for('routines', tab='abbinamenti'))

    return render_template(
        'routines.html',
        active_tab=tab,
        abbinamenti=abbinamenti,
        iframe_src=iframe_src,
        payments=payments,
        paganti_options=paganti_options,
        filter_pagante=filter_pagante or '',
        filter_day=filter_day or '',
        filter_month=filter_month,
        filter_year=filter_year,
        payment_order=payment_order,
        all_time=all_time,
        current_year=now.year,
        current_month=now.month,
        today_iso=now.date().isoformat(),
        current_time=now.strftime('%H:%M'),
        lessons_for_manual=lessons_for_manual if tab == 'pagamenti' else [],
        request_path=request.full_path,
        active_page='routines'
    )


@app.route('/rifiutati')
def rifiutati():
    """Pagina con lista abbinamenti rifiutati."""
    embedded = request.args.get('embedded') == '1'
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            sr.id,
            sr.lezione_id,
            sr.pagamento_id,
            sr.rifiutato_at,
            l.nome_studente,
            l.giorno as lez_giorno,
            l.ora as lez_ora,
            l.costo,
            p.nome_pagante,
            p.giorno as pag_giorno,
            p.ora as pag_ora,
            p.somma
        FROM suggerimenti_rifiutati sr
        JOIN lezioni l ON sr.lezione_id = l.id_lezione
        JOIN pagamenti p ON sr.pagamento_id = p.id_pagamento
        WHERE l.giorno >= ?
        ORDER BY sr.rifiutato_at DESC
    ''', (MIN_DATA_STR,))

    rifiutati_list = []
    for row in cursor.fetchall():
        rifiutati_list.append({
            'id': row['id'],
            'lezione_id': row['lezione_id'],
            'pagamento_id': row['pagamento_id'],
            'rifiutato_at': row['rifiutato_at'],
            'studente': row['nome_studente'],
            'lez_giorno': row['lez_giorno'],
            'lez_ora': row['lez_ora'],
            'costo': row['costo'],
            'pagante': row['nome_pagante'],
            'pag_giorno': row['pag_giorno'],
            'pag_ora': row['pag_ora'],
            'somma': row['somma']
        })

    conn.close()
    return render_template(
        'rifiutati.html',
        rifiutati=rifiutati_list,
        active_page=None if embedded else 'rifiutati',
        embedded=embedded
    )


@app.route('/delete_rifiutato/<int:rifiutato_id>', methods=['POST'])
def delete_rifiutato(rifiutato_id):
    """Elimina un rifiuto (permette di far riapparire il suggerimento)."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM suggerimenti_rifiutati WHERE id = ?', (rifiutato_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('rifiutati'))


@app.route('/normalizza')
def normalizza():
    """Pagina per normalizzazione nomi e aggiornamento Google Calendar."""
    embedded = request.args.get('embedded') == '1'
    conn = get_db()
    cursor = conn.cursor()

    # Analizza varianti di nomi (stessa logica di normalize_student_names.py)
    cursor.execute('SELECT DISTINCT nome_studente FROM lezioni WHERE giorno >= ? ORDER BY nome_studente', (MIN_DATA_STR,))
    all_students = [row[0] for row in cursor.fetchall()]

    # Raggruppa nomi simili
    from collections import defaultdict
    groups = defaultdict(list)

    for student in all_students:
        normalized = student.lower().replace(' ', '').replace('_', '').replace('-', '')
        groups[normalized].append(student)

    # Filtra solo gruppi con più varianti
    name_groups = []
    for normalized, variants in groups.items():
        if len(variants) > 1:
            # Conta frequenza negli abbinamenti
            frequency = {}
            for variant in variants:
                cursor.execute('''
                    SELECT COUNT(*)
                    FROM pagamenti_lezioni pl
                    JOIN lezioni l ON pl.lezione_id = l.id_lezione
                    WHERE l.nome_studente = ? AND l.giorno >= ?
                ''', (variant, MIN_DATA_STR))
                frequency[variant] = cursor.fetchone()[0]

            # Scegli canonico (più frequente, poi più lungo)
            canonical = max(variants, key=lambda x: (frequency.get(x, 0), len(x)))

            name_groups.append({
                'normalized': normalized,
                'variants': variants,
                'canonical': canonical,
                'frequencies': frequency
            })

    # Statistiche lezioni pagate
    cursor.execute('''
        SELECT COUNT(*)
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.nextcloud_event_id IS NOT NULL
            AND l.gratis = 0
            AND l.giorno >= ?
        GROUP BY l.id_lezione
        HAVING COALESCE(SUM(pl.quota_usata), 0) >= l.costo
    ''', (MIN_DATA_STR,))
    paid_lessons_count = len(cursor.fetchall())

    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE nextcloud_event_id IS NOT NULL AND giorno >= ?', (MIN_DATA_STR,))
    total_lessons_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'normalizza.html',
        name_groups=name_groups,
        paid_lessons_count=paid_lessons_count,
        total_lessons_count=total_lessons_count,
        active_page=None if embedded else 'normalizza',
        embedded=embedded
    )


@app.route('/api/normalize_names', methods=['POST'])
def api_normalize_names():
    """API per eseguire normalizzazione nomi studenti."""
    data = request.get_json()
    changes = data.get('changes', [])

    if not changes:
        return jsonify({'success': False, 'error': 'Nessun cambiamento specificato'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        total_updated = 0

        # Raggruppa i cambiamenti per nome_canonico
        canonical_groups = {}
        for change in changes:
            old_name = change['old']
            new_name = change['new']
            if new_name not in canonical_groups:
                canonical_groups[new_name] = []
            canonical_groups[new_name].append(old_name)

        # Per ogni gruppo canonico, gestisci duplicati in associazioni
        for new_name, old_names in canonical_groups.items():
            # Trova tutte le associazioni che verrebbero duplicate
            placeholders = ','.join(['?' for _ in old_names])
            cursor.execute(f'''
                SELECT id_assoc, nome_studente, nome_pagante, updated_at
                FROM associazioni
                WHERE nome_studente IN ({placeholders})
                ORDER BY updated_at DESC
            ''', old_names)

            associations = cursor.fetchall()

            if len(associations) > 1:
                # Mantieni solo la più recente, elimina le altre
                keep_id = associations[0]['id_assoc']
                delete_ids = [a['id_assoc'] for a in associations[1:]]

                if delete_ids:
                    delete_placeholders = ','.join(['?' for _ in delete_ids])
                    cursor.execute(f'DELETE FROM associazioni WHERE id_assoc IN ({delete_placeholders})', delete_ids)

        # Ora esegui la normalizzazione
        for change in changes:
            old_name = change['old']
            new_name = change['new']

            # Aggiorna lezioni
            cursor.execute('UPDATE lezioni SET nome_studente = ? WHERE nome_studente = ?',
                          (new_name, old_name))
            updated = cursor.rowcount

            # Per associazioni: aggiorna SOLO se old_name != new_name
            # e SOLO se new_name non esiste già
            if old_name != new_name:
                cursor.execute('SELECT COUNT(*) FROM associazioni WHERE nome_studente = ?', (new_name,))
                if cursor.fetchone()[0] == 0:
                    # new_name non esiste, possiamo fare UPDATE
                    cursor.execute('''
                        UPDATE associazioni
                        SET nome_studente = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE nome_studente = ?
                    ''', (new_name, old_name))
                    updated += cursor.rowcount
                else:
                    # new_name esiste già, elimina old_name
                    cursor.execute('DELETE FROM associazioni WHERE nome_studente = ?', (old_name,))

            total_updated += updated

        conn.commit()
        return jsonify({'success': True, 'updated': total_updated})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/get_associations')
def api_get_associations():
    """API per recuperare tutte le associazioni."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id_assoc, nome_studente, nome_pagante, note, valid_from
        FROM associazioni
        ORDER BY nome_studente ASC
    ''')

    associations = []
    for row in cursor.fetchall():
        associations.append({
            'id_assoc': row['id_assoc'],
            'nome_studente': row['nome_studente'],
            'nome_pagante': row['nome_pagante'],
            'note': row['note'],
            'valid_from': row['valid_from']
        })

    conn.close()
    return jsonify({'associations': associations})


@app.route('/api/add_association', methods=['POST'])
def api_add_association():
    """API per aggiungere una nuova associazione."""
    data = request.get_json()
    nome_pagante = data.get('nome_pagante', '').strip()
    nome_studente = data.get('nome_studente', '').strip()

    if not nome_pagante or not nome_studente:
        return jsonify({'success': False, 'error': 'Nome pagante e studente obbligatori'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO associazioni (nome_studente, nome_pagante, note, valid_from)
            VALUES (?, ?, 'Da interfaccia web', CURRENT_DATE)
            ON CONFLICT(nome_studente) DO UPDATE SET
                nome_pagante = excluded.nome_pagante,
                note = excluded.note,
                valid_from = CURRENT_DATE,
                updated_at = CURRENT_TIMESTAMP
        ''', (nome_studente, nome_pagante))

        conn.commit()
        return jsonify({'success': True, 'message': 'Associazione creata/aggiornata'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/delete_association/<int:assoc_id>', methods=['POST'])
def api_delete_association(assoc_id):
    """API per eliminare un'associazione."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('DELETE FROM associazioni WHERE id_assoc = ?', (assoc_id,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Associazione non trovata'}), 404

        return jsonify({'success': True, 'message': 'Associazione eliminata'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/approva_paganti')
def approva_paganti():
    """Pagina per approvare/rifiutare nuovi paganti."""
    embedded = request.args.get('embedded') == '1'
    conn = get_db()
    cursor = conn.cursor()

    # Recupera pagamenti in attesa di approvazione
    cursor.execute('''
        SELECT
            id_pagamento,
            nome_pagante,
            giorno,
            ora,
            somma,
            valuta,
            created_at
        FROM pagamenti
        WHERE stato = 'pending_approval' AND giorno >= ?
        ORDER BY giorno DESC, ora DESC
    ''', (MIN_DATA_STR,))

    pending_payments = []
    for row in cursor.fetchall():
        pending_payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'created_at': row['created_at']
        })

    # Conta pagamenti per pagante
    paganti_count = {}
    for payment in pending_payments:
        nome = payment['nome_pagante']
        paganti_count[nome] = paganti_count.get(nome, 0) + 1

    # Recupera pagamenti già rifiutati
    cursor.execute('''
        SELECT
            id_pagamento,
            nome_pagante,
            giorno,
            ora,
            somma,
            valuta
        FROM pagamenti
        WHERE stato = 'rejected' AND giorno >= ?
        ORDER BY giorno DESC, ora DESC
        LIMIT 50
    ''', (MIN_DATA_STR,))

    rejected_payments = []
    for row in cursor.fetchall():
        rejected_payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta']
        })

    conn.close()

    return render_template(
        'approva_paganti.html',
        pending_payments=pending_payments,
        rejected_payments=rejected_payments,
        paganti_count=paganti_count,
        active_page=None if embedded else 'approva',
        embedded=embedded
    )


@app.route('/api/approve_pagante', methods=['POST'])
def api_approve_pagante():
    """API per approvare un pagante (cambia tutti i suoi pagamenti da pending_approval a sospeso)."""
    data = request.get_json()
    nome_pagante = data.get('nome_pagante', '').strip()

    if not nome_pagante:
        return jsonify({'success': False, 'error': 'Nome pagante obbligatorio'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Aggiorna tutti i pagamenti del pagante
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'sospeso'
            WHERE nome_pagante = ? AND stato = 'pending_approval'
        ''', (nome_pagante,))

        updated = cursor.rowcount

        # Aggiungi alla whitelist
        cursor.execute('''
            INSERT OR IGNORE INTO whitelist_paganti (nome_pagante, approvato)
            VALUES (?, 1)
        ''', (nome_pagante,))

        conn.commit()
        return jsonify({
            'success': True,
            'message': f'{updated} pagamenti approvati per {nome_pagante}',
            'updated': updated
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/reject_pagante', methods=['POST'])
def api_reject_pagante():
    """API per rifiutare un pagante (cambia tutti i suoi pagamenti da pending_approval a rejected)."""
    data = request.get_json()
    nome_pagante = data.get('nome_pagante', '').strip()

    if not nome_pagante:
        return jsonify({'success': False, 'error': 'Nome pagante obbligatorio'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Aggiorna tutti i pagamenti del pagante
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'rejected'
            WHERE nome_pagante = ? AND stato = 'pending_approval'
        ''', (nome_pagante,))

        updated = cursor.rowcount

        # Aggiungi alla whitelist con flag rifiutato
        cursor.execute('''
            INSERT OR IGNORE INTO whitelist_paganti (nome_pagante, approvato)
            VALUES (?, 0)
        ''', (nome_pagante,))

        conn.commit()
        return jsonify({
            'success': True,
            'message': f'{updated} pagamenti rifiutati per {nome_pagante}',
            'updated': updated
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/restore_rejected/<int:payment_id>', methods=['POST'])
def api_restore_rejected(payment_id):
    """API per ripristinare un pagamento rifiutato."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE pagamenti
            SET stato = 'pending_approval'
            WHERE id_pagamento = ? AND stato = 'rejected'
        ''', (payment_id,))

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Pagamento non trovato o non rifiutato'}), 404

        conn.commit()
        return jsonify({'success': True, 'message': 'Pagamento ripristinato'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/sync')
def sync():
    """Pagina per sincronizzazione dati."""
    return render_template('sync.html', active_page='sync')


@app.route('/api/sync_all', methods=['POST'])
def api_sync_all():
    """API per sincronizzare TUTTO: pagamenti + lezioni in sequenza."""
    import subprocess

    try:
        python_path = str(Path(__file__).parent.parent / '.cal/bin/python')
        payments_script = Path(__file__).parent.parent / 'telegram_ingestor.py'
        lessons_script = Path(__file__).parent.parent / 'gcal_incremental_sync.py'

        outputs = []
        errors = []

        # 1. Sync pagamenti da Telegram
        result = subprocess.run(
            [python_path, str(payments_script)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            outputs.append(f"✅ PAGAMENTI:\n{result.stdout}")
        else:
            errors.append(f"❌ PAGAMENTI:\n{result.stderr or result.stdout}")

        # 2. Sync lezioni da Google Calendar
        result = subprocess.run(
            [python_path, str(lessons_script)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            outputs.append(f"✅ LEZIONI:\n{result.stdout}")
        else:
            errors.append(f"❌ LEZIONI:\n{result.stderr or result.stdout}")

        # Determina successo
        success = len(errors) == 0

        return jsonify({
            'success': success,
            'output': '\n\n'.join(outputs),
            'error': '\n\n'.join(errors) if errors else None,
            'message': 'Sincronizzazione completa!' if success else 'Sincronizzazione con errori'
        }), 200 if success else 500

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout: operazione troppo lunga'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sync_payments', methods=['POST'])
def api_sync_payments():
    """API per importare nuovi pagamenti da Telegram."""
    import subprocess

    try:
        script_path = Path(__file__).parent.parent / 'telegram_ingestor.py'

        result = subprocess.run(
            [str(Path(__file__).parent.parent / '.cal/bin/python'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            return jsonify({
                'success': True,
                'output': result.stdout,
                'message': 'Pagamenti aggiornati da Telegram'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or result.stdout
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout: operazione troppo lunga'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sync_lessons', methods=['POST'])
def api_sync_lessons():
    """API per sincronizzare lezioni da Google Calendar (incrementale)."""
    import subprocess

    try:
        script_path = Path(__file__).parent.parent / 'gcal_incremental_sync.py'

        result = subprocess.run(
            [str(Path(__file__).parent.parent / '.cal/bin/python'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            return jsonify({
                'success': True,
                'output': result.stdout,
                'message': 'Lezioni sincronizzate da Google Calendar'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or result.stdout
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout: operazione troppo lunga'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/update_calendar', methods=['POST'])
def api_update_calendar():
    """API per aggiornare Google Calendar (colori lezioni pagate + normalizzazione nomi)."""
    import subprocess

    try:
        # Usa update_gcal_incremental.py (aggiorna colori lezioni pagate)
        script_path = Path(__file__).parent.parent / 'update_gcal_incremental.py'

        result = subprocess.run(
            [str(Path(__file__).parent.parent / '.cal/bin/python'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minuti max
        )

        if result.returncode == 0:
            return jsonify({
                'success': True,
                'output': result.stdout,
                'message': 'Calendar aggiornato: colori lezioni pagate applicati'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or result.stdout
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout: operazione troppo lunga'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/force_full_calendar_update', methods=['POST'])
def api_force_full_calendar_update():
    """API per forzare aggiornamento COMPLETO Google Calendar (tutti gli eventi)."""
    import subprocess

    try:
        # Cancella timestamp per forzare full update
        timestamp_file = Path(__file__).parent.parent / '.gcal_last_update'
        if timestamp_file.exists():
            timestamp_file.unlink()

        # Esegui script incrementale (che farà full update senza timestamp)
        script_path = Path(__file__).parent.parent / 'update_gcal_incremental.py'

        result = subprocess.run(
            [str(Path(__file__).parent.parent / '.cal/bin/python'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return jsonify({
                'success': True,
                'output': result.stdout,
                'message': 'Calendario aggiornato COMPLETAMENTE (tutti gli eventi)'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or result.stdout
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout: operazione troppo lunga'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/manual_abbinamento', methods=['POST'])
def api_manual_abbinamento():
    """
    Usa una quota specifica di un pagamento per una lezione indicata (inserimento manuale parziale).
    """
    data = request.get_json(silent=True) or {}
    pagamento_id = data.get('pagamento_id')
    lezione_id = data.get('lezione_id')
    quota = data.get('quota')

    try:
        pagamento_id = int(pagamento_id)
        lezione_id = int(lezione_id)
        quota = float(quota)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Dati non validi'}), 400

    if quota <= 0:
        return jsonify({'success': False, 'error': 'Quota deve essere > 0'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Stato pagamento/residuo
        cursor.execute('''
            SELECT
                p.nome_pagante,
                p.somma - COALESCE(SUM(pl.quota_usata), 0) AS residuo
            FROM pagamenti p
            LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
            WHERE p.id_pagamento = ?
            GROUP BY p.id_pagamento
        ''', (pagamento_id,))
        pay = cursor.fetchone()
        if not pay:
            return jsonify({'success': False, 'error': 'Pagamento non trovato'}), 404
        if pay['residuo'] <= 0:
            return jsonify({'success': False, 'error': 'Pagamento senza residuo'}), 400
        if quota > pay['residuo']:
            return jsonify({'success': False, 'error': 'Quota superiore al residuo del pagamento'}), 400

        # Stato lezione / quanto resta da pagare
        cursor.execute('''
            SELECT
                l.nome_studente,
                l.costo,
                l.gratis,
                l.costo - COALESCE(SUM(pl.quota_usata), 0) AS da_pagare
            FROM lezioni l
            LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
            WHERE l.id_lezione = ?
            GROUP BY l.id_lezione
        ''', (lezione_id,))
        lesson = cursor.fetchone()
        if not lesson:
            return jsonify({'success': False, 'error': 'Lezione non trovata'}), 404
        if lesson['gratis']:
            return jsonify({'success': False, 'error': 'Lezione marcata gratis'}), 400
        if lesson['da_pagare'] <= 0:
            return jsonify({'success': False, 'error': 'Lezione già pagata'}), 400
        if quota > lesson['da_pagare']:
            return jsonify({'success': False, 'error': 'Quota superiore al dovuto per la lezione'}), 400

        # Inserisci/aggiorna
        cursor.execute('''
            SELECT id FROM pagamenti_lezioni
            WHERE pagamento_id = ? AND lezione_id = ?
        ''', (pagamento_id, lezione_id))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                'UPDATE pagamenti_lezioni SET quota_usata = quota_usata + ? WHERE id = ?',
                (quota, existing['id'])
            )
        else:
            cursor.execute(
                'INSERT INTO pagamenti_lezioni (pagamento_id, lezione_id, quota_usata) VALUES (?, ?, ?)',
                (pagamento_id, lezione_id, quota)
            )

        # Salva associazione studente-pagante
        save_association(cursor, pay['nome_pagante'], lesson['nome_studente'])

        # Aggiorna stato pagamento se esaurito
        cursor.execute('''
            UPDATE pagamenti
            SET stato = CASE
                WHEN somma - COALESCE((
                    SELECT SUM(pl.quota_usata) FROM pagamenti_lezioni pl WHERE pl.pagamento_id = ?
                ), 0) = 0 THEN 'associato'
                ELSE 'sospeso'
            END
            WHERE id_pagamento = ?
        ''', (pagamento_id, pagamento_id))

        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


def calculate_statistics(*_unused, **_unused_kwargs):
    """
    Calcola statistiche essenziali su lezioni svolte e pagamenti ricevuti
    per le ultime 4 settimane e gli ultimi 4 mesi (finestra mobile).
    """
    conn = get_db()
    cursor = conn.cursor()

    today = datetime.now().date()

    # Periodo settimana corrente (lunedì-domenica)
    current_week_start = today - timedelta(days=today.weekday())

    def period_stats(start_date, end_date):
        """Restituisce lezioni completate e pagamenti ricevuti fino all'ultima data utile."""
        start_date = max(start_date, MIN_DATA_DATE)
        effective_end = min(end_date, today)
        if effective_end < start_date:
            return 0, 0, 0, effective_end

        cursor.execute(
            'SELECT COUNT(*) FROM lezioni WHERE giorno BETWEEN ? AND ?',
            (str(start_date), str(effective_end))
        )
        lessons_completed = cursor.fetchone()[0] or 0

        status_placeholders = ','.join(['?' for _ in EXCLUDED_PAYMENT_STATUSES])
        cursor.execute(
            f'''
            SELECT COALESCE(SUM(somma), 0), COUNT(*)
            FROM pagamenti
            WHERE giorno BETWEEN ? AND ?
              AND stato NOT IN ({status_placeholders})
            ''',
            [str(start_date), str(effective_end), *EXCLUDED_PAYMENT_STATUSES]
        )
        payments_sum, payments_count = cursor.fetchone()
        payments_sum = payments_sum or 0
        payments_count = payments_count or 0

        return lessons_completed, payments_sum, payments_count, effective_end

    weeks = []
    offset = 0
    while len(weeks) < 4:
        start = current_week_start - timedelta(days=7 * offset)
        end = start + timedelta(days=6)
        if end < MIN_DATA_DATE:
            break
        lessons_completed, payments_sum, payments_count, data_end = period_stats(start, end)
        if offset == 0:
            title = 'Settimana corrente'
        elif offset == 1:
            title = 'Settimana precedente'
        else:
            title = f'{offset} settimane fa'
        display_start = max(start, MIN_DATA_DATE)
        display_end = min(end, today)
        weeks.append({
            'title': title,
            'range_label': f"{display_start.strftime('%d/%m')} → {display_end.strftime('%d/%m')}",
            'lessons_completed': lessons_completed,
            'payments_sum': payments_sum,
            'payments_count': payments_count,
            'data_until': data_end.strftime('%d/%m/%Y'),
            'is_current': offset == 0
        })
        offset += 1

    month_names = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
                   'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

    def month_range(offset):
        year = today.year
        month = today.month
        for _ in range(offset):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        start = datetime(year, month, 1).date()
        if month == 12:
            next_month = datetime(year + 1, 1, 1).date()
        else:
            next_month = datetime(year, month + 1, 1).date()
        end = next_month - timedelta(days=1)
        return start, end, month, year

    months = []
    offset = 0
    while len(months) < 4:
        start, end, month, year = month_range(offset)
        if end < MIN_DATA_DATE:
            break
        lessons_completed, payments_sum, payments_count, data_end = period_stats(start, end)
        if offset == 0:
            title = 'Mese corrente'
        elif offset == 1:
            title = 'Mese precedente'
        else:
            title = f'{offset} mesi fa'
        display_start = max(start, MIN_DATA_DATE)
        display_end = min(end, today)
        months.append({
            'title': title,
            'label': f"{month_names[month]} {year}",
            'range_label': f"{display_start.strftime('%d/%m')} → {display_end.strftime('%d/%m')}",
            'lessons_completed': lessons_completed,
            'payments_sum': payments_sum,
            'payments_count': payments_count,
            'data_until': data_end.strftime('%d/%m/%Y'),
            'is_current': offset == 0
        })
        offset += 1

    conn.close()

    return {
        'today': today.strftime('%d/%m/%Y'),
        'weeks': weeks,
        'months': months
    }


if __name__ == '__main__':
    print("🌐 Interfaccia Web avviata su http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
