#!/usr/bin/env python3
"""
MIDAS — Quarterly COGS Refresh
Runs on the 1st of each quarter (Jan, Apr, Jul, Oct).
Flags actively-selling products whose COGS prices are due for review.
Only products sold in the last 90 days are flagged — inactive products are skipped.

Usage:
    python3 refresh.py --catalog data/products.json --queue data/queue.json \
                       --config config.json
"""

import json
import argparse
import datetime
import requests
from pathlib import Path


ACTIVE_DAYS    = 90   # product must have sold within this window to be flagged
REVIEW_DAYS    = 90   # COGS review interval (quarterly)


def load_json(path: str, default) -> dict:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(data, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_refresh(catalog: dict, cfg: dict) -> tuple[list, list]:
    """
    Evaluate each product. Returns (flagged, skipped_inactive).
    Only flags products that:
      1. Have been sold in the last ACTIVE_DAYS days (lastSeen is recent)
      2. Have a cogsReviewDue date that has passed (or never set)
    """
    today      = datetime.date.today()
    flagged    = []
    inactive   = []

    for key, product in catalog.items():
        title       = product.get("title", key)
        last_seen   = product.get("lastSeen")
        cogs        = product.get("cogs", 0)
        review_due  = product.get("cogsReviewDue")
        already_flagged = product.get("needsReview", False)

        # Skip if already flagged and not yet resolved
        if already_flagged and cogs == 0:
            continue

        # Check if product sold recently
        if not last_seen:
            inactive.append(title)
            continue

        try:
            last_seen_date = datetime.date.fromisoformat(last_seen)
        except ValueError:
            inactive.append(title)
            continue

        days_since_sold = (today - last_seen_date).days
        if days_since_sold > ACTIVE_DAYS:
            inactive.append(title)
            continue  # not selling → skip

        # Check if COGS review is due
        if review_due:
            try:
                due_date = datetime.date.fromisoformat(review_due)
                if due_date > today:
                    continue  # not due yet
            except ValueError:
                pass  # malformed date → treat as due

        # Flag this product for review
        product["needsReview"]      = True
        product["cogsReviewDue"]    = (today + datetime.timedelta(days=REVIEW_DAYS)).isoformat()
        product["cogsReviewFlagged"]= today.isoformat()
        flagged.append({
            "key":       key,
            "title":     title,
            "sku":       product.get("sku", ""),
            "currentCogs": cogs,
            "lastSold":  last_seen,
        })
        print(f"[REFRESH] Flagged: '{title}' — last sold {last_seen}, COGS €{cogs}")

    return flagged, inactive


def build_queue_item(flagged: list, cfg: dict) -> dict:
    """Build an Inbox queue card for the COGS refresh."""
    store_name   = cfg.get("instance", {}).get("name", "Your Store")
    sheet_url    = cfg.get("cogsSheet", {}).get("sheetUrl", "")
    supplier_contact = cfg.get("supplier", {}).get("contact", "")
    today        = datetime.date.today()
    quarter      = f"Q{(today.month - 1) // 3 + 1} {today.year}"

    product_list = "\n".join(
        f"  • {p['title']} (SKU: {p['sku'] or '—'}) — current COGS: €{p['currentCogs']}"
        for p in flagged[:20]  # cap at 20 in the card
    )

    return {
        "id":          f"cogs-refresh-{today.isoformat()}",
        "type":        "cogs_refresh",
        "agent":       "MIDAS",
        "agentColor":  "#FBBC04",
        "agentEmoji":  "💰",
        "actionLabel": "Notify supplier",
        "title":       f"COGS refresh due — {len(flagged)} products",
        "sub":         f"{quarter} · Prices may have changed due to shipping costs",
        "badgeClass":  "tag-y",
        "badgeText":   "COGS Review",
        "createdAt":   today.isoformat(),
        "store":       store_name,
        "quarter":     quarter,
        "flaggedCount": len(flagged),
        "products":    flagged,
        "sheetUrl":    sheet_url,
        "supplierContact": supplier_contact,
        "supplierMessage": (
            f"Hi, could you please update the COGS prices in our shared sheet for the following "
            f"{len(flagged)} products? These are active sellers that need a quarterly price check.\n\n"
            f"{product_list}\n\n"
            f"Sheet: {sheet_url}\n\nThanks!"
        ),
    }


def send_telegram_alert(flagged: list, cfg: dict):
    """Send Telegram notification about the COGS refresh."""
    tg = cfg.get("notifications", {}).get("telegram", {})
    if not tg.get("enabled") or not tg.get("botToken"):
        return

    today   = datetime.date.today()
    quarter = f"Q{(today.month - 1) // 3 + 1} {today.year}"
    names   = ", ".join(p["title"] for p in flagged[:5])
    more    = f" (+{len(flagged) - 5} more)" if len(flagged) > 5 else ""

    msg = (
        f"💰 MIDAS — COGS Refresh Due\n\n"
        f"{quarter}: {len(flagged)} active products need updated prices from your supplier.\n\n"
        f"Products: {names}{more}\n\n"
        f"Open your inbox to notify the supplier with one tap."
    )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tg['botToken']}/sendMessage",
            json={"chat_id": tg["chatId"], "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        r.raise_for_status()
        print(f"[REFRESH] Telegram alert sent")
    except Exception as e:
        print(f"[REFRESH] Telegram alert failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="MIDAS Quarterly COGS Refresh")
    parser.add_argument("--catalog", default="data/products.json", help="Product catalog cache")
    parser.add_argument("--queue",   default="data/queue.json",    help="Inbox queue file")
    parser.add_argument("--config",  default="config.json",        help="Config file")
    parser.add_argument("--dry-run", action="store_true",          help="Preview without writing")
    args = parser.parse_args()

    cfg     = load_json(args.config, {})
    catalog = load_json(args.catalog, {})
    queue   = load_json(args.queue, {"items": []})

    print(f"[REFRESH] Checking {len(catalog)} products in catalog...")
    flagged, inactive = run_refresh(catalog, cfg)

    print(f"[REFRESH] Results: {len(flagged)} flagged, {len(inactive)} inactive (skipped)")

    if not flagged:
        print("[REFRESH] No products need COGS review — all prices are current or products inactive")
        return

    if args.dry_run:
        print(f"[REFRESH] DRY RUN — would flag: {[p['title'] for p in flagged]}")
        return

    # Update catalog with flagged products
    save_json(catalog, args.catalog)

    # Add Inbox queue item
    queue_item = build_queue_item(flagged, cfg)
    items = queue.get("items", [])
    # Remove any existing cogs_refresh card (replace with fresh one)
    items = [i for i in items if i.get("type") != "cogs_refresh"]
    items.insert(0, queue_item)
    queue["items"] = items
    save_json(queue, args.queue)
    print(f"[REFRESH] Queue item added: '{queue_item['title']}'")

    # Telegram alert
    send_telegram_alert(flagged, cfg)

    print(f"[REFRESH] Done — {len(flagged)} products flagged for COGS review")


if __name__ == "__main__":
    main()
