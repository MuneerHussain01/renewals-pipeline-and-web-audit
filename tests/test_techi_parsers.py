"""
Tests for techi_audit.py helper functions:
relative date parsing, absolute date parsing, slug extraction,
robots.txt parsing, and URL filtering.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from techi_audit import (
    parse_relative_date,
    parse_date_text,
    extract_slug,
    parse_robots_txt,
    filter_article_urls,
)

REF_DATE = datetime(2026, 8, 3, 12, 0, 0)


class TestTechiDateParsing:

    def test_relative_days_ago(self):
        dt = parse_relative_date("Updated 6 days ago", reference=REF_DATE)
        assert dt is not None
        assert dt.strftime("%Y-%m-%d") == "2026-07-28"

    def test_relative_hours_ago(self):
        dt = parse_relative_date("3 hours ago", reference=REF_DATE)
        assert dt is not None
        assert dt.strftime("%Y-%m-%d") == "2026-08-03"

    def test_relative_weeks_ago(self):
        dt = parse_relative_date("2 weeks ago", reference=REF_DATE)
        assert dt is not None
        assert dt.strftime("%Y-%m-%d") == "2026-07-20"

    def test_relative_months_ago(self):
        dt = parse_relative_date("1 month ago", reference=REF_DATE)
        assert dt is not None
        # approx 30 days
        assert dt.strftime("%Y-%m-%d") == "2026-07-04"

    def test_parse_date_text_relative(self):
        raw, iso = parse_date_text("Updated 6 days ago")
        assert raw == "Updated 6 days ago"
        assert iso == "2026-07-28"

    def test_parse_date_text_absolute_full(self):
        raw, iso = parse_date_text("January 15, 2025")
        assert raw == "January 15, 2025"
        assert iso == "2025-01-15"

    def test_parse_date_text_with_prefix(self):
        raw, iso = parse_date_text("Published on March 10, 2026")
        assert iso == "2026-03-10"

    def test_parse_date_text_iso(self):
        raw, iso = parse_date_text("2026-05-18")
        assert iso == "2026-05-18"

    def test_parse_date_text_blank(self):
        raw, iso = parse_date_text("")
        assert raw == ""
        assert iso == ""

    def test_parse_date_text_invalid(self):
        raw, iso = parse_date_text("some random non-date text")
        assert raw == "some random non-date text"
        assert iso == ""


class TestTechiUrlHelpers:

    def test_extract_slug(self):
        url = "https://www.techi.com/news/apple-m4-chip-announcement"
        assert extract_slug(url) == "apple-m4-chip-announcement"

    def test_extract_slug_trailing_slash(self):
        url = "https://www.techi.com/reviews/google-pixel-9-pro/"
        assert extract_slug(url) == "google-pixel-9-pro"

    def test_filter_article_urls(self):
        urls = [
            "https://www.techi.com/",
            "https://www.techi.com/category/hardware",
            "https://www.techi.com/tag/ai",
            "https://www.techi.com/privacy-policy",
            "https://www.techi.com/samsung-galaxy-s25-ultra-review",
            "https://www.techi.com/author/john-doe",
            "https://www.techi.com/open-ai-releases-gpt-5-model",
        ]
        filtered = filter_article_urls(urls)
        assert len(filtered) == 2
        assert "https://www.techi.com/samsung-galaxy-s25-ultra-review" in filtered
        assert "https://www.techi.com/open-ai-releases-gpt-5-model" in filtered


class TestRobotsParser:

    def test_parse_robots_sitemaps(self):
        robots_text = """
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php

Sitemap: https://www.techi.com/sitemap_index.xml
Sitemap: https://www.techi.com/news-sitemap.xml
Crawl-delay: 2
"""
        sitemaps, crawl_delay = parse_robots_txt(robots_text)
        assert len(sitemaps) == 2
        assert sitemaps[0] == "https://www.techi.com/sitemap_index.xml"
        assert sitemaps[1] == "https://www.techi.com/news-sitemap.xml"
        assert crawl_delay == 2.0
