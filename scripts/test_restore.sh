#!/bin/sh
# Проверка архивов учебного проекта в отдельных временных БД.
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 POSTGRES.dump MONGODB.archive.gz" >&2
    exit 2
fi
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_mongo=${MONGODB_DATABASE:-specdb}
target="lab_restore_$(date -u +%Y%m%d%H%M%S)_$$"
postgres_created=0
mongo_created=0

compose() {
    docker compose -f "$project_dir/docker-compose.yml" -p "${COMPOSE_PROJECT_NAME:-specdb}" "$@"
}

cleanup() {
    # Удаляются только созданные этим процессом временные БД.
    if [ "$postgres_created" -eq 1 ]; then
        compose exec -T postgres sh -c \
            'PGPASSWORD="$POSTGRES_PASSWORD" exec dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$target"
    fi
    if [ "$mongo_created" -eq 1 ]; then
        compose exec -T -e RESTORE_DB="$target" mongodb mongosh --quiet \
            --eval 'db.getSiblingDB(process.env.RESTORE_DB).dropDatabase()' > /dev/null
    fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec createdb -U "$POSTGRES_USER" "$1"' sh "$target"
postgres_created=1
compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error' \
    sh "$target" < "$1"

# Миграции приложения должны быть применены перед созданием архива.
revision=$(compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -U "$POSTGRES_USER" -d "$1" -At -v ON_ERROR_STOP=1 -c "SELECT version_num FROM orm_lab.alembic_version"' \
    sh "$target")
test "$revision" = "0002"

mongo_created=1
compose exec -T mongodb mongorestore --archive --gzip --stopOnError \
    --nsInclude="$source_mongo.*" --nsFrom="$source_mongo.*" --nsTo="$target.*" < "$2"
count=$(compose exec -T -e RESTORE_DB="$target" mongodb mongosh --quiet \
    --eval 'db.getSiblingDB(process.env.RESTORE_DB).shop_orders.countDocuments({})')
test "$count" -ge 2000
printf 'Restore OK: PostgreSQL revision=%s; MongoDB shop_orders=%s documents\n' "$revision" "$count"
