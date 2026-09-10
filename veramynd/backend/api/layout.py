"""Canonical filesystem layout for the Veramynd product tree.

Keep path discovery here so renames and env overrides stay one-file edits.

Layout (under ``veramynd/``)::

    frontend/          React + Vite operator UI
    backend/           FastAPI API, uploads, jobs, projects.json
    veramynd_parser/   installable pipeline package + CLI + .env
    data/  docs/       samples and design docs
"""

from __future__ import annotations

import os
from pathlib import Path

# ``backend/api/layout.py`` → ``backend/``
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Product root that holds frontend / backend / veramynd_parser as siblings.
VERAMYND_ROOT = BACKEND_ROOT.parent


def _env_path(name: str, default: Path) -> Path:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else default


FRONTEND_ROOT = _env_path("VERAMYND_FRONTEND_ROOT", VERAMYND_ROOT / "frontend")
PARSER_ROOT = _env_path("VERAMYND_PARSER_ROOT", VERAMYND_ROOT / "veramynd_parser")

UPLOADS_DIR = BACKEND_ROOT / "uploads"
RUNS_DIR = BACKEND_ROOT / "runs"
REGISTRY_PATH = BACKEND_ROOT / "projects.json"
WEB_DIR = BACKEND_ROOT / "web"
ASSETS_DIR = WEB_DIR / "assets"
UI_DIST = _env_path("VERAMYND_UI_DIST", FRONTEND_ROOT / "dist")
PARSER_OUTPUT = PARSER_ROOT / "output"

# Legacy alias — older modules imported DASHBOARD_ROOT.
DASHBOARD_ROOT = BACKEND_ROOT

__all__ = [
    "ASSETS_DIR",
    "BACKEND_ROOT",
    "DASHBOARD_ROOT",
    "FRONTEND_ROOT",
    "PARSER_OUTPUT",
    "PARSER_ROOT",
    "REGISTRY_PATH",
    "RUNS_DIR",
    "UI_DIST",
    "UPLOADS_DIR",
    "VERAMYND_ROOT",
    "WEB_DIR",
]
