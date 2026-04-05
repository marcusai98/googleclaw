#!/usr/bin/env python3
"""
FEED — Step 1: Gather performance data per product
Sources:
  - MIDAS dashboard.json   → ROAS per product (last 14 days)
  - Google Ads API         → spend per product (last 14 days)
  - Shopify Analytics API  → conversion rate per product page
"""

import requests
import json
import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# MIDAS — ROAS per product
# ─────────────────────────────────────────────────────────────────────────────

def get_midas_roas(dashboard_path: str, days: int = 14) -> dict:
    """
    Read MIDAS dashboard.json and return per-product ROAS for the last N days.
    Returns: {product_key: {"roas_week1": float, "roas_week2": float, "trend": "up"|"down"|"flat"}}
    """
    if not Path(dashboard_path).exists():
        print(f"[FEED/performance] dashboard.json not found at {dashboard_path}")
        return {}

    with open(dashboard_path) as f:
        dashboard = json.load(f)

    history  = dashboard.get("history", [])
    products = dashboard.get("products", {})
    cutoff   = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    # Build per-product revenue + ROAS from history days
    product_perf = {}

    # Week 1 = last 7 days, Week 2 = 7-14 days ago
    today      = datetime.date.today()
    week1_start = (today - datetime.timedelta(days=7)).isoformat()
    week2_start = (today - datetime.timedelta(days=14)).isoformat()

    for day in history:
        date = day.get("date", "")
        if date < cutoff:
            continue
        is_week1 = date >= week1_start

        for pid, pdata in day.get("products", {}).items():
            if pid not in product_perf:
                product_perf[pid] = {
                    "title":       pdata.get("title", ""),
                    "sku":         pdata.get("sku", ""),
                    "productId":   pdata.get("productId", ""),
                    "revenue_w1":  0, "cogs_w1":  0, "units_w1":  0,
                    "revenue_w2":  0, "cogs_w2":  0, "units_w2":  0,
                }
            key = "w1" if is_week1 else "w2"
            product_perf[pid][f"revenue_{key}"] += pdata.get("revenue", 0)
            product_perf[pid][f"cogs_{key}"]    += pdata.get("cogs", 0)
            product_perf[pid][f"units_{key}"]   += pdata.get("units", 0)

    return product_perf


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE ADS — spend per product (Shopping campaigns)
# ─────────────────────────────────────────────────────────────────────────────

def get_google_ads_spend(cfg: dict, days: int = 14) -> dict:
    """
    Fetch product-level ad spend from Google Ads Shopping campaigns.
    Returns: {product_id_or_title: {"spend_w1": float, "spend_w2": float}}
    """
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("[FEED/performance] google-ads library not installed — skipping")
        return {}

    ga_cfg = cfg.get("googleAds", {})
    if not ga_cfg.get("customerId"):
        return {}

    today       = datetime.date.today()
    week1_start = (today - datetime.timedelta(days=7)).isoformat()
    week2_start = (today - datetime.timedelta(days=14)).isoformat()
    week1_end   = (today - datetime.timedelta(days=1)).isoformat()
    week2_end   = (today - datetime.timedelta(days=8)).isoformat()

    client      = GoogleAdsClient.load_from_dict({
        "developer_token":  ga_cfg["developerToken"],
        "client_id":        ga_cfg["clientId"],
        "client_secret":    ga_cfg["clientSecret"],
        "refresh_token":    ga_cfg["refreshToken"],
        "use_proto_plus":   True,
    })
    customer_id = ga_cfg["customerId"].replace("-", "")
    ga_service  = client.get_service("GoogleAdsService")

    spend_data = {}

    for label, date_from, date_to in [
        ("w1", week1_start, week1_end),
        ("w2", week2_start, week2_end),
    ]:
        query = f"""
            SELECT
                shopping_performance_view.resource_name,
                segments.product_title,
                segments.product_item_id,
                metrics.cost_micros
            FROM shopping_performance_view
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
        """
        try:
            response = ga_service.search_stream(customer_id=customer_id, query=query)
            for batch in response:
                for row in batch.results:
                    title   = row.segments.product_title or ""
                    item_id = row.segments.product_item_id or ""
                    spend   = row.metrics.cost_micros / 1_000_000
                    key     = item_id or title.lower()[:40]
                    if key not in spend_data:
                        spend_data[key] = {"title": title, "spend_w1": 0, "spend_w2": 0}
                    spend_data[key][f"spend_{label}"] += spend
        except Exception as e:
            print(f"[FEED/performance] Google Ads query failed ({label}): {e}")

    return spend_data


# ─────────────────────────────────────────────────────────────────────────────
# SHOPIFY ANALYTICS — conversion rate per product page
# ─────────────────────────────────────────────────────────────────────────────

def get_shopify_conversion_rates(cfg: dict, days: int = 14) -> dict:
    """
    Fetch product page views + add-to-cart events from Shopify Analytics.
    Returns: {product_id: {"views_w1": int, "atc_w1": int, "cr_w1": float,
                            "views_w2": int, "atc_w2": int, "cr_w2": float}}
    """
    shopify_cfg = cfg.get("shopify", {})
    domain      = shopify_cfg.get("storeDomain", "")
    token       = shopify_cfg.get("accessToken", "")

    if not domain or not token:
        return {}

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    today   = datetime.date.today()
    results = {}

    for label, offset_start, offset_end in [("w1", 7, 1), ("w2", 14, 8)]:
        date_from = (today - datetime.timedelta(days=offset_start)).isoformat()
        date_to   = (today - datetime.timedelta(days=offset_end)).isoformat()

        # Use Shopify's product analytics endpoint
        try:
            r = requests.get(
                f"https://{domain}/admin/api/2024-01/reports.json",
                headers=headers,
                params={"since_id": 0, "limit": 50},
                timeout=15
            )
            # Shopify Analytics API is limited on non-Plus plans
            # Fall back to orders-based conversion estimate
        except Exception:
            pass

        # Orders-based fallback: orders per product / estimated sessions
        try:
            r = requests.get(
                f"https://{domain}/admin/api/2024-01/orders.json",
                headers=headers,
                params={
                    "status":             "any",
                    "financial_status":   "paid",
                    "created_at_min":     f"{date_from}T00:00:00Z",
                    "created_at_max":     f"{date_to}T23:59:59Z",
                    "limit":              250,
                    "fields":             "line_items",
                }, timeout=20
            )
            r.raise_for_status()
            for order in r.json().get("orders", []):
                for item in order.get("line_items", []):
                    pid = str(item.get("product_id", ""))
                    if not pid:
                        continue
                    if pid not in results:
                        results[pid] = {
                            "orders_w1": 0, "orders_w2": 0,
                            "units_w1":  0, "units_w2":  0,
                        }
                    results[pid][f"orders_{label}"] += 1
                    results[pid][f"units_{label}"]  += int(item.get("quantity", 1))
        except Exception as e:
            print(f"[FEED/performance] Shopify orders fetch failed ({label}): {e}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MERGE all performance data
# ─────────────────────────────────────────────────────────────────────────────

def merge_performance(midas: dict, ads: dict, shopify: dict) -> list:
    """
    Merge all 3 sources into one performance record per product.
    Returns list of product performance dicts.
    """
    merged = {}

    # Start with MIDAS products (most complete product info)
    for pid, m in midas.items():
        merged[pid] = {
            "key":         pid,
            "title":       m.get("title", ""),
            "sku":         m.get("sku", ""),
            "productId":   m.get("productId", ""),
            # Revenue
            "revenue_w1":  m.get("revenue_w1", 0),
            "revenue_w2":  m.get("revenue_w2", 0),
            # Spend (to be filled from ads)
            "spend_w1":    0,
            "spend_w2":    0,
            # Orders (to be filled from shopify)
            "orders_w1":   0,
            "orders_w2":   0,
        }

    # Merge Google Ads spend
    for key, a in ads.items():
        if key in merged:
            merged[key]["spend_w1"] = a.get("spend_w1", 0)
            merged[key]["spend_w2"] = a.get("spend_w2", 0)
        else:
            # Product in ads but not in MIDAS
            merged[key] = {
                "key": key, "title": a.get("title", ""), "sku": "", "productId": "",
                "revenue_w1": 0, "revenue_w2": 0,
                "spend_w1": a.get("spend_w1", 0), "spend_w2": a.get("spend_w2", 0),
                "orders_w1": 0, "orders_w2": 0,
            }

    # Merge Shopify orders
    for pid, s in shopify.items():
        if pid in merged:
            merged[pid]["orders_w1"] = s.get("orders_w1", 0)
            merged[pid]["orders_w2"] = s.get("orders_w2", 0)

    # Calculate derived metrics
    results = []
    for pid, p in merged.items():
        roas_w1 = round(p["revenue_w1"] / p["spend_w1"], 2) if p["spend_w1"] > 0 else 0
        roas_w2 = round(p["revenue_w2"] / p["spend_w2"], 2) if p["spend_w2"] > 0 else 0

        # Conversion rate (orders / estimated sessions — rough proxy)
        # True CR needs Shopify Analytics Plus; this is order-based signal
        cr_w1 = p["orders_w1"]  # use order count as demand signal
        cr_w2 = p["orders_w2"]

        cr_declining = cr_w1 < cr_w2 * 0.8  # >20% drop in orders

        p.update({
            "roas_w1":      roas_w1,
            "roas_w2":      roas_w2,
            "roas_declining": roas_w1 < roas_w2,
            "cr_w1":        cr_w1,
            "cr_w2":        cr_w2,
            "cr_declining": cr_declining,
            "low_roas":     roas_w1 < 1.5 and roas_w2 < 1.5 and roas_w1 > 0 and roas_w2 > 0,
        })
        results.append(p)

    return results
