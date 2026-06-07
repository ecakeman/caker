#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from app.log_paths import ensure_default_var_layout, var_root


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    vr = ensure_default_var_layout(root)
    print(var_root(root))
    print(f"var layout ready: {vr}")


if __name__ == "__main__":
    main()
