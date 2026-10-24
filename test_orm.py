import unittest
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from orm_lab import crud
from orm_lab.db import make_engine, make_session_factory
from orm_lab.models import User


class ORMTest(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.sessions = make_session_factory(self.engine)
        self.email = f"test-{uuid4().hex}@example.com"
        with self.sessions.begin() as session:
            user = crud.create_user(session, "Тест", self.email, 20)
            self.user_id = user.id
        self.addCleanup(self.remove_user)

    def remove_user(self):
        with self.sessions.begin() as session:
            crud.delete_user(session, self.user_id)

    def test_crud(self):
        with self.sessions.begin() as session:
            user = crud.update_user(session, self.user_id, name="Новое имя", email=self.email, age=21)
            self.assertEqual(user.name, "Новое имя")
            post = crud.create_post(session, user.id, "Заголовок", "Текст")
            self.assertFalse(post.is_published)
            post_id = post.id
            crud.update_post(session, post_id, title="Новый", content="Другой текст", is_published=True)
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, self.user_id).age, 21)
            post = crud.get_post(session, post_id)
            self.assertEqual((post.title, post.content, post.is_published), ("Новый", "Другой текст", True))
            self.assertEqual([p.id for p in crud.list_posts(session, self.user_id)], [post_id])
            self.assertIn(self.user_id, [u.id for u in crud.list_users(session)])
        with self.sessions.begin() as session:
            self.assertTrue(crud.delete_post(session, post_id))
        with self.sessions.begin() as session:
            self.assertIsNone(crud.get_post(session, post_id))
            self.assertFalse(crud.delete_post(session, post_id))
            self.assertIsNone(crud.update_post(session, post_id, title="Нет", content="Нет", is_published=False))
            self.assertTrue(crud.delete_user(session, self.user_id))
        with self.sessions.begin() as session:
            self.assertIsNone(crud.get_user(session, self.user_id))
            self.assertFalse(crud.delete_user(session, self.user_id))
            self.assertIsNone(crud.update_user(session, self.user_id, name="Нет", email=self.email, age=20))

    def test_rollback_whole_transaction(self):
        with self.assertRaises(IntegrityError):
            with self.sessions.begin() as session:
                crud.create_post(session, self.user_id, "Будет откачен", "Текст")
                crud.update_user(session, self.user_id, name="Ошибка", email=self.email, age=-1)
        with self.sessions() as session:
            self.assertEqual(crud.list_posts(session, self.user_id), [])
            self.assertEqual(crud.get_user(session, self.user_id).name, "Тест")
        with self.assertRaises(IntegrityError):
            with self.sessions.begin() as session:
                crud.create_user(session, "Дубликат", self.email, 20)

    def check_cascade(self, load_posts):
        with self.sessions.begin() as session:
            ids = [crud.create_post(session, self.user_id, str(i), "Текст").id for i in range(2)]
        with self.sessions.begin() as session:
            if load_posts:
                user = crud.get_user(session, self.user_id)
                self.assertEqual(len(user.posts), 2)
            self.assertTrue(crud.delete_user(session, self.user_id))
        with self.sessions() as session:
            self.assertIsNone(crud.get_user(session, self.user_id))
            for post_id in ids:
                self.assertIsNone(crud.get_post(session, post_id))

    def test_cascade_loaded_posts(self):
        self.check_cascade(load_posts=True)

    def test_cascade_unloaded_posts(self):
        self.check_cascade(load_posts=False)

    def test_delete_orphan(self):
        with self.sessions.begin() as session:
            post_id = crud.create_post(session, self.user_id, "Сирота", "Текст").id
        with self.sessions.begin() as session:
            user = crud.get_user(session, self.user_id)
            user.posts.clear()
        with self.sessions() as session:
            self.assertIsNotNone(session.get(User, self.user_id))
            self.assertIsNone(crud.get_post(session, post_id))


if __name__ == "__main__":
    unittest.main()
