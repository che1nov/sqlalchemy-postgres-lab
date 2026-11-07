from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuthSession, User, utcnow
from tests.conftest import PASSWORD


def test_auth_lifecycle_and_hashes(client, alice):
    user, headers = alice
    assert set(user) == {"id", "username"}
    assert client.get("/users/me", headers=headers).json() == user
    with client.app.state.sessions() as session:
        stored = session.get(User, user["id"])
        assert stored.password_hash.startswith("$argon2id$")
        assert PASSWORD not in stored.password_hash
        auth = session.scalar(select(AuthSession))
        assert len(auth.token_hash) == 64
        assert auth.token_hash != headers["Authorization"].split()[1]
    assert client.post("/auth/logout", headers=headers).status_code == 204
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token(client, alice):
    _, headers = alice
    with client.app.state.sessions.begin() as session:
        session.scalar(select(AuthSession)).expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/tasks", headers=headers).status_code == 401


def test_duplicate_registration_and_login_errors(client, alice):
    response = client.post("/auth/register", json={"username": " Alice ", "password": PASSWORD})
    assert response.status_code == 409
    assert client.post("/auth/login", json={"username": "ALICE", "password": PASSWORD}).status_code == 200
    for name in ("alice", "missing"):
        response = client.post("/auth/login", json={"username": name, "password": "wrong-password"})
        assert response.status_code == 401
        assert response.json() == {"detail": "Неверное имя или пароль"}
    assert client.get("/users/me", headers=alice[1]).status_code == 200


@pytest.mark.parametrize("path", ["/tasks", "/users", "/users/me", "/analytics/tasks", "/analytics/tasks.png"])
def test_auth_required(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer forged"}).status_code == 401


def test_validation_does_not_echo_password(client):
    response = client.post("/auth/register", json={"username": "alice", "password": "secret"})
    assert response.status_code == 422
    assert "secret" not in response.text


def test_task_crud(client, alice, account):
    user, headers = alice
    bob, _ = account("bob")
    response = client.post("/tasks", headers=headers, json={"title": "  Первая задача  ", "assignee_id": bob["id"]})
    assert response.status_code == 201
    task = response.json()
    assert task["title"] == "Первая задача"
    assert task["status"] == "new"
    assert task["owner_id"] == user["id"]
    url = f"/tasks/{task['id']}"
    assert client.get(url, headers=headers).json() == task
    for status in ("in_progress", "done", "new", "cancelled"):
        response = client.patch(url, headers=headers, json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status
    response = client.patch(url, headers=headers, json={"title": "Новая", "topic": "БД", "description": "SQL", "assignee_id": None})
    assert response.status_code == 200
    assert response.json()["assignee_id"] is None
    assert response.json()["updated_at"] >= task["updated_at"]
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


@pytest.mark.parametrize("changes", [{}, {"title": " "}, {"title": None}, {"topic": None}, {"description": None}, {"status": None}, {"status": "unknown"}, {"owner_id": 22}, {"assignee_id": 0}])
def test_bad_patch_is_atomic(client, alice, changes):
    _, headers = alice
    task = client.post("/tasks", headers=headers, json={"title": "Original"}).json()
    url = f"/tasks/{task['id']}"
    assert client.patch(url, headers=headers, json=changes).status_code == 422
    assert client.get(url, headers=headers).json() == task


def test_invalid_assignee_rolls_back_all_fields(client, alice):
    _, headers = alice
    assert client.post("/tasks", headers=headers, json={"title": "Bad", "assignee_id": 999}).status_code == 422
    task = client.post("/tasks", headers=headers, json={"title": "Original"}).json()
    url = f"/tasks/{task['id']}"
    assert client.patch(url, headers=headers, json={"title": "Changed", "assignee_id": 999}).status_code == 422
    assert client.get(url, headers=headers).json()["title"] == "Original"
    assert client.get("/tasks", headers=headers).json()["total"] == 1


def test_owner_isolation_including_assignee(client, alice, account):
    _, alice_headers = alice
    bob, bob_headers = account("bob")
    task = client.post("/tasks", headers=alice_headers, json={"title": "Private", "assignee_id": bob["id"]}).json()
    url = f"/tasks/{task['id']}"
    assert client.get(url, headers=bob_headers).status_code == 404
    assert client.patch(url, headers=bob_headers, json={"title": "Hacked"}).status_code == 404
    assert client.delete(url, headers=bob_headers).status_code == 404
    assert client.get("/tasks", headers=bob_headers).json()["total"] == 0
    assert client.get("/analytics/tasks", headers=bob_headers).json()["total"] == 0


def test_filters_pagination_and_analytics(client, alice, account):
    user, headers = alice
    _, bob_headers = account("bob")
    client.post("/tasks", headers=bob_headers, json={"title": "Hidden"})
    for i in range(4):
        task = client.post("/tasks", headers=headers, json={
            "title": f"Task {i}", "description": "needle" if i == 0 else "",
            "topic": "DB" if i < 2 else "API", "assignee_id": user["id"] if i < 3 else None,
        }).json()
        if i < 2:
            client.patch(f"/tasks/{task['id']}", headers=headers, json={"status": "done"})
    page = client.get("/tasks", headers=headers, params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 4
    assert [item["title"] for item in page["items"]] == ["Task 2", "Task 1"]
    for params, expected in [({"status": "done"}, 2), ({"topic": "API"}, 2), ({"q": "needle"}, 1), ({"assignee_id": user["id"]}, 3), ({"status": "done", "topic": "API"}, 0)]:
        assert client.get("/tasks", headers=headers, params=params).json()["total"] == expected
        assert client.get("/analytics/tasks", headers=headers, params=params).json()["total"] == expected
    summary = client.get("/analytics/tasks", headers=headers).json()
    assert summary["total"] == 4 and summary["done"] == 2 and summary["completion_rate"] == 50
    for grouping, expected in [("topic", {"API": 2, "DB": 2}), ("assignee", {str(user["id"]): 3, "unassigned": 1})]:
        summary = client.get("/analytics/tasks", headers=headers, params={"group_by": grouping}).json()
        assert {item["key"]: item["count"] for item in summary["groups"]} == expected
    assert client.get("/tasks", headers=headers, params={"offset": 100}).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "invalid"}, {"assignee_id": -1}])
def test_query_validation(client, alice, params):
    assert client.get("/tasks", headers=alice[1], params=params).status_code == 422


def test_injections_and_literal_wildcards(client, alice):
    _, headers = alice
    payload = "'; DROP TABLE tasks; --"
    response = client.post("/tasks", headers=headers, json={"title": payload, "topic": payload})
    assert response.status_code == 201
    assert client.get("/tasks", headers=headers, params={"q": payload}).json()["total"] == 1
    assert client.get("/tasks", headers=headers, params={"topic": payload}).json()["total"] == 1
    for q in ("' OR 1=1 --", "%", "_"):
        assert client.get("/tasks", headers=headers, params={"q": q}).json()["total"] == 0
    client.post("/tasks", headers=headers, json={"title": "100%_complete"})
    assert client.get("/tasks", headers=headers, params={"q": "%_"}).json()["total"] == 1
    assert client.get("/analytics/tasks", headers=headers, params={"group_by": payload}).status_code == 422
    assert client.get("/tasks", headers=headers).json()["total"] == 2


def test_empty_and_nonempty_chart(client, alice):
    _, headers = alice
    for group in ("status", "topic", "assignee"):
        summary = client.get("/analytics/tasks", headers=headers, params={"group_by": group}).json()
        assert summary["total"] == 0 and summary["completion_rate"] == 0
        response = client.get("/analytics/tasks.png", headers=headers, params={"group_by": group})
        assert response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert response.headers["content-type"] == "image/png"
    client.post("/tasks", headers=headers, json={"title": "Plot", "topic": "Базы данных"})
    assert client.get("/analytics/tasks.png?group_by=topic", headers=headers).status_code == 200


def test_health_and_docs(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert "/tasks" in client.get("/openapi.json").json()["paths"]
