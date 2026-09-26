#!/bin/bash
# Safe SQLite backup (works even while the app is running under WAL mode) + prunes
# anything older than 30 days. Add to crontab, e.g. daily at 2am:
#   0 2 * * * /var/www/newhope/deploy/backup.sh >> /var/log/newhope-backup.log 2>&1
set -euo pipefail
PROJECT_DIR="/var/www/newhope"
BACKUP_DIR="$PROJECT_DIR/backups"
mkdir -p "$BACKUP_DIR"
STAMP=$(date +%F_%H%M)
sqlite3 "$PROJECT_DIR/db.sqlite3" ".backup '$BACKUP_DIR/db_$STAMP.sqlite3'"
find "$BACKUP_DIR" -name "db_*.sqlite3" -mtime +30 -delete
echo "Backed up to $BACKUP_DIR/db_$STAMP.sqlite3"
