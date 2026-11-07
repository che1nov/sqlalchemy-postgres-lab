import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy.exc import IntegrityError

from app.models import AuthSession, Task, User, utcnow
from app.repository import Repository, TaskFilters


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Unauthorized(Exception):
    pass


class InvalidAssignee(Exception):
    pass


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, repo: Repository, hasher: PasswordHasher, dummy_hash: str):
        self.repo = repo
        self.hasher = hasher
        self.dummy_hash = dummy_hash

    def register(self, username: str, password: str) -> User:
        user = User(username=username, password_hash=self.hasher.hash(password))
        try:
            self.repo.add(user)
            self.repo.session.commit()
        except IntegrityError as exc:
            self.repo.session.rollback()
            raise Conflict("Имя пользователя уже занято") from exc
        return user

    def login(self, username: str, password: str) -> str:
        user = self.repo.user_by_name(username)
        try:
            self.hasher.verify(user.password_hash if user else self.dummy_hash, password)
        except VerificationError as exc:
            raise Unauthorized("Неверное имя или пароль") from exc
        if user is None:
            raise Unauthorized("Неверное имя или пароль")
        if self.hasher.check_needs_rehash(user.password_hash):
            user.password_hash = self.hasher.hash(password)
        token = secrets.token_urlsafe(32)
        self.repo.add(AuthSession(
            token_hash=token_digest(token), user_id=user.id,
            expires_at=utcnow() + timedelta(days=1),
        ))
        self.repo.session.commit()
        return token

    def authenticate(self, token: str) -> User:
        auth = self.repo.auth_session(token_digest(token))
        if auth is None or auth.expires_at <= utcnow():
            raise Unauthorized("Требуется действующий токен")
        user = self.repo.user(auth.user_id)
        if user is None:
            raise Unauthorized("Требуется действующий токен")
        return user

    def logout(self, token: str):
        auth = self.repo.auth_session(token_digest(token))
        if auth:
            self.repo.delete(auth)
            self.repo.session.commit()

    def users(self, limit: int, offset: int):
        return self.repo.users(limit, offset)


class TaskService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def _check_assignee(self, assignee_id: int | None):
        if assignee_id is not None and self.repo.user(assignee_id) is None:
            raise InvalidAssignee("Исполнитель не найден")

    def create(self, owner_id: int, **fields) -> Task:
        self._check_assignee(fields.get("assignee_id"))
        task = self.repo.add(Task(owner_id=owner_id, **fields))
        self.repo.session.commit()
        return task

    def get(self, owner_id: int, task_id: int) -> Task:
        task = self.repo.task(task_id, owner_id)
        if task is None:
            raise NotFound("Задача не найдена")
        return task

    def list(self, owner_id: int, filters: TaskFilters, limit: int, offset: int):
        return self.repo.tasks(owner_id, filters, limit, offset)

    def update(self, owner_id: int, task_id: int, changes: dict) -> Task:
        task = self.get(owner_id, task_id)
        if "assignee_id" in changes:
            self._check_assignee(changes["assignee_id"])
        for key, value in changes.items():
            setattr(task, key, value)
        task.updated_at = utcnow()
        self.repo.session.commit()
        return task

    def delete(self, owner_id: int, task_id: int):
        self.repo.delete(self.get(owner_id, task_id))
        self.repo.session.commit()
