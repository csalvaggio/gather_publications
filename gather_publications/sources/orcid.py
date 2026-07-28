from __future__ import annotations

import httpx

from ..models import Author, Member, PublicationCandidate, ReportingPeriod
from ..utils import normalize_doi, parse_date
from .base import Source


class OrcidSource(Source):
    name = "orcid"

    def __init__(self, client_id: str | None, client_secret: str | None, user_agent: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self._token: str | None = None

    def _access_token(self) -> str | None:
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            return None
        response = httpx.post(
            "https://orcid.org/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "/read-public",
            },
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
            timeout=30,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def discover(self, member: Member, period: ReportingPeriod) -> list[PublicationCandidate]:
        if not member.orcid:
            return []
        token = self._access_token()
        if not token:
            return []
        orcid = member.orcid.rsplit("/", 1)[-1]
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.orcid+json",
            "User-Agent": self.user_agent,
        }
        response = httpx.get(f"https://pub.orcid.org/v3.0/{orcid}/works", headers=headers, timeout=30)
        response.raise_for_status()
        records: list[PublicationCandidate] = []
        for group in response.json().get("group", []):
            summaries = group.get("work-summary", [])
            if not summaries:
                continue
            item = summaries[0]
            title = (((item.get("title") or {}).get("title") or {}).get("value")) or "Untitled"
            pub_date = item.get("publication-date") or {}
            date_parts = [
                ((pub_date.get(k) or {}).get("value"))
                for k in ("year", "month", "day")
                if (pub_date.get(k) or {}).get("value")
            ]
            publication_date = parse_date(date_parts)
            if publication_date and not period.contains(publication_date):
                continue
            doi = None
            for ext in ((item.get("external-ids") or {}).get("external-id") or []):
                if (ext.get("external-id-type") or "").casefold() == "doi":
                    doi = normalize_doi(ext.get("external-id-value"))
            records.append(PublicationCandidate(
                title=title,
                authors=[Author(name=member.name, orcid=member.orcid, position=1)],
                doi=doi,
                publication_date=publication_date,
                year=publication_date.year if publication_date else None,
                venue=((item.get("journal-title") or {}).get("value")),
                publication_type=item.get("type"),
                url=((item.get("url") or {}).get("value")),
                source=self.name,
                source_record_id=str(item.get("put-code")),
                raw=item,
            ))
        return records
