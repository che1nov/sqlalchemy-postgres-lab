"""Простой CRUD для PostgreSQL на SQLAlchemy Core (без ORM)."""

from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Column, Integer, MetaData, String, Table,
    create_engine, delete, insert, select, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


metadata = MetaData()
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("email", String(255), nullable=False, unique=True),
    Column("age", Integer, nullable=False),
    CheckConstraint("age >= 0", name="users_age_nonnegative"),
)


def connect_db() -> Engine:
    return create_engine(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://specdb:specdb@localhost:5432/specdb",
        ),
        pool_pre_ping=True,
        hide_parameters=True,
    )


def create_tables(engine: Engine) -> None:
    # begin() фиксирует DDL при успехе и откатывает при исключении.
    with engine.begin() as connection:
        metadata.create_all(connection)


def create_user(engine: Engine, name: str, email: str, age: int) -> dict:
    with engine.connect() as connection:
        try:
            row = connection.execute(
                insert(users).values(name=name, email=email, age=age)
                .returning(users)
            ).mappings().one()
            connection.commit()
            return dict(row)
        except Exception:
            connection.rollback()
            raise


def read_users(engine: Engine) -> list[dict]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(
            select(users).order_by(users.c.id)
        ).mappings()]


def read_user(engine: Engine, user_id: int) -> dict | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(users).where(users.c.id == user_id)
        ).mappings().one_or_none()
        return dict(row) if row is not None else None


def update_user(
    engine: Engine, user_id: int, *, name: str, email: str, age: int,
) -> dict | None:
    """Заменить данные пользователя; вернуть None, если id не найден."""
    with engine.connect() as connection:
        try:
            row = connection.execute(
                update(users).where(users.c.id == user_id)
                .values(name=name, email=email, age=age).returning(users)
            ).mappings().one_or_none()
            connection.commit()
            return dict(row) if row is not None else None
        except Exception:
            connection.rollback()
            raise


def delete_user(engine: Engine, user_id: int) -> bool:
    """Вернуть True при удалении, False, если id не найден."""
    with engine.connect() as connection:
        try:
            deleted_id = connection.execute(
                delete(users).where(users.c.id == user_id).returning(users.c.id)
            ).scalar_one_or_none()
            connection.commit()
            return deleted_id is not None
        except Exception:
            connection.rollback()
            raise


def main() -> None:
    engine = connect_db()
    try:
        create_tables(engine)
        email = f"demo-{uuid4().hex}@example.com"
        user = create_user(engine, "Анна", email, 20)
        print("Создан:", user)
        print("Прочитан:", read_user(engine, user["id"]))
        print("Обновлен:", update_user(
            engine, user["id"], name="Анна", email=email, age=21,
        ))
        try:
            update_user(engine, user["id"], name="Анна", email=email, age=-1)
        except IntegrityError:
            print("Отрицательный возраст: ошибка ограничения, выполнен rollback.")
        print("После rollback (возраст остался 21):", read_user(engine, user["id"]))
        temporary = create_user(engine, "Временный", f"temp-{email}", 18)
        print("Временный пользователь удален:", delete_user(engine, temporary["id"]))
        print("После удаления:", read_user(engine, temporary["id"]))
        print("Запись для проверки в DBeaver:", read_user(engine, user["id"]))
    except SQLAlchemyError as error:
        # Не печатаем SQL-параметры и реквизиты подключения.
        print(f"Ошибка БД ({type(error).__name__}). Проверьте подключение и ограничения таблицы.")
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
