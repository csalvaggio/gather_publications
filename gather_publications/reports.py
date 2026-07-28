from __future__ import annotations

import csv
from pathlib import Path

from .database import Database
from .models import ReportingPeriod
from .utils import ensure_directory


def _author_string(db: Database, publication_id: int) -> str:
    return "; ".join(row["name"] for row in db.authors_for(publication_id))


def export_csv(db: Database, period: ReportingPeriod, path: Path, verified_only: bool = False) -> None:
    rows = db.publications_between(period.start.isoformat(), period.end.isoformat(), verified_only)
    ensure_directory(path.parent)
    fields = ["id", "title", "authors", "doi", "publication_date", "online_date", "print_date", "year",
              "venue", "publisher", "volume", "issue", "pages", "publication_type", "url",
              "matched_members", "sources", "verification_status", "review_notes"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            item = {field: row[field] if field in row.keys() else None for field in fields}
            item["authors"] = _author_string(db, row["id"])
            writer.writerow(item)


def export_markdown(db: Database, period: ReportingPeriod, path: Path, verified_only: bool = False) -> None:
    rows = db.publications_between(period.start.isoformat(), period.end.isoformat(), verified_only)
    ensure_directory(path.parent)
    lines = [f"# DIRS Publications: {period.start} through {period.end}", ""]
    for row in rows:
        authors = _author_string(db, row["id"])
        citation = f"- {authors}. **{row['title']}**"
        if row["venue"]:
            citation += f". *{row['venue']}*"
        if row["volume"]:
            citation += f", {row['volume']}"
        if row["issue"]:
            citation += f"({row['issue']})"
        if row["pages"]:
            citation += f", {row['pages']}"
        if row["publication_date"]:
            citation += f" ({row['publication_date']})"
        if row["doi"]:
            citation += f". DOI: {row['doi']}"
        citation += "."
        lines.append(citation)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bib_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def export_bibtex(db: Database, period: ReportingPeriod, path: Path, verified_only: bool = False) -> None:
    rows = db.publications_between(period.start.isoformat(), period.end.isoformat(), verified_only)
    blocks = []
    for row in rows:
        fields = {
            "title": row["title"],
            "author": " and ".join(a["name"] for a in db.authors_for(row["id"])),
            "year": str(row["year"] or ""),
            "doi": row["doi"], "journal": row["venue"], "volume": row["volume"],
            "number": row["issue"], "pages": row["pages"], "publisher": row["publisher"], "url": row["url"],
        }
        lines = [f"@article{{citation{row['id']},"]
        for key, value in fields.items():
            if value:
                lines.append(f"  {key} = {{{_bib_escape(str(value))}}},")
        lines.append("}")
        blocks.append("\n".join(lines))
    ensure_directory(path.parent)
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")

def export_review_report(db: Database, period: ReportingPeriod, path: Path) -> None:
    rows = db.publications_between(period.start.isoformat(), period.end.isoformat(), False)
    ensure_directory(path.parent)
    lines = ["# Publications Requiring Review", ""]
    for row in rows:
        if row["verification_status"] in {"verified", "rejected"}:
            continue
        lines.extend([
            f"## Database ID {row['id']}: {row['title']}",
            "",
            f"- Date: {row['publication_date'] or 'unknown'}",
            f"- Authors: {_author_string(db, row['id'])}",
            f"- Matched members: {row['matched_members'] or 'none'}",
            f"- Sources: {row['sources'] or 'unknown'}",
            f"- Status: {row['verification_status']}",
            f"- Reason/notes: {row['review_notes'] or 'not supplied'}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")
