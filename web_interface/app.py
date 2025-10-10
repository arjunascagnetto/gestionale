#!/usr/bin/env python
"""
Interfaccia Web - Gestione Storico Pagamenti e Lezioni
Flask app per abbinare manualmente pagamenti storici a lezioni.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
import calendar

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "pagamenti.db"


def get_db():
    """Crea connessione database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_unassigned_lessons(order='DESC', filter_studenti=None):
    """
    Recupera TUTTE le lezioni, con flag per indicare se sono abbinate.

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
        filter_studenti: Lista di nomi studenti da filtrare (None = tutti)
    """
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
    where_clause = ''
    params = []
    if filter_studenti and len(filter_studenti) > 0:
        placeholders = ','.join(['?' for _ in filter_studenti])
        where_clause = f' WHERE l.nome_studente IN ({placeholders})'
        params = filter_studenti

    query += where_clause
    query += f' GROUP BY l.id_lezione ORDER BY l.giorno {order}, l.ora {order}'

    cursor.execute(query, params)

    lessons = []
    for row in cursor.fetchall():
        lessons.append({
            'id': row['id_lezione'],
            'studente': row['nome_studente'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'costo': row['costo'],
            'gratis': row['gratis'],
            'is_abbinata': row['is_abbinata'],
            'quota_pagata': row['quota_pagata'],
            'is_completamente_pagata': row['is_completamente_pagata']
        })

    conn.close()
    return lessons


def get_available_payments(order='DESC', filter_paganti=None):
    """
    Recupera TUTTI i pagamenti (inclusi quelli completamente utilizzati).

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
        filter_paganti: Lista di nomi paganti da filtrare (None = tutti)
    """
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
    where_clauses = []
    params = []

    if filter_paganti and len(filter_paganti) > 0:
        placeholders = ','.join(['?' for _ in filter_paganti])
        where_clauses.append(f'p.nome_pagante IN ({placeholders})')
        params = filter_paganti

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)

    query += f' GROUP BY p.id_pagamento ORDER BY p.giorno {order}, p.ora {order}'

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
        ORDER BY pl.id DESC
    ''')

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


def get_all_studenti():
    """Recupera lista unica di tutti gli studenti (da lezioni)."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT nome_studente
        FROM lezioni
        ORDER BY nome_studente ASC
    ''')

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
        ORDER BY nome_pagante ASC
    ''')

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
            AND l.gratis = 0
            AND sr.id IS NULL
        GROUP BY l.id_lezione, p.id_pagamento
        HAVING
            da_pagare > 0
            AND residuo_pagamento > 0
            AND giorni_distanza <= 7
        ORDER BY
            giorni_distanza ASC,
            l.giorno DESC
        LIMIT 20
    ''')

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

    lessons = get_unassigned_lessons(lesson_order, filter_studenti)
    payments = get_available_payments(payment_order, filter_paganti)
    suggestions = get_suggested_abbinamenti()
    abbinamenti = get_existing_abbinamenti()

    # Ottieni liste complete per i filtri
    all_studenti = get_all_studenti()
    all_paganti = get_all_paganti()

    return render_template('index.html',
                          lessons=lessons,
                          payments=payments,
                          suggestions=suggestions,
                          abbinamenti=abbinamenti,
                          lesson_order=lesson_order,
                          payment_order=payment_order,
                          all_studenti=all_studenti,
                          all_paganti=all_paganti,
                          filter_studenti=filter_studenti or [],
                          filter_paganti=filter_paganti or [])


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
            costo_lezione = studente_row['costo'] or 2000  # Default se NULL

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

    return redirect(url_for('index'))


@app.route('/stats')
def stats():
    """Pagina statistiche."""
    # Ottieni mese e anno dai parametri GET (default: mese e anno corrente)
    selected_month = request.args.get('month', type=int)
    selected_year = request.args.get('year', type=int)

    # Se non specificati, usa mese e anno corrente
    today = datetime.now().date()
    if selected_month is None:
        selected_month = today.month
    if selected_year is None:
        selected_year = today.year

    stats_data = calculate_statistics(selected_month, selected_year)
    return render_template('stats.html', stats=stats_data)


@app.route('/rifiutati')
def rifiutati():
    """Pagina con lista abbinamenti rifiutati."""
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
        ORDER BY sr.rifiutato_at DESC
    ''')

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
    return render_template('rifiutati.html', rifiutati=rifiutati_list)


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
    conn = get_db()
    cursor = conn.cursor()

    # Analizza varianti di nomi (stessa logica di normalize_student_names.py)
    cursor.execute('SELECT DISTINCT nome_studente FROM lezioni ORDER BY nome_studente')
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
                    WHERE l.nome_studente = ?
                ''', (variant,))
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
        GROUP BY l.id_lezione
        HAVING COALESCE(SUM(pl.quota_usata), 0) >= l.costo
    ''')
    paid_lessons_count = len(cursor.fetchall())

    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE nextcloud_event_id IS NOT NULL')
    total_lessons_count = cursor.fetchone()[0]

    conn.close()

    return render_template('normalizza.html',
                          name_groups=name_groups,
                          paid_lessons_count=paid_lessons_count,
                          total_lessons_count=total_lessons_count)


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
        for change in changes:
            old_name = change['old']
            new_name = change['new']

            # Aggiorna lezioni
            cursor.execute('UPDATE lezioni SET nome_studente = ? WHERE nome_studente = ?',
                          (new_name, old_name))
            updated = cursor.rowcount

            # Aggiorna associazioni
            cursor.execute('UPDATE associazioni SET nome_studente = ? WHERE nome_studente = ?',
                          (new_name, old_name))
            updated += cursor.rowcount

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


@app.route('/api/update_calendar', methods=['POST'])
def api_update_calendar():
    """API per eseguire aggiornamento INCREMENTALE Google Calendar."""
    import subprocess

    try:
        # Usa la versione incrementale (più veloce, aggiorna solo modifiche)
        script_path = Path(__file__).parent.parent / 'update_gcal_incremental.py'

        # Esegui e cattura output
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
                'message': 'Calendario aggiornato con successo (solo modifiche)'
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


def calculate_statistics(selected_month=None, selected_year=None):
    """
    Calcola tutte le statistiche per la pagina stats.

    Args:
        selected_month: Mese selezionato (1-12), default: mese corrente
        selected_year: Anno selezionato, default: anno corrente
    """
    conn = get_db()
    cursor = conn.cursor()

    # Date di riferimento
    today = datetime.now().date()

    # Usa mese/anno selezionato o corrente
    if selected_month is None:
        selected_month = today.month
    if selected_year is None:
        selected_year = today.year

    week_start = today - timedelta(days=today.weekday())  # Lunedì di questa settimana
    week_end = week_start + timedelta(days=6)  # Domenica

    # Calcola inizio e fine del mese selezionato
    month_start = datetime(selected_year, selected_month, 1).date()
    # Ultimo giorno del mese
    if selected_month == 12:
        month_end = datetime(selected_year + 1, 1, 1).date()
    else:
        month_end = datetime(selected_year, selected_month + 1, 1).date()

    # Numero di giorni nel mese selezionato
    days_in_month = (month_end - month_start).days

    # Nome mese in italiano
    month_names = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
                   'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

    # ===== GENERA LISTE PER I DROPDOWN =====

    # Lista mesi
    available_months = [
        {'value': i, 'label': month_names[i]}
        for i in range(1, 13)
    ]

    # Lista anni (da quando ci sono dati nel DB)
    cursor.execute('''
        SELECT MIN(SUBSTR(giorno, 1, 4)) as min_year, MAX(SUBSTR(giorno, 1, 4)) as max_year
        FROM (
            SELECT giorno FROM pagamenti
            UNION
            SELECT giorno FROM lezioni
        )
    ''')
    year_row = cursor.fetchone()
    min_year = int(year_row[0]) if year_row[0] else today.year
    max_year = int(year_row[1]) if year_row[1] else today.year

    available_years = list(range(min_year, max_year + 1))

    # ===== LEZIONI =====

    # Lezioni oggi
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno = ?', (str(today),))
    lessons_today = cursor.fetchone()[0]

    # Lezioni questa settimana
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno BETWEEN ? AND ?',
                   (str(week_start), str(week_end)))
    lessons_week = cursor.fetchone()[0]

    # Lezioni nel mese selezionato
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno >= ? AND giorno < ?',
                   (str(month_start), str(month_end)))
    lessons_month = cursor.fetchone()[0]

    # Lezioni PASSATE nel mese selezionato (già svolte)
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno >= ? AND giorno < ? AND giorno <= ?',
                   (str(month_start), str(month_end), str(today)))
    lessons_month_past = cursor.fetchone()[0]

    # Lezioni FUTURE nel mese selezionato
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno >= ? AND giorno < ? AND giorno > ?',
                   (str(month_start), str(month_end), str(today)))
    lessons_month_future = cursor.fetchone()[0]

    # Lezioni PASSATE questa settimana
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno BETWEEN ? AND ? AND giorno <= ?',
                   (str(week_start), str(week_end), str(today)))
    lessons_week_past = cursor.fetchone()[0]

    # Lezioni FUTURE questa settimana
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE giorno BETWEEN ? AND ? AND giorno > ?',
                   (str(week_start), str(week_end), str(today)))
    lessons_week_future = cursor.fetchone()[0]

    # ===== PAGAMENTI =====

    # Pagamenti oggi
    cursor.execute('SELECT COALESCE(SUM(somma), 0), COUNT(*) FROM pagamenti WHERE giorno = ?',
                   (str(today),))
    row = cursor.fetchone()
    payments_today = row[0]
    payments_today_count = row[1]

    # Pagamenti questa settimana
    cursor.execute('SELECT COALESCE(SUM(somma), 0), COUNT(*) FROM pagamenti WHERE giorno BETWEEN ? AND ?',
                   (str(week_start), str(week_end)))
    row = cursor.fetchone()
    payments_week = row[0]
    payments_week_count = row[1]

    # Pagamenti nel mese selezionato
    cursor.execute('SELECT COALESCE(SUM(somma), 0), COUNT(*) FROM pagamenti WHERE giorno >= ? AND giorno < ?',
                   (str(month_start), str(month_end)))
    row = cursor.fetchone()
    payments_month = row[0]
    payments_month_count = row[1]

    # Media giornaliera del mese
    payments_month_avg = payments_month / days_in_month if days_in_month > 0 else 0

    # ===== STIME GUADAGNO (basate sui costi delle lezioni) =====

    # Stima guadagno MENSILE (somma dei costi di tutte le lezioni non gratis del mese)
    cursor.execute('''
        SELECT COALESCE(SUM(costo), 0)
        FROM lezioni
        WHERE giorno >= ? AND giorno < ? AND gratis = 0
    ''', (str(month_start), str(month_end)))
    estimated_month_income = cursor.fetchone()[0]

    # Stima guadagno SETTIMANALE
    cursor.execute('''
        SELECT COALESCE(SUM(costo), 0)
        FROM lezioni
        WHERE giorno BETWEEN ? AND ? AND gratis = 0
    ''', (str(week_start), str(week_end)))
    estimated_week_income = cursor.fetchone()[0]

    # Stima guadagno OGGI
    cursor.execute('''
        SELECT COALESCE(SUM(costo), 0)
        FROM lezioni
        WHERE giorno = ? AND gratis = 0
    ''', (str(today),))
    estimated_today_income = cursor.fetchone()[0]

    # ===== TREND ULTIMI 30 GIORNI =====

    # Lezioni per giorno (ultimi 30 giorni)
    chart_start = today - timedelta(days=29)
    cursor.execute('''
        SELECT giorno, COUNT(*) as count
        FROM lezioni
        WHERE giorno BETWEEN ? AND ?
        GROUP BY giorno
        ORDER BY giorno ASC
    ''', (str(chart_start), str(today)))

    lessons_by_day = {row[0]: row[1] for row in cursor.fetchall()}

    chart_lessons_labels = []
    chart_lessons_data = []
    for i in range(30):
        date = chart_start + timedelta(days=i)
        chart_lessons_labels.append(date.strftime('%d/%m'))
        chart_lessons_data.append(lessons_by_day.get(str(date), 0))

    # Pagamenti per giorno (ultimi 30 giorni)
    cursor.execute('''
        SELECT giorno, SUM(somma) as total
        FROM pagamenti
        WHERE giorno BETWEEN ? AND ?
        GROUP BY giorno
        ORDER BY giorno ASC
    ''', (str(chart_start), str(today)))

    payments_by_day = {row[0]: row[1] for row in cursor.fetchall()}

    chart_payments_labels = []
    chart_payments_data = []
    for i in range(30):
        date = chart_start + timedelta(days=i)
        chart_payments_labels.append(date.strftime('%d/%m'))
        chart_payments_data.append(payments_by_day.get(str(date), 0))

    # ===== ABBINAMENTI =====

    # Lezioni completamente pagate
    cursor.execute('''
        SELECT COUNT(DISTINCT l.id_lezione)
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.gratis = 0
        GROUP BY l.id_lezione
        HAVING COALESCE(SUM(pl.quota_usata), 0) >= l.costo
    ''')
    completamente_pagati = len(cursor.fetchall())

    # Lezioni parzialmente pagate
    cursor.execute('''
        SELECT COUNT(DISTINCT l.id_lezione)
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.gratis = 0
        GROUP BY l.id_lezione
        HAVING COALESCE(SUM(pl.quota_usata), 0) > 0 AND COALESCE(SUM(pl.quota_usata), 0) < l.costo
    ''')
    parzialmente_pagati = len(cursor.fetchall())

    # Lezioni non pagate
    cursor.execute('''
        SELECT COUNT(DISTINCT l.id_lezione)
        FROM lezioni l
        LEFT JOIN pagamenti_lezioni pl ON l.id_lezione = pl.lezione_id
        WHERE l.gratis = 0
        GROUP BY l.id_lezione
        HAVING COALESCE(SUM(pl.quota_usata), 0) = 0
    ''')
    non_pagati = len(cursor.fetchall())

    # Lezioni gratis
    cursor.execute('SELECT COUNT(*) FROM lezioni WHERE gratis = 1')
    gratis = cursor.fetchone()[0]

    conn.close()

    return {
        'today': {
            'date': today.strftime('%d/%m/%Y')
        },
        'week': {
            'start': week_start.strftime('%d/%m'),
            'end': week_end.strftime('%d/%m')
        },
        'month': {
            'name': month_names[selected_month],
            'year': selected_year
        },
        'lessons': {
            'today': lessons_today,
            'week': lessons_week,
            'week_past': lessons_week_past,
            'week_future': lessons_week_future,
            'month': lessons_month,
            'month_past': lessons_month_past,
            'month_future': lessons_month_future
        },
        'payments': {
            'today': payments_today,
            'today_count': payments_today_count,
            'week': payments_week,
            'week_count': payments_week_count,
            'month': payments_month,
            'month_count': payments_month_count,
            'month_avg': payments_month_avg
        },
        'income': {
            'estimated_today': estimated_today_income,
            'estimated_week': estimated_week_income,
            'estimated_month': estimated_month_income
        },
        'chart_lessons': {
            'labels': chart_lessons_labels,
            'data': chart_lessons_data
        },
        'chart_payments': {
            'labels': chart_payments_labels,
            'data': chart_payments_data
        },
        'abbinamenti': {
            'completamente_pagati': completamente_pagati,
            'parzialmente_pagati': parzialmente_pagati,
            'non_pagati': non_pagati,
            'gratis': gratis
        },
        'available_months': available_months,
        'available_years': available_years,
        'selected_month': selected_month,
        'selected_year': selected_year
    }


if __name__ == '__main__':
    print("🌐 Interfaccia Web avviata su http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
