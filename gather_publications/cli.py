from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


from .config import load_members, load_reporting_period, load_settings
from .database import Database
from .models import ReportingPeriod
from .pipeline import discover
from .reports import export_bibtex, export_csv, export_markdown, export_review_report
from .utils import ensure_directory, parse_date



def period_from_args(args, config_path: Path) -> ReportingPeriod:
    if args.start or args.end:
        start = parse_date(args.start)
        end = parse_date(args.end)
        if not start or not end:
            raise SystemExit("Both --start and --end must be valid YYYY-MM-DD dates")
        return ReportingPeriod(start, end)
    return load_reporting_period(config_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain the DIRS publication database.")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument("--members", type=Path, default=Path("config/members.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update", help="Discover and store publications")
    update.add_argument("--start")
    update.add_argument("--end")
    update.add_argument("--sources", default="openalex,crossref,semantic_scholar,orcid")
    update.add_argument("--import", dest="imports", action="append", type=Path, default=[])

    export = sub.add_parser("export", help="Generate annual bibliography outputs")
    export.add_argument("--start")
    export.add_argument("--end")
    export.add_argument("--verified-only", action="store_true")
    export.add_argument("--name", help="Output filename prefix, e.g. DIRS_2025_2026")

    review = sub.add_parser("review", help="Set a publication verification status")
    review.add_argument("publication_id", type=int)
    review.add_argument("status", choices=["unreviewed", "candidate", "auto-matched", "verified", "rejected"])
    review.add_argument("--notes")

    sub.add_parser("init-db", help="Create the database and load the member roster")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = load_settings(args.config)
    members = load_members(args.members)
    db = Database(settings.database)
    try:
        if args.command == "init-db":
            db.sync_members(members)
            print(f"Database initialized: {settings.database}")
        elif args.command == "update":
            period = period_from_args(args, args.config)
            sources = {x.strip() for x in args.sources.split(",") if x.strip()}
            discovered, stored = discover(db, members, period, settings, sources, args.imports)
            print(f"Discovered {discovered} source records; stored/updated {stored} unique records.")
        elif args.command == "export":
            period = period_from_args(args, args.config)
            output = ensure_directory(settings.output_dir)
            prefix = args.name or f"DIRS_{period.start.year}_{period.end.year}"
            export_csv(db, period, output / f"{prefix}.csv", args.verified_only)
            export_bibtex(db, period, output / f"{prefix}.bib", args.verified_only)
            export_markdown(db, period, output / f"{prefix}.md", args.verified_only)
            export_review_report(db, period, output / f"{prefix}_review.md")
            print(f"Exports written to: {output}")
        elif args.command == "review":
            db.set_status(args.publication_id, args.status, args.notes)
            print(f"Publication {args.publication_id} set to {args.status}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
