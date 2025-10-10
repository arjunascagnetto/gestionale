#!/usr/bin/env python
"""
Script per applicare la standardizzazione dei nomi studenti nel database.
Legge la mappatura da normalize_student_names.csv e aggiorna la tabella lezioni.
"""
import csv
import sqlite3
from pathlib import Path

# Configurazione
CSV_PATH = Path(__file__).parent / "normalize_student_names.csv"
DB_PATH = Path(__file__).parent / "pagamenti.db"


def load_name_mapping(csv_path):
    """
    Carica la mappatura dei nomi dal file CSV.

    Returns:
        dict: {nome_originale: nome_standardizzato}
    """
    name_map = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            nome_originale = row['nome_originale']
            nome_standardizzato = row['nome_standardizzato']

            # Salta nomi da chiarire o lezioni di prova
            if nome_standardizzato in ['CHIARIRE', 'LEZIONE_PROVA']:
                print(f"⚠️  Saltato: {nome_originale} → {nome_standardizzato} (da gestire manualmente)")
                continue

            name_map[nome_originale] = nome_standardizzato

    return name_map


def apply_name_normalization(db_path, name_map):
    """
    Applica la normalizzazione dei nomi nel database.

    Args:
        db_path: Path del database SQLite
        name_map: Dizionario {nome_originale: nome_standardizzato}

    Returns:
        dict: Statistiche dell'operazione
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    stats = {
        'total_updates': 0,
        'by_name': {}
    }

    print("\n" + "="*60)
    print("APPLICAZIONE STANDARDIZZAZIONE NOMI")
    print("="*60)

    for nome_originale, nome_standardizzato in sorted(name_map.items()):
        # Conta quante lezioni verranno aggiornate
        cursor.execute(
            "SELECT COUNT(*) FROM lezioni WHERE nome_studente = ?",
            (nome_originale,)
        )
        count = cursor.fetchone()[0]

        if count == 0:
            continue

        # Aggiorna il nome
        cursor.execute(
            "UPDATE lezioni SET nome_studente = ? WHERE nome_studente = ?",
            (nome_standardizzato, nome_originale)
        )

        stats['total_updates'] += count

        if nome_standardizzato not in stats['by_name']:
            stats['by_name'][nome_standardizzato] = 0
        stats['by_name'][nome_standardizzato] += count

        # Log dell'aggiornamento
        if nome_originale != nome_standardizzato:
            print(f"✅ {nome_originale} → {nome_standardizzato} ({count} lezioni)")
        else:
            print(f"   {nome_originale} (già corretto, {count} lezioni)")

    # Commit delle modifiche
    conn.commit()

    # Verifica finale: conta studenti unici dopo normalizzazione
    cursor.execute("SELECT COUNT(DISTINCT nome_studente) FROM lezioni")
    studenti_unici = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM lezioni")
    totale_lezioni = cursor.fetchone()[0]

    conn.close()

    stats['studenti_unici'] = studenti_unici
    stats['totale_lezioni'] = totale_lezioni

    return stats


def print_statistics(stats):
    """
    Stampa statistiche dell'operazione.

    Args:
        stats: Dizionario con statistiche
    """
    print("\n" + "="*60)
    print("RIEPILOGO STANDARDIZZAZIONE")
    print("="*60)
    print(f"Lezioni aggiornate: {stats['total_updates']}")
    print(f"Studenti unici dopo normalizzazione: {stats['studenti_unici']}")
    print(f"Totale lezioni nel database: {stats['totale_lezioni']}")
    print("="*60)

    if stats['by_name']:
        print("\n📊 LEZIONI PER STUDENTE (dopo standardizzazione):")
        print("-"*60)

        # Ordina per numero di lezioni (decrescente)
        sorted_students = sorted(
            stats['by_name'].items(),
            key=lambda x: x[1],
            reverse=True
        )

        for nome, count in sorted_students:
            print(f"   {nome:.<40} {count:>3} lezioni")

        print("="*60)


def main():
    """Funzione principale."""
    print("="*60)
    print("STANDARDIZZAZIONE NOMI STUDENTI")
    print("="*60)
    print(f"CSV mappatura: {CSV_PATH.name}")
    print(f"Database: {DB_PATH.name}")
    print("="*60)

    # Verifica file CSV
    if not CSV_PATH.exists():
        print(f"❌ File CSV non trovato: {CSV_PATH}")
        return

    # Verifica database
    if not DB_PATH.exists():
        print(f"❌ Database non trovato: {DB_PATH}")
        return

    # Carica mappatura
    print("\n📖 Caricamento mappatura nomi...")
    name_map = load_name_mapping(CSV_PATH)
    print(f"✅ Caricata mappatura per {len(name_map)} nomi\n")

    # Applica normalizzazione
    stats = apply_name_normalization(DB_PATH, name_map)

    # Stampa statistiche
    print_statistics(stats)

    print("\n✅ Standardizzazione completata!\n")


if __name__ == "__main__":
    main()
