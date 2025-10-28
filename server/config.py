from __future__ import annotations

import os
from pathlib import Path


# Resolve important directories
SERVER_DIR = Path(__file__).resolve().parent
# Assumes this file lives in <project_root>/server/config.py
PROJECT_ROOT = SERVER_DIR.parent

# Default workspace directory for schema descriptions
DEFAULT_WORKDIR = PROJECT_ROOT / "minidev" / "dev_databases" / "database_description"

# Allow override via environment variable for flexibility (e.g., Streamlit, Docker)
WORKDIR = Path(os.getenv("AMBISQL_WORKDIR", str(DEFAULT_WORKDIR)))


def ensure_directories() -> None:
    """Ensure the workspace directory exists.

    This avoids crashes like WinError 3 when code expects the directory
    to exist while reading/writing schema analysis artifacts.
    """
    WORKDIR.mkdir(parents=True, exist_ok=True)


# Ensure on import so any part of the app can rely on it
ensure_directories()

