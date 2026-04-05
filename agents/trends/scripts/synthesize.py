#!/usr/bin/env python3
"""
TRENDS — Seasonal Pattern Synthesizer
Runs monthly. Analyzes trends-history.json and builds seasonal-patterns.json.
The more data collected, the smarter TRENDS becomes at anticipating trends.

Usage:
    python3 synthesize.py --history data/trends-history.json \
                          --output  data/seasonal-patterns.json
"""

import json
import argparse
import datetime
from pathlib import Path
from collections import defaultdict


def load_json(path: str, default) -> dict:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(data: dict, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def synthesize(history: dict) -> dict:
    seen      = history.get("seen", {})
    monthly   = history.get("monthly", {})   # {name: {"YYYY-MM": score}}
    patterns  = {}

    for name, entry in seen.items():
        monthly_data = monthly.get(name, {})
        if not monthly_data:
            continue

        # Group scores by month-of-year (1-12)
        month_scores = defaultdict(list)
        year_months  = set()
        for ym, score in monthly_data.items():
            try:
                dt = datetime.date.fromisoformat(ym + "-01")
                month_scores[dt.month].append(score)
                year_months.add(dt.year)
            except ValueError:
                continue

        if not month_scores:
            continue

        # Find strong months (avg score ≥ 60)
        strong_months = sorted([
            m for m, scores in month_scores.items()
            if sum(scores) / len(scores) >= 60
        ])

        # Find peak month (highest avg score)
        peak_month = max(month_scores, key=lambda m: sum(month_scores[m]) / len(month_scores[m]))
        peak_avg   = sum(month_scores[peak_month]) / len(month_scores[peak_month])

        # Classify pattern
        if len(strong_months) >= 10:
            pattern = "evergreen"
            anticipate_from = None
        elif len(strong_months) <= 3:
            pattern = "annual_seasonal"
            # Start anticipating 2 months before the strong window
            anticipate_from = strong_months[0] - 2 if strong_months else None
            if anticipate_from and anticipate_from < 1:
                anticipate_from += 12
        else:
            pattern = "semi_seasonal"
            anticipate_from = strong_months[0] - 1 if strong_months else None
            if anticipate_from and anticipate_from < 1:
                anticipate_from += 12

        # Build historical peaks (month-year when score was highest)
        historical_peaks = []
        for ym, score in sorted(monthly_data.items(), reverse=True)[:5]:
            if score >= 65:
                historical_peaks.append(ym)

        # Score bonus for known patterns
        if len(year_months) >= 2:
            confidence = "high"
            score_bonus = 10
        elif len(year_months) == 1:
            confidence = "medium"
            score_bonus = 5
        else:
            confidence = "low"
            score_bonus = 0

        avg_score = sum(
            s for scores in month_scores.values() for s in scores
        ) / sum(len(s) for s in month_scores.values())

        patterns[name] = {
            "pattern":              pattern,
            "strongMonths":         strong_months,
            "peakMonth":            peak_month,
            "peakMonthAvgScore":    round(peak_avg, 1),
            "avgScoreAllTime":      round(avg_score, 1),
            "historicalPeaks":      historical_peaks,
            "yearsObserved":        len(year_months),
            "confidence":           confidence,
            "scoreBonus":           score_bonus,
            "anticipate":           anticipate_from is not None,
            "anticipateFromMonth":  anticipate_from,
            "timesReported":        entry.get("timesReported", 0),
            "lastUpdated":          datetime.date.today().isoformat(),
        }

        print(f"[SYNTHESIZE] '{name}': {pattern}, peak month {peak_month}, "
              f"confidence={confidence}, bonus=+{score_bonus}")

    return patterns


def main():
    parser = argparse.ArgumentParser(description="TRENDS Seasonal Synthesizer")
    parser.add_argument("--history", default="data/trends-history.json")
    parser.add_argument("--output",  default="data/seasonal-patterns.json")
    args = parser.parse_args()

    print(f"[SYNTHESIZE] Loading history from {args.history}")
    history = load_json(args.history, {"seen": {}, "monthly": {}})

    patterns = synthesize(history)
    print(f"[SYNTHESIZE] Built patterns for {len(patterns)} product types")

    output = {
        "generatedAt":  datetime.datetime.utcnow().isoformat() + "Z",
        "totalPatterns": len(patterns),
        "patterns":     patterns,
    }
    save_json(output, args.output)
    print(f"[SYNTHESIZE] Written to {args.output}")


if __name__ == "__main__":
    main()
