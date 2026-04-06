#!/usr/bin/env python3
"""
LISTER — Step 3: Image handling
Strategy:
  - Use imageUrl from SCOUT candidate (competitor or CJ catalog image captured during discovery)
  - If total < MIN_IMAGES → generate Gemini visuals to supplement
  - If config.lister.imageMode == "optimize_all" → replace ALL with Gemini-generated
  - If config.lister.imageMode == "supplement"   → candidate image first, Gemini fills gaps

CJ API is NOT called here. Images captured by SCOUT are passed via the candidate object.
Returns list of image dicts ready for Shopify upload.
"""

import requests
import base64
import json
import time
from pathlib import Path


MIN_IMAGES    = 5
GEMINI_API    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"


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


def prepare_images(candidate: dict, cfg: dict) -> list[dict]:
    """
    Collect and prepare images for Shopify upload.
    Source images come from the SCOUT candidate (imageUrl field).
    Gemini is used to supplement or fully replace them.
    Returns list of {"src": url_or_data_uri, "alt": str, "source": "scout"|"gemini"}
    """
    image_mode  = cfg.get("lister", {}).get("imageMode", "supplement")
    gemini_key  = cfg.get("gemini", {}).get("apiKey", "")
    store_lang  = cfg.get("store", {}).get("language", "Dutch")
    title       = candidate.get("title", "product")

    result_images = []

    # ── Collect source image from SCOUT candidate ────────────────────────────
    if image_mode != "optimize_all":
        # SCOUT captures imageUrl from whichever source found the product
        # (CJ catalog thumbnail, competitor Shopify image, etc.)
        source_image = candidate.get("imageUrl", "")
        if source_image and source_image.startswith("http"):
            result_images.append({"src": source_image, "alt": title, "source": "scout"})

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
