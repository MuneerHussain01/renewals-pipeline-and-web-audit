#!/usr/bin/env python3
"""
clean.py - PKHosting renewals data cleanup script.

Reads a messy renewals CSV export from multiple billing systems,
normalizes dates, amounts, domains, and statuses, deduplicates records,
and produces clean output with a full audit trail of every change.

Usage: python clean.py renewals_raw.csv
"""

import csv
import sys
import os
import re
from datetime import datetime, date
from collections import Counter


# -- configuration --

# reference date for the assessment
TODAY = date(2026, 8, 3)

# approximate USD to PKR rate (as of mid-2026)
USD_TO_PKR = 278.0

# valid statuses we normalize everything into
VALID_STATUSES = {"active", "cancelled", "suspended", "expired", "pending"}

# output file names
CLEAN_OUTPUT = "clean.csv"
ISSUES_OUTPUT = "issues.csv"


# -- parsing helpers --

def parse_amount(raw):
    """
    Parse a money string into a float PKR value.
    Handles: Rs 1,500 / PKR1500 / Rs. 1,500.00 / (2,500) for negatives / $29.99
    Returns (amount_pkr, currency, is_converted) or (None, None, False) if blank.
    """
    if raw is None:
        return None, None, False

    raw = raw.strip()
    if not raw:
        return None, None, False

    is_negative = False
    currency = "PKR"
    is_converted = False

    # check for parentheses meaning negative/refund
    if raw.startswith("(") and raw.endswith(")"):
        is_negative = True
        raw = raw[1:-1].strip()

    # check for negative sign
    if raw.startswith("-"):
        is_negative = True
        raw = raw[1:].strip()

    # detect currency
    if "$" in raw and "PKR" not in raw.upper() and "RS" not in raw.upper():
        currency = "USD"
        is_converted = True
        raw = raw.replace("$", "").strip()
    else:
        # strip PKR / Rs / Rs. prefix
        raw = re.sub(r'^(PKR|Rs\.?)\s*', '', raw, flags=re.IGNORECASE).strip()

    # remove thousands separators (commas)
    raw = raw.replace(",", "")

    # remove any remaining non-numeric chars except dot
    raw = re.sub(r'[^\d.]', '', raw)

    if not raw:
        return None, None, False

    try:
        amount = float(raw)
    except ValueError:
        return None, None, False

    if is_converted:
        amount = round(amount * USD_TO_PKR, 2)

    if is_negative:
        amount = -amount

    return amount, currency, is_converted


def normalize_domain(raw):
    """
    Clean up a domain name:
    - lowercase
    - strip whitespace
    - remove www. prefix
    - remove trailing dots
    - remove protocol prefixes
    """
    if not raw or not raw.strip():
        return None

    domain = raw.strip().lower()

    # remove protocol
    domain = re.sub(r'^https?://', '', domain)

    # remove www. prefix
    domain = re.sub(r'^www\.', '', domain)

    # remove trailing dots and slashes
    domain = domain.rstrip("./ ")

    # remove any spaces inside the domain
    domain = domain.replace(" ", "")

    if not domain:
        return None

    return domain


def parse_date(raw):
    """
    Try to parse a date string in multiple formats.
    Returns (date_object, format_used) or (None, None) on failure.

    Ambiguous date strategy (documented in NOTES.md):
    We first try DD/MM/YYYY (more common in Pakistan). If that fails
    or produces an invalid date, we try MM/DD/YYYY. For dates where
    both are valid (e.g., 05/06/2025), we prefer DD/MM/YYYY since
    PKHosting is a Pakistani company and this format is standard there.
    """
    if not raw or not raw.strip():
        return None, None

    raw = raw.strip()

    # try ISO format first (YYYY-MM-DD)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(raw, fmt).date()
            return d, fmt
        except ValueError:
            continue

    # try DD/MM/YYYY first (Pakistani convention)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            return d, "dmy"
        except ValueError:
            continue

    # try MM/DD/YYYY as fallback
    for fmt in ("%m/%d/%Y", "%m-%d-%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            return d, "mdy"
        except ValueError:
            continue

    # try written-out formats
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            return d, fmt
        except ValueError:
            continue

    return None, None


def is_impossible_date(d):
    """Check if a parsed date is obviously wrong (too far past or future)."""
    if d is None:
        return True
    # anything before 2000 or after 2035 is suspicious for hosting renewals
    if d.year < 2000 or d.year > 2035:
        return True
    return False


def normalize_status(raw):
    """Map various status strings to our fixed set."""
    if not raw or not raw.strip():
        return None

    s = raw.strip().lower()

    mapping = {
        "active": "active",
        "actve": "active",
        "acitve": "active",
        "act": "active",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "cancel": "cancelled",
        "cancled": "cancelled",
        "suspended": "suspended",
        "suspend": "suspended",
        "susp": "suspended",
        "suspnded": "suspended",
        "expired": "expired",
        "expire": "expired",
        "exprd": "expired",
        "pending": "pending",
        "pend": "pending",
        "refund": "cancelled",
        "refunded": "cancelled",
    }

    return mapping.get(s, None)


def normalize_email(raw):
    """Basic email cleanup and validation."""
    if not raw or not raw.strip():
        return None

    email = raw.strip().lower()

    # basic format check
    if "@" not in email or "." not in email.split("@")[-1]:
        return None

    return email


def guess_billing_cycle_months(raw):
    """Convert billing cycle text to integer months."""
    if not raw or not raw.strip():
        return None

    s = raw.strip().lower()

    mapping = {
        "monthly": 1,
        "month": 1,
        "1 month": 1,
        "quarterly": 3,
        "quarter": 3,
        "3 months": 3,
        "3 month": 3,
        "semi-annually": 6,
        "semi-annual": 6,
        "6 months": 6,
        "6 month": 6,
        "annually": 12,
        "annual": 12,
        "yearly": 12,
        "year": 12,
        "1 year": 12,
        "12 months": 12,
        "12 month": 12,
        "biennially": 24,
        "biennial": 24,
        "2 years": 24,
        "2 year": 24,
        "24 months": 24,
        "24 month": 24,
        "triennially": 36,
        "triennial": 36,
        "3 years": 36,
        "3 year": 36,
    }

    # try direct match
    if s in mapping:
        return mapping[s]

    # try to extract a number if format is like "12" alone
    try:
        n = int(s)
        if n in (1, 3, 6, 12, 24, 36):
            return n
        return None
    except ValueError:
        pass

    return None


def normalize_service(raw):
    """Standardize service type names."""
    if not raw or not raw.strip():
        return None

    s = raw.strip().lower()

    if "shared" in s or "hosting" in s and "vps" not in s and "reseller" not in s:
        return "Shared Hosting"
    if "vps" in s or "virtual private" in s:
        return "VPS"
    if "ssl" in s or "certificate" in s:
        return "SSL Certificate"
    if "domain" in s or ".pk" in s:
        return ".pk Domain"
    if "reseller" in s:
        return "Reseller Hosting"
    if "dedicated" in s:
        return "Dedicated Server"

    return raw.strip()


# -- deduplication --

def find_duplicates(records):
    """
    Find duplicate records based on customer_id + canonical_domain + service.
    Returns groups of duplicates (list of lists of record indices).

    Dedupe strategy (documented in NOTES.md):
    - Same customer + domain + service = duplicate group
    - Keep the record with the latest renewal date
    - If amounts differ, flag it and keep the higher amount
      (assumption: the higher amount is the current price)
    """
    groups = {}
    for i, rec in enumerate(records):
        key = (
            rec.get("customer_id", "").strip().lower(),
            rec.get("canonical_domain", ""),
            rec.get("service", ""),
        )
        if key[0] and key[1]:  # only group if we have customer and domain
            groups.setdefault(key, []).append(i)

    return {k: v for k, v in groups.items() if len(v) > 1}


# -- main processing --

def process_file(input_path):
    """Main processing pipeline. Returns clean records, issues list, and stats."""

    if not os.path.exists(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    # read input
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    total_in = len(raw_rows)
    issues = []
    processed = []

    # step 1: parse and normalize each row
    for row in raw_rows:
        rid = row.get("record_id", "").strip()
        cid = row.get("customer_id", "").strip()
        rec = {"record_id": rid, "customer_id": cid}

        # domain
        raw_domain = row.get("domain", "")
        canonical = normalize_domain(raw_domain)
        if canonical and canonical != raw_domain.strip().lower():
            issues.append({
                "record_id": rid,
                "field": "domain",
                "raw_value": raw_domain.strip(),
                "problem": "Domain needed cleanup (case, www, trailing chars)",
                "action_taken": f"Normalized to '{canonical}'",
            })
        if not canonical:
            issues.append({
                "record_id": rid,
                "field": "domain",
                "raw_value": raw_domain.strip(),
                "problem": "Domain is blank or invalid",
                "action_taken": "Kept as-is, flagged for review",
            })
        rec["canonical_domain"] = canonical or ""

        # service type
        raw_service = row.get("service_type", "")
        service = normalize_service(raw_service)
        if service and service != raw_service.strip():
            issues.append({
                "record_id": rid,
                "field": "service_type",
                "raw_value": raw_service.strip(),
                "problem": "Service type not in standard form",
                "action_taken": f"Normalized to '{service}'",
            })
        rec["service"] = service or raw_service.strip()

        # billing cycle
        raw_cycle = row.get("billing_cycle", "")
        cycle_months = guess_billing_cycle_months(raw_cycle)
        if cycle_months is None and raw_cycle.strip():
            issues.append({
                "record_id": rid,
                "field": "billing_cycle",
                "raw_value": raw_cycle.strip(),
                "problem": "Could not parse billing cycle",
                "action_taken": "Set to blank, flagged for review",
            })
        elif cycle_months is None:
            issues.append({
                "record_id": rid,
                "field": "billing_cycle",
                "raw_value": "",
                "problem": "Billing cycle is blank",
                "action_taken": "Flagged for review",
            })
        rec["billing_cycle_months"] = cycle_months or ""

        # amount
        raw_amount = row.get("amount", "")
        amount_pkr, currency, is_converted = parse_amount(raw_amount)
        if is_converted:
            issues.append({
                "record_id": rid,
                "field": "amount",
                "raw_value": raw_amount.strip(),
                "problem": f"Amount was in {currency}, converted to PKR",
                "action_taken": f"Converted at {USD_TO_PKR} PKR/USD = {amount_pkr} PKR",
            })
        if amount_pkr is not None and amount_pkr < 0:
            issues.append({
                "record_id": rid,
                "field": "amount",
                "raw_value": raw_amount.strip(),
                "problem": "Negative amount (refund/credit)",
                "action_taken": "Kept negative value, flagged as refund",
            })
        if amount_pkr is None and raw_amount.strip():
            issues.append({
                "record_id": rid,
                "field": "amount",
                "raw_value": raw_amount.strip(),
                "problem": "Could not parse amount",
                "action_taken": "Set to blank, flagged for review",
            })
        elif amount_pkr is None:
            issues.append({
                "record_id": rid,
                "field": "amount",
                "raw_value": "",
                "problem": "Amount is blank",
                "action_taken": "Flagged for review",
            })
        rec["amount_pkr"] = amount_pkr if amount_pkr is not None else ""

        # registered date
        raw_reg = row.get("registered_date", "")
        reg_date, reg_fmt = parse_date(raw_reg)
        if reg_date and is_impossible_date(reg_date):
            issues.append({
                "record_id": rid,
                "field": "registered_date",
                "raw_value": raw_reg.strip(),
                "problem": f"Impossible date parsed: {reg_date}",
                "action_taken": "Marked as invalid, set to blank",
            })
            reg_date = None
        elif reg_date is None and raw_reg.strip():
            issues.append({
                "record_id": rid,
                "field": "registered_date",
                "raw_value": raw_reg.strip(),
                "problem": "Could not parse registration date",
                "action_taken": "Set to blank, flagged",
            })
        elif reg_fmt == "mdy" and reg_date:
            # log that we had to fall back to US format
            issues.append({
                "record_id": rid,
                "field": "registered_date",
                "raw_value": raw_reg.strip(),
                "problem": "Ambiguous date parsed as MM/DD/YYYY (DD/MM failed)",
                "action_taken": f"Interpreted as {reg_date.isoformat()}",
            })
        rec["registered_on"] = reg_date.isoformat() if reg_date else ""

        # renewal date
        raw_ren = row.get("renewal_date", "")
        ren_date, ren_fmt = parse_date(raw_ren)
        if ren_date and is_impossible_date(ren_date):
            issues.append({
                "record_id": rid,
                "field": "renewal_date",
                "raw_value": raw_ren.strip(),
                "problem": f"Impossible date parsed: {ren_date}",
                "action_taken": "Marked as invalid, set to blank",
            })
            ren_date = None
        elif ren_date is None and raw_ren.strip():
            issues.append({
                "record_id": rid,
                "field": "renewal_date",
                "raw_value": raw_ren.strip(),
                "problem": "Could not parse renewal date",
                "action_taken": "Set to blank, flagged",
            })
        elif ren_fmt == "mdy" and ren_date:
            issues.append({
                "record_id": rid,
                "field": "renewal_date",
                "raw_value": raw_ren.strip(),
                "problem": "Ambiguous date parsed as MM/DD/YYYY (DD/MM failed)",
                "action_taken": f"Interpreted as {ren_date.isoformat()}",
            })
        rec["renews_on"] = ren_date.isoformat() if ren_date else ""
        rec["_ren_date"] = ren_date  # keep for later logic

        # status
        raw_status = row.get("status", "")
        status = normalize_status(raw_status)
        if status is None and raw_status.strip():
            issues.append({
                "record_id": rid,
                "field": "status",
                "raw_value": raw_status.strip(),
                "problem": "Unrecognized status value",
                "action_taken": "Flagged for review, kept raw value",
            })
            status = raw_status.strip().lower()
        elif status is None:
            issues.append({
                "record_id": rid,
                "field": "status",
                "raw_value": "",
                "problem": "Status is blank",
                "action_taken": "Flagged for review",
            })
        elif status != raw_status.strip().lower():
            issues.append({
                "record_id": rid,
                "field": "status",
                "raw_value": raw_status.strip(),
                "problem": "Status had typo or non-standard value",
                "action_taken": f"Normalized to '{status}'",
            })
        rec["status"] = status or ""

        # email
        raw_email = row.get("contact_email", "")
        email = normalize_email(raw_email)
        if email is None and raw_email.strip():
            issues.append({
                "record_id": rid,
                "field": "contact_email",
                "raw_value": raw_email.strip(),
                "problem": "Invalid email format",
                "action_taken": "Set to blank, flagged",
            })
        elif email is None:
            issues.append({
                "record_id": rid,
                "field": "contact_email",
                "raw_value": "",
                "problem": "Email is blank",
                "action_taken": "Flagged for review",
            })
        rec["contact_email"] = email or ""

        # customer_id check
        if not cid:
            issues.append({
                "record_id": rid,
                "field": "customer_id",
                "raw_value": "",
                "problem": "Customer ID is blank",
                "action_taken": "Flagged for review",
            })

        processed.append(rec)

    # step 2: detect and resolve duplicates
    dup_groups = find_duplicates(processed)
    dropped_indices = set()

    for key, indices in dup_groups.items():
        # sort by renewal date descending; on tie, prefer higher amount, then higher record_id
        def sort_key(i):
            d = processed[i].get("_ren_date") or date.min
            amt = processed[i].get("amount_pkr")
            amt_val = float(amt) if amt not in ("", None) else 0.0
            rid = processed[i].get("record_id", "")
            return (d, amt_val, rid)

        sorted_idx = sorted(indices, key=sort_key, reverse=True)
        keeper = sorted_idx[0]

        # check if amounts differ among duplicates
        amounts = [processed[i].get("amount_pkr", "") for i in indices]
        amounts_set = set(a for a in amounts if a != "")
        amount_mismatch = len(amounts_set) > 1

        for i in sorted_idx[1:]:
            dropped_indices.add(i)
            rec = processed[i]
            problem = "Duplicate record (same customer + domain + service)"
            if amount_mismatch:
                problem += f"; amounts differ across duplicates: {amounts_set}"
            issues.append({
                "record_id": rec["record_id"],
                "field": "record",
                "raw_value": f"customer={rec['customer_id']}, domain={rec['canonical_domain']}",
                "problem": problem,
                "action_taken": f"Dropped in favor of record {processed[keeper]['record_id']} (latest renewal date / higher amount)",
            })

    # step 3: identify rows to drop (impossible dates with no usable data)
    final_dropped = set()
    for i, rec in enumerate(processed):
        if i in dropped_indices:
            final_dropped.add(i)
            continue

        # drop rows with no domain AND no customer_id -- can't identify them
        if not rec["canonical_domain"] and not rec["customer_id"]:
            final_dropped.add(i)
            issues.append({
                "record_id": rec["record_id"],
                "field": "record",
                "raw_value": "",
                "problem": "Row has no domain and no customer ID",
                "action_taken": "Dropped -- cannot identify record",
            })

    # build final clean list
    clean_records = []
    flagged_ids = set()

    for i, rec in enumerate(processed):
        if i in final_dropped:
            continue

        # determine if this record should be flagged
        is_flagged = False
        if not rec["canonical_domain"] or not rec["customer_id"]:
            is_flagged = True
        if rec["amount_pkr"] == "":
            is_flagged = True
        if not rec["renews_on"]:
            is_flagged = True
        if rec["status"] not in VALID_STATUSES:
            is_flagged = True

        if is_flagged:
            flagged_ids.add(rec["record_id"])

        clean_records.append({
            "record_id": rec["record_id"],
            "customer_id": rec["customer_id"],
            "canonical_domain": rec["canonical_domain"],
            "service": rec["service"],
            "billing_cycle_months": rec["billing_cycle_months"],
            "amount_pkr": rec["amount_pkr"],
            "registered_on": rec["registered_on"],
            "renews_on": rec["renews_on"],
            "status": rec["status"],
            "contact_email": rec["contact_email"],
        })

    # step 4: write outputs
    clean_fields = [
        "record_id", "customer_id", "canonical_domain", "service",
        "billing_cycle_months", "amount_pkr", "registered_on", "renews_on",
        "status", "contact_email",
    ]

    with open(CLEAN_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=clean_fields)
        writer.writeheader()
        writer.writerows(clean_records)

    issue_fields = ["record_id", "field", "raw_value", "problem", "action_taken"]
    with open(ISSUES_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=issue_fields)
        writer.writeheader()
        writer.writerows(issues)

    # step 5: print summary
    kept = len(clean_records)
    dropped = len(final_dropped)
    flagged = len(flagged_ids)
    status_counts = Counter(r["status"] for r in clean_records)

    print("=" * 60)
    print("PKHosting Renewals Cleanup Summary")
    print("=" * 60)
    print(f"Input file:     {input_path}")
    print(f"Rows in:        {total_in}")
    print(f"Rows kept:      {kept}")
    print(f"Rows dropped:   {dropped}")
    print(f"Rows flagged:   {flagged}")
    print(f"Issues logged:  {len(issues)}")
    print("-" * 40)
    print("Totals by status:")
    for status in sorted(status_counts.keys()):
        print(f"  {status:<15} {status_counts[status]:>3}")
    print("-" * 40)

    # renewal window analysis
    window_start = date(2026, 8, 3)
    window_end = date(2026, 9, 2)
    window_total = 0.0
    window_items = []

    for rec in clean_records:
        if not rec["renews_on"] or rec["amount_pkr"] == "":
            continue
        ren = date.fromisoformat(rec["renews_on"])
        if window_start <= ren <= window_end:
            amt = float(rec["amount_pkr"])
            status = rec["status"]
            window_items.append((rec["record_id"], rec["canonical_domain"], amt, status, ren))
            if status == "active":
                window_total += amt

    print(f"\nRenewals due {window_start} to {window_end}:")
    print(f"  Total (active only): PKR {window_total:,.2f}")
    if window_items:
        for rid, dom, amt, st, ren in window_items:
            marker = " *" if st != "active" else ""
            print(f"    {rid}: {dom} -- PKR {amt:,.2f} ({st}, {ren}){marker}")
        print("  (* = excluded from active total)")
    else:
        print("  No renewals found in this window.")

    print("=" * 60)
    print(f"Output: {CLEAN_OUTPUT}, {ISSUES_OUTPUT}")

    return clean_records, issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clean.py <renewals_raw.csv>")
        sys.exit(1)

    process_file(sys.argv[1])
