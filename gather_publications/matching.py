from __future__ import annotations

import re
import unicodedata

from .models import Author, Member, PublicationCandidate


def _normalize_orcid(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().casefold()
    value = value.removeprefix("https://orcid.org/")
    value = value.removeprefix("http://orcid.org/")
    return value.rstrip("/")


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    return " ".join(value.split())


def _name_parts(value: str | None) -> tuple[str, str]:
    """Return the first given-name token and final family-name token."""
    parts = _normalize_name(value).split()
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[-1]


def _is_initial(value: str) -> bool:
    return len(value) == 1 and value.isalpha()


def _affiliation_matches(member: Member, author: Author) -> bool:
    expected = _normalize_name(member.affiliation)
    returned = _normalize_name(author.affiliation)

    if not expected or not returned:
        return False

    if expected in returned or returned in expected:
        return True

    return (
        "rochester institute of technology" in expected
        and returned in {"rit", "rochester institute technology"}
    )


def _canonical_name_match(member: Member, author: Author) -> tuple[float, str | None]:
    """
    Match an author to a member conservatively.

    A full first name must match exactly. A first initial can match the
    canonical first name only with supporting affiliation. Middle initials
    never count as first-name matches because only the first token is used.
    """
    member_given, member_family = _name_parts(member.name)
    author_given, author_family = _name_parts(author.name)

    if not member_given or not member_family:
        return 0.0, None

    if not author_given or author_family != member_family:
        return 0.0, None

    # Exact canonical first and last name.
    if author_given == member_given:
        return 0.90, "canonical author name match"

    # A different full first name is a definite non-match:
    if not _is_initial(author_given):
        return 0.0, None

    # Initial-only names are ambiguous and require affiliation support.
    if author_given == member_given[0] and _affiliation_matches(member, author):
        return 0.80, "first initial, family name, and affiliation match"

    return 0.0, None


def _full_alias_match(member: Member, author: Author) -> tuple[float, str | None]:
    """Use aliases only when the alias contains a full given name."""
    author_given, author_family = _name_parts(author.name)
    if not author_given or not author_family:
        return 0.0, None

    for alias in member.aliases:
        alias_given, alias_family = _name_parts(alias)
        if not alias_given or not alias_family or _is_initial(alias_given):
            continue
        if alias_given == author_given and alias_family == author_family:
            return 0.88, "full author alias match"

    return 0.0, None


def match_member(candidate: PublicationCandidate, member: Member) -> tuple[float, list[str]]:
    reasons: list[str] = []
    member_orcid = _normalize_orcid(member.orcid)

    # ORCID is authoritative when present on both sides.
    if member_orcid:
        for author in candidate.authors:
            author_orcid = _normalize_orcid(author.orcid)
            if author_orcid and author_orcid == member_orcid:
                return 1.0, ["ORCID match"]

    best_score = 0.0
    best_reason: str | None = None

    for author in candidate.authors:
        score, reason = _canonical_name_match(member, author)
        if score > best_score:
            best_score, best_reason = score, reason

        alias_score, alias_reason = _full_alias_match(member, author)
        if alias_score > best_score:
            best_score, best_reason = alias_score, alias_reason

    if best_reason:
        reasons.append(best_reason)

    return best_score, reasons


def assign_member_matches(
    candidate: PublicationCandidate,
    members: list[Member],
    automatic_threshold: float,
    review_threshold: float,
) -> PublicationCandidate:
    matches: list[str] = []
    best_score = 0.0
    best_reasons: list[str] = []

    for member in members:
        score, reasons = match_member(candidate, member)

        if score >= review_threshold:
            matches.append(member.name)

        if score > best_score:
            best_score = score
            best_reasons = reasons

    candidate.matched_members = matches
    candidate.match_confidence = best_score

    if not matches:
        candidate.review_reason = "No laboratory member matched above review threshold"
    elif best_score < automatic_threshold:
        candidate.review_reason = "; ".join(best_reasons) or "Ambiguous author match"
    else:
        candidate.review_reason = None

    return candidate
