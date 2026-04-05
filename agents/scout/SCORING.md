# SCOUT — Scoring Model v2

## Core principle
SCOUT's job: find products with real trend demand that can sell for ≥€40.
Margin is NOT scored here — that's LISTER/MIDAS territory.

## Score (0–100)

| Dimension       | Weight | Source                          |
|-----------------|--------|---------------------------------|
| Trend match     | 0–35   | Keyword match against trends.json |
| Search volume   | 0–30   | Google Trends volume (trends.json) |
| Demand proof    | 0–25   | Amazon BSR + competitor presence |
| Supplier avail  | 0–10   | CJ: product exists + deliverable |

## Hard filters (instant drop, no scoring)
- Selling price < €40 (any method where price is detectable)
- Zero trend match (no keyword overlap with trends.json)
- CJ only: out of stock + no alternatives

## Trend match (0–35)
```
Exact keyword match in product title     → 35
Partial match (main keyword present)     → 20
Category/niche match only                → 10
No match                                 → DROP
```

## Search volume (0–30)
```
≥ 50,000 / month   → 30
≥ 20,000           → 22
≥ 10,000           → 15
≥  5,000           →  8
<  5,000           →  0
```
Volume from trends.json (pre-validated by TRENDS agent).
If product matches multiple trends, use highest volume.

## Demand proof (0–25)
```
Amazon BSR top 500 in category          → 15
Amazon BSR 500–5,000                    → 10
Amazon BSR 5,000–20,000                 → 5
Found on ≥2 competitor stores           → +10
Found on 1 competitor store             → +5
No demand proof                         → 0
```
Cap at 25.

## Supplier availability (0–10)
```
CJ: in stock, ships ≤14 days            → 10
CJ: in stock, ships 15–25 days          →  6
CJ: low stock or ships >25 days         →  3
CJ: not found (other methods only)      →  0
```

## Multi-source bonus
```
Found by 3 methods   → +20
Found by 2 methods   → +10
Found by 1 method    →  +0
```
Applied after base score, before cap of 100.

## Inbox thresholds
```
≥ 75  → auto-publish to Inbox (high confidence)
60–74 → Inbox with "needs review" flag
< 60  → dropped (not shown)
```

## What gets stored in candidates.json
Even though margin isn't scored, CJ purchase price IS stored
for LISTER to use later:
- cjPrice (purchase price)
- estimatedShipping
- cjProductId
- amazonAsin (if found)
- competitorUrls (if found)
