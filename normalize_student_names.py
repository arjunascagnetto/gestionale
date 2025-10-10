#!/usr/bin/env python
"""
Script per uniformare i nomi degli studenti basandosi sugli abbinamenti esistenti.

Logica:
1. Analizza gli abbinamenti esistenti per trovare varianti di nomi
2. Per ogni gruppo di varianti, sceglie il nome "canonico" (il più frequente)
3. Aggiorna tutti i record con il nome canonico

Esempio: "Yana", "YanaeVasilisa", "Yana Vasilisa" → tutti diventano "YanaeVasilisa"
"""
import sqlite3
from pathlib import Path
from collections import defaultdict
import re

DB_PATH = Path(__file__).parent / "pagamenti.db"


def normalize_name(name):
    """
    Normalizza un nome per il confronto:
    - Rimuove spazi
    - Lowercase
    - Rimuove caratteri speciali
    """
    normalized = name.lower().replace(' ', '').replace('_', '').replace('-', '')
    return normalized


def find_name_groups():
    """
    Trova gruppi di nomi simili basandosi sugli abbinamenti esistenti.

    Returns:
        Dict[str, list]: Dizionario con nome normalizzato -> lista di varianti
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ottieni tutti i nomi studenti unici dalle lezioni
    cursor.execute('SELECT DISTINCT nome_studente FROM lezioni ORDER BY nome_studente')
    all_students = [row[0] for row in cursor.fetchall()]

    # Raggruppa nomi simili
    groups = defaultdict(list)

    for student in all_students:
        normalized = normalize_name(student)
        groups[normalized].append(student)

    conn.close()

    # Filtra solo gruppi con più varianti
    name_groups = {k: v for k, v in groups.items() if len(v) > 1}

    return name_groups, groups


def choose_canonical_name(variants):
    """
    Sceglie il nome canonico tra le varianti.

    Criteri:
    1. Il più lungo (più completo)
    2. Il più frequente negli abbinamenti

    Args:
        variants: Lista di varianti del nome

    Returns:
        str: Nome canonico scelto
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Conta frequenza di ogni variante negli abbinamenti
    frequency = {}
    for variant in variants:
        cursor.execute('''
            SELECT COUNT(*)
            FROM pagamenti_lezioni pl
            JOIN lezioni l ON pl.lezione_id = l.id_lezione
            WHERE l.nome_studente = ?
        ''', (variant,))
        frequency[variant] = cursor.fetchone()[0]

    conn.close()

    # Scegli il più frequente, poi il più lungo
    canonical = max(variants, key=lambda x: (frequency.get(x, 0), len(x)))

    return canonical


def update_student_name(old_name, new_name):
    """
    Aggiorna il nome studente in tutte le tabelle.

    Args:
        old_name: Nome vecchio
        new_name: Nome nuovo (canonico)

    Returns:
        int: Numero di record aggiornati
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updated = 0

    try:
        # Aggiorna lezioni
        cursor.execute('UPDATE lezioni SET nome_studente = ? WHERE nome_studente = ?',
                      (new_name, old_name))
        updated += cursor.rowcount

        # Aggiorna associazioni
        cursor.execute('UPDATE associazioni SET nome_studente = ? WHERE nome_studente = ?',
                      (new_name, old_name))
        updated += cursor.rowcount

        conn.commit()
        return updated

    except Exception as e:
        conn.rollback()
        print(f"❌ Errore aggiornando {old_name} -> {new_name}: {e}")
        return 0
    finally:
        conn.close()


def main():
    """Funzione principale."""
    print("=" * 70)
    print("UNIFORMAZIONE NOMI STUDENTI")
    print("=" * 70)
    print()

    # Trova gruppi di nomi simili
    print("🔍 Analisi nomi studenti...")
    name_groups, all_groups = find_name_groups()

    if not name_groups:
        print("✅ Nessuna variante trovata. Tutti i nomi sono già uniformi!")
        return

    print(f"\n📊 Trovate {len(name_groups)} varianti da uniformare:\n")

    # Mostra gruppi trovati e chiedi conferma
    changes = []
    for normalized, variants in name_groups.items():
        canonical = choose_canonical_name(variants)
        print(f"  Gruppo '{normalized}':")
        print(f"    Varianti: {variants}")
        print(f"    Canonico scelto: '{canonical}'")
        print()

        for variant in variants:
            if variant != canonical:
                changes.append((variant, canonical))

    if not changes:
        print("✅ Nessun cambiamento necessario!")
        return

    print(f"\n⚠️  Saranno effettuati {len(changes)} cambiamenti:")
    for old, new in changes:
        print(f"  '{old}' → '{new}'")

    print("\n" + "=" * 70)
    response = input("Procedere con l'uniformazione? (s/N): ")

    if response.lower() != 's':
        print("❌ Operazione annullata.")
        return

    print("\n🔄 Uniformazione in corso...\n")

    total_updated = 0
    for old_name, new_name in changes:
        updated = update_student_name(old_name, new_name)
        if updated > 0:
            print(f"  ✅ '{old_name}' → '{new_name}': {updated} record aggiornati")
            total_updated += updated

    print("\n" + "=" * 70)
    print(f"✅ COMPLETATO: {total_updated} record totali aggiornati")
    print("=" * 70)

    # Mostra risultato finale
    print("\n📋 Nomi studenti finali:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT nome_studente FROM lezioni ORDER BY nome_studente')
    final_names = [row[0] for row in cursor.fetchall()]
    conn.close()

    for name in final_names:
        normalized = normalize_name(name)
        variants = all_groups.get(normalized, [])
        if len(variants) > 1:
            print(f"  ⚠️  '{name}' (aveva varianti: {variants})")
        else:
            print(f"  ✅ '{name}'")


if __name__ == "__main__":
    main()
