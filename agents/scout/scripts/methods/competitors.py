#!/usr/bin/env python3
"""
SCOUT — Method 3: Competitor store scraping
Reads products from competitor Shopify stores via /products.json (public endpoint).
Returns: product title, price, handle, image.
All Shopify stores expose /products.json — no scraping/auth needed.
"""

import requests
import time
from urllib.parse import urlparse


def fetch_shopify_products(store_url: str, limit: int = 50) -> list:
    """
    Fetch products from a Shopify store's public /products.json endpoint.
    Works on any Shopify store regardless of theme or privacy settings.
    """
    # Normalize URL
    parsed = urlparse(store_url)
    base   = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path.strip('/')}"
    url    = f"{base}/products.json"

    try:
        r = requests.get(url, params={"limit": limit}, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; product-research-bot/1.0)"
        })
        if r.status_code == 200:
            return r.json().get("products", [])
        print(f"[SCOUT/Competitors] {store_url} returned {r.status_code}")
        return []
    except Exception as e:
        print(f"[SCOUT/Competitors] Failed to fetch {store_url}: {e}")
        return []


def parse_product(raw: dict, store_url: str, trend: dict) -> dict:
    """Normalize a Shopify product to SCOUT candidate format."""
    title    = raw.get("title", "")
    handle   = raw.get("handle", "")
    variants = raw.get("variants", [])
    prices   = [float(v.get("price", 0)) for v in variants if v.get("price")]
    min_price = min(prices) if prices else 0.0
    max_price = max(prices) if prices else 0.0

    image = ""
    images = raw.get("images", [])
    if images:
        image = images[0].get("src", "")

    return {
        "title":          title,
        "source":         "competitor",
        "competitorUrl":  f"{store_url.rstrip('/')}/products/{handle}",
        "competitorStore": store_url,
        "competitorPrice": round(min_price, 2),
        "competitorPriceMax": round(max_price, 2),
        "imageUrl":       image,
        "matchedTrend":   trend["name"],
        "trendVolume":    trend.get("monthlyVolume", 0),
        "trendScore":     trend.get("score", 0),
    }


def match_trend(title: str, description: str, trend: dict) -> bool:
    """Check if a competitor product matches a trend keyword."""
    keywords  = trend.get("keywords", [trend.get("name", "").lower()])
    title_l   = title.lower()
    desc_l    = (description or "").lower()

    for kw in keywords:
        kw_l = kw.lower()
        if kw_l in title_l or kw_l in desc_l:
            return True
        # Partial word match (e.g. "zonnebril" matches "zonnebrillen")
        if len(kw_l) > 5 and (kw_l[:6] in title_l or kw_l[:6] in desc_l):
            return True
    return False


def fetch(trends: list, cfg: dict, limit_per_trend: int = 5) -> list:
    """
    Fetch products from all configured competitor stores.
    Filter to only products matching a trend keyword.
    """
    competitor_urls = cfg.get("scout", {}).get("competitors", {}).get("urls", [])
    min_price       = cfg.get("scout", {}).get("minSellingPrice", 40)

    if not competitor_urls:
        print("[SCOUT/Competitors] No competitor URLs in config — skipping")
        return []

    # Fetch all competitor products once (avoid re-fetching per trend)
    all_competitor_products = []
    for store_url in competitor_urls:
        print(f"[SCOUT/Competitors] Fetching {store_url}...")
        products = fetch_shopify_products(store_url, limit=100)
        for p in products:
            all_competitor_products.append((store_url, p))
        time.sleep(1.0)

    print(f"[SCOUT/Competitors] Total products across all stores: {len(all_competitor_products)}")

    # Match against trends
    candidates = []
    seen_titles = set()

    for trend in trends:
        matched = 0
        for store_url, raw in all_competitor_products:
            title = raw.get("title", "")
            desc  = raw.get("body_html", "")

            if not match_trend(title, desc, trend):
                continue

            # Hard filter: price too low
            variants = raw.get("variants", [])
            prices   = [float(v.get("price", 0)) for v in variants if v.get("price")]
            max_p    = max(prices) if prices else 0
            if max_p > 0 and max_p < min_price:
                continue

            # Dedup across trends
            key = title.lower()[:40]
            if key in seen_titles:
                # Still record which trend it matched, for multi-source merge
                continue
            seen_titles.add(key)

            p = parse_product(raw, store_url, trend)
            candidates.append(p)
            matched += 1
            if matched >= limit_per_trend * 3:
                break

    print(f"[SCOUT/Competitors] Found {len(candidates)} trend-matching candidates")
    return candidates
