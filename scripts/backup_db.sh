#!/bin/bash
# OmniAI DB backup — runs daily via cron on the production VPS.
# Keeps last 7 days of compressed backups in /opt/omniai/backups.

set -e

BACKUP_DIR="/opt/omniai/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/omniai_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose -f /opt/omniai/docker-compose.yml exec -T postgres \
    pg_dump -U omniai -d omniai \
    | gzip > "$BACKUP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file is empty: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "$(date): Backup OK — $BACKUP_FILE ($SIZE)"

find "$BACKUP_DIR" -name "omniai_*.sql.gz" -mtime +7 -delete

echo "$(date): Prune complete"