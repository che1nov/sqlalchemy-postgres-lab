import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_engine():
    return create_engine(
        os.getenv("DATABASE_URL", "postgresql+psycopg://specdb:specdb@localhost:5432/specdb"),
        pool_pre_ping=True,
        hide_parameters=True,
    )


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
