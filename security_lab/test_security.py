import os
import unittest
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import OperationFailure
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from security_lab.demo import PAYLOAD, make_engine, safe_lookup, unsafe_lookup


class PostgreSQLSecurityTest(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)

    def test_injection_and_parameterization(self):
        with self.engine.connect() as connection:
            self.assertEqual(set(unsafe_lookup(connection, PAYLOAD)), {"alice", "bob"})
            self.assertEqual(safe_lookup(connection, PAYLOAD), [])
            self.assertEqual(safe_lookup(connection, "alice"), ["alice"])

    def test_apostrophe_is_data(self):
        with self.engine.connect() as connection:
            with connection.begin():
                # Откат ниже выполняется явно, данные не сохраняются.
                connection.execute(text(
                    "INSERT INTO lab.accounts(username, display_name) VALUES (:name, :label)"
                ), {"name": "O'Reilly", "label": "Имя с апострофом"})
                self.assertEqual(safe_lookup(connection, "O'Reilly"), ["O'Reilly"])
                connection.rollback()

    def test_crud_is_allowed(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                name = "test-" + uuid4().hex
                row_id = connection.execute(text(
                    "INSERT INTO lab.accounts(username, display_name) VALUES (:name, :label) RETURNING id"
                ), {"name": name, "label": "Первое имя"}).scalar_one()
                connection.execute(text("UPDATE lab.accounts SET display_name=:label WHERE id=:id"),
                                   {"label": "Новое имя", "id": row_id})
                self.assertEqual(connection.execute(text("SELECT display_name FROM lab.accounts WHERE id=:id"),
                                                    {"id": row_id}).scalar_one(), "Новое имя")
                self.assertEqual(connection.execute(text("DELETE FROM lab.accounts WHERE id=:id"),
                                                    {"id": row_id}).rowcount, 1)
                self.assertEqual(safe_lookup(connection, name), [])
            finally:
                transaction.rollback()

    def test_ddl_and_truncate_denied(self):
        statements = [
            "DROP TABLE lab.accounts",
            "TRUNCATE TABLE lab.accounts",
            "ALTER TABLE lab.accounts ADD COLUMN forbidden integer",
            "CREATE TABLE lab.forbidden(id integer)",
            "CREATE TABLE public.forbidden(id integer)",
        ]
        for statement in statements:
            with self.subTest(statement=statement), self.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with self.assertRaises(ProgrammingError) as error:
                        connection.execute(text(statement))
                    self.assertEqual(error.exception.orig.sqlstate, "42501")
                finally:
                    # Защитный rollback даже при неожиданном успехе DDL.
                    transaction.rollback()


class MongoSecurityTest(unittest.TestCase):
    def test_authenticated_crud(self):
        with MongoClient(os.environ["SECURITY_MONGODB_URI"], serverSelectionTimeoutMS=5000) as client:
            collection = client.security_lab.accounts
            name = "test-" + uuid4().hex
            try:
                result = collection.insert_one({"username": name})
                self.assertIsNotNone(collection.find_one({"_id": result.inserted_id}))
                self.assertEqual(collection.update_one({"_id": result.inserted_id},
                                                      {"$set": {"display_name": "Новое имя"}}).modified_count, 1)
                self.assertEqual(collection.delete_one({"_id": result.inserted_id}).deleted_count, 1)
            finally:
                collection.delete_many({"username": name})

    def test_anonymous_read_denied(self):
        with MongoClient(os.environ["SECURITY_MONGODB_NOAUTH_URI"], serverSelectionTimeoutMS=5000) as client:
            with self.assertRaises(OperationFailure) as error:
                client.security_lab.accounts.find_one({})
            self.assertEqual(error.exception.code, 13)

    def test_wrong_password_denied(self):
        with MongoClient(os.environ["SECURITY_MONGODB_NOAUTH_URI"], username="lab_app",
                         password="deliberately-wrong", authSource="security_lab",
                         serverSelectionTimeoutMS=5000) as client:
            with self.assertRaises(OperationFailure) as error:
                client.security_lab.accounts.find_one({})
            self.assertEqual(error.exception.code, 18)

    def test_other_database_denied(self):
        with MongoClient(os.environ["SECURITY_MONGODB_URI"], serverSelectionTimeoutMS=5000) as client:
            with self.assertRaises(OperationFailure) as error:
                client.admin.accounts.find_one({})
            self.assertEqual(error.exception.code, 13)


if __name__ == "__main__":
    unittest.main()
