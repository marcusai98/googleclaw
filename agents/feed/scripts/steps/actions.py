#!/usr/bin/env python3
"""
FEED — Step 3: Execute optimizations
Actions:
  1. Draft product (if all 3 draft conditions met)
  2. Reduce price by €5 (floor: CJ price × 2.0)
  3. Add new Gemini images
  4. Fill missing product fields
"""

import requests
import json
import time
import datetime


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"


# ─────────────────────────────────────────────────────────────────────────────
# SHOPIFY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_shopify_product(domain: str, token: str, product_id: str) -> dict:
    """Fetch full Shopify product by ID."""
    r = requests.get(
        f"https://{domain}/admin/api/2024-01/products/{product_id}.json",
        headers={"X-Shopify-Access-Token": token},
        timeout=15
    )
    if r.status_code == 200:
        return r.json().get("product", {})
    return {}


def update_shopify_product(domain: str, token: str, product_id: str, payload: dict) -> bool:
    """PATCH a Shopify product."""
    r = requests.put(
        f"https://{domain}/admin/api/2024-01/products/{product_id}.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"product": payload},
        timeout=15
    )
    return r.status_code in (200, 201)


def get_all_active_products(domain: str, token: str) -> list:
    """Fetch all active Shopify products."""
    headers  = {"X-Shopify-Access-Token": token}
    products = []
    url      = f"https://{domain}/admin/api/2024-01/products.json"
    params   = {"status": "active", "limit": 250,
                 "fields": "id,title,variants,images,tags,product_type,body_html,metafields"}

    while url:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        products.extend(r.json().get("products", []))
        link   = r.headers.get("Link", "")
        url    = None
        params = {}
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")

    return products


# ─────────────────────────────────────────────────────────────────────────────
# ACTION 1: Draft product
# ─────────────────────────────────────────────────────────────────────────────

def draft_product(domain: str, token: str, product_id: str, reason: str) -> bool:
    """Set product status to draft."""
    success = update_shopify_product(domain, token, product_id, {
        "status": "draft",
        "tags":   f"feed-drafted, feed-drafted-{datetime.date.today().isoformat()}"
    })
    if success:
        print(f"[FEED/actions] Drafted product {product_id}: {reason}")
    return success


# ─────────────────────────────────────────────────────────────────────────────
# ACTION 2: Reduce price
# ─────────────────────────────────────────────────────────────────────────────

def reduce_price(domain: str, token: str, product: dict,
                 cfg: dict, cogs_lookup: dict) -> dict | None:
    """
    Reduce all variant prices by €5, respecting CJ price × 2.0 floor.
    Returns updated variant list or None if no change made.
    """
    reduction   = cfg.get("feed", {}).get("priceReduction", 5.0)
    floor_multi = cfg.get("feed", {}).get("priceFloorMultiplier", 2.0)

    variants     = product.get("variants", [])
    updated      = []
    any_changed  = False

    for v in variants:
        current_price = float(v.get("price", 0))
        sku           = v.get("sku", "").lower()

        # Determine CJ floor price
        cj_price  = cogs_lookup.get(sku, cogs_lookup.get(product.get("title", "").lower(), 0))
        floor     = round(cj_price * floor_multi, 2) if cj_price > 0 else 0

        new_price = round(current_price - reduction, 2)

        if floor > 0 and new_price < floor:
            print(f"[FEED/actions] Price floor hit for '{product.get('title')}' "
                  f"(€{new_price} < floor €{floor}) — skipping reduction")
            updated.append({"id": v["id"], "price": str(current_price)})
            continue

        if new_price < 1:
            print(f"[FEED/actions] Price would go below €1 — skipping")
            updated.append({"id": v["id"], "price": str(current_price)})
            continue

        updated.append({"id": v["id"], "price": str(new_price)})
        any_changed = True
        print(f"[FEED/actions] Price: €{current_price} → €{new_price} (floor: €{floor or 'none'})")

    if not any_changed:
        return None

    success = update_shopify_product(domain, token, product["id"], {"variants": updated})
    return updated if success else None


# ─────────────────────────────────────────────────────────────────────────────
# ACTION 3: Add Gemini images
# ─────────────────────────────────────────────────────────────────────────────

def generate_and_upload_images(domain: str, token: str,
                                product: dict, cfg: dict, count: int = 2) -> int:
    """Generate new lifestyle images with Gemini and upload to product."""
    gemini_key = cfg.get("gemini", {}).get("apiKey", "")
    if not gemini_key:
        print("[FEED/actions] No Gemini key — skipping image refresh")
        return 0

    title    = product.get("title", "product")
    headers  = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    uploaded = 0

    prompts = [
        f"Fresh lifestyle product photo of {title}, natural daylight, modern minimalist setting, high quality e-commerce photography",
        f"Editorial fashion photo of {title}, trendy aesthetic, soft background, professional product photography",
    ]

    for i, prompt in enumerate(prompts[:count]):
        try:
            r = requests.post(
                f"{GEMINI_API}?key={gemini_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
                },
                timeout=60
            )
            r.raise_for_status()
            parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])

            for part in parts:
                if "inlineData" in part:
                    b64data = part["inlineData"]["data"]
                    # Upload to Shopify
                    img_r = requests.post(
                        f"https://{domain}/admin/api/2024-01/products/{product['id']}/images.json",
                        headers=headers,
                        json={"image": {
                            "attachment": b64data,
                            "filename":   f"feed-refresh-{datetime.date.today().isoformat()}-{i+1}.jpg",
                            "alt":        title,
                        }},
                        timeout=30
                    )
                    if img_r.status_code in (200, 201):
                        uploaded += 1
                        print(f"[FEED/actions] New image uploaded for '{title}'")
            time.sleep(2)
        except Exception as e:
            print(f"[FEED/actions] Image generation failed: {e}")

    return uploaded


# ─────────────────────────────────────────────────────────────────────────────
# ACTION 4: Fill missing fields
# ─────────────────────────────────────────────────────────────────────────────

def fill_missing_fields(domain: str, token: str, product: dict, cfg: dict) -> bool:
    """Fill any missing Shopify product fields using GPT."""
    missing = {}

    if not product.get("body_html"):
        missing["needs_description"] = True
    if not product.get("product_type"):
        missing["needs_product_type"] = True
    if not product.get("tags"):
        missing["needs_tags"] = True

    if not missing:
        return False

    api_key = cfg.get("openai", {}).get("apiKey", "")
    if not api_key:
        return False

    title    = product.get("title", "")
    lang     = cfg.get("store", {}).get("language", "Dutch")
    to_fill  = ", ".join(k.replace("needs_", "") for k in missing)

    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content":
                    f"Fill missing Shopify product fields for: '{title}'\n"
                    f"Language: {lang}\nNeeded: {to_fill}\n"
                    f"Return JSON only: {{\"body_html\": \"...\", \"product_type\": \"...\", \"tags\": \"...\"}}"
                }],
                "max_tokens": 500,
                "temperature": 0.4,
            }, timeout=20)
        r.raise_for_status()
        raw  = r.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json")
        data = json.loads(raw)

        patch = {}
        if missing.get("needs_description") and data.get("body_html"):
            patch["body_html"] = data["body_html"]
        if missing.get("needs_product_type") and data.get("product_type"):
            patch["product_type"] = data["product_type"]
        if missing.get("needs_tags") and data.get("tags"):
            patch["tags"] = data["tags"]

        if patch:
            update_shopify_product(domain, token, product["id"], patch)
            print(f"[FEED/actions] Filled missing fields for '{title}': {list(patch.keys())}")
            return True

    except Exception as e:
        print(f"[FEED/actions] Fill missing fields failed: {e}")

    return False
