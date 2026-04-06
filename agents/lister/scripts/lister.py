#!/usr/bin/env python3
"""
LISTER — GoogleClaw Product Listing Agent
Triggered ONLY after user approves a SCOUT candidate.
Creates full Shopify listing: SEO copy (Claude) + images (Gemini) + publish.

CJ Dropshipping is NOT used here. All candidate data (title, cjPrice, imageUrl,
competitorPrice, etc.) is already present from SCOUT's output.
LISTER's job: take that data + generate copy/images + publish to Shopify.

Usage:
    python3 lister.py --config config.json \
                      --candidate '{"title": "...", "cjPrice": 12.50, ...}' \
                      --queue data/queue.json

Or via queue (card ID):
    python3 lister.py --config config.json \
                      --card-id "scout-barrel-jeans-1" \
                      --queue data/queue.json
"""

import json
import argparse
import datetime
from pathlib import Path

from steps import pricing, copy, images, collections, shopify_publish


# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: str, default):
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(data, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def mark_card_listed(queue: dict, card_id: str, result: dict) -> dict:
    """Update queue card status to 'listed'."""
    for item in queue.get("items", []):
        if item.get("id") == card_id:
            item["status"]         = "listed"
            item["listedAt"]       = datetime.datetime.utcnow().isoformat() + "Z"
            item["shopifyUrl"]     = result.get("shopifyUrl", "")
            item["storefrontUrl"]  = result.get("storefrontUrl", "")
            item["shopifyProductId"] = result.get("shopifyProductId", "")
            break
    return queue


def run(candidate: dict, cfg: dict, card_id: str = "", queue_path: str = "data/queue.json"):
    """Full LISTER pipeline for one candidate."""
    title = candidate.get("title", "Unknown")
    print(f"\n[LISTER] Starting pipeline for: '{title}'")
    print(f"[LISTER] {'='*60}")

    # ── 1. Pricing ────────────────────────────────────────────────────────────
    print(f"[LISTER] Step 1: Pricing...")
    price_result = pricing.determine_price(candidate, cfg)
    print(f"[LISTER] Price: €{price_result['price']} (method: {price_result['method']})")

    # ── 2. SEO Copy (Claude) ──────────────────────────────────────────────────
    print(f"[LISTER] Step 2: Generating SEO copy (Claude)...")
    copy_result = copy.generate_copy(candidate, price_result, cfg)
    print(f"[LISTER] Copy title: '{copy_result.get('title', '')}'")

    # ── 3. Images ─────────────────────────────────────────────────────────────
    print(f"[LISTER] Step 3: Preparing images...")
    image_list = images.prepare_images(candidate, cfg)
    print(f"[LISTER] Images ready: {len(image_list)}")

    # ── 4. Collections & Tags ─────────────────────────────────────────────────
    print(f"[LISTER] Step 4: Assigning collections & tags...")
    collection_data = collections.assign(candidate, copy_result)

    # ── 5. Shopify publish ────────────────────────────────────────────────────
    print(f"[LISTER] Step 5: Publishing to Shopify...")
    result = shopify_publish.publish(
        candidate, price_result, copy_result,
        image_list, collection_data, cfg
    )

    print(f"\n[LISTER] ✅ Listed: '{result['title']}'")
    print(f"[LISTER] Shopify: {result['shopifyUrl']}")
    print(f"[LISTER] Storefront: {result['storefrontUrl']}")
    print(f"[LISTER] Price: €{result['price']} | Variants: {result['variantCount']} | Images: {result['imageCount']}")
    print(f"[LISTER] Collections: {', '.join(result['collections'])}")
    print(f"[LISTER] Status: {result['status'].upper()}")

    # ── Update queue card ─────────────────────────────────────────────────────
    if card_id:
        queue = load_json(queue_path, {"items": []})
        queue = mark_card_listed(queue, card_id, result)
        save_json(queue, queue_path)
        print(f"[LISTER] Queue card '{card_id}' marked as listed")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LISTER — Shopify Product Listing")
    parser.add_argument("--config",    default="config.json",     help="Config file")
    parser.add_argument("--queue",     default="data/queue.json", help="Inbox queue file")
    parser.add_argument("--candidate", default=None,              help="Candidate JSON string")
    parser.add_argument("--card-id",   default=None,              help="Queue card ID to list")
    args = parser.parse_args()

    cfg   = load_json(args.config, {})
    queue = load_json(args.queue, {"items": []})

    # Resolve candidate from card ID or inline JSON
    if args.card_id:
        candidate = None
        for item in queue.get("items", []):
            if item.get("id") == args.card_id:
                candidate = item
                break
        if not candidate:
            print(f"[LISTER] Card '{args.card_id}' not found in queue")
            return
    elif args.candidate:
        try:
            candidate = json.loads(args.candidate)
        except json.JSONDecodeError as e:
            print(f"[LISTER] Invalid candidate JSON: {e}")
            return
    else:
        print("[LISTER] Provide --candidate JSON or --card-id")
        return

    run(candidate, cfg, card_id=args.card_id or "", queue_path=args.queue)


if __name__ == "__main__":
    main()
