from __future__ import annotations

from pathlib import Path


def profile_path(root: Path) -> Path:
    return (root / "data" / "profile" / "agent.md").resolve()


def load_profile(root: Path) -> str:
    path = profile_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"Missing agent profile: {path}")
    return path.read_text(encoding="utf-8").strip()
