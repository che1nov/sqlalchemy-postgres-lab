"""Интеграционные тесты в отдельной коллекции; данные проекта не удаляются."""
import os
import unittest
from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from mongo_orders import (
    CITY_STATUS_DATE, CUSTOMER_DATE, END, START, STATUS_DATE,
    OrderRepository, generate_orders, index_summary,
)


class MongoOrdersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                                 serverSelectionTimeoutMS=5000, tz_aware=True)
        cls.addClassCleanup(cls.client.close)
        cls.collection = cls.client[os.getenv("MONGODB_DATABASE", "specdb")][f"test_orders_{uuid4().hex}"]
        cls.addClassCleanup(cls.collection.drop)
        cls.repo = OrderRepository(cls.collection)
        cls.repo.create_indexes()
        cls.repo.seed_demo()
        cls.orders = generate_orders()

    def test_seed_and_unique_index(self):
        self.repo.seed_demo()
        self.assertEqual(self.collection.count_documents({}), 2000)
        with self.assertRaises(DuplicateKeyError):
            self.collection.insert_one(dict(self.orders[0]))

    def test_collection_methods(self):
        order = dict(self.orders[0], order_number="TEST-PAYMENT", status="new")
        self.collection.insert_one(order)
        try:
            self.assertTrue(self.repo.mark_paid("TEST-PAYMENT"))
            self.assertFalse(self.repo.mark_paid("TEST-PAYMENT"))
            self.assertEqual(self.repo.find_order("TEST-PAYMENT")["status"], "paid")
            self.assertFalse(self.repo.mark_paid("MISSING"))
            self.assertIsNone(self.repo.find_order("MISSING"))
            rows = self.repo.customer_orders("C-001", 3)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["customer"]["id"] == "C-001" for row in rows))
            self.assertEqual([r["created_at"] for r in rows], sorted([r["created_at"] for r in rows], reverse=True))
            with self.assertRaises(ValueError):
                self.repo.customer_orders("C-001", 0)
        finally:
            self.collection.delete_one({"order_number": "TEST-PAYMENT"})

    def test_analytics_against_python(self):
        start, end = START + timedelta(days=20), END - timedelta(days=30)
        cities = defaultdict(lambda: [0, 0])
        categories = defaultdict(lambda: [0, 0])
        months = defaultdict(lambda: [0, 0])
        for order in self.orders:
            if order["status"] != "paid" or not start <= order["created_at"] < end:
                continue
            city = order["delivery"]["address"]["city"]
            cities[city][0] += 1
            cities[city][1] += order["payment"]["total_kopecks"]
            if city == "Самара":
                for item in order["items"]:
                    category = item["product"]["category"]
                    categories[category][0] += item["quantity"]
                    categories[category][1] += item["quantity"] * item["unit_price_kopecks"]
            if order["customer"]["id"] == "C-001":
                month = order["created_at"].strftime("%Y-%m")
                months[month][0] += 1
                months[month][1] += order["payment"]["total_kopecks"]
        self.assertEqual(
            {r["_id"]: [r["orders"], r["revenue_kopecks"]] for r in self.repo.revenue_by_city(start, end)}, dict(cities))
        self.assertEqual(
            {r["_id"]: [r["units"], r["revenue_kopecks"]] for r in self.repo.category_sales("Самара", start, end)}, dict(categories))
        self.assertEqual(
            {r["_id"]: [r["orders"], r["spent_kopecks"]] for r in self.repo.customer_monthly_spending("C-001", start, end)}, dict(months))
        self.assertEqual(self.repo.revenue_by_city(END, END), [])

    def test_indexes_actually_used(self):
        cases = [
            (self.repo.city_revenue_pipeline(START, END), STATUS_DATE),
            (self.repo.category_sales_pipeline("Самара", START, END), CITY_STATUS_DATE),
            (self.repo.customer_monthly_pipeline("C-001", START, END), CUSTOMER_DATE),
        ]
        for pipeline, index in cases:
            with self.subTest(index=index):
                summary = index_summary(self.repo.explain(pipeline, index))
                self.assertIn(index, summary["IXSCAN"])
                self.assertTrue(summary["executionStats"])
                for stats in summary["executionStats"]:
                    self.assertGreater(stats["totalKeysExamined"], 0)
                    self.assertLess(stats["totalDocsExamined"], 2000)


if __name__ == "__main__":
    unittest.main()
