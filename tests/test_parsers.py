"""
Tests for date, money, and domain parsers used in clean.py.
All tests are offline -- no network or file I/O needed.
"""

import sys
import os
from datetime import date

# add parent directory so we can import from clean.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clean import (
    parse_amount,
    normalize_domain,
    parse_date,
    normalize_status,
    normalize_email,
    guess_billing_cycle_months,
    normalize_service,
    is_impossible_date,
)


# -- amount parsing tests --

class TestParseAmount:

    def test_simple_pkr_with_rs(self):
        amount, currency, converted = parse_amount("Rs 4500")
        assert amount == 4500.0
        assert converted is False

    def test_pkr_with_thousands_separator(self):
        amount, currency, converted = parse_amount("PKR 8,750")
        assert amount == 8750.0

    def test_pkr_with_rs_dot(self):
        amount, currency, converted = parse_amount("Rs. 2,500")
        assert amount == 2500.0

    def test_pkr_no_prefix(self):
        amount, currency, converted = parse_amount("PKR 1500")
        assert amount == 1500.0

    def test_usd_amount(self):
        amount, currency, converted = parse_amount("$29.99")
        assert currency == "USD"
        assert converted is True
        assert amount > 0  # should be converted to PKR

    def test_negative_parentheses(self):
        amount, currency, converted = parse_amount("(2,500)")
        assert amount == -2500.0

    def test_negative_sign(self):
        amount, currency, converted = parse_amount("-Rs 1000")
        assert amount == -1000.0

    def test_blank_string(self):
        amount, currency, converted = parse_amount("")
        assert amount is None

    def test_none_input(self):
        amount, currency, converted = parse_amount(None)
        assert amount is None

    def test_whitespace_only(self):
        amount, currency, converted = parse_amount("   ")
        assert amount is None

    def test_large_amount_with_commas(self):
        amount, currency, converted = parse_amount("Rs 95,000")
        assert amount == 95000.0

    def test_amount_with_decimal(self):
        amount, currency, converted = parse_amount("Rs 4500.50")
        assert amount == 4500.50

    def test_pkr_prefix_no_space(self):
        amount, currency, converted = parse_amount("PKR1500")
        assert amount == 1500.0

    def test_garbage_string(self):
        amount, currency, converted = parse_amount("abc xyz")
        assert amount is None


# -- domain normalization tests --

class TestNormalizeDomain:

    def test_www_prefix_removal(self):
        assert normalize_domain("www.karachifoods.pk") == "karachifoods.pk"

    def test_uppercase(self):
        assert normalize_domain("LahoreTextiles.com") == "lahoretextiles.com"

    def test_trailing_dot(self):
        assert normalize_domain("multansweets.com.") == "multansweets.com"

    def test_trailing_space(self):
        assert normalize_domain("FaisalabadWeaves.pk ") == "faisalabadweaves.pk"

    def test_leading_space(self):
        assert normalize_domain(" abbottabadresorts.com") == "abbottabadresorts.com"

    def test_all_caps_www(self):
        assert normalize_domain("WWW.BAHAWALPUR-DARBAR.PK") == "bahawalpur-darbar.pk"

    def test_http_prefix(self):
        assert normalize_domain("http://example.pk") == "example.pk"

    def test_https_www(self):
        assert normalize_domain("https://www.example.pk") == "example.pk"

    def test_blank(self):
        assert normalize_domain("") is None

    def test_none(self):
        assert normalize_domain(None) is None

    def test_trailing_slash(self):
        assert normalize_domain("example.pk/") == "example.pk"

    def test_spaces_inside(self):
        assert normalize_domain("exam ple.pk") == "example.pk"

    def test_all_uppercase_pk(self):
        assert normalize_domain("PeshawarCrafts.PK") == "peshawarcrafts.pk"


# -- date parsing tests --

class TestParseDate:

    def test_dd_mm_yyyy(self):
        d, fmt = parse_date("15/03/2023")
        assert d == date(2023, 3, 15)

    def test_mm_dd_yyyy_forced(self):
        # day > 12 forces MM/DD interpretation to fail for DD/MM,
        # so this should fall through to MM/DD
        d, fmt = parse_date("03/15/2024")
        assert d == date(2024, 3, 15)
        assert fmt == "mdy"

    def test_iso_format(self):
        d, fmt = parse_date("2025-06-22")
        assert d == date(2025, 6, 22)

    def test_impossible_feb_30(self):
        # 30/02/2024 should fail to parse (Feb 30 does not exist)
        d, fmt = parse_date("30/02/2024")
        assert d is None

    def test_month_13(self):
        # 13/25/2024 -- neither DD/MM nor MM/DD works
        d, fmt = parse_date("13/25/2024")
        assert d is None

    def test_written_month(self):
        d, fmt = parse_date("January 15, 2025")
        assert d == date(2025, 1, 15)

    def test_written_month_abbrev(self):
        d, fmt = parse_date("Jan 15, 2025")
        assert d == date(2025, 1, 15)

    def test_blank(self):
        d, fmt = parse_date("")
        assert d is None

    def test_none(self):
        d, fmt = parse_date(None)
        assert d is None

    def test_ambiguous_date_prefers_dmy(self):
        # 05/06/2025 is valid both as DD/MM and MM/DD
        # we prefer DD/MM (Pakistani convention)
        d, fmt = parse_date("05/06/2025")
        assert d == date(2025, 6, 5)  # June 5, not May 6
        assert fmt == "dmy"

    def test_dd_mm_with_dashes(self):
        d, fmt = parse_date("15-03-2023")
        assert d == date(2023, 3, 15)

    def test_impossible_date_check_old(self):
        assert is_impossible_date(date(1999, 1, 1)) is True

    def test_impossible_date_check_far_future(self):
        assert is_impossible_date(date(2040, 1, 1)) is True

    def test_valid_date_check(self):
        assert is_impossible_date(date(2025, 6, 15)) is False

    def test_mm_dd_high_day(self):
        # 09/30/2025 -- day 30 > 12, DD/MM would need month 30
        d, fmt = parse_date("09/30/2025")
        assert d == date(2025, 9, 30)
        assert fmt == "mdy"


# -- status normalization tests --

class TestNormalizeStatus:

    def test_active(self):
        assert normalize_status("active") == "active"

    def test_active_typo(self):
        assert normalize_status("actve") == "active"

    def test_cancelled_british(self):
        assert normalize_status("cancelled") == "cancelled"

    def test_cancelled_american(self):
        assert normalize_status("canceled") == "cancelled"

    def test_cancelled_typo(self):
        assert normalize_status("cancled") == "cancelled"

    def test_suspended_case(self):
        assert normalize_status("Suspended") == "suspended"

    def test_active_caps(self):
        assert normalize_status("ACTIVE") == "active"

    def test_refunded_maps_to_cancelled(self):
        assert normalize_status("refunded") == "cancelled"

    def test_blank(self):
        assert normalize_status("") is None

    def test_unknown(self):
        assert normalize_status("foobar") is None


# -- email normalization tests --

class TestNormalizeEmail:

    def test_valid_email(self):
        assert normalize_email("Ahmed.Ali@karachifoods.pk") == "ahmed.ali@karachifoods.pk"

    def test_no_at_sign(self):
        assert normalize_email("notanemail") is None

    def test_no_dot_after_at(self):
        assert normalize_email("user@domain") is None

    def test_blank(self):
        assert normalize_email("") is None

    def test_whitespace(self):
        assert normalize_email("  user@example.com  ") == "user@example.com"


# -- billing cycle tests --

class TestBillingCycle:

    def test_monthly(self):
        assert guess_billing_cycle_months("monthly") == 1

    def test_quarterly(self):
        assert guess_billing_cycle_months("quarterly") == 3

    def test_annual(self):
        assert guess_billing_cycle_months("annual") == 12

    def test_annually(self):
        assert guess_billing_cycle_months("annually") == 12

    def test_biennial(self):
        assert guess_billing_cycle_months("biennial") == 24

    def test_biennially(self):
        assert guess_billing_cycle_months("biennially") == 24

    def test_numeric_12(self):
        assert guess_billing_cycle_months("12") == 12

    def test_blank(self):
        assert guess_billing_cycle_months("") is None

    def test_garbage(self):
        assert guess_billing_cycle_months("forever") is None


# -- service normalization tests --

class TestNormalizeService:

    def test_shared_hosting(self):
        assert normalize_service("shared hosting") == "Shared Hosting"

    def test_vps(self):
        assert normalize_service("VPS") == "VPS"

    def test_ssl_certificate(self):
        assert normalize_service("SSL certificate") == "SSL Certificate"

    def test_pk_domain(self):
        assert normalize_service(".pk domain registration") == ".pk Domain"

    def test_blank(self):
        assert normalize_service("") is None
