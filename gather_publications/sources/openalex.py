from __future__ import annotations

from datetime import date

from ..http import CachedHttpClient
from ..models import Author, Member, PublicationCandidate, ReportingPeriod
from ..utils import normalize_doi, parse_date
from .base import Source


class OpenAlexSource(Source):
    name = "openalex"

    def __init__(self, http: CachedHttpClient, api_key: str | None = None, email: str | None = None):
        self.http = http
        self.api_key = api_key
        self.email = email

    def _resolve_author(self, member: Member) -> str | None:
        if member.openalex_id:
            return member.openalex_id.rsplit("/", 1)[-1]
        params = {"search": member.name, "per_page": 10}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["mailto"] = self.email
        payload = self.http.get_json(self.name, "https://api.openalex.org/authors", params=params)
        results = payload.get("results") or []
        if not results:
            return None
        affiliation = (member.affiliation or "").casefold()
        ranked = sorted(
            results,
            key=lambda r: (
                affiliation in " ".join(
                    institution.get("display_name", "")
                    for institution in (r.get("last_known_institutions") or [])
                    if institution
                ).casefold(),
                r.get("works_count") or 0,
            ),
            reverse=True,
        )
        return ranked[0]["id"].rsplit("/", 1)[-1]

    def discover(self, member: Member, period: ReportingPeriod) -> list[PublicationCandidate]:
        author_id = self._resolve_author(member)
        if not author_id:
            return []
        cursor = "*"
        records: list[PublicationCandidate] = []
        while cursor:
            params = {
                "filter": f"authorships.author.id:{author_id},from_publication_date:{period.start},to_publication_date:{period.end}",
                "per_page": 100,
                "cursor": cursor,
            }
            if self.api_key:
                params["api_key"] = self.api_key
            if self.email:
                params["mailto"] = self.email
            payload = self.http.get_json(self.name, "https://api.openalex.org/works", params=params)
            for item in payload.get("results") or []:
                authors = []
            
                for position, authorship in enumerate(
                    item.get("authorships") or [],
                    start=1,
                ):
                    authorship = authorship or {}
                    author = authorship.get("author") or {}
                    institutions = authorship.get("institutions") or []
                    authors.append(Author(
                        name=author.get("display_name", "Unknown"),
                        orcid=author.get("orcid"),
                        position=position,
                        affiliation="; ".join(i.get("display_name", "") for i in institutions if i.get("display_name")) or None,
                    ))
                primary = item.get("primary_location") or {}
                source = primary.get("source") or {}
                publication_date = parse_date(item.get("publication_date"))
                records.append(PublicationCandidate(
                    title=item.get("title") or item.get("display_name") or "Untitled",
                    authors=authors,
                    doi=normalize_doi(item.get("doi")),
                    publication_date=publication_date,
                    year=item.get("publication_year") or (publication_date.year if publication_date else None),
                    venue=source.get("display_name"),
                    publisher=source.get("host_organization_name"),
                    publication_type=item.get("type"),
                    url=primary.get("landing_page_url") or item.get("id"),
                    source=self.name,
                    source_record_id=item.get("id"),
                    raw=item,
                ))
            cursor = payload.get("meta", {}).get("next_cursor")
        return records
