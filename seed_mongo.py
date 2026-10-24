from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pprint import pprint
from random import Random

from pymongo import ASCENDING, MongoClient


MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("MONGODB_DATABASE", "specdb")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "student_orders")


def generate_orders(count: int = 100) -> list[dict]:
    rng = Random(42)
    names = [
        "Анна Смирнова",
        "Иван Петров",
        "Мария Иванова",
        "Дмитрий Соколов",
        "Елена Кузнецова",
        "Алексей Попов",
        "Ольга Васильева",
        "Никита Морозов",
    ]
    cities = ["Самара", "Казань", "Москва", "Санкт-Петербург", "Уфа"]
    products = ["Клавиатура", "Монитор", "Наушники", "SSD", "Мышь", "USB-C хаб"]
    statuses = ["new", "paid", "shipped", "done", "cancelled"]
    base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

    orders = []
    for order_id in range(1, count + 1):
        quantity = rng.randint(1, 5)
        unit_price = rng.randint(900, 25_000)

        orders.append(
            {
                "order_number": f"ORD-{order_id:04d}",
                "customer_name": rng.choice(names),
                "city": rng.choice(cities),
                "product": rng.choice(products),
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": quantity * unit_price,
                "status": rng.choice(statuses),
                "created_at": base_date + timedelta(days=rng.randint(0, 240)),
                "is_priority": rng.choice([True, False]),
            }
        )

    return orders


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")

    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    collection.delete_many({})
    collection.insert_many(generate_orders())
    collection.create_index([("order_number", ASCENDING)], unique=True)

    print(f"База данных: {DATABASE_NAME}")
    print(f"Коллекция: {COLLECTION_NAME}")
    print(f"Количество записей: {collection.count_documents({})}")
    print("Пример одной записи:")
    pprint(collection.find_one({}, {"_id": 0}))


if __name__ == "__main__":
    main()
