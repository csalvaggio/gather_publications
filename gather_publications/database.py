from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Member, PublicationCandidate
from .utils import candidate_fingerprint, ensure_directory, json_dumps, normalize_doi

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT,
    affiliation TEXT,
    orcid TEXT,
    openalex_id TEXT,
    semantic_scholar_id TEXT,
    scholar_profile_id TEXT,
    active_from TEXT,
    active_until TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    doi TEXT UNIQUE,
    publication_date TEXT,
    online_date TEXT,
    print_date TEXT,
    year INTEGER,
    venue TEXT,
    publisher TEXT,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    publication_type TEXT,
    abstract TEXT,
    url TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unreviewed',
    review_notes TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publication_authors (
    publication_id INTEGER NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    orcid TEXT,
    affiliation TEXT,
    PRIMARY KEY (publication_id, position)
);
CREATE TABLE IF NOT EXISTS publication_members (
    publication_id INTEGER NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    PRIMARY KEY (publication_id, member_id)
);
CREATE TABLE IF NOT EXISTS provenance (
    publication_id INTEGER NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    source_record_id TEXT,
    raw_json TEXT,
    discovered_at TEXT NOT NULL,
    UNIQUE(publication_id, source, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_publications_date ON publications(publication_date);
CREATE INDEX IF NOT EXISTS idx_publications_year ON publications(year);
CREATE INDEX IF NOT EXISTS idx_pub_authors_name ON publication_authors(name);
"""


class Database:
    def __init__(self, path: Path):
        ensure_directory(path.parent)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def sync_members(self, members: list[Member]) -> None:
        with self.connection:
            for m in members:
                self.connection.execute(
                    """INSERT INTO members(name, role, affiliation, orcid, openalex_id,
                       semantic_scholar_id, scholar_profile_id, active_from, active_until, aliases_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(name) DO UPDATE SET role=excluded.role, affiliation=excluded.affiliation,
                       orcid=excluded.orcid, openalex_id=excluded.openalex_id,
                       semantic_scholar_id=excluded.semantic_scholar_id,
                       scholar_profile_id=excluded.scholar_profile_id, active_from=excluded.active_from,
                       active_until=excluded.active_until, aliases_json=excluded.aliases_json""",
                    (m.name, m.role, m.affiliation, m.orcid, m.openalex_id,
                     m.semantic_scholar_id, m.scholar_profile_id,
                     m.active_from.isoformat() if m.active_from else None,
                     m.active_until.isoformat() if m.active_until else None,
                     json_dumps(m.aliases)),
                )

    def upsert_publication(self, candidate: PublicationCandidate) -> int:
        now = datetime.now(timezone.utc).isoformat()
        doi = normalize_doi(candidate.doi)
        key = f"doi:{doi}" if doi else f"title:{candidate_fingerprint(candidate.title, candidate.year)}"
        status = "candidate" if candidate.review_reason else "auto-matched"
        with self.connection:
            self.connection.execute(
                """INSERT INTO publications(canonical_key,title,doi,publication_date,online_date,print_date,
                   year,venue,publisher,volume,issue,pages,publication_type,abstract,url,
                   verification_status,review_notes,first_seen,last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(canonical_key) DO UPDATE SET
                   title=excluded.title, doi=COALESCE(excluded.doi, publications.doi),
                   publication_date=COALESCE(excluded.publication_date, publications.publication_date),
                   online_date=COALESCE(excluded.online_date, publications.online_date),
                   print_date=COALESCE(excluded.print_date, publications.print_date),
                   year=COALESCE(excluded.year, publications.year), venue=COALESCE(excluded.venue, publications.venue),
                   publisher=COALESCE(excluded.publisher, publications.publisher),
                   volume=COALESCE(excluded.volume, publications.volume), issue=COALESCE(excluded.issue, publications.issue),
                   pages=COALESCE(excluded.pages, publications.pages),
                   publication_type=COALESCE(excluded.publication_type, publications.publication_type),
                   abstract=COALESCE(excluded.abstract, publications.abstract), url=COALESCE(excluded.url, publications.url),
                   review_notes=COALESCE(excluded.review_notes, publications.review_notes), last_seen=excluded.last_seen""",
                (key, candidate.title, doi,
                 candidate.publication_date.isoformat() if candidate.publication_date else None,
                 candidate.online_date.isoformat() if candidate.online_date else None,
                 candidate.print_date.isoformat() if candidate.print_date else None,
                 candidate.year, candidate.venue, candidate.publisher, candidate.volume,
                 candidate.issue, candidate.pages, candidate.publication_type,
                 candidate.abstract, candidate.url, status, candidate.review_reason, now, now),
            )
            publication_id = self.connection.execute(
                "SELECT id FROM publications WHERE canonical_key=?", (key,)
            ).fetchone()["id"]
            self.connection.execute("DELETE FROM publication_authors WHERE publication_id=?", (publication_id,))
            for index, author in enumerate(candidate.authors, 1):
                self.connection.execute(
                    "INSERT INTO publication_authors(publication_id,position,name,orcid,affiliation) VALUES(?,?,?,?,?)",
                    (publication_id, author.position or index, author.name, author.orcid, author.affiliation),
                )
            for member_name in candidate.matched_members:
                row = self.connection.execute("SELECT id FROM members WHERE name=?", (member_name,)).fetchone()
                if row:
                    self.connection.execute(
                        "INSERT INTO publication_members(publication_id,member_id,confidence) VALUES(?,?,?) "
                        "ON CONFLICT(publication_id,member_id) DO UPDATE SET confidence=max(confidence,excluded.confidence)",
                        (publication_id, row["id"], candidate.match_confidence),
                    )
            self.connection.execute(
                "INSERT OR IGNORE INTO provenance(publication_id,source,source_record_id,raw_json,discovered_at) VALUES(?,?,?,?,?)",
                (publication_id, candidate.source, candidate.source_record_id, json_dumps(candidate.raw), now),
            )
        return publication_id

    def publications_between(self, start: str, end: str, verified_only: bool = False) -> list[sqlite3.Row]:
        verification = "AND p.verification_status='verified'" if verified_only else ""
        return self.connection.execute(
            f"""SELECT p.*,
                GROUP_CONCAT(DISTINCT m.name) AS matched_members,
                GROUP_CONCAT(DISTINCT pr.source) AS sources
                FROM publications p
                LEFT JOIN publication_members pm ON pm.publication_id=p.id
                LEFT JOIN members m ON m.id=pm.member_id
                LEFT JOIN provenance pr ON pr.publication_id=p.id
                WHERE p.publication_date BETWEEN ? AND ? {verification}
                GROUP BY p.id ORDER BY p.publication_date, p.title""",
            (start, end),
        ).fetchall()

    def authors_for(self, publication_id: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM publication_authors WHERE publication_id=? ORDER BY position", (publication_id,)
        ).fetchall()

    def set_status(self, publication_id: int, status: str, notes: str | None = None) -> None:
        valid = {"unreviewed", "candidate", "auto-matched", "verified", "rejected"}
        if status not in valid:
            raise ValueError(f"Status must be one of: {', '.join(sorted(valid))}")
        with self.connection:
            self.connection.execute(
                "UPDATE publications SET verification_status=?, review_notes=COALESCE(?,review_notes) WHERE id=?",
                (status, notes, publication_id),
            )
