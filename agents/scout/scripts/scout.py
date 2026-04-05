#!/usr/bin/env python3
"""
SCOUT — GoogleClaw Product Research Agent
Reads trends.json, runs all 3 sourcing methods in parallel,
scores candidates, and writes candidates.json for the Inbox.

Usage:
    python3 scout.py --config config.json \
                     --trends data/trends.json \
                     --output data/candidates.json \
                     --queue  data/queue.json
"""

import json
import argparse
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from methods import cj, amazon, competitors


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
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


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_trend_match(title: str, trend: dict) -> int:
    """Score how well a product title matches a trend keyword. 0–35."""
    title_l  = title.lower()
    name_l   = trend.get("name", "").lower()
    keywords = [k.lower() for k in trend.get("keywords", [name_l])]

    # Exact keyword in title
    for kw in keywords:
        if kw in title_l:
            return 35

    # Partial: main keyword fragments
    for kw in keywords:
        words = kw.split()
        if all(w in title_l for w in words):
            return 20
        if any(w in title_l for w in words if len(w) > 4):
            return 10

    return 0  # no match → will be dropped


def score_volume(volume: int) -> int:
    """Score based on monthly search volume. 0–30."""
    if volume >= 50000: return 30
    if volume >= 20000: return 22
    if volume >= 10000: return 15
    if volume >=  5000: return  8
    return 0


def score_demand(candidate: dict) -> int:
    """Score demand proof from Amazon BSR + competitor presence. 0–25."""
    score = 0

    bsr = candidate.get("amazonBsr", 999999)
    if bsr <= 500:     score += 15
    elif bsr <= 5000:  score += 10
    elif bsr <= 20000: score += 5

    # Count how many competitor stores carry this product
    stores = len(set(candidate.get("competitorStores", [])))
    if stores >= 2:  score += 10
    elif stores == 1: score += 5

    return min(score, 25)


def score_supplier(candidate: dict) -> int:
    """Score CJ supplier availability. 0–10."""
    if not candidate.get("cjProductId"):
        return 0
    if not candidate.get("inStock"):
        return 0
    days = candidate.get("estimatedShipping", 99)
    if days <= 14: return 10
    if days <= 25: return  6
    return 3


def multi_source_bonus(sources: set) -> int:
    """Bonus for products found by multiple methods."""
    n = len(sources)
    if n >= 3: return 20
    if n == 2: return 10
    return 0


def score_candidate(merged: dict, trend: dict) -> int:
    """Calculate final score for a merged candidate."""
    title  = merged.get("title", "")
    volume = merged.get("trendVolume", 0)

    trend_score   = score_trend_match(title, trend)
    if trend_score == 0:
        return 0  # hard drop — no trend match

    volume_score  = score_volume(volume)
    demand_score  = score_demand(merged)
    supplier_score= score_supplier(merged)
    bonus         = multi_source_bonus(merged.get("sources", set()))

    total = trend_score + volume_score + demand_score + supplier_score + bonus
    return min(total, 100)


# ─────────────────────────────────────────────────────────────────────────────
# MERGE
# ─────────────────────────────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Create a merge key from title (lowercase, strip noise)."""
    stop = ["the", "a", "an", "portable", "foldable", "new", "best", "for", "with"]
    words = [w for w in title.lower().split() if w not in stop and len(w) > 2]
    return " ".join(words[:5])


def merge_candidates(all_raw: list) -> list:
    """
    Merge candidates from all 3 methods by title similarity.
    Aggregates: sources, CJ data, Amazon data, competitor data.
    """
    merged_map = {}

    for c in all_raw:
        key = normalize_title(c.get("title", ""))
        if not key:
            continue

        # Find existing entry with similar key
        best_key = None
        for existing_key in merged_map:
            # Simple overlap check
            ew = set(existing_key.split())
            cw = set(key.split())
            overlap = len(ew & cw) / max(len(ew | cw), 1)
            if overlap >= 0.6:
                best_key = existing_key
                break

        if best_key is None:
            # New product — initialize
            merged_map[key] = {
                "title":            c["title"],
                "matchedTrend":     c.get("matchedTrend", ""),
                "trendVolume":      c.get("trendVolume", 0),
                "trendScore":       c.get("trendScore", 0),
                "sources":          {c["source"]},
                # CJ fields
                "cjProductId":      c.get("cjProductId", ""),
                "cjPrice":          c.get("cjPrice", 0),
                "cjUrl":            c.get("cjUrl", ""),
                "estimatedShipping":c.get("estimatedShipping", 99),
                "inStock":          c.get("inStock", False),
                # Amazon fields
                "amazonAsin":       c.get("amazonAsin", ""),
                "amazonUrl":        c.get("amazonUrl", ""),
                "amazonPrice":      c.get("amazonPrice", 0),
                "amazonBsr":        c.get("amazonBsr", 999999),
                "reviewCount":      c.get("reviewCount", 0),
                # Competitor fields
                "competitorStores": [c["competitorStore"]] if c.get("competitorStore") else [],
                "competitorUrls":   [c["competitorUrl"]]   if c.get("competitorUrl")   else [],
                "competitorPrice":  c.get("competitorPrice", 0),
                # Image
                "imageUrl":         c.get("imageUrl", ""),
            }
        else:
            # Merge into existing
            m = merged_map[best_key]
            m["sources"].add(c["source"])
            # Prefer more complete data
            if c.get("cjProductId") and not m["cjProductId"]:
                m["cjProductId"]       = c["cjProductId"]
                m["cjPrice"]           = c["cjPrice"]
                m["cjUrl"]             = c["cjUrl"]
                m["estimatedShipping"] = c["estimatedShipping"]
                m["inStock"]           = c["inStock"]
            if c.get("amazonAsin") and not m["amazonAsin"]:
                m["amazonAsin"]   = c["amazonAsin"]
                m["amazonUrl"]    = c["amazonUrl"]
                m["amazonPrice"]  = c["amazonPrice"]
                m["amazonBsr"]    = c["amazonBsr"]
                m["reviewCount"]  = c["reviewCount"]
            if c.get("competitorStore"):
                if c["competitorStore"] not in m["competitorStores"]:
                    m["competitorStores"].append(c["competitorStore"])
                if c.get("competitorUrl") and c["competitorUrl"] not in m["competitorUrls"]:
                    m["competitorUrls"].append(c["competitorUrl"])
            if not m["imageUrl"] and c.get("imageUrl"):
                m["imageUrl"] = c["imageUrl"]
            # Use highest trendVolume
            if c.get("trendVolume", 0) > m["trendVolume"]:
                m["trendVolume"] = c["trendVolume"]

    return list(merged_map.values())


# ─────────────────────────────────────────────────────────────────────────────
# QUEUE CARD
# ─────────────────────────────────────────────────────────────────────────────

def build_queue_card(candidate: dict, rank: int) -> dict:
    """Build an Inbox card for a scored candidate."""
    sources   = sorted(candidate["sources"])
    multi     = len(sources) >= 2
    score     = candidate["score"]
    tag       = "HIGH" if score >= 75 else "REVIEW"

    return {
        "id":           f"scout-{candidate['matchedTrend'].lower().replace(' ', '-')}-{rank}",
        "type":         "product",
        "agent":        "SCOUT",
        "agentColor":   "#34A853",
        "agentEmoji":   "🔍",
        "actionLabel":  "List this product",
        "title":        candidate["title"],
        "sub":          f"Trend: {candidate['matchedTrend']} · {candidate['trendVolume']:,}/mo searches",
        "score":        score,
        "badgeClass":   "tag-g" if score >= 75 else "tag-y",
        "badgeText":    tag,
        "sources":      sources,
        "multiSource":  multi,
        "trend":        candidate["matchedTrend"],
        "trendVolume":  candidate["trendVolume"],
        "cjProductId":  candidate.get("cjProductId", ""),
        "cjPrice":      candidate.get("cjPrice", 0),
        "cjUrl":        candidate.get("cjUrl", ""),
        "amazonAsin":   candidate.get("amazonAsin", ""),
        "amazonBsr":    candidate.get("amazonBsr", 0),
        "amazonUrl":    candidate.get("amazonUrl", ""),
        "competitorUrls": candidate.get("competitorUrls", []),
        "imageUrl":     candidate.get("imageUrl", ""),
        "createdAt":    datetime.date.today().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SCOUT Product Research")
    parser.add_argument("--config",  default="config.json",          help="Config file")
    parser.add_argument("--trends",  default="data/trends.json",     help="TRENDS output")
    parser.add_argument("--output",  default="data/candidates.json", help="Candidates output")
    parser.add_argument("--queue",   default="data/queue.json",      help="Inbox queue")
    parser.add_argument("--limit",   type=int, default=10,           help="Max candidates in output")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg         = load_json(args.config, {})
    trends_data = load_json(args.trends, {})

    # ── Freshness check ──────────────────────────────────────────────────────
    # SCOUT only runs if trends.json was generated today.
    # TRENDS runs at 00:00 — SCOUT at 10:00 — so 10h window is plenty.
    # If TRENDS failed or Manus ran long, we bail rather than use stale data.
    MAX_TRENDS_AGE_HOURS = 12  # generous upper bound

    generated_at = None
    if isinstance(trends_data, dict):
        generated_at = trends_data.get("generatedAt")

    if not generated_at:
        print("[SCOUT] trends.json has no generatedAt timestamp — run TRENDS first")
        return

    try:
        ts  = datetime.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds() / 3600
        if age > MAX_TRENDS_AGE_HOURS:
            print(f"[SCOUT] trends.json is {age:.1f}h old (max {MAX_TRENDS_AGE_HOURS}h) — "
                  f"TRENDS may have failed. Skipping run.")
            return
        print(f"[SCOUT] trends.json is {age:.1f}h old — fresh enough, continuing.")
    except Exception as e:
        print(f"[SCOUT] Could not parse generatedAt '{generated_at}': {e} — skipping.")
        return

    trends = trends_data.get("trends", [])

    if not trends:
        print("[SCOUT] No trends found in trends.json — run TRENDS first")
        return

    print(f"[SCOUT] Running on {len(trends)} trends...")
    scout_cfg      = cfg.get("scout", {}).get("methods", {})
    limit_per      = cfg.get("scout", {}).get("candidatesPerMethod", 10)
    min_price      = cfg.get("scout", {}).get("minSellingPrice", 40)

    # Run all 3 methods (in parallel where possible)
    all_raw = []

    def run_cj():
        if scout_cfg.get("cj", {}).get("enabled", True):
            return cj.fetch(trends, cfg, limit_per_trend=limit_per)
        return []

    def run_amazon():
        if scout_cfg.get("amazon", {}).get("enabled", True):
            return amazon.fetch(trends, cfg, limit_per_trend=limit_per)
        return []

    def run_competitors():
        if scout_cfg.get("competitors", {}).get("enabled", True):
            return competitors.fetch(trends, cfg, limit_per_trend=limit_per)
        return []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_cj):          "cj",
            executor.submit(run_amazon):      "amazon",
            executor.submit(run_competitors): "competitors",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results = future.result()
                all_raw.extend(results)
                print(f"[SCOUT] {name}: {len(results)} candidates")
            except Exception as e:
                print(f"[SCOUT] {name} failed: {e}")

    print(f"[SCOUT] Total raw: {len(all_raw)} — merging...")

    # Merge + deduplicate
    merged = merge_candidates(all_raw)
    print(f"[SCOUT] After merge: {len(merged)} unique products")

    # Score each merged candidate
    trend_map = {t["name"]: t for t in trends}
    scored = []
    for m in merged:
        trend = trend_map.get(m["matchedTrend"], {"name": m["matchedTrend"], "keywords": []})
        m["sources"] = set(m["sources"])  # ensure it's a set for scoring

        # Hard filter: selling price
        prices = [p for p in [m.get("amazonPrice", 0), m.get("competitorPrice", 0)] if p > 0]
        max_known_price = max(prices) if prices else 0
        if 0 < max_known_price < min_price:
            print(f"[SCOUT] Dropped '{m['title']}' — price €{max_known_price} < €{min_price}")
            continue

        final_score = score_candidate(m, trend)
        if final_score < 60:
            print(f"[SCOUT] Dropped '{m['title']}' — score {final_score} < 60")
            continue

        m["score"]   = final_score
        m["sources"] = list(m["sources"])  # back to list for JSON
        scored.append(m)

    # Sort by score desc, take top N
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:args.limit]

    print(f"[SCOUT] {len(top)} candidates pass threshold (score ≥60)")

    if args.dry_run:
        for i, c in enumerate(top):
            print(f"  {i+1}. [{c['score']}] {c['title']} ({', '.join(c['sources'])})")
        return

    # Save candidates.json
    save_json({
        "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "totalCandidates": len(top),
        "candidates": top,
    }, args.output)
    print(f"[SCOUT] candidates.json written ({len(top)} products)")

    # Build Inbox queue cards
    queue = load_json(args.queue, {"items": []})
    items = queue.get("items", [])

    # Remove old scout product cards
    items = [i for i in items if not (i.get("type") == "product" and i.get("agent") == "SCOUT")]

    for rank, candidate in enumerate(top, 1):
        card = build_queue_card(candidate, rank)
        items.insert(0, card)

    queue["items"] = items
    save_json(queue, args.queue)
    print(f"[SCOUT] {len(top)} cards added to Inbox queue")


if __name__ == "__main__":
    main()
