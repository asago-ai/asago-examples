from pathlib import Path

import nbformat
import pytest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = tuple(
    sorted(
        path
        for member in ROOT.glob("asago-*")
        for path in member.rglob("*.ipynb")
        if ".ipynb_checkpoints" not in path.parts
    )
)


def test_notebooks_exist() -> None:
    assert NOTEBOOKS, "No example notebooks were found"


@pytest.mark.parametrize("notebook_path", NOTEBOOKS, ids=lambda path: str(path.relative_to(ROOT)))
def test_notebook_is_valid(notebook_path: Path) -> None:
    notebook = nbformat.read(notebook_path, as_version=4)
    nbformat.validate(notebook)


@pytest.mark.parametrize("notebook_path", NOTEBOOKS, ids=lambda path: str(path.relative_to(ROOT)))
def test_notebook_code_cells_compile(notebook_path: Path) -> None:
    notebook = nbformat.read(notebook_path, as_version=4)
    for cell_number, cell in enumerate(notebook.cells):
        if cell.cell_type == "code":
            compile(cell.source, f"{notebook_path}:cell {cell_number}", "exec")
