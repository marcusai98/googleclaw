# TRENDS — Weekly Market Research Agent

Identifies the top trending product types within the store's niche.
Runs every Monday at 02:00 and writes `data/trends.json` for SCOUT to consume.

## How it works

1. Builds a research prompt based on your store's niche and target market
2. Submits to Manus AI for deep research (Google Trends + Keyword Planner + TikTok + Reddit)
3. Validates each candidate against strict Google data criteria
4. Writes up to 10 validated product types to `trends.json`

## Validation rules (all must pass)

A product type is only included if:
- Google Trends curve is **rising** for the past 4 weeks
- Year-over-year growth of **≥ 20%**
- Monthly search volume **≥ 5,000** in target market
- Average CPC **≤ €2.00**
- Peak window is **1-5 months away**

## Config requirements

Add to your `config.json`:
```json
{
  "store": {
    "niche": "women's fashion",
    "market": "Netherlands",
    "language": "Dutch"
  },
  "manus": {
    "apiKey": "YOUR_MANUS_API_KEY"
  }
}
```

## Install & run

```bash
pip3 install requests
python3 scripts/call_manus.py --config config.json --output data/trends.json
```

## Register cron in OpenClaw

```
openclaw cron add \
  --name "trends-{store-name}" \
  --schedule "0 2 * * 1" \
  --task "$(cat prompt.md)" \
  --model "manus"
```

## Output: trends.json

```json
{
  "generatedAt": "2026-04-07T02:00:00Z",
  "validUntil": "2026-04-14T02:00:00Z",
  "storeNiche": "women's fashion",
  "market": "Netherlands",
  "trendsCount": 7,
  "productTypes": [
    {
      "name": "Regenjas",
      "momentum": "rising",
      "peakWindow": "Okt – Nov 2026",
      "monthsUntilPeak": 6,
      "googleTrendDirection": "rising",
      "monthlySearchVolume": 22000,
      "avgCpc": "€0.42",
      "reason": "Consistent stijgend zoekvolume de afgelopen 3 jaar. Herfstseizoen nadert. TikTok NL toont vroege interesse.",
      "score": 82
    }
  ]
}
```

## Notes

- Manus tasks typically take 10-40 minutes — the script polls automatically
- If fewer than 3 trends are validated, a warning is logged but the run is still considered successful
- SCOUT reads trends.json daily — always keep it fresh (max 7 days old)
