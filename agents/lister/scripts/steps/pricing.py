#!/usr/bin/env python3
"""
LISTER — Step 1: Pricing
Determines selling price using this hierarchy:
1. Competitor price - €1.00
2. AI suggestion (GPT) if competitor price seems off
3. Fallback: CJ purchase price × multiplier (default 3x)
"""

import os
import json
import requests


def get_ai_price_suggestion(product_title: str, cj_price: float,
                             competitor_price: float, cfg: dict) -> float:
    """Ask GPT for a smart price suggestion."""
    api_key = cfg.get("openai", {}).get("apiKey", "")
    if not api_key:
        return 0.0

    prompt = (
        f"You are a dropshipping pricing expert for a Shopify store in {cfg.get('store', {}).get('market', 'Netherlands')}.\n"
        f"Product: {product_title}\n"
        f"Purchase price (CJ): €{cj_price:.2f}\n"
        f"Competitor sells it for: €{competitor_price:.2f}\n\n"
        f"Suggest an optimal selling price in EUR that:\n"
        f"- Is competitive (at or below competitor)\n"
        f"- Has at least 2.5x margin over purchase price\n"
        f"- Feels psychologically right (e.g. €29.95, €34.99)\n\n"
        f"Reply with ONLY a number, no currency symbol, no explanation. Example: 34.95"
    )

    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0.3,
            }, timeout=15)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        return float(raw.replace(",", ".").replace("€", ""))
    except Exception as e:
        print(f"[LISTER/pricing] AI suggestion failed: {e}")
        return 0.0


def determine_price(candidate: dict, cfg: dict) -> dict:
    """
    Returns pricing dict:
    {
        "price": float,
        "compareAtPrice": float | None,   # original competitor price (for strikethrough)
        "method": "competitor_minus_1" | "ai_suggestion" | "cogs_multiplier",
        "cjPrice": float,
    }
    """
    cj_price          = candidate.get("cjPrice", 0.0)
    competitor_price  = candidate.get("competitorPrice", 0.0)
    multiplier        = cfg.get("lister", {}).get("cogsMultiplier", 3.0)
    use_ai_suggestion = cfg.get("lister", {}).get("useAiPriceSuggestion", True)
    min_margin        = cfg.get("lister", {}).get("minMarginMultiplier", 2.0)

    fallback_price = round(cj_price * multiplier, 2) if cj_price > 0 else 0.0

    # Method 1: Competitor price - €1
    if competitor_price and competitor_price > 0:
        proposed = round(competitor_price - 1.0, 2)

        # Sanity check: must be at least min_margin × cj_price
        min_acceptable = round(cj_price * min_margin, 2) if cj_price > 0 else 0
        if proposed < min_acceptable and min_acceptable > 0:
            print(f"[LISTER/pricing] Competitor price €{competitor_price} - €1 = €{proposed} "
                  f"is below min margin (€{min_acceptable}) — using AI or fallback")
        else:
            # Optionally get AI to verify / improve the price
            if use_ai_suggestion and cj_price > 0:
                ai_price = get_ai_price_suggestion(
                    candidate.get("title", ""), cj_price, competitor_price, cfg
                )
                if ai_price > 0 and ai_price >= min_acceptable:
                    return {
                        "price":          ai_price,
                        "compareAtPrice": competitor_price,
                        "method":         "ai_suggestion",
                        "cjPrice":        cj_price,
                    }

            return {
                "price":          proposed,
                "compareAtPrice": competitor_price,
                "method":         "competitor_minus_1",
                "cjPrice":        cj_price,
            }

    # Method 2: CJ × multiplier
    if fallback_price > 0:
        # Try AI suggestion over the fallback too
        if use_ai_suggestion and competitor_price == 0:
            ai_price = get_ai_price_suggestion(
                candidate.get("title", ""), cj_price, fallback_price, cfg
            )
            if ai_price > 0:
                return {
                    "price":          ai_price,
                    "compareAtPrice": None,
                    "method":         "ai_suggestion",
                    "cjPrice":        cj_price,
                }

        return {
            "price":          fallback_price,
            "compareAtPrice": None,
            "method":         "cogs_multiplier",
            "cjPrice":        cj_price,
        }

    # Fallback: no price data at all
    print(f"[LISTER/pricing] WARNING: no price data for '{candidate.get('title')}' — defaulting to €49.95")
    return {
        "price":          49.95,
        "compareAtPrice": None,
        "method":         "default",
        "cjPrice":        cj_price,
    }
