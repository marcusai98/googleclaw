#!/usr/bin/env python3
"""
MIDAS — GoogleClaw P&L Sync Agent
Fetches revenue (Shopify), ad spend (Google Ads), COGS (Google Sheets)
and writes daily P&L to dashboard.json.

Usage:
    python3 fetch.py --config /path/to/config.json --output /path/to/dashboard.json
"""

import json
import os
import sys
import argparse
import datetime
import requests
from pathlib import Path

# ─── Optional imports (graceful fallback if not installed) ───────────────────
try:
    from google.ads.googleads.client import GoogleAdsClient
    HAS_GOOGLE_ADS = True
except ImportError:
    HAS_GOOGLE_ADS = False

try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials as SACredentials
    from google.oauth2.credentials import Credentials as OAuthCredentials
    HAS_SHEETS = True
except ImportError:
    HAS_SHEETS = False


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# SHOPIFY
# ─────────────────────────────────────────────────────────────────────────────

def shopify_fetch_orders(cfg: dict, date_from: str, date_to: str) -> list:
    """Fetch paid orders from Shopify for a date range (YYYY-MM-DD)."""
    domain = cfg["shopify"]["storeDomain"]
    token  = cfg["shopify"]["accessToken"]
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    url = f"https://{domain}/admin/api/2024-01/orders.json"
    orders = []
    params = {
        "status": "any",
        "financial_status": "paid",
        "created_at_min": f"{date_from}T00:00:00+00:00",
        "created_at_max": f"{date_to}T23:59:59+00:00",
        "limit": 250,
        "fields": "id,created_at,total_price,subtotal_price,total_tax,total_discounts,"
                  "total_shipping_price_set,gateway,line_items,total_price_usd"
    }
    while url:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        orders.extend(data.get("orders", []))
        # Pagination
        link = r.headers.get("Link", "")
        url = None
        params = {}
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
    return orders


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT CATALOG CACHE (products.json)
# ─────────────────────────────────────────────────────────────────────────────

def load_product_cache(path: str) -> dict:
    """
    Load local product catalog cache.
    Structure: {sku_or_product_id: {title, sku, shopifyProductId, shopifyVariantId, cogs, supplier, lastUpdated}}
    """
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_product_cache(cache: dict, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def build_combined_lookup(sheets_cogs: dict, product_cache: dict) -> dict:
    """
    Merge Google Sheets COGS + products.json cache into one unified lookup.
    products.json takes priority (more specific / manually confirmed).
    Returns: {key: {"cogs": float, "source": str}}
    """
    lookup = {}

    # Layer 1: Google Sheets (base layer)
    for k, v in sheets_cogs.items():
        lookup[k.lower().strip()] = {"cogs": v, "source": "sheets"}

    # Layer 2: products.json (overrides sheets where present)
    for entry in product_cache.values():
        cogs = entry.get("cogs", 0)
        if cogs <= 0:
            continue
        # Index by SKU
        sku = entry.get("sku", "").strip().lower()
        if sku:
            lookup[sku] = {"cogs": cogs, "source": "catalog"}
        # Index by Shopify product ID
        pid = str(entry.get("shopifyProductId", "")).strip()
        if pid:
            lookup[pid] = {"cogs": cogs, "source": "catalog"}
        # Index by title
        title = entry.get("title", "").strip().lower()
        if title:
            lookup[title] = {"cogs": cogs, "source": "catalog"}

    return lookup


def match_cogs(item: dict, lookup: dict, cfg: dict) -> tuple[float, str]:
    """
    Match a Shopify line item to its COGS using the hierarchy:
    1. SKU exact
    2. Shopify product_id
    3. Title exact
    4. Title fuzzy (substring)
    5. Default margin %

    Returns (cost_price, match_method)
    """
    sku        = (item.get("sku") or "").strip().lower()
    product_id = str(item.get("product_id") or "").strip()
    title      = (item.get("title") or "").strip().lower()
    sell_price = float(item.get("price") or 0)

    # 1. SKU exact
    if sku and sku in lookup:
        return lookup[sku]["cogs"], "sku_exact"

    # 2. Shopify product_id
    if product_id and product_id in lookup:
        return lookup[product_id]["cogs"], "product_id"

    # 3. Title exact
    if title and title in lookup:
        return lookup[title]["cogs"], "title_exact"

    # 4. Title fuzzy — substring match
    if title:
        for k, v in lookup.items():
            if len(k) > 4 and (k in title or title in k):
                return v["cogs"], "title_fuzzy"

    # 5. Default margin fallback
    default_margin = cfg.get("costs", {}).get("defaultMarginPercent", 40) / 100
    return round(sell_price * (1 - default_margin), 2), "default_margin"


def shopify_calc_day(orders: list, lookup: dict, cfg: dict,
                     product_cache: dict, cache_path: str) -> dict:
    """Calculate P&L for a single day. Updates product_cache with new/unmatched products."""
    revenue          = 0.0
    cogs             = 0.0
    transaction_fees = 0.0
    order_count      = len(orders)
    product_stats    = {}
    unmatched        = []
    cache_updated    = False

    shopify_plan_fee_pct = cfg.get("costs", {}).get("shopifyTransactionFeePercent", 0)
    third_party_fee_pct  = cfg.get("costs", {}).get("thirdPartyGatewayFeePercent", 2.9)
    shopify_fee_fixed    = cfg.get("costs", {}).get("shopifyPaymentsFeeFixed", 0.25)

    for order in orders:
        order_revenue = float(order.get("total_price", 0))
        revenue += order_revenue

        # Transaction/payment fees
        gateway = order.get("gateway", "")
        if "shopify_payments" in gateway.lower():
            fee_pct = cfg.get("costs", {}).get("shopifyPaymentsFeePercent", 1.9)
            transaction_fees += (order_revenue * fee_pct / 100) + shopify_fee_fixed
        else:
            transaction_fees += order_revenue * third_party_fee_pct / 100
            transaction_fees += order_revenue * shopify_plan_fee_pct / 100

        # COGS per line item
        for item in order.get("line_items", []):
            sku          = (item.get("sku") or "").strip()
            title        = (item.get("title") or "").strip()
            variant      = (item.get("variant_title") or "").strip()
            product_id   = str(item.get("product_id") or "")
            variant_id   = str(item.get("variant_id") or "")
            qty          = int(item.get("quantity") or 1)
            sell_price   = float(item.get("price") or 0)
            item_revenue = sell_price * qty

            cost, match_method = match_cogs(item, lookup, cfg)
            item_cogs = round(cost * qty, 2)
            cogs += item_cogs

            # Register new products in cache (for supplier to fill COGS)
            cache_key = sku or product_id or title
            today_s   = datetime.date.today().isoformat()
            review_due = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()

            if cache_key and cache_key not in product_cache:
                # Brand new product — register it
                product_cache[cache_key] = {
                    "title":            title,
                    "variantTitle":     variant,
                    "sku":              sku,
                    "shopifyProductId": product_id,
                    "shopifyVariantId": variant_id,
                    "cogs":             cost if match_method != "default_margin" else 0,
                    "cogsSource":       match_method,
                    "cogsLastUpdated":  today_s,
                    "cogsReviewDue":    review_due,
                    "supplier":         "",
                    "needsReview":      match_method == "default_margin",
                    "firstSeen":        today_s,
                    "lastSeen":         today_s,
                }
                cache_updated = True
                if match_method == "default_margin":
                    unmatched.append(title or sku)

            elif cache_key in product_cache:
                entry          = product_cache[cache_key]
                prev_last_seen = entry.get("lastSeen", "")
                entry["lastSeen"] = today_s

                # Detect reactivated product: was inactive >90 days, now selling again
                # AND COGS review is overdue → flag immediately
                if prev_last_seen:
                    try:
                        days_inactive = (datetime.date.today() -
                                         datetime.date.fromisoformat(prev_last_seen)).days
                        cogs_due      = entry.get("cogsReviewDue", "")
                        if (days_inactive > 90 and cogs_due and
                                datetime.date.fromisoformat(cogs_due) <= datetime.date.today()):
                            entry["needsReview"] = True
                            print(f"[MIDAS] Reactivated product needs COGS review: '{title}' "
                                  f"(inactive {days_inactive}d)")
                            unmatched.append(title or sku)
                            cache_updated = True
                    except ValueError:
                        pass

                cache_updated = True

            # Per-product stats
            pid = sku or product_id or title
            if pid not in product_stats:
                product_stats[pid] = {
                    "title":       title,
                    "sku":         sku,
                    "productId":   product_id,
                    "variantId":   variant_id,
                    "revenue":     0,
                    "cogs":        0,
                    "units":       0,
                    "cogsSource":  match_method,
                }
            product_stats[pid]["revenue"] += item_revenue
            product_stats[pid]["cogs"]    += item_cogs
            product_stats[pid]["units"]   += qty

    if cache_updated:
        save_product_cache(product_cache, cache_path)
        if unmatched:
            print(f"[MIDAS] {len(unmatched)} products need COGS review: {', '.join(unmatched[:5])}")

    return {
        "revenue":          round(revenue, 2),
        "orders":           order_count,
        "cogs":             round(cogs, 2),
        "transactionFees":  round(transaction_fees, 2),
        "unmatchedProducts": len(unmatched),
        "products":         product_stats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE ADS
# ─────────────────────────────────────────────────────────────────────────────

def google_ads_fetch_spend(cfg: dict, date_from: str, date_to: str) -> float:
    """Fetch total ad spend from Google Ads for a date range."""
    if not HAS_GOOGLE_ADS:
        print("[MIDAS] google-ads library not installed — using 0 for spend", file=sys.stderr)
        return 0.0

    ga_cfg = cfg["googleAds"]
    client = GoogleAdsClient.load_from_dict({
        "developer_token": ga_cfg["developerToken"],
        "client_id": ga_cfg["clientId"],
        "client_secret": ga_cfg["clientSecret"],
        "refresh_token": ga_cfg["refreshToken"],
        "use_proto_plus": True,
    })

    customer_id = ga_cfg["customerId"].replace("-", "")
    ga_service  = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND campaign.status = 'ENABLED'
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    total_micros = 0
    for batch in response:
        for row in batch.results:
            total_micros += row.metrics.cost_micros

    return round(total_micros / 1_000_000, 2)


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS (COGS)
# ─────────────────────────────────────────────────────────────────────────────

def sheets_load_cogs(cfg: dict) -> dict:
    """Load COGS lookup from Google Sheets. Returns {identifier: cost_price}."""
    if not HAS_SHEETS:
        print("[MIDAS] google-api-python-client not installed — COGS from sheet skipped", file=sys.stderr)
        return {}

    sheet_cfg = cfg.get("cogsSheet", {})
    if not sheet_cfg.get("spreadsheetId"):
        return {}

    spreadsheet_id = sheet_cfg["spreadsheetId"]
    sheet_name     = sheet_cfg.get("sheetName", "Sheet1")
    header_row     = sheet_cfg.get("headerRow", 1)
    id_col         = sheet_cfg.get("productIdentifierColumn", "A")
    price_col      = sheet_cfg.get("cogsPriceColumn", "C")
    match_by       = sheet_cfg.get("matchBy", "sku")

    # Auth: service account or OAuth token
    creds = _sheets_auth(cfg)
    service = build("sheets", "v4", credentials=creds)

    # Read the relevant columns
    range_notation = f"{sheet_name}!{id_col}:{price_col}"
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_notation
    ).execute()

    rows = result.get("values", [])
    lookup = {}
    for i, row in enumerate(rows):
        if i < header_row - 1:
            continue  # skip header rows
        if len(row) < 2:
            continue
        identifier = str(row[0]).strip()
        try:
            price = float(str(row[-1]).replace(",", ".").replace("€", "").strip())
        except ValueError:
            continue
        if identifier:
            key = identifier if match_by == "sku" else identifier.lower()
            lookup[key] = price

    return lookup


def _sheets_auth(cfg: dict):
    """Return Google API credentials from config."""
    sheets_cfg = cfg.get("cogsSheet", {})
    # Service account preferred
    sa_file = sheets_cfg.get("serviceAccountFile")
    if sa_file and Path(sa_file).exists():
        return SACredentials.from_service_account_file(
            sa_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
    # OAuth token fallback
    oauth = cfg.get("google", {})
    return OAuthCredentials(
        token=None,
        refresh_token=oauth.get("refreshToken"),
        client_id=oauth.get("clientId"),
        client_secret=oauth.get("clientSecret"),
        token_uri="https://oauth2.googleapis.com/token",
    )


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD.JSON
# ─────────────────────────────────────────────────────────────────────────────

def load_dashboard(path: str) -> dict:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {"store": "", "lastUpdated": "", "history": [], "products": {}}


def save_dashboard(dashboard: dict, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(dashboard, f, indent=2)


def upsert_day(dashboard: dict, date: str, day_data: dict):
    """Insert or update a day in history. Keeps last 90 days."""
    history = dashboard.get("history", [])
    # Remove existing entry for this date
    history = [d for d in history if d.get("date") != date]
    history.append({"date": date, **day_data})
    # Sort by date, keep last 90
    history.sort(key=lambda d: d["date"])
    dashboard["history"] = history[-90:]


def calc_net_profit(day: dict, cfg: dict, ad_spend: float) -> dict:
    """Merge ad spend into day data and calculate net profit."""
    revenue   = day["revenue"]
    cogs      = day["cogs"]
    tx_fees   = day["transactionFees"]
    ad_spend  = round(ad_spend, 2)

    # Shopify subscription prorated per day
    monthly_sub = cfg.get("costs", {}).get("shopifyMonthly", 39)
    sub_per_day = round(monthly_sub / 30, 2)

    gross_profit = revenue - cogs - ad_spend - tx_fees - sub_per_day
    roas = round(revenue / ad_spend, 2) if ad_spend > 0 else 0
    margin = round(gross_profit / revenue, 3) if revenue > 0 else 0

    # Apply default margin to unmatched COGS
    if cogs == 0 and revenue > 0:
        default_margin = cfg.get("costs", {}).get("defaultMarginPercent", 40) / 100
        cogs = round(revenue * (1 - default_margin), 2)
        gross_profit = revenue - cogs - ad_spend - tx_fees - sub_per_day
        margin = round(gross_profit / revenue, 3)

    return {
        "date": day.get("date", ""),
        "revenue": revenue,
        "orders": day["orders"],
        "cogs": cogs,
        "adSpend": ad_spend,
        "transactionFees": tx_fees,
        "shopifySubscription": sub_per_day,
        "netProfit": round(gross_profit, 2),
        "roas": roas,
        "margin": margin,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MIDAS P&L Sync")
    parser.add_argument("--config",   default="config.json",        help="Path to config.json")
    parser.add_argument("--output",   default="data/dashboard.json",help="Path to dashboard.json")
    parser.add_argument("--catalog",  default="data/products.json", help="Path to product catalog cache")
    parser.add_argument("--date",     default=None,                 help="Specific date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--backfill", action="store_true",          help="Fetch last 30 days (first run)")
    args = parser.parse_args()

    cfg       = load_config(args.config)
    dashboard = load_dashboard(args.output)
    dashboard["store"] = cfg["shopify"]["storeDomain"]

    today     = datetime.datetime.now(datetime.timezone.utc).date()
    yesterday = today - datetime.timedelta(days=1)

    if args.backfill or not dashboard["history"]:
        print("[MIDAS] First run or --backfill — fetching last 30 days")
        date_from = (today - datetime.timedelta(days=30)).isoformat()
        date_to   = yesterday.isoformat()
        dates = []
        d = datetime.date.fromisoformat(date_from)
        while d <= datetime.date.fromisoformat(date_to):
            dates.append(d.isoformat())
            d += datetime.timedelta(days=1)
    else:
        target = args.date or yesterday.isoformat()
        dates  = [target]

    # Load COGS sources and merge into unified lookup
    print("[MIDAS] Loading COGS from Google Sheets...")
    sheets_cogs   = sheets_load_cogs(cfg)
    print(f"[MIDAS] Sheets: {len(sheets_cogs)} entries")

    print("[MIDAS] Loading product catalog cache...")
    product_cache = load_product_cache(args.catalog)
    print(f"[MIDAS] Catalog: {len(product_cache)} products")

    lookup = build_combined_lookup(sheets_cogs, product_cache)
    print(f"[MIDAS] Combined lookup: {len(lookup)} entries")

    for date in dates:
        print(f"[MIDAS] Processing {date}...")

        orders = shopify_fetch_orders(cfg, date, date)
        day    = shopify_calc_day(orders, lookup, cfg, product_cache, args.catalog)
        day["date"] = date

        ad_spend = google_ads_fetch_spend(cfg, date, date)
        result   = calc_net_profit(day, cfg, ad_spend)

        upsert_day(dashboard, date, result)
        print(f"[MIDAS] {date} → revenue=€{result['revenue']} spend=€{result['adSpend']} "
              f"profit=€{result['netProfit']} roas={result['roas']}x "
              f"unmatched={day.get('unmatchedProducts', 0)}")

    # Product-level summary (last 7 days)
    recent      = dashboard["history"][-7:]
    product_agg = {}
    for day in recent:
        for pid, pdata in day.get("products", {}).items():
            if pid not in product_agg:
                product_agg[pid] = {
                    "title":      pdata["title"],
                    "sku":        pdata["sku"],
                    "productId":  pdata.get("productId", ""),
                    "revenue":    0, "cogs": 0, "units": 0,
                    "cogsSource": pdata.get("cogsSource", "unknown"),
                }
            product_agg[pid]["revenue"] += pdata["revenue"]
            product_agg[pid]["cogs"]    += pdata["cogs"]
            product_agg[pid]["units"]   += pdata["units"]

    # Flag products that still need COGS review
    needs_review = [
        p["title"] for p in product_cache.values()
        if p.get("needsReview") and p.get("cogs", 0) == 0
    ]
    if needs_review:
        print(f"[MIDAS] {len(needs_review)} products need COGS from supplier: "
              f"{', '.join(needs_review[:5])}")

    dashboard["products"]    = product_agg
    dashboard["needsReview"] = needs_review
    dashboard["lastUpdated"] = datetime.datetime.utcnow().isoformat() + "Z"

    save_dashboard(dashboard, args.output)
    print(f"[MIDAS] Done — {len(dashboard['history'])} days in history")


if __name__ == "__main__":
    main()
