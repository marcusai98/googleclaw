#!/usr/bin/env python3
"""
LISTER — Step 5: Shopify Publish
Builds the full Shopify product payload and creates it via Admin API.
- Status: active (live) or draft, based on config
- All sales channels included
- Single default variant (Shopify manages inventory, supplier fulfills manually)
- Full metadata: SEO, collections, tags

CJ is not used here. All candidate data comes from SCOUT.
Variants are created as a clean single-variant product — the seller
can add size/color variants manually in Shopify if needed.
"""

import requests
import base64
from io import BytesIO


def get_shopify_token(cfg: dict) -> str:
    """Get or refresh Shopify access token."""
    shopify_cfg = cfg.get("shopify", {})
    token       = shopify_cfg.get("accessToken", "")
    if token:
        return token

    # OAuth client credentials flow (auto-refresh)
    domain        = shopify_cfg.get("storeDomain", "")
    client_id     = shopify_cfg.get("clientId", "")
    client_secret = shopify_cfg.get("clientSecret", "")
    if client_id and client_secret:
        r = requests.post(
            f"https://{domain}/admin/oauth/access_token",
            json={"client_id": client_id, "client_secret": client_secret,
                  "grant_type": "client_credentials"},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("access_token", "")
    return ""


def build_variant(price: float, compare_at: float | None) -> list:
    """
    Build a single default Shopify variant.
    Variants (size/color) can be added manually in Shopify after listing.
    """
    return [{
        "price":                str(round(price, 2)),
        "compare_at_price":     str(round(compare_at, 2)) if compare_at else None,
        "inventory_management": "shopify",
        "fulfillment_service":  "manual",
        "requires_shipping":    True,
        "taxable":              True,
        "inventory_quantity":   99,
    }]


def upload_image(domain: str, token: str, image: dict, product_id: int, position: int) -> bool:
    """Upload a single image to a Shopify product."""
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    url     = f"https://{domain}/admin/api/2024-01/products/{product_id}/images.json"

    src = image.get("src", "")
    alt = image.get("alt", "")

    # Handle base64 data URIs (Gemini-generated)
    if src.startswith("data:"):
        try:
            header, b64data = src.split(",", 1)
            mime = header.split(":")[1].split(";")[0]
            payload = {
                "image": {
                    "attachment": b64data,
                    "filename":   f"product-image-{position}.jpg",
                    "alt":        alt,
                    "position":   position,
                }
            }
        except Exception as e:
            print(f"[LISTER/publish] Image parse error: {e}")
            return False
    else:
        payload = {
            "image": {
                "src":      src,
                "alt":      alt,
                "position": position,
            }
        }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code in (200, 201):
            return True
        print(f"[LISTER/publish] Image upload failed ({r.status_code}): {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[LISTER/publish] Image upload error: {e}")
        return False


def ensure_collection(domain: str, token: str, title: str) -> int | None:
    """Get or create a custom collection by title. Returns collection ID."""
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    # Search for existing
    r = requests.get(
        f"https://{domain}/admin/api/2024-01/custom_collections.json",
        headers=headers, params={"title": title}, timeout=15
    )
    cols = r.json().get("custom_collections", [])
    if cols:
        return cols[0]["id"]

    # Create
    r = requests.post(
        f"https://{domain}/admin/api/2024-01/custom_collections.json",
        headers=headers,
        json={"custom_collection": {"title": title, "published": True}},
        timeout=15
    )
    if r.status_code in (200, 201):
        return r.json()["custom_collection"]["id"]
    return None


def add_to_collections(domain: str, token: str, product_id: int, collection_titles: list):
    """Add product to all detected collections."""
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    for title in collection_titles:
        col_id = ensure_collection(domain, token, title)
        if not col_id:
            continue
        requests.post(
            f"https://{domain}/admin/api/2024-01/collects.json",
            headers=headers,
            json={"collect": {"product_id": product_id, "collection_id": col_id}},
            timeout=15
        )
        print(f"[LISTER/publish] Added to collection: {title}")


def publish(candidate: dict, pricing: dict, copy: dict, images: list,
            collection_data: dict, cfg: dict) -> dict:
    """
    Create the Shopify product and return result dict.
    """
    shopify_cfg = cfg.get("shopify", {})
    domain      = shopify_cfg.get("storeDomain", "")
    token       = get_shopify_token(cfg)
    status      = cfg.get("lister", {}).get("publishStatus", "active")  # "active" or "draft"

    if not domain or not token:
        raise ValueError("[LISTER/publish] Missing Shopify domain or token")

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    price      = pricing["price"]
    compare_at = pricing.get("compareAtPrice")

    # Build single default variant
    variants = build_variant(price, compare_at)

    # Build product payload
    product_payload = {
        "product": {
            "title":            copy["title"],
            "body_html":        copy["description"],
            "vendor":           copy.get("vendor", "Imported"),
            "product_type":     copy.get("productType", ""),
            "tags":             ", ".join(collection_data["tags"]),
            "status":           status,
            "variants":         variants,
            "options":          [],
            "metafields": [
                {
                    "namespace": "seo",
                    "key":       "title",
                    "value":     copy.get("metaTitle", copy["title"])[:60],
                    "type":      "single_line_text_field",
                },
                {
                    "namespace": "seo",
                    "key":       "description",
                    "value":     copy.get("metaDescription", "")[:160],
                    "type":      "single_line_text_field",
                },
            ],
        }
    }

    # Create product
    url = f"https://{domain}/admin/api/2024-01/products.json"
    r   = requests.post(url, headers=headers, json=product_payload, timeout=30)

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Shopify product creation failed ({r.status_code}): {r.text[:300]}")

    product = r.json()["product"]
    product_id = product["id"]
    print(f"[LISTER/publish] Product created: ID {product_id} — '{copy['title']}'")

    # Upload images
    for i, img in enumerate(images, 1):
        success = upload_image(domain, token, img, product_id, i)
        if success:
            print(f"[LISTER/publish] Image {i}/{len(images)} uploaded ({img['source']})")

    # Add to collections
    add_to_collections(domain, token, product_id, collection_data["collections"])

    return {
        "shopifyProductId": product_id,
        "shopifyUrl":       f"https://{domain}/admin/products/{product_id}",
        "storefrontUrl":    f"https://{domain}/products/{product['handle']}",
        "title":            copy["title"],
        "price":            price,
        "status":           status,
        "variantCount":     len(variants),
        "imageCount":       len(images),
        "collections":      collection_data["collections"],
    }
