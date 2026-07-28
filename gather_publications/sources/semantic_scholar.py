from __future__ import annotations

from ..http import CachedHttpClient
from ..models import Author, Member, PublicationCandidate, ReportingPeriod
from ..utils import normalize_doi, parse_date
from .base import Source


class SemanticScholarSource(Source):
    name = "semantic_scholar"

    def __init__(self, http: CachedHttpClient, api_key: str | None = None):
        self.http = http
        self.api_key = api_key

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key} if self.api_key else {}

    def _resolve_author(self, member: Member) -> str | None:
        if member.semantic_scholar_id:
            return member.semantic_scholar_id
        payload = self.http.get_json(
            self.name,
            "https://api.semanticscholar.org/graph/v1/author/search",
            params={"query": member.name, "limit": 10, "fields": "name,affiliations,paperCount"},
            headers=self.headers,
        )
        results = payload.get("data", [])
        if not results:
            return None
        affiliation = (member.affiliation or "").casefold()
        ranked = sorted(results, key=lambda r: (
            affiliation in " ".join(r.get("affiliations") or []).casefold(),
            r.get("paperCount", 0),
        ), reverse=True)
        return ranked[0].get("authorId")

    def discover(self, member: Member, period: ReportingPeriod) -> list[PublicationCandidate]:
        author_id = self._resolve_author(member)
        if not author_id:
            return []
        offset = 0
        records: list[PublicationCandidate] = []
        fields = "title,authors,year,publicationDate,venue,journal,externalIds,url,publicationTypes,abstract"
        while True:
            payload = self.http.get_json(
                self.name,
                f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers",
                params={"offset": offset, "limit": 100, "fields": fields},
                headers=self.headers,
            )
            data = payload.get("data", [])
            for item in data:
                publication_date = parse_date(item.get("publicationDate"))
                year = item.get("year") or (publication_date.year if publication_date else None)
                if publication_date and not period.contains(publication_date):
                    continue
                if not publication_date and year and not (period.start.year <= year <= period.end.year):
                    continue
                external = item.get("externalIds") or {}
                journal = item.get("journal") or {}
                records.append(PublicationCandidate(
                    title=item.get("title") or "Untitled",
                    authors=[Author(name=a.get("name", "Unknown"), position=i) for i, a in enumerate(item.get("authors", []), 1)],
                    doi=normalize_doi(external.get("DOI")),
                    publication_date=publication_date,
                    year=year,
                    venue=journal.get("name") or item.get("venue"),
                    volume=journal.get("volume"),
                    pages=journal.get("pages"),
                    publication_type=", ".join(item.get("publicationTypes") or []) or None,
                    abstract=item.get("abstract"),
                    url=item.get("url"),
                    source=self.name,
                    source_record_id=item.get("paperId"),
                    raw=item,
                ))
            if len(data) < 100:
                break
            offset += len(data)
        return records
