from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..http import CachedHttpClient
from ..models import Author, Member, PublicationCandidate, ReportingPeriod
from ..utils import normalize_doi, parse_date
from .base import Source


CROSSREF_WORKS_URL = "https://api.crossref.org/v1/works"
DEFAULT_MAX_RESULTS = 10


def _date_parts(item: dict[str, Any], key: str):
    """Return a date parsed from a Crossref date-parts field, if present."""
    value = item.get(key) or {}
    parts = value.get("date-parts") or []

    if not parts or not parts[0]:
        return None

    return parse_date(parts[0])


def _normalize_person_name(value: str | None) -> str:
    """Normalize a person's name for conservative local matching."""
    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    value = value.casefold()
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    return " ".join(value.split())


def _split_person_name(value: str | None) -> tuple[str, str]:
    """
    Return the normalized first given-name token and family-name token.

    Middle names and initials are intentionally ignored.
    """
    parts = _normalize_person_name(value).split()

    if len(parts) < 2:
        return "", ""

    return parts[0], parts[-1]


def _is_initial(value: str) -> bool:
    """Return True when a normalized given-name value is one letter."""
    return len(value) == 1 and value.isalpha()


def _names_compatible(expected: str, returned: str) -> bool:
    """
    Conservatively compare an expected member name with a Crossref author.

    Rules:
    - Family names must match exactly.
    - Full given names must match exactly.
    - A one-letter initial may match the first letter of a full given name.
    - Two different full given names never match merely because they share
      the same first initial.
    """
    expected_given, expected_family = _split_person_name(expected)
    returned_given, returned_family = _split_person_name(returned)

    if not expected_family or expected_family != returned_family:
        return False

    if not expected_given or not returned_given:
        return False

    if expected_given == returned_given:
        return True

    expected_is_initial = _is_initial(expected_given)
    returned_is_initial = _is_initial(returned_given)

    if expected_is_initial and not returned_is_initial:
        return expected_given == returned_given[0]

    if returned_is_initial and not expected_is_initial:
        return returned_given == expected_given[0]

    return False


def _crossref_author_name(author: dict[str, Any]) -> str:
    """Build a display name from a Crossref author object."""
    name = " ".join(
        part
        for part in (author.get("given"), author.get("family"))
        if part
    ).strip()

    return name or str(author.get("name") or "").strip()


def _normalize_orcid(value: str | None) -> str:
    """Normalize an ORCID URL or bare ORCID identifier."""
    if not value:
        return ""

    value = value.strip().casefold()
    value = value.removeprefix("https://orcid.org/")
    value = value.removeprefix("http://orcid.org/")
    return value


def _author_affiliations(author: dict[str, Any]) -> list[str]:
    """Return normalized Crossref affiliation strings for one author."""
    return [
        _normalize_person_name(entry.get("name"))
        for entry in (author.get("affiliation") or [])
        if entry and entry.get("name")
    ]


def _affiliation_matches(
    author: dict[str, Any],
    member: Member,
) -> bool:
    """Check whether the author's affiliation resembles the member's."""
    expected = _normalize_person_name(member.affiliation)

    if not expected:
        return False

    for returned in _author_affiliations(author):
        if expected in returned or returned in expected:
            return True

        # Useful abbreviation handling for RIT.
        if (
            "rochester institute of technology" in expected
            and returned == "rit"
        ):
            return True

    return False


def _record_matches_member( item: dict[str, Any], member: Member,) -> bool:
    """
    Match a Crossref author conservatively.

    Acceptance rules:
    1. Matching ORCID is authoritative.
    2. A matching full canonical given name and family name is accepted.
    3. A returned first initial may match the canonical given name only when
       the initial is genuinely the author's first-name field.
    4. Initial-only matches require supporting affiliation metadata.
    5. Middle initials are never treated as first-name initials.
    """
    expected_orcid = _normalize_orcid(member.orcid)
    canonical_given, canonical_family = _split_person_name(member.name)

    if not canonical_given or not canonical_family:
        return False

    for author in item.get("author") or []:
        if not author:
            continue

        returned_orcid = _normalize_orcid(author.get("ORCID"))

        if (
            expected_orcid
            and returned_orcid
            and expected_orcid == returned_orcid
        ):
            return True

        # Use Crossref's structured given and family fields directly.
        returned_given_raw = str(author.get("given") or "").strip()
        returned_family_raw = str(author.get("family") or "").strip()

        returned_given = _normalize_person_name(
            returned_given_raw
        ).split()

        returned_family = _normalize_person_name(
            returned_family_raw
        )

        if not returned_given or not returned_family:
            continue

        returned_first = returned_given[0]

        if returned_family != canonical_family:
            continue

        if returned_first == canonical_given:
            return True

        if not _is_initial(returned_first):
            continue

        # Initial-only records are ambiguous, so require both the correct
        # first initial and matching affiliation.
        if (
            returned_first == canonical_given[0]
            and _affiliation_matches(author, member)
        ):
            return True

    return False


def _parse_authors(item: dict[str, Any]) -> list[Author]:
    """Convert Crossref author metadata to the application's Author model."""
    authors: list[Author] = []

    for position, raw_author in enumerate(item.get("author") or [], start=1):
        if not raw_author:
            continue

        name = _crossref_author_name(raw_author) or "Unknown"
        affiliations = raw_author.get("affiliation") or []
        affiliation = "; ".join(
            str(entry.get("name") or "").strip()
            for entry in affiliations
            if entry and entry.get("name")
        ) or None

        authors.append(
            Author(
                name=name,
                orcid=raw_author.get("ORCID"),
                position=position,
                affiliation=affiliation,
            )
        )

    return authors


class CrossrefSource(Source):
    """
    Discover a small, high-relevance set of Crossref candidates for a member.

    Crossref's query.author search is not an exact-author lookup. To avoid
    collecting large numbers of weak matches, this source intentionally:

    1. requests only the first, relevance-ranked page;
    2. limits that page to a modest number of records; and
    3. rejects records unless their returned author metadata strongly matches
       the member's canonical name or one of the aliases in members.yaml.
    """

    name = "crossref"

    def __init__(
        self,
        http: CachedHttpClient,
        email: str | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
    ):
        self.http = http
        self.email = email
        self.max_results = max(1, min(int(max_results), 1000))

    def discover(
        self,
        member: Member,
        period: ReportingPeriod,
    ) -> list[PublicationCandidate]:
        params: dict[str, Any] = {
            "query.author": member.name,
            "filter": (
                f"from-pub-date:{period.start},"
                f"until-pub-date:{period.end}"
            ),
            "rows": self.max_results,
        }

        if self.email:
            params["mailto"] = self.email

        payload = self.http.get_json(
            self.name,
            CROSSREF_WORKS_URL,
            params=params,
        )

        message = payload.get("message") or {}
        items = message.get("items") or []
        records: list[PublicationCandidate] = []

        for raw_item in items:
            item = raw_item or {}

            if not _record_matches_member(item, member):
                continue

            online_date = _date_parts(item, "published-online")
            print_date = _date_parts(item, "published-print")
            publication_date = (
                online_date
                or print_date
                or _date_parts(item, "published")
            )

            title_values = item.get("title") or ["Untitled"]
            venue_values = item.get("container-title") or [None]

            records.append(
                PublicationCandidate(
                    title=str(title_values[0] or "Untitled"),
                    authors=_parse_authors(item),
                    doi=normalize_doi(item.get("DOI")),
                    publication_date=publication_date,
                    online_date=online_date,
                    print_date=print_date,
                    year=(
                        publication_date.year
                        if publication_date is not None
                        else None
                    ),
                    venue=venue_values[0],
                    publisher=item.get("publisher"),
                    volume=item.get("volume"),
                    issue=item.get("issue"),
                    pages=item.get("page"),
                    publication_type=item.get("type"),
                    abstract=item.get("abstract"),
                    url=item.get("URL"),
                    source=self.name,
                    source_record_id=item.get("DOI"),
                    raw=item,
                )
            )

        return records
