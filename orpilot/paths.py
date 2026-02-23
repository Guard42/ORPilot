"""Canonical filesystem paths for the ORPilot project."""

from pathlib import Path

# Absolute path to the ORPilot project root (the directory that contains
# the `orpilot/` package).  This file lives at  orpilot/paths.py, so the
# project root is one level up.
PROJECT_ROOT: Path = Path(__file__).parent.parent

# All CSV data files (user-provided and computed) live here.
DATA_DIR: Path = PROJECT_ROOT / "data"
