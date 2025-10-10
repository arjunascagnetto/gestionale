#!/usr/bin/env python
"""
Script MASTER per importazione completa dati
Esegue in sequenza:
1. Scaricamento TUTTI i pagamenti da Telegram (dal 1 agosto a oggi)
2. Sincronizzazione TUTTE le lezioni da Google Calendar (dal 1 agosto a oggi)

Questo script automatizza l'intero processo di import storico.
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Path degli script
BASE_DIR = Path(__file__).parent
TELEGRAM_SCRIPT = BASE_DIR / "telegram_bulk_ingestor.py"
GCAL_SCRIPT = BASE_DIR / "gcal_bulk_sync.py"
PYTHON_BIN = BASE_DIR / ".cal" / "bin" / "python"


def run_script(script_path, description):
    """
    Esegue uno script Python e mostra l'output in tempo reale.

    Args:
        script_path: Path dello script da eseguire
        description: Descrizione dell'operazione

    Returns:
        True se successo, False altrimenti
    """
    print("\n" + "="*60)
    print(f"▶️  {description}")
    print("="*60)
    print(f"Script: {script_path.name}")
    print(f"Inizio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        # Esegui lo script
        result = subprocess.run(
            [str(PYTHON_BIN), str(script_path)],
            check=True,
            text=True,
            capture_output=False  # Mostra output in tempo reale
        )

        print(f"\n✅ {description} completato!")
        print(f"Fine: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Errore durante: {description}")
        print(f"Codice uscita: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n❌ Errore imprevisto: {e}")
        return False


def main():
    """Funzione principale."""
    print("="*60)
    print("IMPORTAZIONE COMPLETA DATI STORICI")
    print("="*60)
    print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Range: 01/08/2024 → {datetime.now().strftime('%d/%m/%Y')}")
    print("="*60)
    print("\nQuesta operazione scaricherà:")
    print("  1️⃣  TUTTI i messaggi di pagamento da Telegram")
    print("  2️⃣  TUTTE le lezioni da Google Calendar")
    print("\nNOTA: L'operazione potrebbe richiedere alcuni minuti.")
    print("\nPremere CTRL+C per annullare.")
    print("="*60)

    # Verifica esistenza script
    if not TELEGRAM_SCRIPT.exists():
        print(f"\n❌ Script non trovato: {TELEGRAM_SCRIPT}")
        return 1

    if not GCAL_SCRIPT.exists():
        print(f"\n❌ Script non trovato: {GCAL_SCRIPT}")
        return 1

    # Verifica Python binario
    if not PYTHON_BIN.exists():
        print(f"\n❌ Python non trovato: {PYTHON_BIN}")
        print("Usare il Python del sistema invece.")
        return 1

    # Pausa per conferma (opzionale, commenta se vuoi esecuzione automatica)
    try:
        input("\n⏸️  Premi INVIO per continuare o CTRL+C per annullare...\n")
    except KeyboardInterrupt:
        print("\n\n❌ Operazione annullata dall'utente.")
        return 0

    # STEP 1: Scarica pagamenti da Telegram
    success_telegram = run_script(
        TELEGRAM_SCRIPT,
        "STEP 1/2: Scaricamento pagamenti da Telegram"
    )

    if not success_telegram:
        print("\n❌ ERRORE nello step 1. Import interrotto.")
        return 1

    # STEP 2: Sincronizza lezioni da Google Calendar
    success_gcal = run_script(
        GCAL_SCRIPT,
        "STEP 2/2: Sincronizzazione lezioni da Google Calendar"
    )

    if not success_gcal:
        print("\n❌ ERRORE nello step 2. Import parzialmente completato.")
        return 1

    # Riepilogo finale
    print("\n" + "="*60)
    print("✅ IMPORTAZIONE COMPLETA TERMINATA CON SUCCESSO!")
    print("="*60)
    print(f"Completato: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
    print("Prossimi passi:")
    print("  1. Verifica i dati nel database (pagamenti.db)")
    print("  2. Avvia il bot Telegram per abbinare i pagamenti:")
    print("     .cal/bin/python association_resolver.py")
    print("  3. Oppure usa l'interfaccia web:")
    print("     cd web_interface && ../.cal/bin/python app.py")
    print("="*60 + "\n")

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n❌ Operazione interrotta dall'utente.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        sys.exit(1)
