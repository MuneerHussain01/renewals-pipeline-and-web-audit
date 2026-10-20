# PKHosting Renewal Analysis & Data Engineering Notes

Reference Date: 2026-08-03
Renewal Window: 2026-08-03 to 2026-09-02 (inclusive)

---

## 1. Renewal Total Calculation (2026-08-03 to 2026-09-02)

### Summary of Figures by Policy Stance

| Category | Amount (PKR) | Rationale |
|---|---|---|
| Primary Baseline (Active Only) | 57,600.00 | Only active customers with confirmed valid payment expectations |
| Including Suspended Services | 60,100.00 | Suspended services (+2,500.00) frequently resolve upon payment reminders |
| Max Potential (Including Cancelled) | 85,100.00 | If cancelled accounts (+25,000.00) are re-engaged or contractually obligated |

The recommended operational cash flow baseline for financial planning is **PKR 57,600.00**.

---

## 2. Inclusions (Active Renewals in Window)

The following 11 active service records fall directly in the 30-day renewal window:

1. **Record 1004** - `faisalabadweaves.pk` (Shared Hosting, Annual)
   - Renews on: 2026-08-20
   - Amount: PKR 4,500.00
   - Status: active
   - Note: Customer ID was missing in source data, but domain and contact email are present. Kept and included in pipeline.

2. **Record 1006** - `peshawarcrafts.pk` (VPS, Monthly)
   - Renews on: 2026-08-25
   - Amount: PKR 9,000.00
   - Status: active

3. **Record 1007** - `quettagems.pk` (.pk Domain Registration, Biennial)
   - Renews on: 2026-08-28
   - Amount: PKR 3,000.00
   - Status: active
   - Note: Registration date had an impossible date (30/02/2024), which was blanked and logged in `issues.csv`. The renewal date (28/08/2026) is valid.

4. **Record 1011** - `hyderabadspices.pk` (Shared Hosting, Monthly)
   - Renews on: 2026-08-07
   - Amount: PKR 450.00
   - Status: active

5. **Record 1013** - `karachifoods.pk` (Shared Hosting, Annual)
   - Renews on: 2026-08-15
   - Amount: PKR 4,500.00
   - Status: active
   - Note: Deduplicated with Record 1001. Kept the newer record instance.

6. **Record 1016** - `bahawalpur-darbar.pk` (VPS, Monthly)
   - Renews on: 2026-09-02
   - Amount: PKR 8,750.00
   - Status: active
   - Note: Falls on the exact boundary end date (2026-09-02). Included under inclusive window logic.

7. **Record 1019** - `chitralhandicrafts.pk` (Shared Hosting, Annual)
   - Renews on: 2026-08-28
   - Amount: PKR 4,500.00
   - Status: active

8. **Record 1022** - `turbatfisheries.pk` (VPS, Monthly)
   - Renews on: 2026-08-17
   - Amount: PKR 9,200.00
   - Status: active

9. **Record 1027** - `jacobabadoil.com` (VPS, Monthly)
   - Renews on: 2026-08-05
   - Amount: PKR 8,750.00
   - Status: active

10. **Record 1028** - `sukkurbarrage.pk` (Shared Hosting, Annual)
    - Renews on: 2026-08-12
    - Amount: PKR 4,500.00
    - Status: active

11. **Record 1033** - `okaragardens.com` (Shared Hosting, Monthly)
    - Renews on: 2026-08-21
    - Amount: PKR 450.00
    - Status: active

**Subtotal of Active Renewals:** 4,500 + 9,000 + 3,000 + 450 + 4,500 + 8,750 + 4,500 + 9,200 + 8,750 + 4,500 + 450 = **PKR 57,600.00**

---

## 3. Exclusions & Edge Case Rulings

### A. Cancelled Services in Window
- **Record 1009** - `rawalpindimotors.pk` (VPS, Quarterly, due 2026-08-05, PKR 25,000.00)
  - Ruling: **EXCLUDED** from active cashflow.
  - Reason: The client has cancelled service prior to the renewal date. Attempting to charge or forecasting this renewal as expected incoming revenue leads to overestimating collection.

### B. Suspended Services in Window
- **Record 1029** - `larkanaarts.pk` (SSL Certificate, Annual, due 2026-08-19, PKR 2,500.00)
  - Ruling: **EXCLUDED** from the primary baseline, tracked as secondary recoverable revenue.
  - Reason: Suspended accounts reflect non-payment or policy lock. While some percentage of suspended accounts pay when receiving automated renewal prompts, conservative accounting requires treating them as unearned until restored.

### C. The Refund / Negative Entry
- **Record 1020** - `dikimarket.pk` (VPS, Quarterly, amount: `(2,500)` -> -PKR 2,500.00, status: `refunded`)
  - Ruling: **EXCLUDED** from the window total.
  - Reason: The renewal date on this entry is 2026-01-06, which is outside the August 2026 window. Furthermore, refunds represent historical credits or reversals, not active renewal invoices.

### D. Duplicate with Two Amounts
- **Record 1010 vs Record 1026** - `gujranwalasteel.com` (SSL Certificate, Customer PKH-210)
  - Raw amounts: Record 1010 listed `Rs 2500`, Record 1026 listed `Rs 2800`.
  - Renewal date: 2026-09-18 (both records).
  - Ruling:
    1. **Outside Window**: 2026-09-18 falls 16 days after the window closes (2026-09-02). Therefore, neither record impacts the window total.
    2. **Deduplication Priority**: Record 1026 (PKR 2,800.00) was retained in `clean.csv`, and Record 1010 was dropped. In multi-system exports where renewal dates are identical, a higher amount in a later record indicates an updated tariff, price increase, or currency adjustment. Both amounts and the drop action are logged in `issues.csv`.

### E. The USD Line
- **Record 1018** - `gilgittreks.com` (.pk Domain Registration, Biennial)
  - Raw amount: `$29.99`
  - Converted amount: `PKR 8,337.22` (at 278.0 PKR/USD).
  - Renews on: 2027-04-15
  - Ruling: **EXCLUDED** from the window total because the renewal is due in April 2027. Conversion logic successfully normalizes the line to PKR for portfolio valuation, and the conversion is documented in `issues.csv`.

---

## 4. Ambiguous Date Strategy

Dates in `renewals_raw.csv` originated from three disparate billing systems, creating format collisions:
- System A used standard Pakistani / Commonwealth notation: `DD/MM/YYYY`.
- System B used US corporate notation: `MM/DD/YYYY`.
- System C exported mixed or ISO-like patterns.

### Decision Hierarchy

1. **Unambiguous Formats**:
   - ISO formats (`YYYY-MM-DD`, `YYYY/MM/DD`) and written month names (`January 15, 2025`) are parsed directly.
2. **Numeric Values Above 12**:
   - If the first integer is > 12 (e.g. `15/03/2023`), it must be the day, resolving to `DD/MM/YYYY`.
   - If the second integer is > 12 (e.g. `03/15/2024` or `08/20/2026`), it must be the day, resolving to `MM/DD/YYYY`.
3. **True Ambiguity (Both numbers <= 12, e.g. 05/06/2025)**:
   - Strategy: Prefer `DD/MM/YYYY`.
   - Reason: PKHosting.com operates in Pakistan, where `DD/MM/YYYY` is the official legal and commercial convention. Defaulting to `DD/MM/YYYY` minimizes regional misinterpretation.
4. **Invalid / Impossible Dates**:
   - Days such as `30/02/2024` (February 30) or months such as `13/25/2024` are rejected by Python `strptime`.
   - Rather than dropping the entire customer row, the unparseable date is cleared to blank (`""`), and an explicit entry is written to `issues.csv`. This preserves customer and billing records for manual audit.

---

## 5. Deduplication Strategy

### Composite Key Definition
A duplicate group is identified when all three normalized fields match:
`customer_id` + `canonical_domain` + `service`

Domains are normalized before keying (lowercase, stripping `www.`, removing trailing periods and spaces). Services are normalized to standard names (`Shared Hosting`, `VPS`, `SSL Certificate`, `.pk Domain`).

### Resolution Hierarchy
When duplicates exist within a group:
1. **Latest Renewal Date**: Retain the record with the most advanced renewal date (latest active period).
2. **Amount Priority**: If renewal dates tie and amounts differ (as in Record 1010 vs 1026), retain the higher amount, reflecting current billing pricing or revised tariffs.
3. **Record Sequence**: If dates and amounts match (as in Record 1001 vs 1013), retain the higher `record_id` (representing the later export sequence).
4. **Full Audit Trail**: Every dropped duplicate is logged in `issues.csv` with raw values, conflict notes, and the ID of the retained record. No row is silently deleted.
