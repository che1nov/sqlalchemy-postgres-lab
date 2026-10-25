"""Фикстуры для настоящего PostgreSQL; миграции применяются перед pytest."""
from uuid import uuid4

import pytest
from faker import Faker
from sqlalchemy.orm import Session

from orm_lab import crud
from orm_lab.db import make_engine


@pytest.fixture(scope="session")
def engine():
    engine = make_engine()
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("Эти интеграционные тесты требуют PostgreSQL")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    # Внешняя транзакция принадлежит фикстуре. Даже Session.commit() внутри
    # теста фиксирует лишь SAVEPOINT; teardown откатывает все данные теста.
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def fake():
    generator = Faker("ru_RU")
    generator.seed_instance(42)
    return generator


@pytest.fixture
def user_data(fake):
    return {
        "name": fake.name(),
        # UUID не даёт пересечься с данными других запусков в общей учебной БД.
        "email": f"{uuid4().hex}.{fake.user_name()}@example.com",
        "age": fake.random_int(min=18, max=80),
    }


@pytest.fixture
def user(db, user_data):
    return crud.create_user(db, **user_data)


@pytest.fixture
def post_data(fake):
    return {"title": fake.sentence(nb_words=5), "content": fake.paragraph(nb_sentences=3)}


@pytest.fixture
def post(db, user, post_data):
    return crud.create_post(db, user.id, **post_data)
