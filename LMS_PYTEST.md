# PostgreSQL: pytest, фикстуры и Faker

**Код тестов:** [tests/postgres/test_crud.py](tests/postgres/test_crud.py).
**Фикстуры:** [tests/postgres/conftest.py](tests/postgres/conftest.py).
**Проверяемый CRUD:** [orm_lab/crud.py](orm_lab/crud.py).

Реализован 21 интеграционный тест на реальной PostgreSQL: 9 позитивных и
12 негативных случаев с учётом параметризации. SQLite и моки не используются.

## Запуск

Из корня проекта:

```bash
docker compose -p specdb up -d --wait postgres
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt
alembic upgrade head
python -m pytest -v
```

Если окружение уже создано, шаг `python3 -m venv .venv` можно пропустить.
Настройка подключения — через `DATABASE_URL`, по умолчанию используется
локальная учебная база `specdb` из Docker Compose.
Миграции применяются перед тестами, `create_all` не подменяет их проверку.

Отдельный запуск групп:

```bash
python -m pytest -v -m positive
python -m pytest -v -m negative
```

`pytest.ini` ограничивает обычный запуск каталогом `tests/postgres`, чтобы
тестирование этого задания не требовало одновременно MongoDB и Redis.
Прежние unittest-тесты остаются доступны отдельными командами из README.

## Фикстуры

| Фикстура | Назначение |
|---|---|
| `engine` | Подключение PostgreSQL на всю сессию pytest; закрытие пула после тестов |
| `db` | Отдельная SQLAlchemy Session и внешняя транзакция для каждого теста |
| `fake` | Faker с русской локалью и фиксированным seed |
| `user_data` | Сгенерированные имя, email и возраст |
| `user` | Пользователь, вставленный через проверяемую CRUD-функцию |
| `post_data` | Сгенерированные заголовок и текст поста |
| `post` | Пост, связанный с пользователем |

Faker генерирует имена, части email, возраст, предложения и абзацы.
UUID в email предотвращает пересечение с существующими данными. Тесты не зависят
от конкретных сгенерированных строк или числовых id.

В `db` используется внешний `connection.begin()` и
`Session(..., join_transaction_mode="create_savepoint")`. В `finally` сессия
закрывается и выполняется rollback внешней транзакции. Даже вызов `db.commit()`
в тесте не фиксирует записи за пределами этой транзакции.
Это проверка фиксации на уровне SAVEPOINT, а не видимости данных в другой
независимой транзакции. PostgreSQL sequence может увеличиться после rollback,
поэтому пропуски в id допустимы.

## Позитивные сценарии

- Создание и чтение пользователя, проверка всех переданных полей.
- Список пользователей и порядок по id.
- Обновление и удаление пользователя.
- Создание поста, чтение, выборка постов автора и связь `User.posts`.
- Обновление поста с публикацией.
- Удаление поста с сохранением автора.
- Каскадное удаление постов вместе с автором: для загруженной и незагруженной связи.

Перед повторным чтением вызывается `db.expunge_all()`, чтобы проверять данные
из PostgreSQL, а не только объекты в identity map сессии.

Пример теста:

```python
@pytest.mark.positive
def test_delete_user(db, user):
    user_id = user.id
    assert crud.delete_user(db, user_id) is True
    db.expunge_all()
    assert crud.get_user(db, user_id) is None
```

## Негативные сценарии

| Ситуация | Ожидание |
|---|---|
| Отрицательный возраст | CHECK, SQLSTATE `23514` |
| `NULL` в имени, email или возрасте | NOT NULL, `23502` |
| Дубликат email при создании | UNIQUE, `23505` |
| Изменение email на уже занятый | UNIQUE; исходный email сохранён |
| Ошибка обновления после вставки поста | Откат и обновления, и нового поста |
| Пост без существующего автора | FOREIGN KEY, `23503` |
| `NULL` в заголовке или тексте поста | NOT NULL, `23502` |
| Чтение/обновление отсутствующей записи | `None` |
| Повторное удаление | `False` |

Используются `pytest.raises(IntegrityError)` и `pytest.mark.parametrize`.
Ожидаемая ошибочная операция выполняется внутри `db.begin_nested()`.
Исключение выходит из SAVEPOINT, после чего проверяется тип нарушения,
сохранность предыдущих данных и возможность продолжать работу с сессией.
Ошибки подключения не считаются ожидаемым успешным негативным тестом.

```python
@pytest.mark.negative
def test_duplicate_email_rejected(db, user, user_data):
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.create_user(db, **user_data)
    assert error.value.orig.sqlstate == "23505"
    assert crud.get_user(db, user.id).email == user_data["email"]
```

## Результат и GitHub Actions

Локальная проверка: **21 passed**.
Workflow [PostgreSQL integration tests](.github/workflows/tests.yml) устанавливает
`requirements-test.txt`, применяет миграции и запускает `python -m pytest -v`.
Результат доступен на вкладке Actions репозитория.

Для ЛМС можно приложить ссылку на этот документ или каталог `tests/postgres`.
Репозиторий приватный: преподавателю нужен доступ; альтернатива — скриншоты
`conftest.py`, тестов и вывода `21 passed`.
