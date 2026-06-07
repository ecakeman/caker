from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_entry(path: Path, *, root: Path) -> dict[str, str]:
    rel = str(path.resolve().relative_to(root.resolve()))
    if path.is_dir():
        return {
            "path": rel,
            "sha256": tree_sha256(path),
            "bytes": str(sum(p.stat().st_size for p in path.rglob("*") if p.is_file())),
        }
    return {
        "path": rel,
        "sha256": file_sha256(path) if path.is_file() else "",
        "bytes": str(path.stat().st_size) if path.is_file() else "0",
    }


def tree_sha256(path: Path) -> str:
    h = hashlib.sha256()
    root = path.resolve()
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = str(item.resolve().relative_to(root))
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(file_sha256(item).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()
