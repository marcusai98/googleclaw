#!/usr/bin/env python3
"""
LISTER — Step 4: Collections & Tagging
Auto-assigns collections and enriches tags based on:
- Product type (from copy.py)
- Trend keyword
- Season/occasion
- Category from CJ
Shopify smart collections pick up products automatically via tags.
"""

import datetime


# Keyword → collection mapping (Dutch + English keywords)
COLLECTION_MAP = {
    # Jurken / Dresses
    "jurk": "Jurken", "dress": "Jurken", "maxi jurk": "Jurken",
    "midi jurk": "Jurken", "kant jurk": "Jurken", "bloemenjurk": "Jurken",

    # Tops / Blouses
    "blouse": "Tops & Blouses", "top": "Tops & Blouses", "kant top": "Tops & Blouses",
    "ballonblouse": "Tops & Blouses", "linnen blouse": "Tops & Blouses",
    "polkadot blouse": "Tops & Blouses",

    # Broeken
    "broek": "Broeken", "jeans": "Broeken", "legging": "Broeken",
    "cargobroek": "Broeken", "linnen broek": "Broeken", "barrel jeans": "Broeken",

    # Rokken
    "rok": "Rokken", "skirt": "Rokken", "midi rok": "Rokken",

    # Jassen / Outerwear
    "jas": "Jassen & Vesten", "jacket": "Jassen & Vesten", "coat": "Jassen & Vesten",
    "trenchcoat": "Jassen & Vesten", "franjejas": "Jassen & Vesten",
    "blazer": "Jassen & Vesten", "vest": "Jassen & Vesten",

    # Schoenen
    "schoenen": "Schoenen", "sandalen": "Schoenen", "heels": "Schoenen",
    "kitten heels": "Schoenen", "pumps": "Schoenen", "sneakers": "Schoenen",
    "strappy sandalen": "Schoenen",

    # Accessoires
    "zonnebril": "Accessoires", "sunglasses": "Accessoires", "tas": "Accessoires",
    "bag": "Accessoires", "sieraden": "Accessoires", "jewelry": "Accessoires",

    # Sets
    "set": "Sets & Combi's", "co-ord": "Sets & Combi's", "matching": "Sets & Combi's",
}

# Trend/category → seasonal tags
SEASON_MAP = {
    "lente":   ["lente", "voorjaar", "spring"],
    "zomer":   ["zomer", "summer", "vakantie"],
    "herfst":  ["herfst", "autumn", "fall"],
    "winter":  ["winter", "koud"],
    "festival":["festival", "zomer", "boho"],
    "casual":  ["casual", "dagelijks", "everyday"],
    "zakelijk":["zakelijk", "office", "smart"],
}


def get_current_season() -> str:
    month = datetime.date.today().month
    if month in [3, 4, 5]: return "lente"
    if month in [6, 7, 8]: return "zomer"
    if month in [9, 10, 11]: return "herfst"
    return "winter"


def detect_collections(title: str, product_type: str, tags: list) -> list[str]:
    """Detect which Shopify collections this product belongs to."""
    combined = f"{title} {product_type} {' '.join(tags)}".lower()
    collections = set()

    for keyword, collection in COLLECTION_MAP.items():
        if keyword in combined:
            collections.add(collection)

    # Always add "Nieuw" for fresh listings
    collections.add("Nieuwe collectie")

    return sorted(collections)


def enrich_tags(tags: list, candidate: dict, product_type: str, collections: list) -> list[str]:
    """Add seasonal, occasion, and system tags to the copy-generated tags."""
    enriched = set(t.lower().strip() for t in tags if t)

    # Season tags
    season      = get_current_season()
    season_tags = SEASON_MAP.get(season, [season])
    enriched.update(season_tags)

    # Trend tag
    trend = candidate.get("matchedTrend", "")
    if trend:
        enriched.add(trend.lower())

    # Collection tags (for Shopify smart collection rules)
    for col in collections:
        enriched.add(col.lower().replace(" & ", "-").replace(" ", "-"))

    # Source tags (hidden internal tags for filtering)
    enriched.add("googlelcaw-listing")
    enriched.add(f"scout-score-{candidate.get('score', 0)}")

    # Product type tag
    if product_type:
        enriched.add(product_type.lower())

    return sorted(enriched)


def assign(candidate: dict, copy: dict) -> dict:
    """
    Main entry point. Returns:
    {
        "collections": [...],
        "tags": [...],
        "productType": str,
    }
    """
    title        = copy.get("title", candidate.get("title", ""))
    product_type = copy.get("productType", "")
    base_tags    = copy.get("tags", [])

    collections = detect_collections(title, product_type, base_tags)
    final_tags  = enrich_tags(base_tags, candidate, product_type, collections)

    print(f"[LISTER/collections] Collections: {collections}")
    print(f"[LISTER/collections] Tags ({len(final_tags)}): {', '.join(list(final_tags)[:8])}...")

    return {
        "collections": collections,
        "tags":        final_tags,
        "productType": product_type,
    }
