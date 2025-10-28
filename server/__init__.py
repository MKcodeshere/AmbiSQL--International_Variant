"""Server package initialization.

Ensures the workspace directory for schema artifacts exists at import time.
"""

# Importing config ensures directory creation and exposes WORKDIR for reuse
from .config import WORKDIR  # noqa: F401

