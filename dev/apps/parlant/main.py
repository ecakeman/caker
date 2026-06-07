from __future__ import annotations

import logging
from pathlib import Path

from app.config import apply_runtime_env, load_settings
from app.log_paths import ensure_default_var_layout
from app.server import run

logging.basicConfig(level=logging.INFO)


def main() -> None:
    root = Path(__file__).resolve().parent
    settings = load_settings(root)
    ensure_default_var_layout(root)
    apply_runtime_env(settings)
    run(settings)


if __name__ == "__main__":
    main()
