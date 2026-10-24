"""Интеграционный тест: требуется запущенный PostgreSQL."""

import unittest
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from crud_users import (
    connect_db, create_tables, create_user, delete_user,
    read_user, read_users, update_user,
)


class CRUDTest(unittest.TestCase):
    def test_crud_and_rollback(self):
        engine = connect_db()
        self.addCleanup(engine.dispose)
        create_tables(engine)
        email = f"test-{uuid4().hex}@example.com"
        user = create_user(engine, "Тест", email, 20)
        user_id = user["id"]
        self.addCleanup(delete_user, engine, user_id)
        self.assertEqual(read_user(engine, user_id), user)
        self.assertIn(user, read_users(engine))

        with self.assertRaises(IntegrityError):
            create_user(engine, "Дубликат", email, 30)
        self.assertEqual(read_user(engine, user_id), user)
        self.assertEqual(sum(row["email"] == email for row in read_users(engine)), 1)

        with self.assertRaises(IntegrityError):
            update_user(engine, user_id, name="Ошибка", email=email, age=-1)
        self.assertEqual(read_user(engine, user_id), user)

        changed = update_user(engine, user_id, name="Изменён", email=email, age=21)
        self.assertEqual(changed["age"], 21)
        self.assertEqual(changed["name"], "Изменён")
        self.assertEqual(read_user(engine, user_id), changed)
        self.assertTrue(delete_user(engine, user_id))
        self.assertIsNone(read_user(engine, user_id))
        self.assertFalse(delete_user(engine, user_id))
        self.assertIsNone(update_user(engine, user_id, name="Нет", email=email, age=20))


if __name__ == "__main__":
    unittest.main()
