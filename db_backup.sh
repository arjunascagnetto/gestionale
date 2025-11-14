#!/bin/bash
#
# Script di backup automatico per pagamenti.db
# Esegue backup giornaliero con timestamp e pulizia backup vecchi
#

# Configurazione
PROJECT_DIR="/home/arjuna/nextcloud"
DB_FILE="$PROJECT_DIR/pagamenti.db"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_FILE="$BACKUP_DIR/backup.log"
RETENTION_DAYS=30  # Mantieni backup degli ultimi 30 giorni

# Timestamp formato: YYYY-MM-DD_HH-MM-SS
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/pagamenti_backup_$TIMESTAMP.db"

# Funzione di log
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Verifica che il database esista
if [ ! -f "$DB_FILE" ]; then
    log_message "❌ ERRORE: Database non trovato: $DB_FILE"
    exit 1
fi

# Verifica che la directory di backup esista
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    log_message "📁 Directory backup creata: $BACKUP_DIR"
fi

# Esegui backup
log_message "🔄 Inizio backup del database..."

# Usa sqlite3 per fare un backup consistente (gestisce lock correttamente)
if command -v sqlite3 &> /dev/null; then
    sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
    BACKUP_RESULT=$?
else
    # Fallback: copia semplice (meno sicuro ma funziona)
    cp "$DB_FILE" "$BACKUP_FILE"
    BACKUP_RESULT=$?
fi

# Verifica risultato backup
if [ $BACKUP_RESULT -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_message "✅ Backup completato con successo: $BACKUP_FILE ($BACKUP_SIZE)"
else
    log_message "❌ ERRORE: Backup fallito con codice $BACKUP_RESULT"
    exit 1
fi

# Pulizia backup vecchi (mantieni solo ultimi RETENTION_DAYS giorni)
log_message "🧹 Pulizia backup vecchi (> $RETENTION_DAYS giorni)..."

DELETED_COUNT=0
while IFS= read -r old_backup; do
    rm -f "$old_backup"
    ((DELETED_COUNT++))
    log_message "🗑️  Eliminato: $(basename "$old_backup")"
done < <(find "$BACKUP_DIR" -name "pagamenti_backup_*.db" -type f -mtime +$RETENTION_DAYS)

if [ $DELETED_COUNT -eq 0 ]; then
    log_message "✅ Nessun backup vecchio da eliminare"
else
    log_message "✅ Eliminati $DELETED_COUNT backup vecchi"
fi

# Statistiche finali
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "pagamenti_backup_*.db" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log_message "📊 Totale backup: $TOTAL_BACKUPS file ($TOTAL_SIZE)"
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
