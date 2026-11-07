from io import BytesIO
from threading import Lock
from typing import Literal

import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.models import Status
from app.repository import Repository, TaskFilters

GroupBy = Literal["status", "topic", "assignee"]
_plot_lock = Lock()  # Matplotlib has process-wide state and is not thread-safe.


def summarize(rows, group_by: GroupBy) -> dict:
    frame = pd.DataFrame(rows, columns=["status", "topic", "assignee_id"])
    total = len(frame)
    done = int((frame["status"] == Status.DONE.value).sum())
    column = "assignee_id" if group_by == "assignee" else group_by
    if group_by == "assignee":
        frame[column] = frame[column].map(lambda value: str(int(value)) if pd.notna(value) else "unassigned")
    counts = frame.groupby(column).size().sort_index()
    if group_by == "status":
        counts = counts.reindex([status.value for status in Status], fill_value=0)
    return {
        "total": total, "done": done,
        "completion_rate": round(done / total * 100, 2) if total else 0.0,
        "group_by": group_by,
        "groups": [{"key": str(key), "count": int(value)} for key, value in counts.items()],
    }


def render_chart(summary: dict) -> bytes:
    with _plot_lock:
        # JSON includes every group. Chart shows top 20 to keep labels readable.
        groups = sorted(summary["groups"], key=lambda item: (-item["count"], item["key"]))[:20]
        figure = Figure(figsize=(10, max(3.5, len(groups) * 0.4 + 1.8)), layout="constrained")
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        if groups and summary["total"]:
            labels = [item["key"] if len(item["key"]) <= 35 else item["key"][:32] + "..." for item in groups]
            bars = axes.barh(range(len(groups)), [item["count"] for item in groups], color="#1c8179")
            axes.set_yticks(range(len(groups)), labels)
            axes.bar_label(bars, padding=4)
            axes.invert_yaxis()
            axes.set_xlim(0, max(item["count"] for item in groups) * 1.18 + 1)
            axes.xaxis.get_major_locator().set_params(integer=True)
        else:
            axes.text(0.5, 0.5, "No tasks", ha="center", va="center", transform=axes.transAxes)
        suffix = " (top 20)" if len(summary["groups"]) > 20 else ""
        axes.set_title(f"Tasks by {summary['group_by']}{suffix} | total: {summary['total']}")
        axes.set_xlabel("Task count")
        output = BytesIO()
        figure.savefig(output, format="png", dpi=140)
        return output.getvalue()


class AnalyticsService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def summary(self, owner_id: int, filters: TaskFilters, group_by: GroupBy):
        return summarize(self.repo.analytics_rows(owner_id, filters), group_by)
