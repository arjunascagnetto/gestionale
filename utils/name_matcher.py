#!/usr/bin/env python
"""
Utility per il matching fuzzy tra nomi di studenti e paganti.
Gestisce transliteration cirillico-latino e calcolo similarità.
"""
from rapidfuzz import fuzz
from transliterate import translit
from unidecode import unidecode
import re


def normalize_name(name):
    """
    Normalizza un nome rimuovendo caratteri speciali, accenti e convertendo in lowercase.

    Args:
        name: Nome da normalizzare

    Returns:
        Nome normalizzato (lowercase, senza accenti, senza caratteri speciali)
    """
    if not name:
        return ""

    # Rimuovi numeri e caratteri speciali tranne spazi
    name = re.sub(r'[^\w\s\u0400-\u04FF]', '', name)

    # Rimuovi accenti (per caratteri latini)
    name = unidecode(name)

    # Lowercase e strip
    return name.lower().strip()


def transliterate_cyrillic(text):
    """
    Translittera testo cirillico in latino.

    Args:
        text: Testo potenzialmente in cirillico

    Returns:
        Testo translitterato in latino
    """
    try:
        # Prova a translitterare dal russo
        return translit(text, 'ru', reversed=True)
    except Exception:
        # Se fallisce (es. testo già latino), ritorna originale
        return text


def extract_first_name(full_name):
    """
    Estrae il primo nome da un nome completo.

    Args:
        full_name: Nome completo (es. "Дарья М." o "Ekaterina A")

    Returns:
        Solo il primo nome (es. "Дарья" o "Ekaterina")
    """
    if not full_name:
        return ""

    # Split per spazi e prendi la prima parte
    parts = full_name.strip().split()
    if parts:
        # Rimuovi eventuali punti o virgole
        return parts[0].rstrip('.,;:')

    return full_name


def calculate_similarity(name1, name2):
    """
    Calcola la similarità tra due nomi usando diversi algoritmi.

    Args:
        name1: Primo nome
        name2: Secondo nome

    Returns:
        Score di similarità (0-100)
    """
    if not name1 or not name2:
        return 0

    # Normalizza entrambi i nomi
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    # Translittera se necessario
    trans1 = transliterate_cyrillic(norm1)
    trans2 = transliterate_cyrillic(norm2)

    # Calcola diversi tipi di similarità
    ratio = fuzz.ratio(trans1, trans2)
    partial_ratio = fuzz.partial_ratio(trans1, trans2)
    token_sort = fuzz.token_sort_ratio(trans1, trans2)

    # Prendi il massimo tra i vari score
    return max(ratio, partial_ratio, token_sort)


def find_best_matches(source_name, candidate_names, min_score=0, top_n=5):
    """
    Trova i migliori match per un nome tra una lista di candidati.

    Args:
        source_name: Nome da matchare (es. nome pagante)
        candidate_names: Lista di nomi candidati (es. nomi studenti)
        min_score: Score minimo per considerare un match (0-100)
        top_n: Numero massimo di risultati da ritornare

    Returns:
        Lista di tuple (nome_candidato, score) ordinata per score decrescente
    """
    if not source_name or not candidate_names:
        return []

    # Estrai solo il primo nome dal source
    source_first_name = extract_first_name(source_name)

    matches = []

    for candidate in candidate_names:
        # Calcola similarità
        score = calculate_similarity(source_first_name, candidate)

        # Aggiungi solo se supera la soglia minima
        if score >= min_score:
            matches.append((candidate, score))

    # Ordina per score decrescente e prendi i top_n
    matches.sort(key=lambda x: x[1], reverse=True)

    return matches[:top_n]


def get_match_with_confidence(source_name, candidate_names, high_confidence_threshold=95):
    """
    Trova il miglior match e determina se ha alta confidenza.

    Args:
        source_name: Nome da matchare
        candidate_names: Lista di nomi candidati
        high_confidence_threshold: Soglia per considerare un match ad alta confidenza

    Returns:
        dict con:
        - best_match: Nome del miglior candidato (o None)
        - score: Score del miglior match (0-100)
        - high_confidence: Boolean, True se score >= threshold
        - all_matches: Lista di tutti i match ordinati
    """
    matches = find_best_matches(source_name, candidate_names, min_score=0, top_n=10)

    if not matches:
        return {
            'best_match': None,
            'score': 0,
            'high_confidence': False,
            'all_matches': []
        }

    best_match, best_score = matches[0]

    return {
        'best_match': best_match,
        'score': best_score,
        'high_confidence': best_score >= high_confidence_threshold,
        'all_matches': matches
    }


# Test della funzione se eseguito direttamente
if __name__ == "__main__":
    # Test transliteration
    print("Test Transliteration:")
    print(f"Екатерина → {transliterate_cyrillic('Екатерина')}")
    print(f"Дарья → {transliterate_cyrillic('Дарья')}")
    print(f"Наили → {transliterate_cyrillic('Наили')}")
    print()

    # Test matching
    print("Test Matching:")

    paganti = [
        "Екатерина А.",
        "Дарья М.",
        "Наили Г.",
        "Алексей Д.",
        "Роберт Л."
    ]

    studenti = [
        "Ekaterina",
        "Daria",
        "Naili",
        "Aleksey D",
        "Sofia",
        "Elena"
    ]

    for pagante in paganti:
        result = get_match_with_confidence(pagante, studenti, high_confidence_threshold=95)
        print(f"\nPagante: {pagante}")
        print(f"  Best match: {result['best_match']} (score: {result['score']})")
        print(f"  High confidence: {result['high_confidence']}")
        print(f"  Top 3 matches: {result['all_matches'][:3]}")
