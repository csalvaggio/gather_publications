from __future__ import annotations

from collections import defaultdict

from difflib import SequenceMatcher

from .models import PublicationCandidate
from .utils import normalize_doi, normalize_text


def _merge_text(preferred: str | None, alternate: str | None) -> str | None:
    return preferred or alternate


def merge_candidates(primary: PublicationCandidate, other: PublicationCandidate) -> PublicationCandidate:
    primary.doi = normalize_doi(primary.doi or other.doi)
    primary.publication_date = primary.publication_date or other.publication_date
    primary.online_date = primary.online_date or other.online_date
    primary.print_date = primary.print_date or other.print_date
    primary.year = primary.year or other.year
    primary.venue = _merge_text(primary.venue, other.venue)
    primary.publisher = _merge_text(primary.publisher, other.publisher)
    primary.volume = _merge_text(primary.volume, other.volume)
    primary.issue = _merge_text(primary.issue, other.issue)
    primary.pages = _merge_text(primary.pages, other.pages)
    primary.publication_type = _merge_text(primary.publication_type, other.publication_type)
    primary.abstract = _merge_text(primary.abstract, other.abstract)
    primary.url = _merge_text(primary.url, other.url)
    if len(other.authors) > len(primary.authors):
        primary.authors = other.authors
    primary.matched_members = sorted(set(primary.matched_members + other.matched_members))
    primary.match_confidence = max(primary.match_confidence, other.match_confidence)
    primary.raw.setdefault("merged_sources", [])
    primary.raw["merged_sources"] = sorted(
        set(primary.raw["merged_sources"] + [primary.source, other.source])
    )
    return primary


def deduplicate(candidates: list[PublicationCandidate], title_threshold: float = 93.0) -> list[PublicationCandidate]:
    by_doi: dict[str, PublicationCandidate] = {}
    without_doi: list[PublicationCandidate] = []
    for candidate in candidates:
        doi = normalize_doi(candidate.doi)
        candidate.doi = doi
        if doi:
            if doi in by_doi:
                merge_candidates(by_doi[doi], candidate)
            else:
                by_doi[doi] = candidate
        else:
            without_doi.append(candidate)

    output = list(by_doi.values())
    buckets: dict[int | None, list[PublicationCandidate]] = defaultdict(list)
    for candidate in without_doi:
        buckets[candidate.year].append(candidate)

    for bucket in buckets.values():
        merged: list[PublicationCandidate] = []
        for candidate in bucket:
            title = normalize_text(candidate.title)
            duplicate = next(
                (
                    existing
                    for existing in merged
                    if SequenceMatcher(None, title, normalize_text(existing.title)).ratio() * 100 >= title_threshold
                ),
                None,
            )
            if duplicate:
                merge_candidates(duplicate, candidate)
            else:
                merged.append(candidate)
        output.extend(merged)
    return output
