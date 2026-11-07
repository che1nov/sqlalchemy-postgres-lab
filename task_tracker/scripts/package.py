"""Build an LMS archive without local databases, credentials or virtualenvs."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def build():
    destination = ROOT.parent / "dist/Чернов_Илья_Итоговое_задание_Трекер_задач.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    excluded = {".venv", "__pycache__", ".pytest_cache", ".mplconfig", ".git"}
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or excluded.intersection(relative.parts):
                continue
            if path.name.startswith(".env") or ".db" in path.suffixes or path.name.endswith((".db-wal", ".db-shm", ".db-journal", ".pyc")):
                continue
            archive.write(path, Path("task_tracker") / relative)
        workflow = ROOT.parent / ".github/workflows/task-tracker.yml"
        if workflow.exists():
            archive.write(workflow, ".github/workflows/task-tracker.yml")
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert "task_tracker/scripts/demo.py" in archive.namelist()
        print(f"{len(archive.namelist())} files, {destination.stat().st_size:,} bytes")
    print(destination)


if __name__ == "__main__":
    build()
