# Резервное копирование, Docker и GitHub Actions

## Файлы для сдачи

- [scripts/backup_postgres.sh](scripts/backup_postgres.sh) — резервная копия PostgreSQL.
- [scripts/backup_mongodb.sh](scripts/backup_mongodb.sh) — резервная копия MongoDB.
- [Dockerfile](Dockerfile) — образ Python-приложения.
- [docker-compose.yml](docker-compose.yml) — приложение и базы данных.
- [.github/workflows/docker-backup.yml](.github/workflows/docker-backup.yml) — сборка, тесты, резервное копирование и восстановление в CI.
- [scripts/test_restore.sh](scripts/test_restore.sh) — проверка восстановления в временные базы.

## Развёртывание приложения и БД

Требуется Docker с Compose v2; Python на хосте для этого способа запуска не нужен.
Из корня проекта:

```bash
docker compose -p specdb up --build -d
docker compose -p specdb logs app
```

`app` — существующее консольное приложение лабораторной работы. Оно применяет
миграции Alembic, выполняет ORM CRUD с каскадным удалением и завершается с кодом 0.
Статус `Exited (0)` для него ожидаем; это не постоянно работающий HTTP-сервер.
PostgreSQL, MongoDB и Redis продолжают работать.

Dockerfile использует Python 3.12, устанавливает зависимости и запускает процесс
от непривилегированного пользователя. `.dockerignore` исключает виртуальное
окружение, Git, локальные `.env` и резервные копии из контекста сборки.
`depends_on: condition: service_healthy` задерживает запуск приложения до
готовности баз. Адреса внутри сети Compose используют имена сервисов:
`postgres:5432`, `mongodb:27017`, `redis:6379`.
Данные хранятся в именованных volumes. Реквизиты в Compose — учебные локальные.

Повторный запуск приложения и другие работы в том же образе:

```bash
docker compose -p specdb run --rm app
docker compose -p specdb run --rm app python mongo_orders.py
docker compose -p specdb run --rm app python -m redis_lab.cache --ttl 1
docker compose -p specdb run --rm app python -m unittest -v test_crud_users test_orm test_mongo_orders test_redis_lab
```

Штатная остановка с сохранением volumes:

```bash
docker compose -p specdb down
```

## Резервное копирование

Скрипты исполняемые (`chmod +x` записан в Git). Они запускаются **на хосте**,
а утилиты `pg_dump` и `mongodump` работают внутри контейнеров соответствующих БД.
Поэтому устанавливать эти утилиты на хост отдельно не нужно.

```bash
./scripts/backup_postgres.sh
./scripts/backup_mongodb.sh
```

Каждый скрипт выводит в stdout путь к готовому архиву. Диагностика идёт в stderr.
Файлы сохраняются в `backups/` с UTC-временем и случайным суффиксом:

```text
postgres_YYYYMMDDTHHMMSSZ_RANDOM.dump
mongodb_YYYYMMDDTHHMMSSZ_RANDOM.archive.gz
```

- PostgreSQL: `pg_dump --format=custom`, структура и данные базы `POSTGRES_DB`.
  Перед публикацией архива выполняется `pg_restore --list`.
- MongoDB: `mongodump --db=specdb --archive --gzip`, документы и метаданные индексов.
- `set -eu` прерывает скрипт при ошибках. Данные сначала записываются во временный
  файл; после успешной команды файл переименовывается. `trap` убирает временный
  файл при завершении или ошибке.
- `umask 077` ограничивает доступ к новым архивам владельцем.
- `backups/` исключён из Git и Docker-образа.

Параметры через окружение:

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `specdb` | Проект Compose, где запущены БД |
| `BACKUP_DIR` | `backups/` в проекте | Каталог архивов на хосте |
| `MONGODB_DATABASE` | `specdb` | MongoDB-база для копирования |

Для PostgreSQL пользователь, пароль и имя базы читаются из окружения контейнера.
MongoDB-скрипт рассчитан на локальный сервис из Compose без аутентификации.
`pg_dump` копирует одну базу, но не глобальные роли сервера.
MongoDB здесь работает как standalone: для согласованной копии при записи
в несколько коллекций остановите изменяющие данные процессы на время копирования.
Этот пример не использует replica set и `--oplog`.

## Проверка восстановления

Сначала примените миграции и наполните MongoDB командами выше. Затем:

```bash
pg_archive=$(./scripts/backup_postgres.sh)
mongo_archive=$(./scripts/backup_mongodb.sh)
./scripts/test_restore.sh "$pg_archive" "$mongo_archive"
```

Проверочный скрипт создаёт отдельные временные базы `lab_restore_...`.
Для PostgreSQL используется `createdb` и `pg_restore --exit-on-error`.
Для MongoDB — `mongorestore --archive --gzip` с переназначением namespace
`specdb.* → lab_restore_...*`, включая коллекции и индексы.
Исходные базы не перезаписываются.

После восстановления проверяются ревизия Alembic `0002` и наличие не менее 2000
документов `shop_orders`. Это smoke-проверка восстановления учебных данных,
а не полное побайтовое сравнение всех записей. Временные базы удаляются через
`trap`, архивы остаются для пользователя.

Ожидаемый результат:

```text
Restore OK: PostgreSQL revision=0002; MongoDB shop_orders=2000 documents
```

## Возможности GitHub Actions на примере проекта

GitHub Actions выполняет YAML-workflows из `.github/workflows/` на runner —
выделенной машине для запуска заданий. В этой работе:

| Возможность | Использование |
|---|---|
| Автоматические события | `push` и `pull_request` запускают проверки |
| Ручной запуск | `workflow_dispatch` добавляет кнопку Run workflow |
| Jobs и steps | Задание `integration` выполняет сборку и проверки последовательно |
| Готовые actions | `actions/checkout` получает код репозитория |
| Переменные окружения | `COMPOSE_PROJECT_NAME` задаётся для всего job |
| Права доступа | `contents: read` — workflow не меняет репозиторий |
| Условные шаги | `failure()` выводит логи, `always()` очищает временное окружение CI |
| Проверка интеграции | В образе запускаются все 16 тестов PostgreSQL, MongoDB и Redis |
| Проверка архивов | Создание копий и восстановление в новые БД |

`docker compose down -v` используется только для временного окружения runner.
Локально команда `down` выше не удаляет volumes.
Архивы из CI не публикуются как artifacts; в CI они служат проверке восстановления.

Вкладка **Actions → Docker build and backup restore** содержит статусы и логи
шагов. Также сохранены отдельные workflows PostgreSQL, MongoDB и Redis.
Для ЛМС подойдёт ссылка на этот документ, скрипты или весь репозиторий.
Приватный репозиторий требует доступа преподавателя.
