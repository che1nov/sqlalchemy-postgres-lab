from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.analytics import summarize
from app.services import InvalidAssignee, NotFound, TaskService


def test_missing_task_stops_delete():
    repo = Mock()
    repo.task.return_value = None
    with pytest.raises(NotFound):
        TaskService(repo).delete(1, 7)
    repo.task.assert_called_once_with(7, 1)
    repo.delete.assert_not_called()
    repo.session.commit.assert_not_called()


def test_unknown_assignee_does_not_mutate_task():
    repo = Mock()
    task = SimpleNamespace(title="Original", assignee_id=None)
    repo.task.return_value = task
    repo.user.return_value = None
    with pytest.raises(InvalidAssignee):
        TaskService(repo).update(1, 7, {"title": "Changed", "assignee_id": 42})
    assert task.title == "Original"
    repo.session.commit.assert_not_called()


def test_unassign_commits():
    repo = Mock()
    repo.task.return_value = SimpleNamespace(assignee_id=42)
    result = TaskService(repo).update(1, 7, {"assignee_id": None})
    assert result.assignee_id is None
    repo.user.assert_not_called()
    repo.session.commit.assert_called_once()


def test_analytics_rounding_and_null_group():
    rows = [{"status": status, "topic": "DB", "assignee_id": None} for status in ("new", "done", "cancelled")]
    result = summarize(rows, "assignee")
    assert result["completion_rate"] == 33.33
    assert result["groups"] == [{"key": "unassigned", "count": 3}]
