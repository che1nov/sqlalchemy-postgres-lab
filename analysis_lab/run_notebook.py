"""Выполнить тетрадку и сохранить реальные результаты в .ipynb."""

from pathlib import Path

import nbformat
from nbclient import NotebookClient


def main():
    path = Path(__file__).with_name("data_analysis.ipynb")
    notebook = nbformat.read(path, as_version=4)
    NotebookClient(
        notebook,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(path.parent)}},
    ).execute()
    nbformat.validate(notebook)
    nbformat.write(notebook, path)
    print(f"Все ячейки выполнены, результаты сохранены: {path}")


if __name__ == "__main__":
    main()
