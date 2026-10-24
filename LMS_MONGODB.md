# MongoDB: вложенные документы, индексы и аналитика

**Файл для сдачи:** [mongo_orders.py](mongo_orders.py).
**Тесты:** [test_mongo_orders.py](test_mongo_orders.py).

## 1. Коллекция

База `specdb`, коллекция `shop_orders`, 2000 демонстрационных заказов.
Старая коллекция `student_orders` остаётся отдельной работой.

Вложенные документы: `customer.contact`, `delivery.address`, `payment`.
Массив `items` содержит документы с вложенным `product`.
Денежные значения — целые копейки, валюта — RUB, даты — UTC.

Пример структуры (часть полей):

```python
{
    "order_number": "DEMO-00001",
    "customer": {
        "id": "C-082",
        "name": "Покупатель 82",
        "contact": {"email": "customer82@example.com"},
    },
    "delivery": {
        "address": {"city": "Москва", "street": "Учебная", "house": "82"},
        "method": "courier",
    },
    "items": [{
        "product": {"sku": "KB-01", "name": "Клавиатура", "category": "accessories"},
        "quantity": 3,
        "unit_price_kopecks": 350000,
    }],
    "payment": {"currency": "RUB", "total_kopecks": 1050000},
    "status": "paid",
    # created_at — BSON Date
}
```

Наполнение использует пакетные `UpdateOne(..., upsert=True)` по уникальному
`order_number`. Повторный запуск не создаёт дубликаты и восстанавливает исходные
DEMO-заказы. Остальные документы не удаляются. Уменьшение числа генерируемых
записей не удаляет ранее созданные заказы.

## 2. Класс OrderRepository

| Метод | Назначение |
|---|---|
| `create_indexes` | Создать уникальный и составные индексы |
| `seed_demo` | Наполнить коллекцию вложенными документами |
| `find_order` | Найти заказ по номеру |
| `customer_orders` | Получить последние заказы покупателя |
| `mark_paid` | Атомарно перевести новый заказ в оплаченный |
| `revenue_by_city` | Посчитать выручку и число оплаченных заказов по городам |
| `category_sales` | Посчитать продажи товарных категорий в городе |
| `customer_monthly_spending` | Посчитать расходы покупателя по месяцам |
| `explain` | Получить план и статистику выполнения агрегации |

`mark_paid` использует фильтр по номеру **и текущему статусу** в одном
`update_one`, поэтому два последовательных вызова не оплатят заказ повторно.
Многодокументная транзакция для этой операции не требуется.

## 3. Индексы и аналитические запросы

| Индекс | Поля | Использование |
|---|---|---|
| `order_number_unique` | `order_number ASC`, unique | Поиск, upsert, смена статуса |
| `status_created_at` | `status ASC, created_at ASC` | Оплаченные заказы за период |
| `city_status_created_at` | `delivery.address.city ASC, status ASC, created_at ASC` | Продажи категорий в выбранном городе |
| `customer_created_at` | `customer.id ASC, created_at DESC` | История и месячные расходы покупателя |

Во всех аналитических pipeline сначала стоит `$match`: равенство по первым
полям составного индекса, затем диапазон дат `[start, end)`.
Далее выполняются `$group`, `$sort`, а для категорий — ещё и `$unwind` массива
`items` с вычислением суммы `quantity × unit_price_kopecks`.

Пример агрегации:

```python
pipeline = [
    {"$match": {"status": "paid", "created_at": {"$gte": START, "$lt": END}}},
    {"$group": {
        "_id": "$delivery.address.city",
        "orders": {"$sum": 1},
        "revenue_kopecks": {"$sum": "$payment.total_kopecks"},
    }},
    {"$sort": {"revenue_kopecks": -1, "_id": 1}},
]
result = list(collection.aggregate(pipeline, hint="status_created_at"))
plan = collection.database.command({
    "explain": {
        "aggregate": collection.name,
        "pipeline": pipeline,
        "cursor": {},
        "hint": "status_created_at",
    },
    "verbosity": "executionStats",
})
```

В учебном примере `hint` явно выбирает соответствующий индекс, чтобы результат
проверки не зависел от выбора планировщика на небольшой коллекции.
Это подтверждает использование индекса, но не доказывает, что принудительный
выбор всегда быстрее автоматического. Индекс ускоряет начальную выборку;
группировка и сортировка вычисленной выручки выполняются после неё.
В запросе расходов статус `paid` проверяется после индексного отбора покупателя
и периода: поле статуса не включено в `customer_created_at`.

### Проверенный результат на MongoDB 7

Период: 2026-01-01 включительно — 2027-01-01 исключительно.
В коллекции 2000 документов; для каждого запроса `explain` подтвердил `IXSCAN`.

| Запрос | Индекс | Ключей прочитано | Документов прочитано |
|---|---|---:|---:|
| Выручка по городам | `status_created_at` | 681 | 681 |
| Категории в Самаре | `city_status_created_at` | 188 | 188 |
| Расходы C-001 по месяцам | `customer_created_at` | 14 | 14 |

Для Самары получено 188 оплаченных заказов на 719 920 000 копеек
(7 199 200 рублей). При добавлении других данных результаты могут измениться.
Четыре интеграционных теста проверяют аналитику независимым расчётом на Python,
методы коллекции, уникальность, повторное наполнение и фактическое использование
индексов. Тесты создают и удаляют только свою временную коллекцию.

## Запуск

```bash
docker compose -p specdb up -d mongodb
source .venv/bin/activate
pip install -r requirements.txt
python mongo_orders.py
python -m unittest -v test_mongo_orders
```

Переменные окружения: `MONGODB_URI` (по умолчанию `mongodb://localhost:27017`),
`MONGODB_DATABASE` (`specdb`), `MONGODB_ORDERS_COLLECTION` (`shop_orders`, только
демонстрация; тесты используют отдельную коллекцию со случайным именем).

В MongoDB Compass: подключиться к `mongodb://localhost:27017`, открыть
`specdb → shop_orders`; документы видны на вкладке Documents, индексы — Indexes.

Для ЛМС можно приложить файл `mongo_orders.py`, скриншот его кода или ссылку
на файл в GitHub. Репозиторий приватный — для просмотра ссылки преподавателю
потребуется доступ.
