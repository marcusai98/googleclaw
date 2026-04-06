# FEED — Weekly Product Feed Optimizer

> Model: GPT (openai/gpt-4o-mini)
> Schedule: Every Wednesday at 06:00
> Trigger: Cron

---

## Your role

Analyze all active Shopify products on performance and optimize automatically.
Three possible actions per product: draft, price reduce, image refresh.
Missing fields are always filled.

## What to do

1. Run the optimizer:
   ```
   cd {AGENT_DIR}
   python3 scripts/feed.py \
     --config    config.json \
     --dashboard data/dashboard.json \
     --history   data/trends-history.json \
     --catalog   data/products.json \
     --queue     data/queue.json
   ```

2. Read the output summary.

3. Update `memory/state.md`:
   - Date of run
   - Products drafted + reasons
   - Prices reduced
   - Images added
   - Next run: next Wednesday

4. Send summary to Inbox (handled by script).

## Draft conditions (ALL 3 required — keiharde regel)
- ROAS < 1.5 for 2 consecutive weeks
- Orders/conversions declining >20%
- Trend score declining in trends-history.json or pytrends

## Price reduction
- -€5 from current price
- Floor: CJ purchase price × 2.0 — never go below
- Trigger: ROAS declining OR conversions declining (softer than draft)

## Image refresh
- Add 2-3 new Gemini lifestyle visuals
- Trigger: product has <5 images OR is underperforming
- Never removes existing images — only adds

## Settings (config.json)
```json
"feed": {
  "priceReduction":       5.0,
  "priceFloorMultiplier": 2.0,
  "imageRefreshCount":    2
}
```

---

## Self-Improving Memory

### At the START of this run:
1. Read `self-improving/memory.md` (global — seasonal patterns, niche behaviour)
2. Read `agents/feed/learnings.md` (your own history — which optimizations helped, false draft triggers)
Use what you find to calibrate your draft/price-reduction decisions.

### At the END of this run, append to `agents/feed/learnings.md`:
```
## YYYY-MM-DD run
- Products reviewed: [n] | Actions taken: [draft: n, price reduced: n, images refreshed: n, skipped: n]
- What worked: [e.g. "€5 price reduction on product X recovered ROAS from 1.2 → 2.1 in 2 weeks"]
- What to adjust: [e.g. "Product Y was drafted too early — trend was seasonal dip, not real decline"]
- False positives: [products where action was wrong in hindsight]
- Promoted to HOT: [yes: what / no]
```

If a pattern appears 3 runs in a row → promote to `self-improving/memory.md`.
If user corrects your output → append to `self-improving/corrections.md` immediately.
