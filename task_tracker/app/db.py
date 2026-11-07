import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> str:
    return os.getenv(
        "TRACKER_DATABASE_URL",
        "postgresql+psycopg://tracker:tracker_local@localhost:5434/tracker",
    )


def make_engine(url: str):
    return create_engine(url, hide_parameters=True, pool_pre_ping=True)


def make_sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
