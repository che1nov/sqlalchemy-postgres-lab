# sqlalchemy-postgres-lab

Учебный проект по базам данных: SQLAlchemy Core, SQLAlchemy ORM, Alembic и PostgreSQL.
Работы по MongoDB и Redis также сохранены в репозитории.

## PostgreSQL — pytest, фикстуры и Faker

Код: [tests/postgres](tests/postgres). Инструкция для сдачи:
[LMS_PYTEST.md](LMS_PYTEST.md).
21 тест проверяет ORM CRUD, каскады и негативные сценарии ограничений БД.
Каждый тест изолирован транзакцией с откатом; данные создаются с Faker.

```bash
source .venv/bin/activate
pip install -r requirements-test.txt
docker compose -p specdb up -d --wait postgres
alembic upgrade head
python -m pytest -v
```

## Docker, резервное копирование и GitHub Actions

Инструкция и материалы для сдачи: [LMS_DOCKER_BACKUP.md](LMS_DOCKER_BACKUP.md).

```bash
docker compose -p specdb up --build -d
docker compose -p specdb logs app
./scripts/backup_postgres.sh
./scripts/backup_mongodb.sh
```

Сервис `app` применяет миграции, запускает консольную ORM-демонстрацию и успешно
завершается; базы продолжают работать. Архивы сохраняются в `backups/`.
Workflow `Docker build and backup restore` собирает образ, запускает все тесты
и проверяет восстановление резервных копий в отдельные временные БД.

## Redis — TTL, Pub/Sub и очередь задач

Код: [redis_lab](redis_lab). Инструкция для запуска и сдачи:
[LMS_REDIS.md](LMS_REDIS.md).

```bash
docker compose -p specdb up -d redis
source .venv/bin/activate
python -m redis_lab.cache --ttl 3
python -m unittest -v test_redis_lab
```

Pub/Sub: сначала `python -m redis_lab.subscriber`, затем в другом терминале
`python -m redis_lab.publisher "Привет"`.
Очередь: `python -m redis_lab.task_queue 10 20 30`, затем
`python -m redis_lab.worker --once`.

## MongoDB — вложенные документы, индексы и аналитика

Новая работа: [mongo_orders.py](mongo_orders.py), отчёт для сдачи —
[LMS_MONGODB.md](LMS_MONGODB.md). Коллекция `shop_orders` содержит 2000 заказов
с вложенными адресами, контактами, оплатой и массивами товаров.
Класс `OrderRepository` реализует методы коллекции и три агрегации;
`explain` подтверждает использование составных индексов.

```bash
docker compose -p specdb up -d mongodb
source .venv/bin/activate
pip install -r requirements.txt
python mongo_orders.py
python -m unittest -v test_mongo_orders
```

## ORM и Alembic — быстрый запуск

```bash
docker compose -p specdb up -d postgres
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m orm_lab.demo
python -m unittest -v test_orm test_crud_users
```

Python 3.9+. При первом запуске дождитесь готовности PostgreSQL:
`docker compose -p specdb exec postgres pg_isready -U specdb -d specdb`.
Для внешней БД задайте `DATABASE_URL` (формат приведён ниже).

### Файлы текущего задания

- [`orm_lab/models.py`](orm_lab/models.py) — модели `User` и `Post`, связь один ко многим.
- [`orm_lab/crud.py`](orm_lab/crud.py) — вставка, выборка, обновление и удаление обеих сущностей.
- [`orm_lab/db.py`](orm_lab/db.py) — Engine и фабрика Session.
- [`orm_lab/demo.py`](orm_lab/demo.py) — запускаемая демонстрация CRUD, rollback и каскада.
- [`migrations/versions/0001_create_users_and_posts.py`](migrations/versions/0001_create_users_and_posts.py) — первая миграция.
- [`migrations/versions/0002_add_post_is_published.py`](migrations/versions/0002_add_post_is_published.py) — добавление поля `Post.is_published`.
- [`test_orm.py`](test_orm.py) — интеграционные тесты.
- [`LMS.md`](LMS.md) — сниппет и пояснения для сдачи.

Это небольшой учебный модуль: модели, функции работы с БД и демонстрация.
HTTP и бизнес-сценариев здесь нет, поэтому дополнительные слои не нужны.

### Транзакции и каскад

CRUD принимает `Session`, выполняет `add`, `get`/`select`, изменение атрибутов,
`delete` и `flush`. `flush` отправляет изменения в БД, но не делает commit.
Вызывающий код оборачивает сценарий в `with sessions.begin() as session:`:
при успехе происходит commit, при исключении — rollback всех шагов сценария.
Исключения нужно перехватывать снаружи этого блока.

`User.posts` содержит `cascade="all, delete-orphan"`. Удаление пользователя
удаляет его посты; удаление поста из коллекции также удаляет его из БД.
`ForeignKey(..., ondelete="CASCADE")` и `passive_deletes=True` позволяют PostgreSQL
удалять незагруженные посты без их предварительного чтения.

ORM использует схему `orm_lab`, Core — `public.users`. Alembic управляет только
`orm_lab`; старые таблицы не включаются в автогенерацию. ORM-таблицы создаются
миграциями, без `Base.metadata.create_all()`.

### Как создавались миграции

Сначала были описаны модели без `is_published`, затем выполнены:

```bash
alembic revision --autogenerate --rev-id 0001 -m "create users and posts"
alembic upgrade head
```

После добавления `Post.is_published`:

```bash
alembic revision --autogenerate --rev-id 0002 -m "add post is_published"
alembic upgrade head
alembic current
alembic check
```

Поле обязательное, с серверным значением по умолчанию `false`, поэтому миграция
подходит и для таблицы с существующими постами. Обе миграции содержат `downgrade`.
При клонировании проекта повторно генерировать миграции не нужно — достаточно
`alembic upgrade head`. Новые изменения модели создавайте новой ревизией.

### DBeaver

Подключение: `localhost:5432`, база `specdb`, пользователь и учебный пароль `specdb`.
Эти реквизиты предназначены только для локальной лабораторной работы.

```sql
SELECT * FROM orm_lab.alembic_version;
SELECT * FROM orm_lab.users;
SELECT * FROM orm_lab.posts;
```

ORM-демонстрация удаляет свои записи, чтобы показать каскад. Тесты также убирают
свои данные. Для скриншота результата используйте вывод `python -m orm_lab.demo`.

## Предыдущие работы и настройка окружения

Проект поднимает PostgreSQL, MongoDB и Redis через Docker Compose и содержит Python-скрипт, который подключается к локальной MongoDB, создает коллекцию `student_orders`, наполняет ее 100 записями и печатает метаданные для отчета в ЛМС.

## 1. Запуск баз данных

```bash
docker compose -p specdb up -d
```

Порты:

- PostgreSQL: `localhost:5432`
- MongoDB: `localhost:27017`
- Redis: `localhost:6379`

Проверка PostgreSQL через `psql`:

```bash
psql "postgresql://specdb:specdb@localhost:5432/specdb" -c "select version();"
```

## 2. Python-окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Установленные библиотеки:

- `sqlalchemy`
- `pymongo`
- `redis`
- `alembic`

## 3. Наполнение MongoDB

```bash
python seed_mongo.py
```

Скрипт использует:

- база данных: `specdb`
- коллекция: `student_orders`
- подключение: `mongodb://localhost:27017`

Можно переопределить настройки через переменные окружения:

```bash
MONGODB_URI="mongodb://localhost:27017" \
MONGODB_DATABASE="specdb" \
MONGODB_COLLECTION="student_orders" \
python seed_mongo.py
```

## 4. MongoDB Compass

Для MongoDB Compass:

```text
mongodb://localhost:27017
```

После подключения откройте:

```text
specdb -> student_orders
```

## 5. Что приложить в ЛМС

Подойдет один из вариантов:

- скриншот MongoDB Compass с коллекцией `student_orders`;
- скриншот терминала после команды `python seed_mongo.py`, где видно количество записей и пример одной записи.

Пример ожидаемого вывода:

```text
База данных: specdb
Коллекция: student_orders
Количество записей: 100
Пример одной записи:
{...}
```

## 6. DBeaver и MongoDB Compass

Если приложения еще не установлены на macOS, удобнее поставить через Homebrew:

```bash
brew install --cask dbeaver-community mongodb-compass
```

DBeaver можно использовать для подключения к PostgreSQL:

```text
Host: localhost
Port: 5432
Database: specdb
User: specdb
Password: specdb
```

## 7. CRUD на SQLAlchemy Core и PostgreSQL

Реализация находится в `crud_users.py`: используется Core (`Table`, `select`,
`insert`, `update`, `delete`), без ORM и Session. Требуется Python 3.9+.

```bash
docker compose -p specdb up -d postgres
source .venv/bin/activate
pip install -r requirements.txt
python crud_users.py
```

Подключение по умолчанию использует PostgreSQL из этого Docker Compose.
Для другой БД задайте переменную окружения `DATABASE_URL` в формате
`postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME`.

Таблица `public.users` создаётся при первом запуске: `id` — первичный ключ,
`name` и `email` — обязательные строки, `email` уникален,
`age` — обязательное целое число не меньше нуля.

Функции:

- `connect_db()` — создаёт Engine; соединение открывается при первом обращении к БД.
- `create_tables(engine)` — создаёт таблицу, если её ещё нет.
- `create_user(engine, name, email, age)` — возвращает созданную запись.
- `read_users(engine)` — возвращает все записи по id.
- `read_user(engine, user_id)` — возвращает запись или `None`.
- `update_user(engine, user_id, name=..., email=..., age=...)` — заменяет поля и возвращает запись или `None`.
- `delete_user(engine, user_id)` — возвращает `True`, если запись удалена, иначе `False`.

Каждая функция записи открывает собственное соединение и фиксирует изменения
через `commit()`. При исключении выполняется явный `rollback()`, после чего
исключение передаётся вызывающему коду. Чтение не содержит явного отката.
Ошибка открытия соединения передаётся вызывающему коду: транзакция в этом случае ещё не началась.

Демонстрация создаёт пользователя, читает и обновляет его, затем пробует записать
отрицательный возраст. PostgreSQL отклоняет изменение; после отката возраст
остаётся равным 21. Для демонстрации удаления создаётся отдельная временная запись.
Каждый запуск оставляет одного нового пользователя для просмотра в DBeaver.

В DBeaver подключитесь с параметрами из раздела 6, обновите список таблиц
и откройте `specdb → Schemas → public → Tables → users → Data` либо выполните:

```sql
SELECT id, name, email, age FROM public.users ORDER BY id;
```

Транзакции Core описаны в [документации SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/connections.html#commit-as-you-go).

Интеграционный тест CRUD, отсутствующего id и отката при нарушениях `UNIQUE`
и `CHECK` (требуется PostgreSQL; тест удаляет свою запись):

```bash
python -m unittest -v test_crud_users
```
