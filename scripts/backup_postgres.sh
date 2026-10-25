#!/bin/sh
# Логическая копия PostgreSQL в custom-формате. Выполняется с хоста.
set -eu
umask 077

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir=${BACKUP_DIR:-"$project_dir/backups"}
mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary=$(mktemp "$backup_dir/.postgres_${timestamp}.XXXXXX")
trap 'rm -f "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
archive="$backup_dir/postgres_${timestamp}_${temporary##*.}.dump"

docker compose -f "$project_dir/docker-compose.yml" -p "${COMPOSE_PROJECT_NAME:-specdb}" \
    exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
    > "$temporary"

# Проверить заголовок/содержимое архива до публикации готового файла.
docker compose -f "$project_dir/docker-compose.yml" -p "${COMPOSE_PROJECT_NAME:-specdb}" \
    exec -T postgres pg_restore --list < "$temporary" > /dev/null
mv "$temporary" "$archive"
printf '%s\n' "$archive"
