# Publication Gathering System

A reusable Python application for discovering, reconciling, verifying, storing, and exporting publications associated with an individual or group of authors.  Think of it as "*How can I create a bibliography for everything my lab members authored this year?*"

The produced SQLite database is the master institutional record. Annual bibliographies are filtered exports rather than one-time collections.

## Current capabilities

- OpenAlex discovery by author
- Crossref discovery by author and reporting period
- Semantic Scholar discovery by author
- ORCID work retrieval for members with ORCID IDs and API credentials
- "Google Scholar" or "Publish or Perish" import from BibTeX or CSV
- DOI-first deduplication, followed by fuzzy title/year matching
- Laboratory-member matching using names, aliases, ORCID, and affiliation
- SQLite storage of publications, authors, member links, provenance, and review status
- CSV, BibTeX, Markdown, and manual-review exports
- Disk caching of API responses

## Important limitation

Google Scholar does not provide a supported general-purpose publications API. This application therefore imports Scholar results rather than scraping Scholar. Export selected profile entries as BibTeX, or export results from Publish or Perish as BibTeX/CSV, then pass the file to `update --import`.

## Installation

Python 3.11 or newer is recommended.

```bash
git clone https://github.com/csalvaggio/gather_publications.git
cd gather_publications
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Edit:

- `config/config.yaml`
- `config/members.yaml`

Replace `user@abc.edu` with a real contact address before using Crossref. Add API credentials where available.

## Initialize the database

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  init-db
```

## Discover publications

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  update
```

Select sources explicitly:

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  update \
  --sources crossref,semantic_scholar
```

Override the configured reporting period:

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  update \
  --start 2025-07-01 \
  --end 2026-06-30
```

## Import "Google Scholar" or "Publish or Perish" results

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  update \
  --sources crossref,openalex \
  --import imports/author1.bib \
  --import imports/author2.csv
```

## Generate annual outputs

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  export \
  --name publications_2025_2026
```

Only include manually verified records:

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  export \
  --verified-only \
  --name publications_2025_2026_verified
```

Outputs are written to `output/` by default:

- `publications_2025_2026.csv`
- `publications_2025_2026.bib`
- `publications_2025_2026.md`
- `publications_2025_2026_review.md`

## Verify or reject a record

The CSV and review report contain the database publication ID.

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  review 42 verified \
  --notes "Verified against publisher landing page on 2026-07-27"
```

```bash
gather-publications \
  --config config/config.yaml \
  --members config/members.yaml \
  review 57 rejected \
  --notes "Different researcher with the same name"
```

## Database model

The SQLite file stores:

- `members`: canonical laboratory roster and identifiers
- `publications`: reconciled publication metadata and verification state
- `publication_authors`: ordered authorship
- `publication_members`: matched laboratory members and confidence
- `provenance`: every source record retained as JSON

The original source data are deliberately retained so ambiguous merges can be audited later.

## Suggested workflow

1. Maintain the laboratory roster and stable author identifiers
2. Run all enabled discovery sources
3. Import "Google Scholar" or "Publish or Perish" exports
4. Examine the CSV and review report
5. Verify or reject ambiguous records
6. Check official publisher pages for final publication dates
7. Export the verified annual bibliography

## Date caution

Discovery services do not always agree on publication dates. This version preserves online, print, and selected publication dates when supplied, but the final inclusion decision should be verified against the publisher when dates conflict or only a year is known.

## Example

To create a clean, brand-new report:

```bash
rm -fr output
rm -fr data
rm -fr cache
gather-publications --config config/config.yaml --members config/members.yaml init-db
gather-publications --config config/config.yaml --members config/members.yaml update
gather-publications --config config/config.yaml --members config/members.yaml export --name publications_2025_2026
cat output/publications_2025_2026.bib 
```

## License

This project is licensed under the GNU General Public License v3.0.
See `LICENSE` for details.

## Contact

### Author

Carl Salvaggio, Ph.D.  
Professor of Imaging Science  
Director, Digital Imaging and Remote Sensing (DIRS) Laboratory

### E-mail

carl.salvaggio@rit.edu

### Organization

Chester F. Carlson Center for Imaging Science  
Rochester Institute of Technology  
Rochester, New York, 14623  
United States
