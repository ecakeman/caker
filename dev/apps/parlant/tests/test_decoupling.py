from __future__ import annotations

import ast
from pathlib import Path


def _imports_in_package(pkg_dir: Path) -> set[str]:
    found: set[str] = set()
    for path in pkg_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
    return found


def test_data_pipeline_does_not_import_app() -> None:
    root = Path(__file__).resolve().parents[1]
    imports = _imports_in_package(root / "data_pipeline")
    assert "app" not in imports


def test_app_does_not_import_data_pipeline() -> None:
    root = Path(__file__).resolve().parents[1]
    imports = _imports_in_package(root / "app")
    assert "data_pipeline" not in imports
