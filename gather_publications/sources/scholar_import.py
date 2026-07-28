from __future__ import annotations

import csv
import re
from pathlib import Path

from ..models import Author, PublicationCandidate
from ..utils import normalize_doi, parse_date


def _split_authors(value: str) -> list[Author]:
    return [Author(name=name.strip(), position=i) for i, name in enumerate(value.split(" and "), 1) if name.strip()]


def _bib_entries(text: str):
    pos = 0
    while True:
        match = re.search(r"@(\w+)\s*\{", text[pos:], re.I)
        if not match:
            return
        start = pos + match.start()
        body_start = pos + match.end()
        depth = 1
        i = body_start
        while i < len(text) and depth:
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            i += 1
        if depth:
            return
        yield match.group(1).lower(), text[body_start:i-1]
        pos = i


def _parse_fields(body: str) -> tuple[str, dict[str, str]]:
    comma = body.find(",")
    entry_id = body[:comma].strip() if comma >= 0 else "imported"
    fields_text = body[comma + 1:] if comma >= 0 else ""
    fields = {}
    pattern = re.compile(r'(\w[\w-]*)\s*=\s*(\{|")', re.I)
    pos = 0
    while (m := pattern.search(fields_text, pos)):
        key = m.group(1).lower()
        opener = m.group(2)
        value_start = m.end()
        if opener == '"':
            i = value_start
            escaped = False
            while i < len(fields_text):
                if fields_text[i] == '"' and not escaped: break
                escaped = fields_text[i] == "\\" and not escaped
                if fields_text[i] != "\\": escaped = False
                i += 1
            value, pos = fields_text[value_start:i], i + 1
        else:
            depth, i = 1, value_start
            while i < len(fields_text) and depth:
                if fields_text[i] == "{": depth += 1
                elif fields_text[i] == "}": depth -= 1
                i += 1
            value, pos = fields_text[value_start:i-1], i
        fields[key] = value.strip().replace("\n", " ")
    return entry_id, fields


def import_bibtex(path: Path) -> list[PublicationCandidate]:
    records = []
    text = path.read_text(encoding="utf-8")
    for entry_type, body in _bib_entries(text):
        entry_id, entry = _parse_fields(body)
        year = int(entry["year"]) if entry.get("year", "").isdigit() else None
        month = int(entry.get("month", "1")) if entry.get("month", "1").isdigit() else 1
        records.append(PublicationCandidate(
            title=entry.get("title", "Untitled").strip("{}"),
            authors=_split_authors(entry.get("author", "")),
            doi=normalize_doi(entry.get("doi")),
            publication_date=parse_date([year, month, 1]) if year else None,
            year=year,
            venue=entry.get("journal") or entry.get("booktitle"),
            publisher=entry.get("publisher"), volume=entry.get("volume"),
            issue=entry.get("number"), pages=entry.get("pages"),
            publication_type=entry_type, url=entry.get("url"),
            source="google_scholar_import", source_record_id=entry_id, raw=entry,
        ))
    return records


def import_csv(path: Path) -> list[PublicationCandidate]:
    records = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            lower = {k.casefold().strip(): (v or "").strip() for k, v in row.items() if k}
            year_text = lower.get("year", "")
            year = int(year_text) if year_text.isdigit() else None
            author_text = lower.get("authors") or lower.get("author") or ""
            records.append(PublicationCandidate(
                title=lower.get("title") or "Untitled",
                authors=[Author(name=x.strip(), position=i) for i, x in enumerate(author_text.replace(";", " and ").split(" and "), 1) if x.strip()],
                doi=normalize_doi(lower.get("doi")),
                publication_date=parse_date(lower.get("publication date") or lower.get("date")) or (parse_date([year, 1, 1]) if year else None),
                year=year, venue=lower.get("publication") or lower.get("journal") or lower.get("venue"),
                volume=lower.get("volume"), issue=lower.get("issue") or lower.get("number"), pages=lower.get("pages"),
                publication_type=lower.get("type"), url=lower.get("url"), source="google_scholar_import", raw=row,
            ))
    return records
