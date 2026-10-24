# SQLAlchemy ORM: User → Post, Alembic, CRUD

Проект: **sqlalchemy-postgres-lab**.

Выполнены два шага миграции:

1. `0001` — таблицы `orm_lab.users` и `orm_lab.posts`, внешний ключ с `ON DELETE CASCADE`.
2. `0002` — новое обязательное поле `posts.is_published` с `DEFAULT false`.

Полные модели: [orm_lab/models.py](orm_lab/models.py).
CRUD: [orm_lab/crud.py](orm_lab/crud.py).
Миграции: [migrations/versions](migrations/versions).

## Сниппет для скриншота

Ниже запускаемый пример после `alembic upgrade head`. Он использует модели и
CRUD из проекта, показывает создание связанных записей, выборку, обновление и каскад.

```python
from uuid import uuid4
from orm_lab import crud
from orm_lab.db import make_engine, make_session_factory

engine = make_engine()
sessions = make_session_factory(engine)
try:
    # Commit при успехе; rollback при исключении.
    with sessions.begin() as session:
        user = crud.create_user(session, "Анна", f"{uuid4().hex}@example.com", 20)
        post = crud.create_post(session, user.id, "Первый пост", "Изучаю ORM")
        user_id, post_id = user.id, post.id

    with sessions.begin() as session:
        user = crud.get_user(session, user_id)
        print(user.name, len(user.posts))  # Анна 1
        crud.update_post(session, post_id, title="Готово",
                         content="Изучил миграции", is_published=True)

    with sessions.begin() as session:
        crud.delete_user(session, user_id)

    with sessions() as session:
        assert crud.get_post(session, post_id) is None
        print("Пользователь и пост удалены каскадно")
finally:
    engine.dispose()
```

В модели `User`: `relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)`.
В модели `Post`: `ForeignKey("orm_lab.users.id", ondelete="CASCADE")`.

## Проверка

```bash
alembic current       # 0002 (head)
alembic check         # No new upgrade operations detected.
python -m unittest -v test_orm test_crud_users  # 6 tests, OK
python -m orm_lab.demo
```

Репозиторий приватный: для сдачи ссылкой преподавателю нужно предоставить доступ.
Без предоставления доступа можно приложить скриншот сниппета и вывода демонстрации.
