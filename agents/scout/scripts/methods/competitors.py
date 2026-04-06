#!/usr/bin/env python3
"""
SCOUT — Method 3: Competitor research via Google Sheets
Reads a user-maintained competitor product sheet (view-only sharelink).
No scraping, no API key needed — just a public CSV export URL.

Expected sheet columns (row 1 = headers, case-insensitive):
  Product / Title  — product name or type
  URL              — product or store URL (optional)
  Price            — selling price (numeric, optional)
  Niche / Category — product category (optional)
  Notes            — any extra context (optional)

Share the sheet: Google Sheets → Share → Anyone with the link → Viewer.
CSV export URL: https://docs.google.com/spreadsheets/d/{ID}/export?format=csv
"""

import csv
import io
import requests
import time


def fetch_sheet_csv(csv_url: str) -> list:
    """Download Google Sheets as CSV and return list of dicts."""
    try:
        r = requests.get(csv_url, timeout=20, headers={
            "User-Agent": "GoogleClaw-SCOUT/1.0"
        })
        if r.status_code != 200:
            print(f"[SCOUT/Competitors] Sheet returned HTTP {r.status_code}")
            return []
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        print(f"[SCOUT/Competitors] Loaded {len(rows)} rows from competitor sheet")
        return rows
    except Exception as e:
        print(f"[SCOUT/Competitors] Failed to fetch sheet: {e}")
        return []


def normalize_headers(row: dict) -> dict:
    """Normalize column names to lowercase, strip whitespace."""
    return {k.strip().lower(): v.strip() for k, v in row.items() if k}


def parse_price(val: str) -> float:
    """Extract numeric price from a string like '€89', '89.99', etc."""
    if not val:
        return 0.0
    cleaned = val.replace("€", "").replace("$", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def match_trend(row: dict, trend: dict) -> bool:
    """Check if a competitor product row matches a trend keyword."""
    keywords = trend.get("keywords", [trend.get("name", "").lower()])
    haystack = " ".join([
        row.get("product", ""),
        row.get("title", ""),
        row.get("niche", ""),
        row.get("category", ""),
        row.get("notes", ""),
    ]).lower()

    for kw in keywords:
        kw_l = kw.lower()
        if kw_l in haystack:
            return True
        if len(kw_l) > 5 and kw_l[:6] in haystack:
            return True
    return False


def parse_row(row: dict, trend: dict) -> dict:
    """Convert a sheet row to SCOUT candidate format."""
    name  = row.get("product") or row.get("title") or ""
    url   = row.get("url", "")
    price = parse_price(row.get("price", ""))

    return {
        "title":           name,
        "source":          "competitor_sheet",
        "competitorUrl":   url,
        "competitorStore": "Google Sheets",
        "competitorPrice": price,
        "competitorPriceMax": price,
        "imageUrl":        "",
        "matchedTrend":    trend["name"],
        "trendVolume":     trend.get("monthlyVolume", 0),
        "trendScore":      trend.get("score", 0),
    }


def fetch(trends: list, cfg: dict, limit_per_trend: int = 5) -> list:
    """
    Fetch competitor products from user-provided Google Sheets.
    Filters rows to only those matching an active trend.
    """
    competitor_cfg = cfg.get("scout", {}).get("competitors", {})
    csv_url        = competitor_cfg.get("sheetsCsvUrl", "")
    min_price      = cfg.get("scout", {}).get("minSellingPrice", 40)

    if not csv_url:
        print("[SCOUT/Competitors] No Google Sheets URL in config — skipping")
        return []

    raw_rows = fetch_sheet_csv(csv_url)
    if not raw_rows:
        return []

    rows = [normalize_headers(r) for r in raw_rows]
    candidates  = []
    seen_titles = set()

    for trend in trends:
        matched = 0
        for row in rows:
            if not match_trend(row, trend):
                continue

            price = parse_price(row.get("price", ""))
            if price > 0 and price < min_price:
                continue  # Hard filter: below minimum selling price

            key = (row.get("product") or row.get("title") or "").lower()[:40]
            if key in seen_titles:
                continue
            seen_titles.add(key)

            candidates.append(parse_row(row, trend))
            matched += 1
            if matched >= limit_per_trend:
                break

    print(f"[SCOUT/Competitors] {len(candidates)} trend-matching rows from sheet")
    return candidates
