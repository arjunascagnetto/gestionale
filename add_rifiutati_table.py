#!/usr/bin/env python
"""
Script per aggiungere la tabella suggerimenti_rifiutati al database.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "pagamenti.db"

def add_rifiutati_table():
    """Aggiunge tabella per tracciare suggerimenti rifiutati."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("📊 Creazione tabella suggerimenti_rifiutati...")

    # Crea tabella suggerimenti_rifiutati
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggerimenti_rifiutati (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lezione_id INTEGER NOT NULL,
            pagamento_id INTEGER NOT NULL,
            rifiutato_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lezione_id) REFERENCES lezioni(id_lezione),
            FOREIGN KEY (pagamento_id) REFERENCES pagamenti(id_pagamento),
            UNIQUE(lezione_id, pagamento_id)
        )
    ''')

    conn.commit()

    # Verifica
    cursor.execute("SELECT COUNT(*) FROM suggerimenti_rifiutati")
    count = cursor.fetchone()[0]

    print(f"✅ Tabella creata con successo!")
    print(f"   Record attuali: {count}")

    conn.close()

if __name__ == "__main__":
    add_rifiutati_table()
