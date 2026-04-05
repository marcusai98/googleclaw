#!/usr/bin/env python3
"""
TRENDS — Research + Validation Pipeline
1. Manus AI     → generates 15-20 candidate product types
2. pytrends     → validates Google Trends curve per candidate
3. Google Ads   → validates search volume + CPC per candidate
4. Writes validated trends to trends.json

Usage:
    python3 call_manus.py --config config.json --output data/trends.json
"""

import json
import time
import argparse
import datetime
import requests
from pathlib import Path

# Optional imports
try:
    from pytrends.request import TrendReq
    HAS_PYTRENDS = True
except ImportError:
    HAS_PYTRENDS = False
    print("[TRENDS] pytrends not installed — skipping Google Trends validation")

try:
    from google.ads.googleads.client import GoogleAdsClient
    HAS_GOOGLE_ADS = True
except ImportError:
    HAS_GOOGLE_ADS = False
    print("[TRENDS] google-ads not installed — skipping Keyword Planner validation")

MANUS_API_URL = "https://api.manus.ai/v1"
POLL_INTERVAL = 30
MAX_WAIT      = 3600


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — MANUS: generate candidates
# ─────────────────────────────────────────────────────────────────────────────

def build_manus_prompt(cfg: dict) -> str:
    niche  = cfg["store"]["niche"]
    market = cfg["store"]["market"]
    lang   = cfg["store"].get("language", "English")
    today  = datetime.date.today().isoformat()

    return f"""
You are a product trend researcher for a dropshipping store.

Store niche: {niche}
Target market: {market}
Research language: {lang}
Today's date: {today}

## Task

Generate 20 candidate trending PRODUCT TYPES within the "{niche}" niche for the {market} market.

Product type level (not too broad, not too specific):
- Too broad: "clothing"
- Too specific: "blue Nike polo size M"
- Correct: "polo shirt", "regenjas", "sandalen", "zwembroek", "jurk"

## Research sources to use
- TikTok trending content in {market} for {niche}
- Reddit communities relevant to {niche}
- Seasonal calendar for {market} — what is coming up in the next 1-6 months?
- Fashion/trend industry reports
- Google Shopping trending searches if available

## For each candidate, provide

Return ONLY a JSON array. No markdown, no explanation. Exactly:

[
  {{
    "name": "Product type name in {lang}",
    "englishName": "English translation",
    "signals": ["TikTok NL trending", "Seasonal: autumn approaching"],
    "estimatedPeakWindow": "Month – Month YYYY",
    "estimatedMonthsUntilPeak": 3,
    "category": "seasonal | evergreen | viral | emerging"
  }}
]

Return exactly 20 candidates. Only the JSON array, nothing else.
"""


def submit_manus_task(api_key: str, prompt: str) -> str:
    headers = {"API_KEY": api_key, "Content-Type": "application/json"}
    r = requests.post(f"{MANUS_API_URL}/tasks",
                      json={"input": prompt, "version": "v2"},
                      headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise ValueError(f"No task_id in Manus response: {data}")
    print(f"[TRENDS] Manus task submitted: {task_id}")
    return task_id


def poll_manus_task(api_key: str, task_id: str) -> str:
    headers = {"API_KEY": api_key}
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        r = requests.get(f"{MANUS_API_URL}/tasks/{task_id}", headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "")
        print(f"[TRENDS] Manus status: {status}")
        if status in ("completed", "success", "done"):
            return data.get("result") or data.get("output") or data.get("response") or str(data)
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Manus task failed: {data.get('error', status)}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Manus task {task_id} timed out after {MAX_WAIT}s")


def extract_candidates(text: str) -> list:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON array from Manus response:\n{text[:500]}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — PYTRENDS: validate Google Trends curve
# ─────────────────────────────────────────────────────────────────────────────

# Google Trends geo codes
GEO_MAP = {
    "Netherlands": "NL", "Germany": "DE", "Belgium": "BE",
    "France": "FR", "United Kingdom": "GB", "United States": "US",
    "Spain": "ES", "Italy": "IT", "Poland": "PL", "Portugal": "PT",
}

def pytrends_validate(candidates: list, market: str) -> dict:
    """
    Returns dict: {candidate_name: {rising: bool, yoy_growth: float, consistent: bool}}
    """
    if not HAS_PYTRENDS:
        return {c["name"]: {"rising": True, "yoy_growth": 0, "consistent": True, "skipped": True}
                for c in candidates}

    geo  = GEO_MAP.get(market, "")
    pytr = TrendReq(hl="en-US", tz=60)
    results = {}

    # Process in batches of 5 (pytrends limit)
    for i in range(0, len(candidates), 5):
        batch = candidates[i:i+5]
        terms = [c.get("englishName", c["name"]) for c in batch]
        try:
            pytr.build_payload(terms, timeframe="today 12-m", geo=geo)
            df = pytr.interest_over_time()
            if df.empty:
                for c in batch:
                    results[c["name"]] = {"rising": False, "yoy_growth": 0, "consistent": False}
                continue

            for c, term in zip(batch, terms):
                if term not in df.columns:
                    results[c["name"]] = {"rising": False, "yoy_growth": 0, "consistent": False}
                    continue

                series = df[term].values
                n = len(series)
                if n < 8:
                    results[c["name"]] = {"rising": False, "yoy_growth": 0, "consistent": False}
                    continue

                # Rising: last 4 weeks avg > previous 4 weeks avg
                recent = series[-4:].mean()
                prev   = series[-8:-4].mean()
                rising = recent > prev * 1.05  # at least 5% higher

                # YoY growth: last month vs same month last year
                last_month  = series[-4:].mean()
                year_ago    = series[:4].mean()
                yoy = ((last_month - year_ago) / year_ago * 100) if year_ago > 0 else 0

                # Consistent: not a single spike (std/mean ratio)
                mean = series[-12:].mean()
                std  = series[-12:].std()
                consistent = (std / mean < 1.5) if mean > 0 else False

                results[c["name"]] = {
                    "rising": bool(rising),
                    "yoy_growth": round(float(yoy), 1),
                    "consistent": bool(consistent),
                    "recent_avg": round(float(recent), 1),
                }
                print(f"[TRENDS] pytrends '{term}': rising={rising}, yoy={yoy:.0f}%, consistent={consistent}")

        except Exception as e:
            print(f"[TRENDS] pytrends batch error: {e}")
            for c in batch:
                results[c["name"]] = {"rising": True, "yoy_growth": 0, "consistent": True, "error": str(e)}

        time.sleep(2)  # rate limit

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — GOOGLE ADS: search volume + CPC via Keyword Planner
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODES = {
    "Dutch": "1010", "German": "1001", "French": "1002",
    "English": "1000", "Spanish": "1003", "Italian": "1004",
}

LOCATION_CODES = {
    "Netherlands": "2528", "Germany": "2276", "Belgium": "2056",
    "France": "2250", "United Kingdom": "2826", "United States": "2840",
}

def google_ads_keyword_data(candidates: list, cfg: dict) -> dict:
    """
    Returns dict: {candidate_name: {monthly_volume: int, avg_cpc: float}}
    """
    if not HAS_GOOGLE_ADS:
        return {c["name"]: {"monthly_volume": 0, "avg_cpc": 0, "skipped": True}
                for c in candidates}

    ga_cfg = cfg["googleAds"]
    market = cfg["store"]["market"]
    lang   = cfg["store"].get("language", "English")

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": ga_cfg["developerToken"],
            "client_id":       ga_cfg["clientId"],
            "client_secret":   ga_cfg["clientSecret"],
            "refresh_token":   ga_cfg["refreshToken"],
            "use_proto_plus":  True,
        })
        customer_id = ga_cfg["customerId"].replace("-", "")
        kp_service  = client.get_service("KeywordPlanIdeaService")

        results = {}
        for c in candidates:
            term = c.get("englishName", c["name"])
            try:
                request = client.get_type("GenerateKeywordIdeasRequest")
                request.customer_id = customer_id
                request.keyword_seed.keywords.append(term)
                request.geo_target_constants.append(
                    f"geoTargetConstants/{LOCATION_CODES.get(market, '2528')}"
                )
                request.language = f"languageConstants/{LANGUAGE_CODES.get(lang, '1010')}"

                response = kp_service.generate_keyword_ideas(request=request)
                # Take the first (exact match) result
                for idea in response:
                    kw = idea.text
                    if kw.lower() == term.lower():
                        vol = idea.keyword_idea_metrics.avg_monthly_searches
                        cpc = idea.keyword_idea_metrics.average_cpc_micros / 1_000_000
                        results[c["name"]] = {
                            "monthly_volume": int(vol),
                            "avg_cpc": round(float(cpc), 2),
                        }
                        print(f"[TRENDS] KW '{term}': vol={vol}, cpc=€{cpc:.2f}")
                        break
                else:
                    results[c["name"]] = {"monthly_volume": 0, "avg_cpc": 0}
            except Exception as e:
                print(f"[TRENDS] KW Planner error for '{term}': {e}")
                results[c["name"]] = {"monthly_volume": 0, "avg_cpc": 0, "error": str(e)}

        return results

    except Exception as e:
        print(f"[TRENDS] Google Ads connection error: {e}")
        return {c["name"]: {"monthly_volume": 0, "avg_cpc": 0, "error": str(e)}
                for c in candidates}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — SCORE + FILTER
# ─────────────────────────────────────────────────────────────────────────────

def score_candidate(candidate: dict, trends_data: dict, kw_data: dict, cfg: dict) -> dict:
    name     = candidate["name"]
    td       = trends_data.get(name, {})
    kw       = kw_data.get(name, {})

    # Hard filters
    min_volume = cfg.get("thresholds", {}).get("minMonthlySearchVolume", 5000)
    max_cpc    = cfg.get("thresholds", {}).get("maxCpc", 2.0)

    rising     = td.get("rising", True)
    consistent = td.get("consistent", True)
    volume     = kw.get("monthly_volume", 0)
    cpc        = kw.get("avg_cpc", 0)
    yoy        = td.get("yoy_growth", 0)

    # Skip if clearly bad (unless data was skipped/missing)
    skipped = td.get("skipped") or kw.get("skipped")
    if not skipped:
        if not rising:
            return None
        if volume > 0 and volume < min_volume:
            return None
        if cpc > 0 and cpc > max_cpc:
            return None
        if yoy < -20:  # actively declining YoY
            return None

    # Scoring
    months_to_peak = candidate.get("estimatedMonthsUntilPeak", 3)

    # Trend momentum (0-30)
    trend_score = 0
    if rising:          trend_score += 15
    if consistent:      trend_score += 10
    if yoy >= 50:       trend_score += 5
    elif yoy >= 20:     trend_score += 3

    # Volume (0-25)
    if   volume >= 50000: vol_score = 25
    elif volume >= 20000: vol_score = 20
    elif volume >= 10000: vol_score = 15
    elif volume >= 5000:  vol_score = 10
    else:                 vol_score = 5 if skipped else 0

    # Timing (0-20) — sweet spot is 2-4 months away
    if   1 <= months_to_peak <= 2:  timing_score = 15
    elif 2 < months_to_peak <= 4:   timing_score = 20
    elif 4 < months_to_peak <= 6:   timing_score = 10
    else:                            timing_score = 3

    # CPC / competition (0-15) — lower CPC = less competition = better
    if   cpc == 0:        cpc_score = 8  # unknown
    elif cpc <= 0.30:     cpc_score = 15
    elif cpc <= 0.60:     cpc_score = 12
    elif cpc <= 1.00:     cpc_score = 9
    elif cpc <= 1.50:     cpc_score = 6
    elif cpc <= 2.00:     cpc_score = 3
    else:                 cpc_score = 0

    # Signals (0-10)
    signals    = candidate.get("signals", [])
    sig_score  = min(10, len(signals) * 3)

    total = trend_score + vol_score + timing_score + cpc_score + sig_score

    # Momentum label
    if yoy >= 50 or (rising and months_to_peak <= 2):
        momentum = "accelerating"
    elif rising:
        momentum = "rising"
    else:
        momentum = "stable"

    return {
        "name":                  name,
        "momentum":              momentum,
        "peakWindow":            candidate.get("estimatedPeakWindow", ""),
        "monthsUntilPeak":       months_to_peak,
        "googleTrendDirection":  "rising" if rising else "stable",
        "yoyGrowth":             f"+{yoy:.0f}%" if yoy >= 0 else f"{yoy:.0f}%",
        "monthlySearchVolume":   volume,
        "avgCpc":                f"€{cpc:.2f}" if cpc > 0 else "unknown",
        "signals":               signals,
        "reason":                f"{', '.join(signals[:2])}. YoY growth: {yoy:.0f}%. "
                                 f"Peak expected: {candidate.get('estimatedPeakWindow', '?')}.",
        "score":                 min(100, total),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TRENDS Research Pipeline")
    parser.add_argument("--config",      default="config.json",       help="Path to config.json")
    parser.add_argument("--output",      default="data/trends.json",  help="Output path")
    parser.add_argument("--candidates",  default=None,                help="Skip Manus, load candidates JSON directly")
    args = parser.parse_args()

    cfg    = load_config(args.config)
    niche  = cfg["store"]["niche"]
    market = cfg["store"]["market"]
    today  = datetime.date.today()

    print(f"[TRENDS] Starting: {niche} / {market}")

    # Step 1: Manus candidates
    if args.candidates:
        print(f"[TRENDS] Loading candidates from {args.candidates}")
        with open(args.candidates) as f:
            candidates = json.load(f)
    else:
        api_key   = cfg["manus"]["apiKey"]
        prompt    = build_manus_prompt(cfg)
        task_id   = submit_manus_task(api_key, prompt)
        result    = poll_manus_task(api_key, task_id)
        candidates = extract_candidates(result)
        print(f"[TRENDS] Manus returned {len(candidates)} candidates")

    # Step 2: pytrends validation
    print(f"[TRENDS] Running pytrends validation...")
    trends_data = pytrends_validate(candidates, market)

    # Step 3: Google Ads keyword data
    print(f"[TRENDS] Fetching Keyword Planner data...")
    kw_data = google_ads_keyword_data(candidates, cfg)

    # Step 4: Score + filter
    print(f"[TRENDS] Scoring and filtering...")
    scored = []
    for c in candidates:
        result = score_candidate(c, trends_data, kw_data, cfg)
        if result and result["score"] >= 50:
            scored.append(result)
        elif result:
            print(f"[TRENDS] Dropped '{c['name']}' — score {result['score']} < 50")
        else:
            print(f"[TRENDS] Dropped '{c['name']}' — failed hard filter")

    scored.sort(key=lambda x: x["score"], reverse=True)
    final = scored[:10]

    if len(final) < 3:
        print(f"[TRENDS] WARNING: Only {len(final)} trends validated")

    # Build output
    output = {
        "generatedAt":   datetime.datetime.utcnow().isoformat() + "Z",
        "validUntil":    (today + datetime.timedelta(days=7)).isoformat() + "T02:00:00Z",
        "storeNiche":    niche,
        "market":        market,
        "trendsCount":   len(final),
        "productTypes":  final,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[TRENDS] Done — {len(final)} validated trends:")
    for t in final:
        print(f"  {t['score']:3d} — {t['name']} | {t['momentum']} | peak: {t['peakWindow']}")


if __name__ == "__main__":
    main()
