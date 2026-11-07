from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.analytics import AnalyticsService, GroupBy, render_chart
from app.models import Status, User
from app.repository import Repository, TaskFilters
from app.schemas import AnalyticsOut, Credentials, TaskCreate, TaskOut, TaskPage, TaskPatch, TokenOut, UserOut
from app.services import AuthService, TaskService, Unauthorized

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def repository(request: Request):
    with request.app.state.sessions() as session:
        yield Repository(session)


Repo = Annotated[Repository, Depends(repository)]


def auth_service(request: Request, repo: Repo):
    return AuthService(repo, request.app.state.hasher, request.app.state.dummy_hash)


Auth = Annotated[AuthService, Depends(auth_service)]


def token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        raise Unauthorized("Передайте Bearer-токен")
    return credentials.credentials


Token = Annotated[str, Depends(token)]


def current_user(auth: Auth, access_token: Token):
    return auth.authenticate(access_token)


CurrentUser = Annotated[User, Depends(current_user)]


def filters(
    status: Status | None = None,
    topic: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
):
    return TaskFilters(status=status, topic=topic, assignee_id=assignee_id, q=q)


Filters = Annotated[TaskFilters, Depends(filters)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/auth/register", response_model=UserOut, status_code=201, tags=["auth"])
def register(body: Credentials, auth: Auth):
    return auth.register(body.username, body.password)


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(body: Credentials, auth: Auth, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return TokenOut(access_token=auth.login(body.username, body.password))


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(user: CurrentUser, access_token: Token, auth: Auth):
    auth.logout(access_token)


@router.get("/users/me", response_model=UserOut, tags=["users"])
def me(user: CurrentUser):
    return user


@router.get("/users", response_model=list[UserOut], tags=["users"])
def users(user: CurrentUser, auth: Auth, limit: Limit = 20, offset: Offset = 0):
    return auth.users(limit, offset)


@router.post("/tasks", response_model=TaskOut, status_code=201, tags=["tasks"])
def create_task(body: TaskCreate, user: CurrentUser, repo: Repo):
    return TaskService(repo).create(user.id, **body.model_dump())


@router.get("/tasks", response_model=TaskPage, tags=["tasks"])
def list_tasks(user: CurrentUser, repo: Repo, search: Filters, limit: Limit = 20, offset: Offset = 0):
    items, total = TaskService(repo).list(user.id, search, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/tasks/{task_id}", response_model=TaskOut, tags=["tasks"])
def get_task(task_id: int, user: CurrentUser, repo: Repo):
    return TaskService(repo).get(user.id, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut, tags=["tasks"])
def update_task(task_id: int, body: TaskPatch, user: CurrentUser, repo: Repo):
    return TaskService(repo).update(user.id, task_id, body.model_dump(exclude_unset=True))


@router.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
def delete_task(task_id: int, user: CurrentUser, repo: Repo):
    TaskService(repo).delete(user.id, task_id)


@router.get("/analytics/tasks", response_model=AnalyticsOut, tags=["analytics"])
def analytics(user: CurrentUser, repo: Repo, search: Filters, group_by: GroupBy = "status"):
    return AnalyticsService(repo).summary(user.id, search, group_by)


@router.get("/analytics/tasks.png", tags=["analytics"], responses={200: {"content": {"image/png": {}}}}, response_class=Response)
def chart(user: CurrentUser, repo: Repo, search: Filters, group_by: GroupBy = "status"):
    summary = AnalyticsService(repo).summary(user.id, search, group_by)
    return Response(render_chart(summary), media_type="image/png", headers={"Cache-Control": "no-store"})
