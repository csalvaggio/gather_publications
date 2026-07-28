from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(".,; ") or None


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parts = value.strip().split("-")
        try:
            y = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 1
            d = int(parts[2]) if len(parts) > 2 else 1
            return date(y, m, d)
        except (ValueError, IndexError):
            return None
    if isinstance(value, (list, tuple)) and value:
        try:
            y = int(value[0])
            m = int(value[1]) if len(value) > 1 else 1
            d = int(value[2]) if len(value) > 2 else 1
            return date(y, m, d)
        except (ValueError, TypeError):
            return None
    return None


def candidate_fingerprint(title: str, year: int | None = None) -> str:
    payload = f"{normalize_text(title)}|{year or ''}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
