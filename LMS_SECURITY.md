# Безопасность PostgreSQL и MongoDB

## Код для сдачи

- [security_lab/demo.py](security_lab/demo.py) — уязвимый SQL, параметризация, проверка прав и аутентификации.
- [security/postgres-init.sh](security/postgres-init.sh) — роль PostgreSQL и SQL-команды назначения прав.
- [security/mongo-init.js](security/mongo-init.js) — пользователь MongoDB и его роль.
- [docker-compose.security.yml](docker-compose.security.yml) — изолированные БД с аутентификацией.
- [security_lab/test_security.py](security_lab/test_security.py) — 8 интеграционных тестов.

## Запуск

Из корня проекта, при работающем Docker:

```bash
./scripts/setup_security.sh
docker compose --env-file security/.env -f docker-compose.security.yml -p specdb-security run --build --rm demo
docker compose --env-file security/.env -f docker-compose.security.yml -p specdb-security run --rm demo python -m unittest -v security_lab.test_security
```

Для генерации паролей нужен Python 3 на хосте. Скрипт создаёт четыре случайных
пароля в `security/.env` с правами `0600`; файл исключён из Git и Docker-образа.
Существующий `.env` не перезаписывается. Пароли не печатаются в выводе демонстрации.

Используется отдельный Compose-проект `specdb-security` и отдельные volumes.
PostgreSQL доступен на `127.0.0.1:5433`, MongoDB — на `127.0.0.1:27018`.
Обычные базы предыдущих работ на портах 5432/27017 не изменяются.
Init-скрипты выполняются только при первом запуске с пустыми volumes.
Изменение `.env` само по себе не меняет пароли уже созданных пользователей.

## 1. SQL-инъекция и параметризация

В `lab.accounts` находятся две синтетические записи `alice` и `bob`.
Уязвимая функция подставляет ввод в строку SQL:

```python
query = f"SELECT username FROM lab.accounts WHERE username = '{username}' ORDER BY username"
connection.execute(text(query))
```

Учебный вредоносный ввод:

```text
' OR '1'='1' --
```

Он делает условие истинным для всех строк и комментирует остаток запроса.
Вместо поиска одного имени возвращаются обе записи. Инъекция демонстрирует
несанкционированное чтение; она не удаляет и не изменяет данные.
`text()` сам по себе не защищает SQL, если строка уже собрана через f-string.

Защищённая версия передаёт значение отдельно от SQL:

```python
query = text("SELECT username FROM lab.accounts WHERE username = :username ORDER BY username")
connection.execute(query, {"username": username})
```

Та же строка теперь является целиком значением параметра и возвращает пустой
список. Обычный ввод `alice` возвращает одну запись. Тест с именем `O'Reilly`
проверяет корректную обработку апострофа без ручного экранирования.
Параметры применяются к значениям; имена таблиц и столбцов этим способом
не подставляются. В данной работе они фиксированы в коде.

## 2. PostgreSQL: CRUD разрешён, удаление таблиц запрещено

Роли разделены:

| Роль | Назначение |
|---|---|
| `lab_admin` | Инициализация, владелец схемы и таблиц |
| `lab_app` | Подключение приложения, только явно выданные права |

Основные настройки:

```sql
-- Пароль передаётся init-скриптом отдельно из окружения.
CREATE ROLE lab_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

REVOKE ALL ON DATABASE security_lab FROM PUBLIC;
GRANT CONNECT ON DATABASE security_lab TO lab_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA lab TO lab_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lab TO lab_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lab TO lab_app;
```

Команды создания схемы и таблиц выполняются от `lab_admin`.
`lab_app` не владеет ими и не входит в роль владельца. В PostgreSQL нет
отдельной отзываемой привилегии `DROP`: удаление объекта связано с владением
или правами superuser. Поэтому `REVOKE DELETE` не решает задачу запрета
`DROP TABLE`: `DELETE` относится к строкам.
[Документация PostgreSQL о привилегиях](https://www.postgresql.org/docs/16/ddl-priv.html).

Приложению разрешены чтение, вставка, обновление и удаление строк.
Запрещены `DROP TABLE`, `ALTER TABLE`, `TRUNCATE` и создание таблиц в `lab`/`public`.
Тесты реально выполняют эти команды и ожидают SQLSTATE `42501`.
Каждая попытка обёрнута транзакцией, которая откатывается даже при неожиданном
успехе команды, чтобы проверка не уничтожила учебную таблицу.

## 3. MongoDB: базовая аутентификация

MongoDB запускается с `--auth`. Администратор создаётся в базе `admin` через
переменные `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`.
Приложение использует другого пользователя:

```javascript
const appDb = db.getSiblingDB("security_lab");
appDb.createUser({
  user: "lab_app",
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: "security_lab" }],
});
```

Формат подключения приложения:

```text
mongodb://lab_app:<пароль>@localhost:27018/security_lab?authSource=security_lab
```

Используется парольная аутентификация SCRAM. `authSource` указывает базу,
где создан пользователь. Роль `readWrite` ограничена базой `security_lab`;
она не даёт доступ к данным `admin`. Эта роль разрешает также некоторые DDL-
операции внутри своей базы; запрет удаления таблиц в задании реализован
отдельно для PostgreSQL.

Проверяется именно чтение коллекции: `ping` может работать без аутентификации
и сам по себе не доказывает защиту данных. Тесты ожидают:

- правильные реквизиты — успешный CRUD;
- отсутствие реквизитов — `Unauthorized`, код 13;
- неправильный пароль — `AuthenticationFailed`, код 18;
- чтение другой базы — `Unauthorized`, код 13.

Включение access control требует аутентификации и ограничивает операции
назначенными ролями. [Документация MongoDB](https://www.mongodb.com/docs/manual/tutorial/enable-authentication/).
Это локальный учебный стенд без TLS, порты опубликованы только на loopback.

## Результат и GitHub Actions

Демонстрация выводит результаты уязвимого/защищённого запроса, отказ `DROP TABLE`
и успешный/отклонённый доступ к MongoDB. Workflow
[Database security lab](.github/workflows/security.yml) создаёт временные
учётные данные, запускает отдельные БД и выполняет 8 тестов.
Секреты и дампы не публикуются как artifacts.

Для остановки с сохранением данных и пользователей:

```bash
docker compose --env-file security/.env -f docker-compose.security.yml -p specdb-security down
```

В ЛМС можно прикрепить этот документ или ссылки на перечисленные файлы.
Для приватного репозитория преподавателю нужно предоставить доступ.
