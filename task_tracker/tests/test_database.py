from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, make_sessions
from app.models import AuthSession, Task, User, utcnow
from app.repository import Repository, TaskFilters
from app.services import TaskService


def test_migration_roundtrip_and_metadata(migrated_url):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.check(config)
    engine = make_engine(migrated_url)
    assert {"users", "tasks", "auth_sessions"} <= set(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()


def test_foreign_keys_checks_and_rollback(migrated_url):
    engine = make_engine(migrated_url)
    sessions = make_sessions(engine)
    with sessions.begin() as session:
        owner = User(username="owner", password_hash="test-only")
        session.add(owner)
        session.flush()
        owner_id = owner.id
    for values in [{"status": "invalid"}, {"title": " "}, {"topic": " "}, {"assignee_id": 999}, {"owner_id": 999}]:
        with pytest.raises(IntegrityError):
            with sessions.begin() as session:
                fields = dict(owner_id=owner_id, title="Valid", status="new", topic="DB")
                fields.update(values)
                session.add(Task(**fields))
    with sessions() as session:
        assert session.scalars(select(Task)).all() == []
    engine.dispose()


def test_delete_fk_actions_and_repository(migrated_url):
    engine = make_engine(migrated_url)
    sessions = make_sessions(engine)
    with sessions.begin() as session:
        owner = User(username="owner", password_hash="test-only")
        assignee = User(username="assignee", password_hash="test-only")
        session.add_all([owner, assignee])
        session.flush()
        owner_id, assignee_id = owner.id, assignee.id
        session.add(AuthSession(token_hash="a" * 64, user_id=owner_id, expires_at=utcnow()))
    with sessions() as session:
        service = TaskService(Repository(session))
        task = service.create(owner_id, title="Task", assignee_id=assignee_id)
        task_id = task.id
    with sessions.begin() as session:
        session.execute(delete(User).where(User.id == assignee_id))
    with sessions() as session:
        repo = Repository(session)
        assert repo.task(task_id, owner_id).assignee_id is None
        assert repo.tasks(owner_id, TaskFilters(), 20, 0)[1] == 1
    with sessions.begin() as session:
        session.execute(delete(User).where(User.id == owner_id))
    with sessions() as session:
        assert session.scalars(select(Task)).all() == []
        assert session.scalars(select(AuthSession)).all() == []
        assert session.bind.dialect.name == "postgresql"
    engine.dispose()
