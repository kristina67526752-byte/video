#!/usr/bin/env bash
# Sauvegarde quotidienne de la base et des photos (à lancer par cron depuis le dossier du projet).
#   0 3 * * * cd /opt/workcam && ./deploy/backup.sh >> /var/log/workcam-backup.log 2>&1
set -euo pipefail
DEST="${BACKUP_DIR:-/opt/workcam-backups}"
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$DEST"
docker compose exec -T db pg_dump -U workcam -Fc workcam > "$DEST/db-$STAMP.dump"
docker compose run --rm -T -v "$DEST":/backup --entrypoint sh app -c "tar czf /backup/uploads-$STAMP.tgz -C /app uploads"
find "$DEST" -type f -mtime +14 -delete
echo "Sauvegarde OK : $STAMP"
