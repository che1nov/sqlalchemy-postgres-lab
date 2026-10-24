from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from orm_lab import crud
from orm_lab.db import make_engine, make_session_factory


def main():
    engine = make_engine()
    sessions = make_session_factory(engine)
    try:
        # begin() делает commit при успехе, rollback при любом исключении.
        with sessions.begin() as session:
            user = crud.create_user(session, "Анна", f"orm-{uuid4().hex}@example.com", 20)
            post = crud.create_post(session, user.id, "Первая запись", "Изучаю ORM")
            user_id, post_id = user.id, post.id
        print(f"Созданы User id={user_id} и Post id={post_id}")

        with sessions.begin() as session:
            user = crud.get_user(session, user_id)
            print(f"Прочитан {user.name}; публикаций: {len(user.posts)}")
            crud.update_user(session, user_id, name="Анна", email=user.email, age=21)
            crud.update_post(session, post_id, title="Обновлённая запись", content="Alembic работает", is_published=True)
        print("Пользователь обновлён, пост опубликован")

        try:
            with sessions.begin() as session:
                user = crud.get_user(session, user_id)
                crud.update_user(session, user_id, name="Ошибка", email=user.email, age=-1)
        except IntegrityError:
            print("Ошибка CHECK: транзакция автоматически откачена")

        with sessions() as session:
            user = crud.get_user(session, user_id)
            assert user.age == 21
            print(f"После rollback: {user.name}, возраст {user.age}")
        with sessions.begin() as session:
            crud.delete_user(session, user_id)
        with sessions() as session:
            assert crud.get_user(session, user_id) is None
            assert crud.get_post(session, post_id) is None
        print("Пользователь и его пост удалены каскадно")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
