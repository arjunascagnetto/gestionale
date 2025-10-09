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
            COALESCE(SUM(pl.quota_usata), 0) as quota_pagata,
            CASE WHEN COALESCE(SUM(pl.quota_usata), 0) > 0 THEN 1 ELSE 0 END as is_abbinata
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
            'is_abbinata': row['is_abbinata']
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
            p.somma - COALESCE(SUM(pl.quota_usata), 0) as residuo
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
            'residuo': row['residuo']
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


def save_association(nome_pagante, nome_studente):
    """Salva associazione pagante→studente (aggiorna se esiste già)."""
    conn = get_db()
    cursor = conn.cursor()

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
        conn.commit()
    except Exception as e:
        print(f"Errore salvataggio associazione: {e}")
    finally:
        conn.close()


@app.route('/')
def index():
    """Pagina principale."""
    lesson_order = request.args.get('lesson_order', 'DESC')
    payment_order = request.args.get('payment_order', 'DESC')

    lessons = get_unassigned_lessons(lesson_order)
    payments = get_available_payments(payment_order)
    abbinamenti = get_existing_abbinamenti()

    return render_template('index.html',
                          lessons=lessons,
                          payments=payments,
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
        # Calcola costo per lezione (assumiamo tutte le lezioni costano uguale)
        # In futuro potresti aggiungere un campo 'costo' alla tabella lezioni
        costo_per_lezione = 2000  # Default: 2000 RUB per lezione

        # Per ogni lezione, distribuisci i pagamenti
        for lesson_id in lesson_ids:
            # Recupera studente
            cursor.execute('SELECT nome_studente FROM lezioni WHERE id_lezione = ?', (lesson_id,))
            studente_row = cursor.fetchone()

            if not studente_row:
                print(f"Errore: Lezione {lesson_id} non trovata")
                continue

            studente = studente_row['nome_studente']

            quota_residua = costo_per_lezione

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
                save_association(nome_pagante, studente)

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
