#!/usr/bin/env python3
"""
TRENDS — Manus AI Research Script
Submits a trend research task to Manus and writes validated trends to trends.json.

Usage:
    python3 call_manus.py --config config.json --output data/trends.json
"""

import json
import time
import argparse
import datetime
import requests
from pathlib import Path

MANUS_API_URL = "https://api.manus.ai/v1"
POLL_INTERVAL  = 30   # seconds between status checks
MAX_WAIT       = 3600 # max 60 minutes


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def build_research_prompt(cfg: dict) -> str:
    niche   = cfg["store"]["niche"]
    market  = cfg["store"]["market"]
    lang    = cfg["store"].get("language", "English")
    today   = datetime.date.today().isoformat()

    return f"""
You are a product trend researcher for a dropshipping store.

Store niche: {niche}
Target market: {market}
Research language: {lang}
Today's date: {today}

## Task

Find the top trending PRODUCT TYPES within the "{niche}" niche for the {market} market.

Product types should be at the right level of specificity:
- Not too broad: "clothing" is too broad
- Not too specific: "blue Nike polo shirt size M" is too specific
- Just right: "polo shirt", "regenjas", "sandalen", "zwembroek"

## Research process

### Step 1: Generate candidates
Use these secondary sources to generate a list of candidate product types:
- TikTok trending content in {market} related to {niche}
- Reddit communities relevant to {niche}
- Seasonal calendar for {market} (what's coming up in the next 1-6 months?)
- Fashion/industry trend reports if applicable

Generate 15-20 candidate product types.

### Step 2: Validate via Google data (REQUIRED for each candidate)
For each candidate, check:

1. **Google Trends** — search the term in {market}:
   - Is the trend curve rising over the past 4 weeks? (required)
   - Is it up at least 20% year-over-year? (required)
   - Is it a consistent trend (not a single spike)? (required)

2. **Google Keyword Planner data** (estimate if direct access unavailable):
   - Monthly search volume in {market}: must be ≥ 5,000
   - Average CPC: must be ≤ €2.00 (or local currency equivalent)

3. **Seasonal timing**:
   - Peak window must be within the next 1-5 months
   - Too early (>5 months out): skip — too early to source
   - Too late (<2 weeks to peak): skip — opportunity has passed

### Step 3: Score each validated candidate (0-100)
- Trend momentum (rising speed): 0-30 points
- Monthly search volume (normalized): 0-25 points
- Seasonal timing (how close to optimal): 0-20 points
- Low competition (lower CPC = higher score): 0-15 points
- Multi-platform presence: 0-10 points

### Step 4: Filter and rank
- Discard any candidate that fails Google validation criteria
- Keep only candidates scoring ≥ 50
- Return maximum 10, ranked by score

## Required output format

Return ONLY valid JSON, no markdown, no explanation. Exactly this structure:

{{
  "generatedAt": "{today}T02:00:00Z",
  "validUntil": "{(datetime.date.today() + datetime.timedelta(days=7)).isoformat()}T02:00:00Z",
  "storeNiche": "{niche}",
  "market": "{market}",
  "productTypes": [
    {{
      "name": "Product Type Name",
      "momentum": "rising | accelerating | peaking | stable",
      "peakWindow": "Month – Month YYYY",
      "monthsUntilPeak": 3,
      "googleTrendDirection": "rising | stable | declining",
      "monthlySearchVolume": 22000,
      "avgCpc": "€0.42",
      "reason": "2-3 sentence explanation of why this is validated and timely.",
      "score": 82
    }}
  ]
}}

Only return the JSON. Nothing else.
"""


def submit_task(api_key: str, prompt: str) -> str:
    """Submit research task to Manus. Returns task_id."""
    headers = {
        "API_KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "input": prompt,
        "version": "v2"
    }
    r = requests.post(f"{MANUS_API_URL}/tasks", json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise ValueError(f"No task_id in Manus response: {data}")
    print(f"[TRENDS] Task submitted: {task_id}")
    return task_id


def poll_task(api_key: str, task_id: str) -> str:
    """Poll Manus until task completes. Returns result text."""
    headers = {"API_KEY": api_key}
    deadline = time.time() + MAX_WAIT

    while time.time() < deadline:
        r = requests.get(f"{MANUS_API_URL}/tasks/{task_id}", headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "")
        print(f"[TRENDS] Status: {status}")

        if status in ("completed", "success", "done"):
            # Extract result text
            result = (
                data.get("result") or
                data.get("output") or
                data.get("response") or
                str(data)
            )
            return result

        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Manus task failed: {data.get('error', status)}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Manus task {task_id} did not complete within {MAX_WAIT}s")


def extract_json(text: str) -> dict:
    """Extract JSON from Manus response (may contain surrounding text)."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find JSON block
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from Manus response:\n{text[:500]}")


def validate_output(data: dict) -> list:
    """Validate and filter product types. Returns only valid entries."""
    product_types = data.get("productTypes", [])
    valid = []
    for pt in product_types:
        # Must have required fields
        if not pt.get("name") or not pt.get("score"):
            continue
        # Must meet minimum score
        if pt.get("score", 0) < 50:
            print(f"[TRENDS] Skipping '{pt['name']}' — score {pt.get('score')} < 50")
            continue
        # Must not be declining
        if pt.get("googleTrendDirection") == "declining":
            print(f"[TRENDS] Skipping '{pt['name']}' — Google trend declining")
            continue
        valid.append(pt)

    # Sort by score descending, cap at 10
    valid.sort(key=lambda x: x.get("score", 0), reverse=True)
    return valid[:10]


def main():
    parser = argparse.ArgumentParser(description="TRENDS — Manus AI Research")
    parser.add_argument("--config", default="config.json",      help="Path to config.json")
    parser.add_argument("--output", default="data/trends.json", help="Path to trends.json")
    args = parser.parse_args()

    cfg     = load_config(args.config)
    api_key = cfg["manus"]["apiKey"]

    print(f"[TRENDS] Starting research for: {cfg['store']['niche']} / {cfg['store']['market']}")

    # Build prompt
    prompt = build_research_prompt(cfg)

    # Submit to Manus
    task_id = submit_task(api_key, prompt)

    # Poll for result
    result_text = poll_task(api_key, task_id)

    # Parse and validate
    raw_data = extract_json(result_text)
    validated = validate_output(raw_data)

    if len(validated) < 3:
        print(f"[TRENDS] WARNING: Only {len(validated)} trends validated (minimum 3 recommended)")

    # Build final output
    output = {
        "generatedAt":   raw_data.get("generatedAt", datetime.datetime.utcnow().isoformat() + "Z"),
        "validUntil":    raw_data.get("validUntil"),
        "storeNiche":    cfg["store"]["niche"],
        "market":        cfg["store"]["market"],
        "trendsCount":   len(validated),
        "productTypes":  validated,
    }

    # Write output
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[TRENDS] Done — {len(validated)} validated trends written to {args.output}")
    for pt in validated:
        print(f"  {pt['score']:3d} — {pt['name']} ({pt.get('peakWindow', '?')})")


if __name__ == "__main__":
    main()
