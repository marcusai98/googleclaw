#!/usr/bin/env python3
"""
FEED — GoogleClaw Product Feed Optimizer
Weekly run (Wednesday 06:00).
Analyzes all active Shopify products on performance and takes action:
  - Draft: ROAS <1.5 (2 weeks) + declining conversions + declining trend (all 3 required)
  - Price -€5: performance declining, floor = CJ price × 2.0
  - New images: Gemini-generated lifestyle visuals
  - Fill missing fields: GPT fills empty description/type/tags

Usage:
    python3 feed.py --config config.json \
                    --dashboard data/dashboard.json \
                    --history   data/trends-history.json \
                    --catalog   data/products.json \
                    --queue     data/queue.json
"""

import json
import argparse
import datetime
from pathlib import Path

from steps import performance, trend_check, actions


def load_json(path: str, default):
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(data, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_cogs_lookup(catalog: dict) -> dict:
    """Build SKU/title → CJ price lookup from products.json catalog."""
    lookup = {}
    for entry in catalog.values():
        cj_price = entry.get("cjPrice", 0) or entry.get("cogs", 0)
        if cj_price <= 0:
            continue
        sku   = entry.get("sku", "").lower().strip()
        title = entry.get("title", "").lower().strip()
        if sku:   lookup[sku]   = cj_price
        if title: lookup[title] = cj_price
    return lookup


def should_draft(perf: dict, trend_declining: bool) -> tuple[bool, str]:
    """
    All 3 conditions required to draft:
    1. ROAS < 1.5 for both weeks
    2. Conversion/orders declining (>20% drop)
    3. Trend declining
    """
    reasons = []
    if perf.get("low_roas"):
        reasons.append(f"ROAS w1={perf['roas_w1']}x w2={perf['roas_w2']}x (both <1.5)")
    if perf.get("cr_declining"):
        reasons.append(f"Orders declining: {perf['cr_w2']}→{perf['cr_w1']}")
    if trend_declining:
        reasons.append("Trend declining")

    if len(reasons) == 3:
        return True, " | ".join(reasons)
    return False, ""


def main():
    parser = argparse.ArgumentParser(description="FEED — Product Feed Optimizer")
    parser.add_argument("--config",    default="config.json",              help="Config")
    parser.add_argument("--dashboard", default="data/dashboard.json",      help="MIDAS dashboard")
    parser.add_argument("--history",   default="data/trends-history.json", help="TRENDS history")
    parser.add_argument("--catalog",   default="data/products.json",       help="Products catalog")
    parser.add_argument("--queue",     default="data/queue.json",          help="Inbox queue")
    parser.add_argument("--dry-run",   action="store_true",                help="Preview only")
    args = parser.parse_args()

    cfg          = load_json(args.config, {})
    catalog      = load_json(args.catalog, {})
    queue        = load_json(args.queue, {"items": []})
    cogs_lookup  = build_cogs_lookup(catalog)

    shopify_cfg  = cfg.get("shopify", {})
    domain       = shopify_cfg.get("storeDomain", "")
    token        = shopify_cfg.get("accessToken", "")

    print(f"[FEED] Starting weekly optimization run — {datetime.date.today()}")

    # ── Step 1: Gather all performance data ──────────────────────────────────
    print("[FEED] Gathering performance data...")
    midas_data   = performance.get_midas_roas(args.dashboard)
    ads_data     = performance.get_google_ads_spend(cfg)
    shopify_data = performance.get_shopify_conversion_rates(cfg)
    perf_list    = performance.merge_performance(midas_data, ads_data, shopify_data)
    print(f"[FEED] Products with performance data: {len(perf_list)}")

    # ── Step 2: Fetch all active Shopify products ─────────────────────────────
    print("[FEED] Fetching active Shopify products...")
    shopify_products = actions.get_all_active_products(domain, token)
    shopify_by_id    = {str(p["id"]): p for p in shopify_products}
    print(f"[FEED] Active products: {len(shopify_products)}")

    # ── Step 3: Evaluate + act on each product ────────────────────────────────
    summary = {
        "drafted":          [],
        "price_reduced":    [],
        "images_added":     [],
        "fields_filled":    [],
        "no_action":        0,
        "skipped_no_data":  0,
    }

    for perf in perf_list:
        product_id = perf.get("productId", "")
        title      = perf.get("title", "")

        # Skip if not in active Shopify products
        if product_id not in shopify_by_id:
            summary["skipped_no_data"] += 1
            continue

        product = shopify_by_id[product_id]

        # Step 2: Check trend direction
        trend_name     = perf.get("matchedTrend", title)
        declining, reason = trend_check.is_trend_declining(
            title, trend_name, args.history, cfg
        )

        # ── Evaluate draft ────────────────────────────────────────────────────
        do_draft, draft_reason = should_draft(perf, declining)

        if do_draft:
            print(f"[FEED] DRAFT: '{title}' — {draft_reason}")
            if not args.dry_run:
                actions.draft_product(domain, token, product_id, draft_reason)
            summary["drafted"].append({
                "title":  title,
                "reason": draft_reason,
                "roas_w1": perf["roas_w1"],
                "roas_w2": perf["roas_w2"],
            })
            continue  # drafted → skip other optimizations

        # ── Evaluate price reduction ───────────────────────────────────────────
        # Trigger: ROAS declining OR orders declining (less strict than draft)
        price_action_needed = (
            perf.get("roas_declining") and perf.get("roas_w1", 99) < 2.5
        ) or perf.get("cr_declining")

        if price_action_needed:
            print(f"[FEED] PRICE REDUCE: '{title}' (ROAS: {perf['roas_w1']}x)")
            if not args.dry_run:
                result = actions.reduce_price(domain, token, product, cfg, cogs_lookup)
                if result:
                    summary["price_reduced"].append({
                        "title":    title,
                        "roas_w1":  perf["roas_w1"],
                    })

        # ── Add new images ────────────────────────────────────────────────────
        # Trigger: underperforming (price_action_needed) OR fewer than 5 images
        current_image_count = len(product.get("images", []))
        needs_images = current_image_count < 5 or price_action_needed

        if needs_images:
            needed = max(0, 5 - current_image_count) + (2 if price_action_needed else 0)
            print(f"[FEED] IMAGES: '{title}' — adding {min(needed, 3)} new visuals "
                  f"(current: {current_image_count})")
            if not args.dry_run:
                uploaded = actions.generate_and_upload_images(
                    domain, token, product, cfg, count=min(needed, 3)
                )
                if uploaded > 0:
                    summary["images_added"].append({"title": title, "count": uploaded})

        # ── Fill missing fields ───────────────────────────────────────────────
        if not args.dry_run:
            filled = actions.fill_missing_fields(domain, token, product, cfg)
            if filled:
                summary["fields_filled"].append(title)

        if not do_draft and not price_action_needed and not needs_images:
            summary["no_action"] += 1

    # ── Step 4: Build Inbox summary card ─────────────────────────────────────
    total_actions = (len(summary["drafted"]) + len(summary["price_reduced"]) +
                     len(summary["images_added"]) + len(summary["fields_filled"]))

    print(f"\n[FEED] Run complete:")
    print(f"  Drafted:        {len(summary['drafted'])}")
    print(f"  Price reduced:  {len(summary['price_reduced'])}")
    print(f"  Images added:   {len(summary['images_added'])}")
    print(f"  Fields filled:  {len(summary['fields_filled'])}")
    print(f"  No action:      {summary['no_action']}")

    if total_actions > 0 and not args.dry_run:
        card = {
            "id":          f"feed-{datetime.date.today().isoformat()}",
            "type":        "feed",
            "agent":       "FEED",
            "agentColor":  "#4285F4",
            "agentEmoji":  "⚙️",
            "title":       f"Feed optimizer — {total_actions} actions taken",
            "sub":         f"Wed {datetime.date.today().isoformat()} · Weekly run",
            "badgeClass":  "tag-b",
            "badgeText":   "FEED",
            "createdAt":   datetime.date.today().isoformat(),
            "summary":     summary,
            "actionLabel": "View details",
        }
        items = [i for i in queue.get("items", []) if i.get("agent") != "FEED" or
                 i.get("id") == card["id"]]
        items.insert(0, card)
        queue["items"] = items
        save_json(queue, args.queue)
        print(f"[FEED] Inbox card created")


if __name__ == "__main__":
    main()
