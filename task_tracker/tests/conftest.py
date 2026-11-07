import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "test-password-123"


@pytest.fixture
def migrated_url(monkeypatch):
    # CREATE DATABASE cannot run inside a transaction. Each test owns a random
    # database; application databases and their existing tables are never reset.
    admin_url = make_url(os.getenv(
        "TRACKER_TEST_DATABASE_URL",
        "postgresql+psycopg://tracker:tracker_local@localhost:5434/postgres",
    ))
    name = f"tracker_test_{uuid4().hex}"
    with psycopg.connect(
        admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            url = admin_url.set(database=name).render_as_string(hide_password=False)
            monkeypatch.setenv("TRACKER_DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def client(migrated_url):
    with TestClient(create_app(migrated_url)) as client:
        yield client


@pytest.fixture
def account(client):
    def create(username="alice"):
        credentials = {"username": username, "password": PASSWORD}
        response = client.post("/auth/register", json=credentials)
        assert response.status_code == 201, response.text
        login = client.post("/auth/login", json=credentials)
        assert login.status_code == 200, login.text
        return response.json(), {"Authorization": f"Bearer {login.json()['access_token']}"}
    return create


@pytest.fixture
def alice(account):
    return account()
