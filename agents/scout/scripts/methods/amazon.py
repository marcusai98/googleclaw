#!/usr/bin/env python3
"""
SCOUT — Method 2: Amazon via Apify
Searches Amazon for products matching trend keywords using the Apify
Amazon Product Scraper actor (apify/amazon-product-scraper).

No Amazon Associate account needed. Just an Apify token.
Returns: title, price, BSR, review count, rating, product URL.
Used for: demand proof + selling price ceiling.
"""

import json
import time
import urllib.request
import urllib.error
from typing import Optional

APIFY_BASE  = "https://api.apify.com/v2"
ACTOR_ID    = "apify~amazon-product-scraper"

# Amazon domain per market
AMAZON_DOMAIN_MAP = {
    "NL": "amazon.nl",
    "DE": "amazon.de",
    "UK": "amazon.co.uk",
    "US": "amazon.com",
    "FR": "amazon.fr",
    "BE": "amazon.com.be",
    "ES": "amazon.es",
    "IT": "amazon.it",
}


def _apify_run(token: str, input_data: dict, timeout_secs: int = 90) -> list:
    """
    Run an Apify actor synchronously and return dataset items.
    Uses run-sync-get-dataset-items for clean one-call execution.
    """
    url = (
        f"{APIFY_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items"
        f"?token={token}&timeout={timeout_secs}&memory=256"
    )
    payload = json.dumps(input_data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_secs + 15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"[SCOUT/Amazon/Apify] HTTP {e.code}: {body}")
        return []
    except Exception as e:
        print(f"[SCOUT/Amazon/Apify] Request failed: {e}")
        return []


def parse_item(raw: dict, keyword: str, trend: dict) -> Optional[dict]:
    """Normalize an Apify Amazon scraper result to SCOUT candidate format."""
    try:
        title = raw.get("productName") or raw.get("name") or ""
        if not title:
            return None

        asin  = raw.get("asin") or ""
        url   = raw.get("url") or (f"https://amazon.com/dp/{asin}" if asin else "")

        # Price — multiple possible fields depending on actor version
        price = 0.0
        for field in ("price", "currentPrice", "priceAmount"):
            raw_price = raw.get(field)
            if raw_price:
                try:
                    price = float(str(raw_price).replace("€", "").replace("$", "").replace(",", ".").strip())
                    break
                except ValueError:
                    pass

        # BSR — lower is better
        bsr = raw.get("bestSellerRank") or raw.get("bsrRank") or 999999
        try:
            bsr = int(str(bsr).replace(",", "").replace(".", "").strip())
        except (ValueError, TypeError):
            bsr = 999999

        # Reviews
        review_count = 0
        for field in ("reviewsCount", "ratingsTotal", "numberOfRatings"):
            val = raw.get(field)
            if val:
                try:
                    review_count = int(str(val).replace(",", ""))
                    break
                except (ValueError, TypeError):
                    pass

        # Rating
        rating = 0.0
        for field in ("stars", "rating", "starRating"):
            val = raw.get(field)
            if val:
                try:
                    rating = float(str(val).replace(",", "."))
                    break
                except (ValueError, TypeError):
                    pass

        image = raw.get("thumbnailImage") or raw.get("image") or ""

        return {
            "title":         title,
            "source":        "amazon",
            "amazonAsin":    asin,
            "amazonUrl":     url,
            "amazonPrice":   round(price, 2),
            "amazonBsr":     bsr,
            "reviewCount":   review_count,
            "rating":        round(rating, 1),
            "imageUrl":      image,
            "matchedTrend":  trend["name"],
            "trendVolume":   trend.get("monthlyVolume", 0),
            "trendScore":    trend.get("score", 0),
        }
    except Exception as e:
        print(f"[SCOUT/Amazon/Apify] parse_item error: {e}")
        return None


def fetch(trends: list, cfg: dict, limit_per_trend: int = 5) -> list:
    """
    For each trend, search Amazon via Apify and return candidates.
    Batches keywords to minimise Apify actor runs (= cost).
    """
    apify_token = cfg.get("apify", {}).get("token", "")
    if not apify_token:
        print("[SCOUT/Amazon/Apify] No Apify token in config — skipping")
        return []

    market     = cfg.get("store", {}).get("market", "NL").upper()[:2]
    domain     = AMAZON_DOMAIN_MAP.get(market, "amazon.com")
    min_price  = cfg.get("scout", {}).get("minSellingPrice", 40)

    # Collect keywords across all trends (deduplicated, max 2 per trend)
    keyword_to_trends: dict = {}
    for trend in trends:
        keywords = trend.get("keywords", [trend.get("name", "")])
        for kw in keywords[:2]:
            kw_clean = kw.strip()
            if not kw_clean:
                continue
            if kw_clean not in keyword_to_trends:
                keyword_to_trends[kw_clean] = []
            keyword_to_trends[kw_clean].append(trend)

    if not keyword_to_trends:
        print("[SCOUT/Amazon/Apify] No keywords to search")
        return []

    # Build Apify input — batch all keywords in one run to save cost
    queries = [
        {"searchQuery": kw, "domain": domain}
        for kw in list(keyword_to_trends.keys())[:20]   # cap at 20 keywords per run
    ]

    input_data = {
        "queries":          queries,
        "maxItemsPerSearch": limit_per_trend * 2,
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"]
        }
    }

    print(f"[SCOUT/Amazon/Apify] Running actor for {len(queries)} keywords on {domain}...")
    raw_items = _apify_run(apify_token, input_data)
    print(f"[SCOUT/Amazon/Apify] Actor returned {len(raw_items)} raw items")

    # Map items back to trend(s)
    candidates = []
    for raw in raw_items:
        # Determine which keyword triggered this item
        search_query = raw.get("searchQuery") or raw.get("keyword") or ""
        matched_trends = keyword_to_trends.get(search_query, [])

        # Fallback: try to match by title keywords
        if not matched_trends:
            for kw, t_list in keyword_to_trends.items():
                if kw.lower() in (raw.get("productName") or "").lower():
                    matched_trends = t_list
                    break
        if not matched_trends:
            matched_trends = [trends[0]] if trends else []

        for trend in matched_trends[:1]:  # attach to first matching trend
            item = parse_item(raw, search_query, trend)
            if not item:
                continue
            # Hard filter: price too low (if price is known)
            if 0 < item["amazonPrice"] < min_price:
                continue
            candidates.append(item)

    print(f"[SCOUT/Amazon/Apify] {len(candidates)} candidates after filtering")
    return candidates
