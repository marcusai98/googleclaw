#!/usr/bin/env python3
"""
LISTER — Step 3: Image handling
Strategy:
  - Collect CJ product images (priority source)
  - If total < MIN_IMAGES → generate Gemini visuals to supplement
  - If config.lister.imageMode == "optimize_all" → replace ALL with Gemini-generated
  - If config.lister.imageMode == "supplement"   → CJ/competitor first, Gemini fills gaps
Returns list of image dicts ready for Shopify upload.
"""

import requests
import base64
import json
import time
from pathlib import Path


MIN_IMAGES    = 5
GEMINI_API    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"


def fetch_cj_images(cj_product_id: str, token: str) -> list[str]:
    """Fetch all image URLs for a CJ product."""
    if not cj_product_id or not token:
        return []
    try:
        r = requests.get(
            "https://developers.cjdropshipping.com/api2.0/v1/product/query",
            headers={"CJ-Access-Token": token},
            params={"pid": cj_product_id},
            timeout=15
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        return data.get("productImageSet", "").split(",") if data.get("productImageSet") else []
    except Exception as e:
        print(f"[LISTER/images] CJ image fetch failed: {e}")
        return []


def generate_gemini_image(prompt: str, api_key: str) -> str | None:
    """Generate one product image with Gemini. Returns base64 data URI."""
    try:
        r = requests.post(
            f"{GEMINI_API}?key={api_key}",
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
                mime = part["inlineData"]["mimeType"]
                data = part["inlineData"]["data"]
                return f"data:{mime};base64,{data}"
        return None
    except Exception as e:
        print(f"[LISTER/images] Gemini generation failed: {e}")
        return None


def build_gemini_prompts(candidate: dict, count: int, store_language: str) -> list[str]:
    """Build image generation prompts for a product."""
    title   = candidate.get("title", "product")
    trend   = candidate.get("matchedTrend", "")
    prompts = []

    styles = [
        f"Professional product photo of {title}, white background, studio lighting, high resolution, e-commerce style",
        f"Lifestyle photo of {title}, worn by a person, natural light, {trend} fashion trend, editorial style",
        f"Close-up detail shot of {title}, texture and material visible, neutral background",
        f"Flat lay photo of {title}, minimal aesthetic, clean background, fashion photography",
        f"Model wearing {title}, outdoor urban setting, natural daylight, {trend} style",
    ]

    return styles[:count]


def prepare_images(candidate: dict, cfg: dict, cj_token: str = "") -> list[dict]:
    """
    Collect and prepare images for Shopify upload.
    Returns list of {"src": url_or_data_uri, "alt": str, "source": "cj"|"gemini"}
    """
    image_mode  = cfg.get("lister", {}).get("imageMode", "supplement")
    gemini_key  = cfg.get("gemini", {}).get("apiKey", "")
    store_lang  = cfg.get("store", {}).get("language", "Dutch")
    title       = candidate.get("title", "product")

    result_images = []

    # ── Collect source images ────────────────────────────────────────────────
    if image_mode != "optimize_all":
        # CJ images (first priority)
        cj_id     = candidate.get("cjProductId", "")
        cj_urls   = fetch_cj_images(cj_id, cj_token) if cj_id and cj_token else []
        for url in cj_urls[:8]:  # cap at 8 from CJ
            if url.strip():
                result_images.append({"src": url.strip(), "alt": title, "source": "cj"})

        # Competitor images as secondary (if we have competitor URL and need more)
        # Note: competitor images are scraped from Shopify /products.json earlier
        comp_image = candidate.get("imageUrl", "")
        if comp_image and len(result_images) < MIN_IMAGES:
            if not any(img["src"] == comp_image for img in result_images):
                result_images.append({"src": comp_image, "alt": title, "source": "competitor"})

    # ── Generate Gemini visuals if needed ────────────────────────────────────
    if not gemini_key:
        print(f"[LISTER/images] No Gemini key — skipping AI generation")
    else:
        if image_mode == "optimize_all":
            # Replace everything with Gemini-generated images
            result_images = []
            needed        = MIN_IMAGES
            print(f"[LISTER/images] Mode: optimize_all — generating {needed} Gemini images")
        else:
            # Supplement only
            needed = max(0, MIN_IMAGES - len(result_images))
            if needed > 0:
                print(f"[LISTER/images] Have {len(result_images)} images — generating {needed} more with Gemini")

        if needed > 0:
            prompts = build_gemini_prompts(candidate, needed, store_lang)
            for i, prompt in enumerate(prompts):
                print(f"[LISTER/images] Generating image {i+1}/{len(prompts)}...")
                data_uri = generate_gemini_image(prompt, gemini_key)
                if data_uri:
                    result_images.append({
                        "src":    data_uri,
                        "alt":    f"{title} — foto {len(result_images) + 1}",
                        "source": "gemini",
                    })
                time.sleep(1.5)  # Gemini rate limit

    total = len(result_images)
    gemini_count = sum(1 for img in result_images if img["source"] == "gemini")
    print(f"[LISTER/images] Ready: {total} images ({gemini_count} Gemini, {total - gemini_count} sourced)")

    if total < MIN_IMAGES:
        print(f"[LISTER/images] WARNING: only {total} images — below minimum of {MIN_IMAGES}")

    return result_images
