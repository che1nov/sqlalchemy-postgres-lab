# Отчет по лабораторной работе

## Установленное ПО

- PostgreSQL, MongoDB и Redis подняты через Docker Compose.
- `psql` установлен локально: `psql (PostgreSQL) 14.20`.
- DBeaver Community установлен через Homebrew cask.
- MongoDB Compass установлен через Homebrew cask.

## Python-окружение

Создано виртуальное окружение:

```bash
python3 -m venv .venv
```

Установлены библиотеки:

- `sqlalchemy`
- `pymongo`
- `redis`
- `alembic`

## MongoDB

Подключение:

```text
mongodb://localhost:27017
```

База данных:

```text
specdb
```

Коллекция:

```text
student_orders
```

## Вывод скрипта

Команда:

```bash
.venv/bin/python seed_mongo.py
```

Результат:

```text
База данных: specdb
Коллекция: student_orders
Количество записей: 100
Пример одной записи:
{'city': 'Казань',
 'created_at': datetime.datetime(2026, 7, 8, 0, 0),
 'customer_name': 'Елена Кузнецова',
 'is_priority': True,
 'order_number': 'ORD-0001',
 'product': 'Монитор',
 'quantity': 1,
 'status': 'paid',
 'total_amount': 1719,
 'unit_price': 1719}
```
