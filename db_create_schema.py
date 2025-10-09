#!/usr/bin/env python
"""
Script per la creazione dello schema del database per il progetto di gestione pagamenti.
Crea tutte le tabelle necessarie come descritto nella documentazione del progetto.
"""
import os
import sqlite3
import datetime as dt
from pathlib import Path

# Configurazione
DB_FILENAME = "pagamenti.db"
# Garantisce che il DB sia creato nella directory del progetto, anche se lo script viene eseguito da un'altra posizione
DB_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / DB_FILENAME

def create_schema(conn):
    """
    Crea tutte le tabelle e gli indici necessari per il progetto.
    
    Args:
        conn: Connessione SQLite attiva
    """
    cursor = conn.cursor()
    
    # Creazione della tabella pagamenti
    print("Creazione tabella 'pagamenti'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamenti (
        id_pagamento INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_pagante TEXT NOT NULL,
        giorno DATE NOT NULL,
        ora TIME NOT NULL,
        somma NUMERIC(10,2) NOT NULL,
        valuta TEXT DEFAULT 'EUR',
        stato TEXT CHECK(stato IN ('sospeso', 'associato', 'usato')) DEFAULT 'sospeso',
        fonte_msg_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Creazione della tabella lezioni
    print("Creazione tabella 'lezioni'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lezioni (
        id_lezione INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_studente TEXT NOT NULL,
        giorno DATE NOT NULL,
        ora TIME NOT NULL,
        nextcloud_event_id TEXT UNIQUE,
        durata_min INTEGER DEFAULT 60,
        stato TEXT CHECK(stato IN ('prevista', 'svolta', 'pagata')) DEFAULT 'prevista',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Creazione della tabella associazioni
    print("Creazione tabella 'associazioni'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS associazioni (
        id_assoc INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_studente TEXT UNIQUE NOT NULL,
        nome_pagante TEXT NOT NULL,
        note TEXT,
        valid_from DATE DEFAULT CURRENT_DATE,
        valid_to DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Creazione della tabella ponte pagamenti_lezioni
    print("Creazione tabella 'pagamenti_lezioni'...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamenti_lezioni (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pagamento_id INTEGER NOT NULL,
        lezione_id INTEGER NOT NULL,
        quota_usata NUMERIC(10,2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pagamento_id) REFERENCES pagamenti (id_pagamento) ON DELETE CASCADE,
        FOREIGN KEY (lezione_id) REFERENCES lezioni (id_lezione) ON DELETE CASCADE,
        UNIQUE (pagamento_id, lezione_id)
    )
    ''')
    
    # Creazione degli indici per migliorare le performance delle query più frequenti
    print("Creazione indici...")
    
    # Indici per pagamenti
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_pagamenti_stato_giorno 
    ON pagamenti (stato, giorno)
    ''')
    
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_pagamenti_nome_pagante 
    ON pagamenti (nome_pagante)
    ''')
    
    # Indici per lezioni
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_lezioni_giorno_nome_studente 
    ON lezioni (giorno, nome_studente)
    ''')
    
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_lezioni_stato 
    ON lezioni (stato)
    ''')
    
    # Indici per associazioni
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_associazioni_nome_studente 
    ON associazioni (nome_studente)
    ''')
    
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_associazioni_nome_pagante 
    ON associazioni (nome_pagante)
    ''')
    
    # Indici per pagamenti_lezioni
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_pagamenti_lezioni_pagamento 
    ON pagamenti_lezioni (pagamento_id)
    ''')
    
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_pagamenti_lezioni_lezione 
    ON pagamenti_lezioni (lezione_id)
    ''')
    
    # Creazione di trigger per aggiornare automaticamente il timestamp updated_at
    print("Creazione trigger per updated_at...")
    
    # Trigger per pagamenti
    cursor.execute('''
    CREATE TRIGGER IF NOT EXISTS trg_pagamenti_updated_at 
    AFTER UPDATE ON pagamenti
    FOR EACH ROW
    BEGIN
        UPDATE pagamenti SET updated_at = CURRENT_TIMESTAMP WHERE id_pagamento = NEW.id_pagamento;
    END;
    ''')
    
    # Trigger per lezioni
    cursor.execute('''
    CREATE TRIGGER IF NOT EXISTS trg_lezioni_updated_at 
    AFTER UPDATE ON lezioni
    FOR EACH ROW
    BEGIN
        UPDATE lezioni SET updated_at = CURRENT_TIMESTAMP WHERE id_lezione = NEW.id_lezione;
    END;
    ''')
    
    # Trigger per associazioni
    cursor.execute('''
    CREATE TRIGGER IF NOT EXISTS trg_associazioni_updated_at 
    AFTER UPDATE ON associazioni
    FOR EACH ROW
    BEGIN
        UPDATE associazioni SET updated_at = CURRENT_TIMESTAMP WHERE id_assoc = NEW.id_assoc;
    END;
    ''')
    
    conn.commit()

def main():
    print(f"Creazione schema database in: {DB_PATH}")
    
    # Verifica se il database esiste già
    db_exists = os.path.exists(DB_PATH)
    if db_exists:
        print(f"ATTENZIONE: Il database {DB_FILENAME} esiste già.")
        conferma = input("Vuoi continuare e potenzialmente sovrascrivere le tabelle esistenti? (s/n): ")
        if conferma.lower() != 's':
            print("Operazione annullata.")
            return
    
    # Connessione al database (crea il file se non esiste)
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Creazione dello schema
        create_schema(conn)
        
        # Verifica dello schema
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("\nTabelle create:")
        for table in tables:
            print(f"- {table[0]}")
            
            # Mostra le colonne di ogni tabella
            cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = cursor.fetchall()
            for col in columns:
                print(f"  • {col[1]} ({col[2]})")
            
            # Mostra gli indici di ogni tabella
            cursor.execute(f"PRAGMA index_list({table[0]})")
            indices = cursor.fetchall()
            if indices:
                print(f"  Indici:")
                for idx in indices:
                    print(f"  • {idx[1]}")
            print()
        
        print("Schema creato con successo!")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
