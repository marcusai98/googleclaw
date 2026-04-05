#!/usr/bin/env python3
"""
SCOUT — Method 2: Amazon Product Advertising API
Searches Amazon for products matching trend keywords.
Returns: title, ASIN, BSR, price, review count, product URL.
Used for: demand proof (BSR) and selling price ceiling.
"""

import requests
import time
import hmac
import hashlib
import datetime
from typing import Optional


AMAZON_HOST  = "webservices.amazon.{marketplace}"
AMAZON_REGION_MAP = {
    "NL": ("nl", "eu-west-1"),
    "DE": ("de", "eu-west-1"),
    "UK": ("co.uk", "eu-west-1"),
    "US": ("com", "us-east-1"),
    "FR": ("fr", "eu-west-1"),
}


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret: str, date: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret).encode("utf-8"), date)
    k = _sign(k, region)
    k = _sign(k, service)
    k = _sign(k, "aws4_request")
    return k


def search_items(keyword: str, cfg: dict, marketplace: str = "NL") -> list:
    """
    Search Amazon PA-API for products matching keyword.
    Uses SearchItems endpoint.
    """
    try:
        import paapi5_python_sdk as paapi
    except ImportError:
        print("[SCOUT/Amazon] paapi5-python-sdk not installed — pip install paapi5-python-sdk")
        return []

    tld, region = AMAZON_REGION_MAP.get(marketplace, ("com", "us-east-1"))
    amz_cfg     = cfg.get("amazon", {})
    access_key  = amz_cfg.get("accessKey", "")
    secret_key  = amz_cfg.get("secretKey", "")
    partner_tag = amz_cfg.get("partnerTag", "")

    if not access_key or not partner_tag:
        print("[SCOUT/Amazon] No Amazon PA-API credentials in config — skipping")
        return []

    try:
        from paapi5_python_sdk.api.default_api import DefaultApi
        from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
        from paapi5_python_sdk.models.partner_type import PartnerType
        from paapi5_python_sdk.models.search_index import SearchIndex

        client = DefaultApi(
            access_key=access_key,
            secret_key=secret_key,
            host=f"webservices.amazon.{tld}",
            region=region,
        )

        req = SearchItemsRequest(
            partner_tag=partner_tag,
            partner_type=PartnerType.ASSOCIATES,
            keywords=keyword,
            search_index=SearchIndex.ALL,
            item_count=10,
            resources=[
                "ItemInfo.Title",
                "Offers.Listings.Price",
                "BrowseNodeInfo.BrowseNodes.SalesRank",
                "CustomerReviews.Count",
                "CustomerReviews.StarRating",
                "Images.Primary.Large",
            ]
        )

        resp = client.search_items(req)
        return resp.search_result.items if resp.search_result else []

    except Exception as e:
        print(f"[SCOUT/Amazon] Search failed for '{keyword}': {e}")
        return []


def parse_item(item, keyword: str, trend: dict) -> Optional[dict]:
    """Normalize Amazon PA-API item to SCOUT candidate format."""
    try:
        title = item.item_info.title.display_value if item.item_info else ""
        asin  = item.asin or ""

        # Price
        price = 0.0
        try:
            price = float(item.offers.listings[0].price.amount)
        except Exception:
            pass

        # BSR
        bsr = 999999
        try:
            nodes = item.browse_node_info.browse_nodes
            if nodes:
                ranks = [n.sales_rank for n in nodes if n.sales_rank]
                bsr   = min(ranks) if ranks else 999999
        except Exception:
            pass

        # Reviews
        review_count = 0
        try:
            review_count = item.customer_reviews.count or 0
        except Exception:
            pass

        return {
            "title":         title,
            "source":        "amazon",
            "amazonAsin":    asin,
            "amazonUrl":     f"https://www.amazon.com/dp/{asin}",
            "amazonPrice":   round(price, 2),
            "amazonBsr":     bsr,
            "reviewCount":   review_count,
            "matchedTrend":  trend["name"],
            "trendVolume":   trend.get("monthlyVolume", 0),
            "trendScore":    trend.get("score", 0),
        }
    except Exception:
        return None


def fetch(trends: list, cfg: dict, limit_per_trend: int = 5) -> list:
    """
    For each trend, search Amazon and return candidates.
    """
    marketplace = cfg.get("store", {}).get("market", "NL").upper()
    candidates  = []
    min_price   = cfg.get("scout", {}).get("minSellingPrice", 40)

    for trend in trends:
        keywords = trend.get("keywords", [trend.get("name", "")])
        for kw in keywords[:2]:
            items = search_items(kw, cfg, marketplace)
            for item in items:
                p = parse_item(item, kw, trend)
                if not p or not p["title"]:
                    continue
                # Hard filter: price too low (if detectable)
                if 0 < p["amazonPrice"] < min_price:
                    continue
                candidates.append(p)
            time.sleep(1.0)  # Amazon PA-API rate limit: 1 req/sec

    print(f"[SCOUT/Amazon] Found {len(candidates)} raw candidates")
    return candidates
