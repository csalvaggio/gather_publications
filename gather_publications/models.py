from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class Member:
    name: str
    aliases: list[str] = field(default_factory=list)
    affiliation: str | None = None
    orcid: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    scholar_profile_id: str | None = None
    role: str | None = None
    active_from: date | None = None
    active_until: date | None = None

    @property
    def all_names(self) -> list[str]:
        return list(dict.fromkeys([self.name, *self.aliases]))


@dataclass(slots=True)
class Author:
    name: str
    orcid: str | None = None
    position: int | None = None
    affiliation: str | None = None


@dataclass(slots=True)
class PublicationCandidate:
    title: str
    authors: list[Author] = field(default_factory=list)
    doi: str | None = None
    publication_date: date | None = None
    online_date: date | None = None
    print_date: date | None = None
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publication_type: str | None = None
    abstract: str | None = None
    url: str | None = None
    source: str = "unknown"
    source_record_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    matched_members: list[str] = field(default_factory=list)
    match_confidence: float = 0.0
    review_reason: str | None = None


@dataclass(slots=True)
class ReportingPeriod:
    start: date
    end: date

    def contains(self, value: date | None) -> bool:
        return value is not None and self.start <= value <= self.end
