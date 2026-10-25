#!/bin/sh
# Сжатая логическая копия одной MongoDB-базы. Выполняется с хоста.
set -eu
umask 077

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir=${BACKUP_DIR:-"$project_dir/backups"}
database=${MONGODB_DATABASE:-specdb}
mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary=$(mktemp "$backup_dir/.mongodb_${timestamp}.XXXXXX")
trap 'rm -f "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
archive="$backup_dir/mongodb_${timestamp}_${temporary##*.}.archive.gz"

docker compose -f "$project_dir/docker-compose.yml" -p "${COMPOSE_PROJECT_NAME:-specdb}" \
    exec -T mongodb mongodump --db="$database" --archive --gzip > "$temporary"

test -s "$temporary"
mv "$temporary" "$archive"
printf '%s\n' "$archive"
