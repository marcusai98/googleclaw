# MIDAS COGS REFRESH — Quarterly Cron Prompt

> Model: GPT (openai/gpt-4o-mini)
> Schedule: 1 Jan, 1 Apr, 1 Jul, 1 Oct at 06:00
> Cron expression: 0 6 1 1,4,7,10 *

---

## Your role

Run the quarterly COGS price refresh. Flag active products whose prices may
have changed due to shipping cost updates, supplier price changes, or currency shifts.
Only products sold in the last 90 days are flagged — inactive products are skipped.

## What to do

1. Run the refresh script:
   ```
   cd {AGENT_DIR}
   python3 scripts/refresh.py \
     --catalog data/products.json \
     --queue   data/queue.json \
     --config  config.json
   ```

2. Read the output — how many products were flagged?

3. Update `memory/state.md`:
   - Date of refresh run
   - Number flagged / number skipped (inactive)
   - Quarter label (e.g. Q2 2026)

4. If 0 products flagged → log "No active products need COGS review" and exit cleanly.

## What NOT to do

- Do NOT contact the supplier directly
- Do NOT modify COGS prices yourself
- Do NOT pause any campaigns
- The Inbox card and Telegram alert are handled by the script automatically
