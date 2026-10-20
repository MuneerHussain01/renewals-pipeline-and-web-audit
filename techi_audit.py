#!/usr/bin/env python3
"""
techi_audit.py - TECHi.com article metadata collector.

Discovers article URLs from the site's robots.txt/sitemaps and
collects metadata for up to 20 published articles.

Usage: python techi_audit.py
"""

import csv
import hashlib
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install requests beautifulsoup4")
    sys.exit(1)


# -- configuration --

BASE_URL = "https://www.techi.com"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
MAX_ARTICLES = 20
REQUEST_DELAY = 1.0  # seconds between requests
REQUEST_TIMEOUT = 15  # seconds
CACHE_DIR = ".cache"
OUTPUT_FILE = "techi_articles.csv"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# reference date for relative date calculations
REFERENCE_DATE = datetime(2026, 8, 3)


# -- disk cache --

def get_cache_path(url):
    """Return a filesystem path for caching a URL response."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(CACHE_DIR, url_hash)


def read_cache(url):
    """Read cached response for a URL. Returns None if not cached."""
    path = get_cache_path(url)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def write_cache(url, content):
    """Write response content to disk cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = get_cache_path(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# -- http fetching --

def fetch_url(url, session):
    """
    Fetch a URL with caching, rate limiting, and error handling.
    Returns the response text or None on failure.
    """
    # check cache first
    cached = read_cache(url)
    if cached is not None:
        print(f"  [cache hit] {url}")
        return cached

    # rate limit
    time.sleep(REQUEST_DELAY)

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            print(f"  [404] {url}")
            return None
        resp.raise_for_status()
        content = resp.text
        write_cache(url, content)
        print(f"  [fetched] {url}")
        return content
    except requests.exceptions.Timeout:
        print(f"  [timeout] {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"  [connection error] {url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"  [http error] {url}: {e}")
        return None
    except Exception as e:
        print(f"  [error] {url}: {e}")
        return None


# -- robots.txt parsing --

def parse_robots_txt(content):
    """
    Extract sitemap URLs from robots.txt content.
    Also checks the crawl delay if specified.
    """
    sitemaps = []
    crawl_delay = None

    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            # handle the case where "Sitemap:" was split at the colon in the URL
            if not sitemap_url.startswith("http"):
                # reassemble -- the split removed the http: part
                parts = line.split(None, 1)
                if len(parts) > 1:
                    sitemap_url = parts[1].strip()
            sitemaps.append(sitemap_url)
        elif line.lower().startswith("crawl-delay:"):
            try:
                crawl_delay = float(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass

    return sitemaps, crawl_delay


def check_robots_allowed(robots_content, url):
    """Check if our user agent is allowed to access the URL."""
    rp = RobotFileParser()
    rp.parse(robots_content.splitlines())
    return rp.can_fetch(USER_AGENT, url)


# -- sitemap parsing --

def extract_urls_from_sitemap(content, session):
    """
    Parse a sitemap XML and extract URLs.
    Handles both sitemap indexes and regular sitemaps.
    Returns a list of article URLs.
    """
    urls = []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        print("  [warning] Could not parse sitemap XML")
        return urls

    # strip namespace for easier parsing
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # check if this is a sitemap index
    sitemap_tags = root.findall(f"{ns}sitemap")
    if sitemap_tags:
        print(f"  Found sitemap index with {len(sitemap_tags)} sitemaps")
        for sitemap in sitemap_tags:
            loc = sitemap.find(f"{ns}loc")
            if loc is not None and loc.text:
                sub_content = fetch_url(loc.text.strip(), session)
                if sub_content:
                    urls.extend(extract_urls_from_sitemap(sub_content, session))
                    if len(urls) >= MAX_ARTICLES * 3:
                        # collect enough candidates, stop early
                        break
        return urls

    # regular sitemap -- extract URLs
    for url_tag in root.findall(f"{ns}url"):
        loc = url_tag.find(f"{ns}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    return urls


def filter_article_urls(urls):
    """
    Filter URLs to keep only those that look like articles.
    Excludes category pages, tag pages, author pages, etc.
    """
    article_urls = []
    skip_patterns = [
        "/category/", "/tag/", "/author/", "/page/",
        "/wp-content/", "/wp-admin/", "/feed/",
        "/privacy-policy", "/terms", "/about", "/contact",
    ]

    for url in urls:
        path = urlparse(url).path.lower()

        # skip non-article pages
        if any(pattern in path for pattern in skip_patterns):
            continue

        # skip the homepage
        if path in ("", "/"):
            continue

        # articles usually have a slug with dashes
        slug = path.strip("/").split("/")[-1]
        if slug and "-" in slug and len(slug) > 5:
            article_urls.append(url)

    return article_urls


# -- article metadata extraction --

def extract_slug(url):
    """Extract the URL slug from an article URL."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    return parts[-1] if parts else ""


def extract_category(url, soup):
    """Try to extract the article category from page markup or URL."""
    # Look for category link in article header (e.g. /category/crypto-defi/)
    cat_link = soup.find("a", href=lambda h: h and "/category/" in h)
    if cat_link:
        text = cat_link.get_text(strip=True)
        if text:
            return text

    # try breadcrumbs first
    breadcrumb = soup.find("nav", class_=re.compile(r"breadcrumb", re.I))
    if breadcrumb:
        links = breadcrumb.find_all("a")
        # usually the second-to-last breadcrumb link is the category
        if len(links) >= 2:
            return links[-2].get_text(strip=True)

    # try meta tags
    for meta in soup.find_all("meta", {"property": "article:section"}):
        if meta.get("content"):
            return meta["content"]

    # try from URL path -- first segment after domain
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0].replace("-", " ").title()

    return ""


def extract_author(soup):
    """Extract author handle or name from the article page."""
    # try author profile link (e.g. href="/@qaiser/")
    author_link = soup.find("a", href=lambda h: h and "/@" in h)
    if author_link:
        href = author_link.get("href", "")
        m = re.search(r"/@([^/]+)", href)
        if m:
            return f"@{m.group(1)}"
        text = author_link.get_text(strip=True)
        if text:
            return text

    # try common author markup patterns
    for selector in [
        {"class": re.compile(r"author", re.I)},
        {"rel": "author"},
    ]:
        tag = soup.find("a", selector)
        if tag:
            text = tag.get_text(strip=True)
            if text:
                return text

    # try meta tag
    for meta in soup.find_all("meta", {"name": "author"}):
        if meta.get("content"):
            return meta["content"]

    # try schema.org markup
    author_div = soup.find(attrs={"itemprop": "author"})
    if author_div:
        name = author_div.find(attrs={"itemprop": "name"})
        if name:
            return name.get_text(strip=True)
        return author_div.get_text(strip=True)

    return ""


def parse_relative_date(text, reference=None):
    """
    Parse relative date strings like "Updated 6 days ago" or "3 hours ago".
    Returns a datetime or None.
    """
    if reference is None:
        reference = REFERENCE_DATE

    text = text.lower().strip()

    # patterns: "X days/hours/minutes/weeks/months ago"
    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "second":
        delta = timedelta(seconds=amount)
    elif unit == "minute":
        delta = timedelta(minutes=amount)
    elif unit == "hour":
        delta = timedelta(hours=amount)
    elif unit == "day":
        delta = timedelta(days=amount)
    elif unit == "week":
        delta = timedelta(weeks=amount)
    elif unit == "month":
        delta = timedelta(days=amount * 30)  # approximate
    elif unit == "year":
        delta = timedelta(days=amount * 365)
    else:
        return None

    return reference - delta


def parse_date_text(text):
    """
    Parse a date string that could be absolute, ISO, or relative.
    Returns (date_text, date_iso) tuple.
    """
    if not text:
        return "", ""

    clean = text.strip()
    clean = clean.replace("\ufffd", " ").replace("\xa0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()

    # strip common prefixes
    for prefix in ["Updated", "Published", "Posted", "Modified"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix):].strip()

    # strip leading "on " or "- "
    clean = re.sub(r'^(on|at|-)\s+', '', clean, flags=re.IGNORECASE).strip()

    # match human date with optional time suffix like "October 16, 2026 5:26 PM EDT"
    m_full = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", clean)
    if m_full:
        date_str = m_full.group(1)
        try:
            dt = datetime.strptime(date_str, "%B %d, %Y")
            return text.strip(), dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # try ISO format (e.g. 2026-10-16T21:26:07.689Z or 2026-10-16)
    m_iso = re.match(r"^(\d{4}-\d{2}-\d{2})", clean)
    if m_iso:
        return text.strip(), m_iso.group(1)

    # try relative date first
    rel = parse_relative_date(clean)
    if rel:
        return text.strip(), rel.strftime("%Y-%m-%d")

    # try absolute date formats
    for fmt in (
        "%B %d, %Y",       # January 15, 2025
        "%b %d, %Y",       # Jan 15, 2025
        "%d %B %Y",        # 15 January 2025
        "%d %b %Y",        # 15 Jan 2025
        "%Y-%m-%d",        # 2025-01-15
        "%m/%d/%Y",        # 01/15/2025
        "%d/%m/%Y",        # 15/01/2025
        "%B %d",           # January 15 (assume current year)
        "%b %d",           # Jan 15
    ):
        try:
            dt = datetime.strptime(clean, fmt)
            if dt.year == 1900:  # no year in format
                dt = dt.replace(year=REFERENCE_DATE.year)
            return text.strip(), dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # if nothing worked, return text as-is with no ISO date
    return text.strip(), ""


def extract_date(soup):
    """Extract publication date from the article page."""
    # try time tag first (most semantic)
    time_tag = soup.find("time")
    if time_tag:
        dt_attr = time_tag.get("datetime", "")
        text_content = time_tag.get_text(strip=True)
        text_content = text_content.replace("\ufffd", " ").replace("\xa0", " ")
        text_content = re.sub(r"\s+", " ", text_content).strip()

        # prefer the human visible text for date_text, and datetime for ISO
        if dt_attr:
            _, iso_from_attr = parse_date_text(dt_attr)
            if iso_from_attr:
                display_text = text_content if text_content else dt_attr
                return display_text, iso_from_attr
        return parse_date_text(text_content)

    # try meta tags
    for prop in ["article:published_time", "datePublished", "date"]:
        meta = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
        if meta and meta.get("content"):
            return parse_date_text(meta["content"])

    # try common class names
    for cls in ["date", "post-date", "entry-date", "published", "pub-date"]:
        tag = soup.find(class_=re.compile(cls, re.I))
        if tag:
            return parse_date_text(tag.get_text())

    # try schema.org
    date_tag = soup.find(attrs={"itemprop": "datePublished"})
    if date_tag:
        content = date_tag.get("content") or date_tag.get_text()
        return parse_date_text(content)

    return "", ""


def extract_title(soup):
    """Extract the article title."""
    # try og:title first
    og = soup.find("meta", {"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()

    # try h1
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    # try title tag
    title = soup.find("title")
    if title:
        text = title.get_text(strip=True)
        # remove site name suffix like " - TECHi" or " | TECHi"
        text = re.split(r'\s*[-|]\s*TECHi', text, flags=re.IGNORECASE)[0]
        return text.strip()

    return ""


def extract_article_metadata(url, html):
    """Extract all metadata from an article page."""
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title(soup)
    slug = extract_slug(url)
    category = extract_category(url, soup)
    author = extract_author(soup)
    date_text, date_iso = extract_date(soup)

    return {
        "url": url,
        "slug": slug,
        "title": title,
        "category": category,
        "author_handle": author,
        "date_text": date_text,
        "date_iso": date_iso,
    }


# -- main --

def main():
    global REQUEST_DELAY
    print("TECHi.com Article Metadata Audit")
    print("=" * 50)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # step 1: fetch and parse robots.txt
    print("\nStep 1: Fetching robots.txt...")
    robots_content = fetch_url(ROBOTS_URL, session)
    if not robots_content:
        print("Could not fetch robots.txt. Exiting.")
        sys.exit(1)

    sitemaps, crawl_delay = parse_robots_txt(robots_content)
    print(f"  Found {len(sitemaps)} sitemap(s)")

    if crawl_delay and crawl_delay > REQUEST_DELAY:
        print(f"  Respecting Crawl-delay: {crawl_delay}s")
        REQUEST_DELAY = crawl_delay

    # step 2: collect article URLs from sitemaps
    print("\nStep 2: Parsing sitemaps for article URLs...")
    all_urls = []
    for sitemap_url in sitemaps:
        content = fetch_url(sitemap_url, session)
        if content:
            urls = extract_urls_from_sitemap(content, session)
            all_urls.extend(urls)

    if not all_urls:
        # fallback: try common sitemap paths
        print("  No URLs from declared sitemaps, trying fallback paths...")
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/post-sitemap.xml"]:
            fallback_url = BASE_URL + path
            content = fetch_url(fallback_url, session)
            if content:
                urls = extract_urls_from_sitemap(content, session)
                all_urls.extend(urls)
                if all_urls:
                    break

    print(f"  Total URLs collected: {len(all_urls)}")

    # step 3: filter to article URLs
    article_urls = filter_article_urls(all_urls)
    print(f"  Article URLs after filtering: {len(article_urls)}")

    # limit to MAX_ARTICLES
    article_urls = article_urls[:MAX_ARTICLES]
    print(f"  Processing up to {len(article_urls)} articles")

    # step 4: check robots.txt compliance
    robots_lines = robots_content.splitlines() if robots_content else []

    # step 5: fetch and extract metadata for each article
    print("\nStep 3: Extracting article metadata...")
    articles = []
    for i, url in enumerate(article_urls):
        print(f"\n  [{i+1}/{len(article_urls)}] {url}")

        # check if allowed by robots.txt
        if not check_robots_allowed(robots_content, url):
            print(f"    Skipped (blocked by robots.txt)")
            continue

        html = fetch_url(url, session)
        if not html:
            print(f"    Failed to fetch, skipping")
            continue

        try:
            metadata = extract_article_metadata(url, html)
            articles.append(metadata)
            print(f"    Title: {metadata['title'][:60]}...")
            print(f"    Category: {metadata['category']}")
            print(f"    Author: {metadata['author_handle']}")
            print(f"    Date: {metadata['date_text']} -> {metadata['date_iso']}")
        except Exception as e:
            print(f"    Error extracting metadata: {e}")

    # step 6: write output CSV
    print(f"\nStep 4: Writing {OUTPUT_FILE}...")
    fieldnames = ["url", "slug", "title", "category", "author_handle", "date_text", "date_iso"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)

    # summary
    print("\n" + "=" * 50)
    print(f"Articles collected: {len(articles)}")
    print(f"Output written to: {OUTPUT_FILE}")
    if articles:
        categories = set(a["category"] for a in articles if a["category"])
        authors = set(a["author_handle"] for a in articles if a["author_handle"])
        dated = sum(1 for a in articles if a["date_iso"])
        print(f"Categories found: {len(categories)}")
        print(f"Authors found: {len(authors)}")
        print(f"Articles with parsed dates: {dated}/{len(articles)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
