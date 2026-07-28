from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .models import Member, ReportingPeriod
from .utils import parse_date


@dataclass(slots=True)
class Settings:
    database: Path
    cache_dir: Path
    output_dir: Path
    email: str | None
    openalex_api_key: str | None
    semantic_scholar_api_key: str | None
    orcid_client_id: str | None
    orcid_client_secret: str | None
    fuzzy_title_threshold: float
    automatic_match_threshold: float
    review_match_threshold: float


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_members(path: Path) -> list[Member]:
    data = load_yaml(path)
    members: list[Member] = []
    for item in data.get("members", []):
        members.append(
            Member(
                name=item["name"],
                aliases=item.get("aliases", []),
                affiliation=item.get("affiliation"),
                orcid=item.get("orcid"),
                openalex_id=item.get("openalex_id"),
                semantic_scholar_id=item.get("semantic_scholar_id"),
                scholar_profile_id=item.get("scholar_profile_id"),
                role=item.get("role"),
                active_from=parse_date(item.get("active_from")),
                active_until=parse_date(item.get("active_until")),
            )
        )
    return members


def load_reporting_period(path: Path) -> ReportingPeriod:
    data = load_yaml(path).get("reporting_period", {})
    start = parse_date(data.get("start"))
    end = parse_date(data.get("end"))
    if not start or not end:
        raise ValueError("reporting_period.start and reporting_period.end are required")
    return ReportingPeriod(start=start, end=end)


def load_settings(path: Path) -> Settings:
    data = load_yaml(path)
    base = path.parent.resolve()

    def resolved(name: str, default: str) -> Path:
        value = Path(data.get("paths", {}).get(name, default)).expanduser()
        return value if value.is_absolute() else (base / value).resolve()

    api = data.get("api", {})
    matching = data.get("matching", {})
    return Settings(
        database=resolved("database", "../data/publications.sqlite3"),
        cache_dir=resolved("cache_dir", "../.cache"),
        output_dir=resolved("output_dir", "../output"),
        email=api.get("email"),
        openalex_api_key=api.get("openalex_api_key"),
        semantic_scholar_api_key=api.get("semantic_scholar_api_key"),
        orcid_client_id=api.get("orcid_client_id"),
        orcid_client_secret=api.get("orcid_client_secret"),
        fuzzy_title_threshold=float(matching.get("fuzzy_title_threshold", 93.0)),
        automatic_match_threshold=float(matching.get("automatic_match_threshold", 0.86)),
        review_match_threshold=float(matching.get("review_match_threshold", 0.60)),
    )
