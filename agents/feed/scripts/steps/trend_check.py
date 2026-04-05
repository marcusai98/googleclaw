#!/usr/bin/env python3
"""
FEED — Step 2: Trend direction check
Checks if the product's matched trend is declining.
Sources:
  - trends-history.json (TRENDS agent output — monthly scores)
  - pytrends fallback (real-time Google Trends check)
"""

import json
import datetime
from pathlib import Path


def load_history(history_path: str) -> dict:
    if Path(history_path).exists():
        with open(history_path) as f:
            return json.load(f)
    return {"seen": {}}


def is_trend_declining(product_title: str, trend_name: str,
                       history_path: str, cfg: dict) -> tuple[bool, str]:
    """
    Returns (is_declining: bool, reason: str)
    Checks trends-history.json for recent score trajectory.
    Falls back to pytrends if no history data.
    """
    history = load_history(history_path)
    seen    = history.get("seen", {})

    # Find matching trend in history (by name or product title keywords)
    match_key = None
    for key in seen:
        if (trend_name.lower() in key.lower() or key.lower() in trend_name.lower() or
                any(w in key.lower() for w in product_title.lower().split() if len(w) > 4)):
            match_key = key
            break

    if match_key:
        trend_data = seen[match_key]
        monthly    = trend_data.get("monthly", {})

        if len(monthly) >= 2:
            # Sort months, take last 2
            sorted_months = sorted(monthly.keys())[-2:]
            score_prev = monthly[sorted_months[0]]
            score_curr = monthly[sorted_months[1]]

            if score_curr < score_prev * 0.7:  # >30% drop in monthly score
                return True, f"Trend score dropped {score_prev}→{score_curr} ({sorted_months[0]}→{sorted_months[1]})"
            if score_curr < 40:
                return True, f"Trend score critically low: {score_curr}"
            return False, f"Trend stable: {score_prev}→{score_curr}"

    # Fallback: pytrends check
    return _pytrends_check(trend_name or product_title, cfg)


def _pytrends_check(keyword: str, cfg: dict) -> tuple[bool, str]:
    """Real-time Google Trends check via pytrends."""
    try:
        from pytrends.request import TrendReq
        market = cfg.get("store", {}).get("market", "NL")

        geo_map = {"Netherlands": "NL", "Germany": "DE", "UK": "GB", "France": "FR"}
        geo     = geo_map.get(market, market[:2].upper())

        pt = TrendReq(hl="nl-NL", tz=60)
        pt.build_payload([keyword], timeframe="today 3-m", geo=geo)
        df = pt.interest_over_time()

        if df.empty:
            return False, "No pytrends data — assuming stable"

        values = df[keyword].tolist()
        if len(values) < 4:
            return False, "Insufficient data"

        # Compare last 2 weeks vs previous 2 weeks
        recent   = sum(values[-2:]) / 2
        previous = sum(values[-6:-2]) / 4 if len(values) >= 6 else sum(values[:-2]) / max(len(values) - 2, 1)

        if recent < previous * 0.6:  # >40% drop
            return True, f"pytrends: declining {previous:.0f}→{recent:.0f}"
        return False, f"pytrends: stable {previous:.0f}→{recent:.0f}"

    except ImportError:
        return False, "pytrends not installed — skipping trend check"
    except Exception as e:
        return False, f"pytrends error: {e}"
