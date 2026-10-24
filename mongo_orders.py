"""MongoDB: вложенные заказы, методы коллекции и индексируемая аналитика.

Запуск: python mongo_orders.py. Повторный запуск обновляет только DEMO-заказы.
Денежные суммы хранятся целыми числами в копейках, даты — в UTC.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pprint import pprint
from random import Random

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection


STATUS_DATE = "status_created_at"
CITY_STATUS_DATE = "city_status_created_at"
CUSTOMER_DATE = "customer_created_at"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2027, 1, 1, tzinfo=timezone.utc)


def generate_orders(count: int = 2000) -> list[dict]:
    rng = Random(42)
    cities = ["Самара", "Казань", "Москва", "Уфа"]
    products = [
        ("KB-01", "Клавиатура", "accessories", 350000),
        ("MS-01", "Мышь", "accessories", 180000),
        ("MN-01", "Монитор", "displays", 2400000),
        ("SSD-01", "SSD", "storage", 650000),
    ]
    orders = []
    for i in range(1, count + 1):
        customer_id = rng.randint(1, 100)
        items = []
        for sku, name, category, price in rng.sample(products, rng.randint(1, 3)):
            items.append({
                "product": {"sku": sku, "name": name, "category": category},
                "quantity": rng.randint(1, 3),
                "unit_price_kopecks": price,
            })
        orders.append({
            "order_number": f"DEMO-{i:05d}",
            "customer": {
                "id": f"C-{customer_id:03d}",
                "name": f"Покупатель {customer_id}",
                "contact": {"email": f"customer{customer_id}@example.com"},
            },
            "delivery": {
                "address": {"city": cities[customer_id % len(cities)], "street": "Учебная", "house": str(customer_id)},
                "method": "courier" if i % 2 else "pickup",
            },
            "items": items,
            "payment": {
                "currency": "RUB",
                "total_kopecks": sum(item["quantity"] * item["unit_price_kopecks"] for item in items),
            },
            "status": rng.choice(["new", "paid", "cancelled"]),
            "created_at": START + timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23)),
        })
    return orders


class OrderRepository:
    """Методы одной коллекции. MongoClient создаёт и закрывает вызывающий код."""

    def __init__(self, collection: Collection):
        self.collection = collection

    def create_indexes(self) -> None:
        self.collection.create_index("order_number", unique=True, name="order_number_unique")
        # Равенство по статусу/городу, затем диапазон по дате.
        self.collection.create_index([("status", ASCENDING), ("created_at", ASCENDING)], name=STATUS_DATE)
        self.collection.create_index([
            ("delivery.address.city", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING),
        ], name=CITY_STATUS_DATE)
        self.collection.create_index([
            ("customer.id", ASCENDING), ("created_at", DESCENDING),
        ], name=CUSTOMER_DATE)

    def seed_demo(self, count: int = 2000) -> int:
        """Идемпотентное наполнение по уникальному номеру, без очистки коллекции.

        Повторный запуск восстанавливает исходные данные DEMO-заказов.
        При уменьшении count ранее созданные заказы не удаляются.
        """
        orders = generate_orders(count)
        if orders:
            self.collection.bulk_write([
                UpdateOne({"order_number": order["order_number"]}, {"$set": order}, upsert=True)
                for order in orders
            ], ordered=False)
        return len(orders)

    def find_order(self, order_number: str) -> dict | None:
        return self.collection.find_one({"order_number": order_number}, {"_id": 0})

    def customer_orders(self, customer_id: str, limit: int = 10) -> list[dict]:
        if limit <= 0:
            raise ValueError("limit должен быть положительным")
        return list(self.collection.find({"customer.id": customer_id}, {"_id": 0})
                    .sort("created_at", DESCENDING).limit(limit))

    def mark_paid(self, order_number: str) -> bool:
        """Атомарно оплатить только новый заказ; False для остальных/отсутствующих."""
        result = self.collection.update_one(
            {"order_number": order_number, "status": "new"}, {"$set": {"status": "paid"}},
        )
        return result.modified_count == 1

    @staticmethod
    def city_revenue_pipeline(start: datetime, end: datetime) -> list[dict]:
        return [
            {"$match": {"status": "paid", "created_at": {"$gte": start, "$lt": end}}},
            {"$group": {
                "_id": "$delivery.address.city", "orders": {"$sum": 1},
                "revenue_kopecks": {"$sum": "$payment.total_kopecks"},
            }},
            {"$sort": {"revenue_kopecks": -1, "_id": 1}},
        ]

    @staticmethod
    def category_sales_pipeline(city: str, start: datetime, end: datetime) -> list[dict]:
        return [
            {"$match": {
                "delivery.address.city": city, "status": "paid",
                "created_at": {"$gte": start, "$lt": end},
            }},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product.category",
                "units": {"$sum": "$items.quantity"},
                "revenue_kopecks": {"$sum": {"$multiply": ["$items.quantity", "$items.unit_price_kopecks"]}},
            }},
            {"$sort": {"revenue_kopecks": -1, "_id": 1}},
        ]

    @staticmethod
    def customer_monthly_pipeline(customer_id: str, start: datetime, end: datetime) -> list[dict]:
        return [
            {"$match": {
                "customer.id": customer_id, "created_at": {"$gte": start, "$lt": end},
                "status": "paid",
            }},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at", "timezone": "UTC"}},
                "orders": {"$sum": 1}, "spent_kopecks": {"$sum": "$payment.total_kopecks"},
            }},
            {"$sort": {"_id": 1}},
        ]

    def revenue_by_city(self, start: datetime, end: datetime) -> list[dict]:
        return list(self.collection.aggregate(self.city_revenue_pipeline(start, end), hint=STATUS_DATE))

    def category_sales(self, city: str, start: datetime, end: datetime) -> list[dict]:
        return list(self.collection.aggregate(self.category_sales_pipeline(city, start, end), hint=CITY_STATUS_DATE))

    def customer_monthly_spending(self, customer_id: str, start: datetime, end: datetime) -> list[dict]:
        return list(self.collection.aggregate(self.customer_monthly_pipeline(customer_id, start, end), hint=CUSTOMER_DATE))

    def explain(self, pipeline: list[dict], index: str) -> dict:
        """Реальный план и счётчики выполнения MongoDB, не замер времени Python."""
        return self.collection.database.command({
            "explain": {"aggregate": self.collection.name, "pipeline": pipeline, "cursor": {}, "hint": index},
            "verbosity": "executionStats",
        })


def index_summary(explain: dict) -> dict:
    """Извлечь IXSCAN и счётчики из cursor/queryPlanner разных планов MongoDB."""
    indexes = set()
    stats = []

    def visit(node):
        if isinstance(node, dict):
            if node.get("stage") == "IXSCAN":
                indexes.add(node["indexName"])
            if "totalDocsExamined" in node:
                stats.append({key: node[key] for key in ("totalKeysExamined", "totalDocsExamined")})
            for key, value in node.items():
                if key not in ("rejectedPlans", "allPlansExecution"):
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(explain)
    return {"IXSCAN": sorted(indexes), "executionStats": stats}


def main() -> None:
    with MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                     serverSelectionTimeoutMS=5000, tz_aware=True) as client:
        client.admin.command("ping")
        repository = OrderRepository(client[os.getenv("MONGODB_DATABASE", "specdb")][
            os.getenv("MONGODB_ORDERS_COLLECTION", "shop_orders")
        ])
        repository.create_indexes()
        print("Обработано демонстрационных заказов:", repository.seed_demo())
        print("Документов в коллекции:", repository.collection.count_documents({}))
        print("Пример вложенного документа:")
        pprint(repository.find_order("DEMO-00001"))
        queries = [
            ("Выручка оплаченных заказов по городам", repository.city_revenue_pipeline(START, END), STATUS_DATE),
            ("Продажи категорий в Самаре", repository.category_sales_pipeline("Самара", START, END), CITY_STATUS_DATE),
            ("Расходы покупателя по месяцам", repository.customer_monthly_pipeline("C-001", START, END), CUSTOMER_DATE),
        ]
        for title, pipeline, index in queries:
            print("\n" + title)
            pprint(list(repository.collection.aggregate(pipeline, hint=index)))
            summary = index_summary(repository.explain(pipeline, index))
            assert index in summary["IXSCAN"], f"Ожидалось использование индекса {index}"
            pprint(summary)


if __name__ == "__main__":
    main()
