# SCOUT — Product Scoring Model

SCOUT scores individual AliExpress products on a 0-100 scale.
This score determines what happens to a product:

| Score | Action |
|---|---|
| ≥ 75 | Auto-publish via LISTER (no approval needed) |
| 60 – 74 | Send to Inbox for Henk's approval |
| < 60 | Discard silently |

---

## Scoring dimensions (total: 100 points)

### 1. Trend alignment — 0 to 25 points
How well does this specific product match the validated trend from TRENDS?

| Condition | Points |
|---|---|
| Product type exactly matches a trend in trends.json (score ≥ 80) | 25 |
| Product type matches a trend in trends.json (score 60–79) | 18 |
| Product type loosely related to a trend | 10 |
| No trend match found | 0 |

**Why:** A regenjas in October is validated. A random regenjas in July is not.

---

### 2. Margin potential — 0 to 25 points
Net margin after product cost + estimated shipping.

| Margin % (after COGS + shipping) | Points |
|---|---|
| ≥ 60% | 25 |
| 50 – 59% | 20 |
| 40 – 49% | 15 |
| 30 – 39% | 10 |
| 20 – 29% | 5 |
| < 20% | 0 |

**Calculation:** `(sell_price - buy_price - shipping) / sell_price`
Estimated sell price = buy_price × markup_multiplier (from config, default: 3.5×)

---

### 3. Supplier quality — 0 to 20 points
AliExpress supplier reliability signals.

| Signal | Points |
|---|---|
| Rating ≥ 4.7 stars | +8 |
| Rating 4.3 – 4.6 | +5 |
| Rating < 4.3 | +0 |
| Reviews ≥ 1,000 | +6 |
| Reviews 500 – 999 | +4 |
| Reviews 100 – 499 | +2 |
| Reviews < 100 | +0 |
| Shipping ≤ 10 days (ePacket/AliExpress Standard) | +6 |
| Shipping 11 – 20 days | +3 |
| Shipping > 20 days | +0 |

---

### 4. Competition level — 0 to 20 points
How saturated is the market for this product?

| Condition | Points |
|---|---|
| AliExpress results < 500 for this product type | 20 |
| AliExpress results 500 – 2,000 | 15 |
| AliExpress results 2,001 – 10,000 | 8 |
| AliExpress results > 10,000 | 3 |
| Already in the store's Shopify catalog | 0 (discard) |

**Note:** "Already in catalog" is a hard discard — never score, never show.

---

### 5. Price point — 0 to 10 points
Is the sell price realistic for the target market?

| Sell price range (estimated) | Points |
|---|---|
| €15 – €60 (sweet spot) | 10 |
| €10 – €14 | 6 |
| €61 – €100 | 6 |
| < €10 | 2 |
| > €100 | 2 |

**Why:** Under €10 = hard to make margin. Over €100 = conversion drops.

---

## Hard discards (score = 0, never shown)

These conditions immediately discard a product regardless of score:

- Already exists in the Shopify catalog (by title or SKU match)
- Buy price > €40 (too expensive to dropship safely)
- Shipping time > 30 days (customer experience too poor)
- Supplier rating < 3.5 stars
- Prohibited product category (weapons, adult, hazmat — from config blocklist)
- Product images are watermarked or clearly stolen (detected via image check)

---

## Score calculation example

```
Product: "Waterproof Regenjas Women"
Buy price: €12.50 | Est. sell price: €43.75 (3.5× markup)
Shipping: €2.50 | Margin: (43.75 - 12.50 - 2.50) / 43.75 = 66%

Trend alignment:  "Regenjas" in trends.json with score 82 → 25 pts
Margin:           66% → 25 pts
Supplier:         4.8★ (+8) + 2,400 reviews (+6) + 12 days (+3) = 17 pts
Competition:      3,200 results → 8 pts
Price point:      €43.75 → 10 pts

Total: 25 + 25 + 17 + 8 + 10 = 85 → AUTO-PUBLISH ✓
```

---

## Config overrides

These defaults can be adjusted in `config.json`:

```json
"scout": {
  "autoPublishScore": 75,
  "inboxMinScore": 60,
  "markupMultiplier": 3.5,
  "maxBuyPrice": 40,
  "maxShippingDays": 30,
  "blocklist": ["weapons", "adult", "supplements"]
}
```
