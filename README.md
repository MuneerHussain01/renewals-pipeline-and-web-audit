# Subscription Renewals Pipeline & Polite Web Audit Tool

A data engineering pipeline and polite web crawler built with Python 3.10+.

The project consists of two core components:
1. **Part A: Renewals Cleanup Pipeline (`clean.py`)** - Normalizes messy renewal exports from three billing systems, resolves ambiguous dates, standardizes monetary values and domains, deduplicates records, generates an issue audit trail, and computes renewal forecasts.
2. **Part B: Polite Web Metadata Scraper (`techi_audit.py`)** - Respectful metadata collector for articles discovered via `robots.txt` and XML sitemaps, complete with rate limiting, real user agent, disk caching, and error resilience.

---

## Repository Structure

```
renewals-pipeline-and-web-audit/
│
├── clean.py               # Part A: Main renewal data cleaning pipeline
├── renewals_raw.csv       # Part A: Raw source data (34 records, multi-system export)
├── clean.csv              # Part A: Cleaned, normalized dataset
├── issues.csv             # Part A: Complete audit log of every modified/dropped row
│
├── techi_audit.py         # Part B: Polite TECHi.com article metadata scraper
├── techi_articles.csv     # Part B: Scraped article metadata (20 articles)
│
├── tests/                 # Offline test suite (85 tests)
│   ├── __init__.py
│   ├── test_parsers.py         # Tests for date, money, domain, cycle parsers
│   └── test_techi_parsers.py   # Tests for slug, relative date, robots parsers
│
├── NOTES.md               # Detailed renewal analysis, cash flow totals, and rules
└── README.md              # Setup, architectural decisions, tradeoffs, improvements
```

---

## Quickstart & Setup

### Requirements
- Python 3.10+ (tested on Python 3.11)
- Free libraries: `requests`, `beautifulsoup4`, `pytest`

### Installation

```bash
# Clone or extract the project directory
cd renewals-pipeline-and-web-audit

# Install dependencies
pip install requests beautifulsoup4 pytest
```

### Running the Data Cleaning Pipeline (Part A)

```bash
python clean.py renewals_raw.csv
```

Outputs:
- Displays summary statistics to `stdout` (rows in, rows kept, dropped, flagged, status breakdown, window totals).
- Writes `clean.csv` (standardized schema).
- Writes `issues.csv` (detailed audit trail of all anomalies and actions taken).

### Running the TECHi Scraper (Part B)

```bash
python techi_audit.py
```

Outputs:
- Fetches `https://www.techi.com/robots.txt`, identifies sitemaps, and extracts article URLs.
- Gathers up to 20 articles respecting rate limits (1 req/sec).
- Saves responses to `.cache/` directory to prevent repeat requests on subsequent runs.
- Generates `techi_articles.csv`.

### Running Tests

```bash
pytest -v
# or: python -m pytest tests -v
```

85 passing unit tests covering edge cases, malformed data, and parser boundaries.

---

## Architectural Decisions & Data Cleaning (Part A)

### 1. Schema Normalization
`clean.csv` strictly implements the target schema:
- `record_id`: Preserved primary key from source.
- `customer_id`: Standard customer code or blank if missing.
- `canonical_domain`: Lowercase, protocol stripped, `www.` removed, spaces/dots trimmed.
- `service`: Categorized into standard services (`Shared Hosting`, `VPS`, `SSL Certificate`, `.pk Domain`).
- `billing_cycle_months`: Integer representation of period (`1`, `3`, `6`, `12`, `24`, `36`).
- `amount_pkr`: Float value in PKR.
- `registered_on`: ISO date (`YYYY-MM-DD`) or empty if invalid.
- `renews_on`: ISO date (`YYYY-MM-DD`).
- `status`: Fixed enum set (`active`, `cancelled`, `suspended`, `expired`, `pending`).
- `contact_email`: Sanitized and lowercased email string.

### 2. Money Parser Logic
- Handled currency prefixes: `Rs`, `Rs.`, `PKR`, `$`.
- Handled thousands separators: `8,750` -> `8750.0`.
- Parenthesized negatives / refunds: `(2,500)` -> `-2500.0`.
- Foreign currency conversion: The USD record (`$29.99`) is converted to PKR using a baseline rate of 278.0 PKR/USD, flagged in `issues.csv`.
- Blank amounts are preserved as empty values and flagged for billing review rather than defaulting to zero.

### 3. Ambiguous Date Resolution
Dates in the raw dataset come in mixed formats (`DD/MM/YYYY` and `MM/DD/YYYY`).
- For values where day > 12 (e.g. `15/03/2023` or `03/15/2024`), the format is mathematically unambiguous.
- For ambiguous dates where day and month are both <= 12 (e.g. `05/06/2025`): We adopt `DD/MM/YYYY` priority because PKHosting is a Pakistani entity whose local legal and accounting standard is Day/Month/Year.
- Fallback to `MM/DD/YYYY` occurs if `DD/MM/YYYY` produces an invalid day for the month.
- Impossible dates (e.g., `30/02/2024` or month `13`) are caught, replaced with empty strings, and documented in `issues.csv`.

### 4. Deduplication
- Matching criteria: `(customer_id, canonical_domain, service)`.
- Tie-breaking: Retains the row with the latest renewal date. If renewal dates tie and amounts differ (as in Record 1010 at Rs 2,500 vs Record 1026 at Rs 2,800), the higher amount is retained under the assumption that it represents the updated tariff.
- Full auditability: The dropped record is recorded in `issues.csv` specifying the reason and the retained record ID.

---

## Scraper Behaviour & Polite Crawling (Part B)

`techi_audit.py` follows strict scraping etiquette:
1. **Robots.txt Adherence**: Downloads and reads `https://www.techi.com/robots.txt` before fetching any articles. Parses declared sitemaps and checks crawl permissions using Python's `urllib.robotparser`.
2. **Crawl-Delay & Rate Limiting**: Enforces a minimum 1.0 second pause between outbound requests. If `robots.txt` declares a higher `Crawl-delay`, the script automatically respects the server's requested delay.
3. **Realistic User-Agent**: Uses a standard modern desktop browser header to avoid generic bot blocks.
4. **Local Disk Cache**: Responses are cached by MD5 hash inside `.cache/`. Running the script a second time executes instantly from disk without issuing duplicate network requests to the live server.
5. **Robust Parsing**:
   - Discovers article URLs dynamically from XML sitemap indexes (`/sitemap_index.xml` -> `/post-sitemap1.xml`).
   - Extracts titles, slugs, categories (from breadcrumbs or header category links), author handles (`@handle`), and publish dates.
   - Converts both ISO timestamps and relative dates ("Updated 6 days ago") into canonical ISO dates (`YYYY-MM-DD`).
   - Gracefully handles 404s, timeouts, and markup variations without crashing.

---

## Test Suite Overview

Located in `tests/`, executable offline with `pytest`:
- `test_parsers.py` (71 tests):
  - Amount parsing (currencies, commas, negatives, USD conversion, invalid formats).
  - Domain normalization (www stripping, uppercase, trailing characters, whitespace).
  - Date parsing (DD/MM priority, MM/DD fallback, ISO, text months, leap years, impossible dates).
  - Status and email normalization.
  - Billing cycle integer conversion.
- `test_techi_parsers.py` (14 tests):
  - Relative date calculations ("6 days ago", "3 hours ago", "2 weeks ago").
  - Date text sanitization and ISO formatting.
  - Slug extraction from URLs.
  - URL filtering against navigation and tag pages.
  - `robots.txt` directive extraction.

Total: **85 passing tests**.

---

## Tradeoffs & Future Improvements

1. **Exchange Rates**: Currently, the USD to PKR exchange rate is configured as a static constant (278.0 PKR/USD). In a production environment, this should query an internal treasury rate service or daily bank feed.
2. **Database Storage**: The current implementation operates directly on CSV files. For high-volume production operations, data staging should occur in a relational database (PostgreSQL/SQLite) with transactional constraints.
3. **Scraper Concurrency**: While the current script runs synchronously with polite delays, a larger crawl could utilize an async queue with domain-level rate limiters to crawl multiple partner properties simultaneously without violating polite scraping policies.
