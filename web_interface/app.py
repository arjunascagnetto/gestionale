#!/usr/bin/env python
"""
Interfaccia Web - Gestione Storico Pagamenti e Lezioni
Flask app per abbinare manualmente pagamenti storici a lezioni.
"""
import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "pagamenti.db"


def get_db():
    """Crea connessione database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_unassigned_lessons(order='DESC'):
    """
    Recupera TUTTE le lezioni, con flag per indicare se sono abbinate.

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(f'''
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
        GROUP BY l.id_lezione
        ORDER BY l.giorno {order}, l.ora {order}
    ''')

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


def get_available_payments(order='DESC'):
    """
    Recupera pagamenti con residuo disponibile.

    Args:
        order: 'ASC' o 'DESC' per ordinamento data
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT
            p.id_pagamento,
            p.nome_pagante,
            p.giorno,
            p.ora,
            p.somma,
            p.valuta,
            COALESCE(SUM(pl.quota_usata), 0) as quota_utilizzata,
            p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo,
            CASE WHEN COALESCE(SUM(pl.quota_usata), 0) > 0 THEN 1 ELSE 0 END as has_abbinamenti
        FROM pagamenti p
        LEFT JOIN pagamenti_lezioni pl ON p.id_pagamento = pl.pagamento_id
        WHERE p.stato IN ('sospeso', 'archivio')
        GROUP BY p.id_pagamento
        HAVING residuo > 0
        ORDER BY p.giorno {order}, p.ora {order}
    ''')

    payments = []
    for row in cursor.fetchall():
        payments.append({
            'id': row['id_pagamento'],
            'nome_pagante': row['nome_pagante'],
            'giorno': row['giorno'],
            'ora': row['ora'],
            'somma': row['somma'],
            'valuta': row['valuta'],
            'residuo': row['residuo'],
            'quota_utilizzata': row['quota_utilizzata'],
            'has_abbinamenti': row['has_abbinamenti']
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


def get_suggested_abbinamenti():
    """
    Genera suggerimenti intelligenti di abbinamento basati su:
    1. Associazioni studente-pagante esistenti
    2. Lezioni non ancora completamente pagate
    3. Pagamenti con residuo disponibile
    4. Vicinanza temporale (±7 giorni)

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
        WHERE p.stato IN ('sospeso', 'archivio')
            AND l.gratis = 0
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

    lessons = get_unassigned_lessons(lesson_order)
    payments = get_available_payments(payment_order)
    suggestions = get_suggested_abbinamenti()
    abbinamenti = get_existing_abbinamenti()

    return render_template('index.html',
                          lessons=lessons,
                          payments=payments,
                          suggestions=suggestions,
                          abbinamenti=abbinamenti,
                          lesson_order=lesson_order,
                          payment_order=payment_order)


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
    Rifiuta un suggerimento (non fa nulla sul DB, solo rimuove dalla UI).
    In futuro potremmo salvare i rifiuti per migliorare i suggerimenti.
    """
    data = request.get_json()
    lezione_id = data.get('lezione_id')
    pagamento_id = data.get('pagamento_id')

    # Al momento non salviamo i rifiuti, solo confermiamo
    # In futuro: salvare in una tabella 'suggerimenti_rifiutati'
    return jsonify({'success': True, 'message': 'Suggerimento ignorato'})


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


if __name__ == '__main__':
    print("🌐 Interfaccia Web avviata su http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
