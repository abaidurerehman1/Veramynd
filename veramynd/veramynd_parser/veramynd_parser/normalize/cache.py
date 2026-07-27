"""Content-addressed disk cache for normalization outputs.

Key = SHA-256 of (prompt_version + model + canonical input JSON).
Changing the prompt text, model id, or lesson payload forces a miss.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ..text_utils import atomic_write_text

T = TypeVar("T", bound=BaseModel)


class ContentAddressedCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\0")
        return h.hexdigest()

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str, model: type[T]) -> T | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            return model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Corrupt or partially written (e.g. process killed mid-`put`) —
            # treat as a miss so the caller recomputes and `put` overwrites it.
            return None

    def put(self, key: str, value: BaseModel) -> Path:
        path = self.path_for(key)
        atomic_write_text(path, value.model_dump_json(indent=2) + "\n")
        return path


def canonical_json(payload: dict | BaseModel) -> str:
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
