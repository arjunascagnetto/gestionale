#!/usr/bin/env python
"""
Test di connessione a SQLite e operazioni di base.
"""
import os
import sqlite3
import datetime as dt
from pathlib import Path

# Configurazione
DB_FILENAME = "pagamenti.db"
# Garantisce che il DB sia creato nella directory del progetto, anche se lo script viene eseguito da un'altra posizione
DB_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / DB_FILENAME

def main():
    print(f"Test di connessione a SQLite - DB: {DB_PATH}")
    
    # Connessione al database (crea il file se non esiste)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Per accedere alle colonne per nome
    cursor = conn.cursor()
    
    print("Connessione stabilita con successo.")
    
    # Creazione di una tabella di test
    print("\nCreazione tabella di test...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS test_pagamenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_pagante TEXT NOT NULL,
        giorno DATE NOT NULL,
        ora TIME NOT NULL,
        somma REAL NOT NULL,
        stato TEXT DEFAULT 'sospeso',
        fonte_msg_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Inserimento di un record di test
    print("\nInserimento record di test...")
    now = dt.datetime.now()
    oggi = now.strftime("%Y-%m-%d")
    ora_attuale = now.strftime("%H:%M:%S")
    test_dati = (
        "Mario Rossi",
        oggi,
        ora_attuale,
        25.50,
        "sospeso",
        f"test_msg_{now.timestamp()}"
    )
    
    cursor.execute('''
    INSERT INTO test_pagamenti 
    (nome_pagante, giorno, ora, somma, stato, fonte_msg_id)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', test_dati)
    
    conn.commit()
    print(f"Record inserito con ID: {cursor.lastrowid}")
    
    # Recupero e visualizzazione dei dati
    print("\nRecupero dati inseriti:")
    cursor.execute("SELECT * FROM test_pagamenti ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"ID: {row['id']}")
        print(f"Nome: {row['nome_pagante']}")
        print(f"Data e ora: {row['giorno']} {row['ora']}")
        print(f"Somma: €{row['somma']}")
        print(f"Stato: {row['stato']}")
        print(f"ID Messaggio: {row['fonte_msg_id']}")
        print(f"Creato: {row['created_at']}")
        print(f"Aggiornato: {row['updated_at']}")
        print("-" * 40)
    
    # Test aggiornamento
    print("\nTest aggiornamento record:")
    cursor.execute('''
    UPDATE test_pagamenti 
    SET stato = 'associato', updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (cursor.lastrowid,))
    
    conn.commit()
    print(f"Record aggiornato. Righe modificate: {cursor.rowcount}")
    
    # Verifica aggiornamento
    cursor.execute("SELECT id, stato, updated_at FROM test_pagamenti WHERE id = ?", (cursor.lastrowid,))
    updated_row = cursor.fetchone()
    print(f"Stato aggiornato: {updated_row['stato']}")
    print(f"Timestamp aggiornamento: {updated_row['updated_at']}")
    
    # Verifica indice su fonte_msg_id
    print("\nVerifica struttura tabella e indici:")
    cursor.execute("PRAGMA table_info(test_pagamenti)")
    columns = cursor.fetchall()
    print("Colonne:")
    for col in columns:
        print(f"  {col['name']} ({col['type']})")
    
    cursor.execute("PRAGMA index_list(test_pagamenti)")
    indices = cursor.fetchall()
    print("Indici:")
    for idx in indices:
        print(f"  {idx['name']}")
    
    # Chiusura connessione
    conn.close()
    print("\nTest completato con successo!")

if __name__ == "__main__":
    main()
