# Self-Improving Memory — GoogleClaw

Adapted from the Self-Improving + Proactive Agent skill (v1.2.16).
Scoped to GoogleClaw agents: TRENDS, MIDAS, SCOUT, LISTER, FEED.

---

## Memory Structure

```
workspace/googleclaw/
├── self-improving/
│   ├── memory.md        # HOT — store-wide patterns, always loaded by all agents
│   └── corrections.md  # Explicit corrections log (user corrects agent output)
└── agents/
    ├── trends/learnings.md
    ├── midas/learnings.md
    ├── scout/learnings.md
    ├── lister/learnings.md
    └── feed/learnings.md
```

---

## When Each Agent Loads Memory

**At the start of every run:**
1. Load `self-improving/memory.md` (global store context)
2. Load own `agents/{name}/learnings.md`

**At the end of every run:**
1. Write a brief reflection (see format below)
2. If something broke or underperformed → append to `corrections.md`
3. If a pattern repeated 3x → promote to `self-improving/memory.md`

---

## Reflection Format (end of run)

```
## YYYY-MM-DD — {agent} run
- Input: [brief description of what was processed]
- Result: [what happened]
- What worked: [specific observation]
- What to adjust: [specific suggestion for next run]
- Promoted to HOT: [yes/no — if yes, what]
```

---

## Global memory.md — What Goes Here

Store-wide patterns that ALL agents should know:

- Niche performance: "Mode > Electronics for this store (ROAS 3.1 vs 1.8)"
- Seasonal patterns: "Peak demand Q4 → start TRENDS scanning in September"
- Market behaviour: "NL market price ceiling ~€89 for fashion accessories"
- Supplier patterns: "CJ shipping >20 days = return rate spike — skip those products"
- Copy patterns: "Dutch informal tone outperforms formal (LISTER observation)"

---

## Per-Agent learnings.md — What Goes Here

### TRENDS
- Keywords that consistently return low-quality results → add to skip list
- Trend categories that never convert → deprioritize
- Seasonal timing that proved accurate

### MIDAS
- ROAS patterns that reliably indicate scaling opportunity
- Stores/campaigns that are exceptions to standard thresholds
- False positives in alert logic

### SCOUT
- Score calibrations that improved candidate quality
- Competitor stores that consistently surface good products
- CJ categories to avoid (low stock, long shipping, etc.)

### LISTER
- Copy angles that perform well for this niche
- Pricing methods that correlate with conversions
- Image styles (Gemini prompts) that look most professional

### FEED
- Price reduction amounts that recover ROAS without killing margin
- Products where draft/pause was correct vs too early
- Trend decline patterns that are real vs seasonal noise

---

## Corrections Log Format

```
| Date | Agent | What went wrong | Correction | Lesson |
|------|-------|----------------|------------|--------|
```

---

## Promotion Rules

| Condition | Action |
|-----------|--------|
| Same lesson appears 3x in agent learnings.md | Promote to self-improving/memory.md (HOT) |
| HOT pattern unused 30 days | Move back to agent learnings.md |
| HOT pattern unused 90 days | Archive (add note, keep file small) |
| User explicitly corrects agent | Append to corrections.md immediately |

---

## Memory Size Limits

| File | Max lines | Action when exceeded |
|------|-----------|----------------------|
| self-improving/memory.md | 80 lines | Merge similar, archive oldest |
| agents/{name}/learnings.md | 60 lines | Archive bottom half |
| corrections.md | 50 entries | Archive oldest 25 |
