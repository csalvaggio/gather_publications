from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import ensure_directory


class JsonCache:
    def __init__(self, root: Path, ttl_hours: int = 168):
        self.root = ensure_directory(root)
        self.ttl_seconds = ttl_hours * 3600

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        folder = ensure_directory(self.root / namespace)
        return folder / f"{digest}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists() or time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
