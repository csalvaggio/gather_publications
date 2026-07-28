from __future__ import annotations

from pathlib import Path
from typing import Iterable


from .config import Settings
from .database import Database
from .deduplication import deduplicate
from .http import CachedHttpClient
from .matching import assign_member_matches
from .models import Member, PublicationCandidate, ReportingPeriod
from .sources.crossref import CrossrefSource
from .sources.openalex import OpenAlexSource
from .sources.orcid import OrcidSource
from .sources.scholar_import import import_bibtex, import_csv
from .sources.semantic_scholar import SemanticScholarSource
from .cache import JsonCache



def build_sources(settings: Settings, enabled: set[str]):
    user_agent = f"DIRS-Publications/0.1 ({settings.email or 'no-email-configured'})"
    cache = JsonCache(settings.cache_dir)
    http = CachedHttpClient(cache, user_agent=user_agent)
    sources = []
    if "openalex" in enabled:
        sources.append(OpenAlexSource(http, settings.openalex_api_key, settings.email))
    if "crossref" in enabled:
        sources.append(CrossrefSource(http, settings.email))
    if "semantic_scholar" in enabled:
        sources.append(SemanticScholarSource(http, settings.semantic_scholar_api_key))
    if "orcid" in enabled:
        sources.append(OrcidSource(settings.orcid_client_id, settings.orcid_client_secret, user_agent))
    return sources, http


def discover(
    db: Database,
    members: list[Member],
    period: ReportingPeriod,
    settings: Settings,
    enabled_sources: set[str],
    imports: Iterable[Path] = (),
) -> tuple[int, int]:
    db.sync_members(members)
    sources, http = build_sources(settings, enabled_sources)
    candidates: list[PublicationCandidate] = []
    try:
        for member in members:
            print(f"Searching for {member.name}")
            for source in sources:
                try:
                    found = source.discover(member, period)
                    print(f"  {source.name}: {len(found)}")
                    candidates.extend(found)
                except Exception as exc:
                    print(f"  {source.name} failed: {exc}")
        for path in imports:
            imported = import_bibtex(path) if path.suffix.casefold() in {".bib", ".bibtex"} else import_csv(path)
            print(f"  import {path.name}: {len(imported)}")
            candidates.extend(imported)
    finally:
        http.close()

    matched = [
        assign_member_matches(c, members, settings.automatic_match_threshold, settings.review_match_threshold)
        for c in candidates
    ]
    unique = deduplicate(matched, settings.fuzzy_title_threshold)
    stored = 0
    for candidate in unique:
        if candidate.publication_date and not period.contains(candidate.publication_date):
            continue
        db.upsert_publication(candidate)
        stored += 1
    return len(candidates), stored
