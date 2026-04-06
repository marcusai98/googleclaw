#!/usr/bin/env python3
"""
SCOUT — Method 1: CJ Dropshipping
Searches CJ for products matching trend keywords.
Returns: product name, CJ price, shipping time, stock, product URL.
"""

import requests
import time
from typing import Optional


CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"


def get_access_token(email: str, password: str) -> Optional[str]:
    r = requests.post(f"{CJ_BASE}/authentication/getAccessToken", json={
        "email": email, "password": password
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("result"):
        return data["data"]["accessToken"]
    return None


def search_products(keyword: str, token: str, limit: int = 20) -> list:
    """Search CJ products by keyword. Returns raw product list."""
    r = requests.get(f"{CJ_BASE}/product/list", headers={
        "CJ-Access-Token": token
    }, params={
        "productNameEn": keyword,
        "pageNum": 1,
        "pageSize": limit,
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("list", [])


def parse_product(raw: dict) -> dict:
    """
    Normalize a CJ product to SCOUT candidate format.
    Captures full variant structure (name, SKU, price) so LISTER can build
    proper Shopify variants without needing to re-call CJ.
    """
    raw_variants = raw.get("variants", []) or []
    prices       = [float(v.get("variantSellPrice", 0)) for v in raw_variants if v.get("variantSellPrice")]
    min_price    = min(prices) if prices else 0.0
    max_price    = max(prices) if prices else 0.0

    # Normalize variant list for downstream use by LISTER
    cj_variants = []
    seen_names  = set()
    for v in raw_variants:
        name  = (v.get("variantNameEn") or v.get("variantSku") or "").strip()
        sku   = (v.get("variantSku") or "").strip()
        price = float(v.get("variantSellPrice", 0) or 0)
        img   = (v.get("variantImage") or "").strip()

        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        cj_variants.append({
            "name":   name,
            "sku":    sku,
            "price":  round(price, 2),
            "image":  img,
        })

    ship_time = raw.get("deliveryTime", "") or ""
    try:
        days = int(str(ship_time).split("-")[-1].strip().split(" ")[0])
    except (ValueError, IndexError):
        days = 99

    return {
        "title":              raw.get("productNameEn", ""),
        "source":             "cj",
        "cjProductId":        raw.get("pid", ""),
        "cjUrl":              raw.get("productUrl", ""),
        "cjPrice":            round(min_price, 2),   # lowest variant price (cost floor reference)
        "cjPriceMax":         round(max_price, 2),   # highest variant price
        "cjVariants":         cj_variants,           # full variant list → passed to LISTER
        "estimatedShipping":  days,
        "inStock":            raw.get("productStatus", "") == "PRODUCT_VALID",
        "imageUrl":           raw.get("productImage", ""),
        "category":           raw.get("categoryName", ""),
    }


def fetch(trends: list, cfg: dict, limit_per_trend: int = 5) -> list:
    """
    For each trend in trends.json, search CJ and return candidates.
    trends: list of {name, keywords, volume, ...} from trends.json
    """
    cj_cfg = cfg.get("cj", {})
    email  = cj_cfg.get("email", "")
    pw     = cj_cfg.get("password", "")

    if not email or not pw:
        print("[SCOUT/CJ] No CJ credentials in config — skipping")
        return []

    try:
        token = get_access_token(email, pw)
    except Exception as e:
        print(f"[SCOUT/CJ] Auth failed: {e}")
        return []

    candidates = []
    min_price  = cfg.get("scout", {}).get("minSellingPrice", 40)

    for trend in trends:
        keywords = trend.get("keywords", [trend.get("name", "")])
        for kw in keywords[:2]:  # max 2 keywords per trend to avoid rate limits
            try:
                raw_products = search_products(kw, token, limit=limit_per_trend * 2)
                for raw in raw_products:
                    p = parse_product(raw)
                    if not p["title"]:
                        continue
                    # Hard filter: out of stock entirely
                    if not p["inStock"]:
                        continue
                    p["matchedTrend"]  = trend["name"]
                    p["trendVolume"]   = trend.get("monthlyVolume", 0)
                    p["trendScore"]    = trend.get("score", 0)
                    candidates.append(p)
                time.sleep(0.5)  # rate limit courtesy
            except Exception as e:
                print(f"[SCOUT/CJ] Error fetching '{kw}': {e}")
                continue

    print(f"[SCOUT/CJ] Found {len(candidates)} raw candidates")
    return candidates
