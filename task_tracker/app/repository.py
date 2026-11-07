from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AuthSession, Task, User


@dataclass(frozen=True)
class TaskFilters:
    status: str | None = None
    topic: str | None = None
    assignee_id: int | None = None
    q: str | None = None


class Repository:
    """SQL and persistence only. The caller owns the transaction."""

    def __init__(self, session: Session):
        self.session = session

    def user_by_name(self, username: str):
        return self.session.scalar(select(User).where(User.username == username))

    def user(self, user_id: int):
        return self.session.get(User, user_id)

    def users(self, limit: int, offset: int):
        return self.session.scalars(select(User).order_by(User.id).limit(limit).offset(offset)).all()

    def add(self, item):
        self.session.add(item)
        self.session.flush()
        return item

    def auth_session(self, token_hash: str):
        return self.session.get(AuthSession, token_hash)

    def delete(self, item):
        self.session.delete(item)
        self.session.flush()

    def task(self, task_id: int, owner_id: int):
        return self.session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))

    def task_query(self, owner_id: int, filters: TaskFilters):
        stmt = select(Task).where(Task.owner_id == owner_id)
        if filters.status is not None:
            stmt = stmt.where(Task.status == filters.status)
        if filters.topic is not None:
            stmt = stmt.where(Task.topic == filters.topic)
        if filters.assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == filters.assignee_id)
        if filters.q:
            # SQLAlchemy binds values; autoescape treats % and _ as literal text.
            stmt = stmt.where(or_(
                Task.title.contains(filters.q, autoescape=True),
                Task.description.contains(filters.q, autoescape=True),
            ))
        return stmt

    def tasks(self, owner_id: int, filters: TaskFilters, limit: int, offset: int):
        stmt = self.task_query(owner_id, filters)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        items = self.session.scalars(stmt.order_by(Task.id.desc()).limit(limit).offset(offset)).all()
        return items, total

    def analytics_rows(self, owner_id: int, filters: TaskFilters):
        stmt = self.task_query(owner_id, filters).with_only_columns(
            Task.status, Task.topic, Task.assignee_id,
        )
        return self.session.execute(stmt).mappings().all()
