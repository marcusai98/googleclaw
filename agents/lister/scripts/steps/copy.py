#!/usr/bin/env python3
"""
LISTER — Step 2: SEO Copy (Claude)
Generates full Shopify product metadata in the store's language.
Output: title, description (HTML), tags, meta_title, meta_description,
        product_type, vendor.
"""

import requests
import json


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


def get_store_language(cfg: dict) -> str:
    """Get store language from config. Defaults to Dutch."""
    lang = cfg.get("store", {}).get("language", "Dutch")
    return lang


def build_prompt(candidate: dict, pricing: dict, store_language: str,
                 store_niche: str, market: str) -> str:
    title          = candidate.get("title", "")
    trend          = candidate.get("matchedTrend", "")
    competitor_url = candidate.get("competitorUrls", [""])[0] if candidate.get("competitorUrls") else ""
    amazon_url     = candidate.get("amazonUrl", "")
    cj_category    = candidate.get("category", "")
    price          = pricing.get("price", 0)

    return f"""You are an expert Shopify product copywriter for a dropshipping store.

Store details:
- Niche: {store_niche}
- Market: {market}
- Language: {store_language}
- Selling price: €{price:.2f}

Product to list:
- Name: {title}
- Trending for: {trend}
- Category: {cj_category}
- Competitor reference: {competitor_url or "none"}
- Amazon reference: {amazon_url or "none"}

Generate complete Shopify product copy in {store_language}. Return ONLY valid JSON, no markdown, no explanation:

{{
  "title": "SEO-optimized product title (max 70 chars, includes main keyword)",
  "description": "Full HTML product description (300-500 words). Include: hook sentence, 3-5 bullet benefits, product details, call to action. Use <h2>, <ul>, <li>, <p> tags. No inline styles.",
  "tags": ["tag1", "tag2", ...],
  "metaTitle": "SEO meta title (max 60 chars, includes keyword + brand signal)",
  "metaDescription": "SEO meta description (max 160 chars, includes keyword + CTA)",
  "productType": "Product type category (e.g. Jurken, Jassen, Schoenen)",
  "vendor": "Imported"
}}

Tag requirements:
- 10-15 tags
- Include: trend keyword, product type, season/occasion, style descriptors
- All tags in {store_language}
- Lowercase, no special characters"""


def generate_copy(candidate: dict, pricing: dict, cfg: dict) -> dict:
    """Call Claude to generate full SEO copy. Returns copy dict."""
    api_key        = cfg.get("anthropic", {}).get("apiKey", "")
    store_language = get_store_language(cfg)
    store_niche    = cfg.get("store", {}).get("niche", "fashion")
    market         = cfg.get("store", {}).get("market", "Netherlands")

    if not api_key:
        print("[LISTER/copy] No Anthropic API key — using placeholder copy")
        return _fallback_copy(candidate, pricing, store_language)

    prompt = build_prompt(candidate, pricing, store_language, store_niche, market)

    try:
        r = requests.post(ANTHROPIC_API,
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 2000,
                "messages":   [{"role": "user", "content": prompt}],
            }, timeout=60)
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()

        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        copy = json.loads(raw)
        print(f"[LISTER/copy] Generated copy: '{copy.get('title', '')}'")
        return copy

    except json.JSONDecodeError as e:
        print(f"[LISTER/copy] JSON parse error: {e} — using fallback")
        return _fallback_copy(candidate, pricing, store_language)
    except Exception as e:
        print(f"[LISTER/copy] Claude API error: {e} — using fallback")
        return _fallback_copy(candidate, pricing, store_language)


def _fallback_copy(candidate: dict, pricing: dict, language: str) -> dict:
    """Minimal fallback copy when Claude is unavailable."""
    title = candidate.get("title", "Product")
    trend = candidate.get("matchedTrend", "")
    return {
        "title":           title,
        "description":     f"<p>{title}</p>",
        "tags":            [trend.lower(), "new arrival"] if trend else ["new arrival"],
        "metaTitle":       title[:60],
        "metaDescription": f"Bestel nu {title}. Snel geleverd."[:160],
        "productType":     candidate.get("category", ""),
        "vendor":          "Imported",
    }
