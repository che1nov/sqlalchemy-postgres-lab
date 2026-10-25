#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
umask 077

# Существующие пароли не перезаписываются: volumes уже используют их.
python3 - "$project_dir/security/.env" <<'PY'
import os
import secrets
import sys

path = sys.argv[1]
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print("Используется существующий security/.env")
else:
    with os.fdopen(fd, "w") as output:
        for key in ("PG_ADMIN_PASSWORD", "PG_APP_PASSWORD", "MONGO_ADMIN_PASSWORD", "MONGO_APP_PASSWORD"):
            output.write(f"{key}={secrets.token_urlsafe(24)}\n")
    print("Создан security/.env с новыми случайными паролями")
PY

docker compose --env-file "$project_dir/security/.env" \
    -f "$project_dir/docker-compose.security.yml" -p specdb-security \
    up -d --wait postgres mongodb
