# GoogleClaw — Implementation Blueprint
*Version 1.0 · April 2026 · For handoff to build agent*

## Context
GoogleClaw is a multi-agent orchestrator for Google Ads dropshipping. Agents run autonomously overnight, surface decisions in a mobile inbox, and learn from every approval. Henk spends ~10 minutes/day in the app; agents handle the rest.

## Scope of V1
Agents: HERALD, SCOUT, MIDAS, LISTER, COMMANDER
Mobile: iOS (Expo WebView) + Web (already built)
Infrastructure: VPS 178.16.131.160 + Supabase + MariaDB

---

## Architecture layers (bottom → top)

1. Data Layer — raw sources (Google Ads, Shopify, AliExpress)
2. Warehouse Layer — normalized tables in Supabase
3. Agent Layer — Python scripts per agent
4. Orchestration Layer — OpenClaw crons + event bus
5. API Layer — FastAPI, serves mobile app
6. UI Layer — mobile.html (already built)

---

## Phase 1 — Foundation

### 1.1 Supabase schema

```sql
-- Approval queue (feeds mobile Inbox)
CREATE TABLE gc_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL, -- product / scale / optimize / alert / feed
  agent TEXT NOT NULL,
  payload JSONB NOT NULL,
  status TEXT DEFAULT 'pending', -- pending / approved / declined / auto
  decided_at TIMESTAMPTZ,
  decision_context JSONB, -- what Henk saw when deciding
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Agent memory (self-learning)
CREATE TABLE gc_agent_memory (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent TEXT NOT NULL,
  key TEXT NOT NULL,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(agent, key)
);

-- Store config (per-store thresholds, overrides)
CREATE TABLE gc_store_config (
  google_customer_id TEXT PRIMARY KEY,
  store_name TEXT,
  target_roas NUMERIC DEFAULT 3.0,
  scale_threshold NUMERIC DEFAULT 3.5,
  alert_threshold NUMERIC DEFAULT 1.0,
  max_daily_budget NUMERIC,
  active BOOLEAN DEFAULT true,
  notes TEXT
);

-- Agent runs (audit log)
CREATE TABLE gc_agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent TEXT NOT NULL,
  run_at TIMESTAMPTZ DEFAULT now(),
  duration_ms INTEGER,
  items_found INTEGER DEFAULT 0,
  items_queued INTEGER DEFAULT 0,
  error TEXT,
  summary JSONB
);

-- Product outcomes (SCOUT learning)
CREATE TABLE gc_product_outcomes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_name TEXT,
  supplier_url TEXT,
  scout_score INTEGER,
  trend_stage TEXT,
  buy_price NUMERIC,
  sell_price NUMERIC,
  margin NUMERIC,
  approved BOOLEAN,
  launched BOOLEAN DEFAULT false,
  revenue_30d NUMERIC,
  roas_30d NUMERIC,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 1.2 Shared Python module (agents/shared.py)

```python
# supabase client, google ads client, shopify client
# read/write gc_agent_memory
# push to gc_queue
# send Telegram notification
# log agent run to gc_agent_runs
```

### 1.3 FastAPI server (api/main.py)

Endpoints:
- GET  /queue              → pending items for mobile Inbox
- POST /queue/{id}/approve → approve + execute action
- POST /queue/{id}/decline → decline
- GET  /dashboard          → home screen data (revenue, ROAS, profit, 7d chart)
- GET  /agents             → agent status + last run
- GET  /analytics          → full analytics data
- WS   /live               → WebSocket for real-time queue updates

Auth: Bearer token (stored in mobile app config)

---

## Phase 2 — Core agents

### HERALD — Performance Monitor

**Purpose:** Watch every active store. Surface scaling opportunities and underperformance alerts.

**Triggers:**
- Cron: every day at 06:00 (nightly data settled)
- Real-time: hourly check on stores with spend >€100/day

**Data sources:**
- Google Ads API → campaign performance (ROAS, spend, impressions)
- MariaDB v_store_performance → confirmed revenue (Shopify source of truth)
- gc_store_config → per-store thresholds

**Logic:**
```
For each active store:
  roas_3d = average ROAS last 3 days
  roas_7d = average ROAS last 7 days
  spend_7d = total spend last 7 days

  IF roas_3d >= store.scale_threshold AND spend_7d >= 150:
    → queue item type='scale'
    payload: current_budget, proposed_budget (+30-40%), roas data

  IF roas_7d <= store.alert_threshold AND spend_7d >= 100:
    days_below = consecutive days ROAS < 1.0
    net_loss = revenue - spend (7d)
    → queue item type='alert'
    payload: roas, spend, revenue, net_loss, days_below
```

**Learning:**
- After each approved scale: track if ROAS held or dropped
- After N scales on same store: update scale_threshold in memory
- "Stores in category X respond best to +35% increments"

**Output example:**
```json
{
  "type": "scale",
  "agent": "HERALD",
  "store": "LED Desk Lamp Store",
  "campaign": "PMAX All Products",
  "currentBudget": "€45",
  "proposedBudget": "€65",
  "roas3d": "3.82x",
  "roas7d": "3.41x",
  "spend7d": "€285",
  "roas_data": [2.9, 3.1, 3.4, 3.2, 3.6, 3.7, 3.82],
  "reason": "3-day ROAS consistently above 3.5x. Strong momentum."
}
```

---

### SCOUT — Product Research

**Purpose:** Find trending products every night. Score them. Surface the best ones for approval.

**Triggers:**
- Cron: daily at 02:00

**Data sources:**
- Google Trends API → search volume trend (12 weeks)
- AliExpress scraper / Alitools API → price, rating, reviews, stock
- Competitor Shopify stores → what's selling (optional, V2)
- gc_product_outcomes → past approvals to train scoring

**Scoring model (0–100):**
```
trend_score      = 0–30 pts  (slope of 12-week trend curve)
margin_score     = 0–25 pts  (margin / sell_price ratio)
competition_score= 0–20 pts  (search volume vs listing count)
supplier_score   = 0–15 pts  (rating, review count, stock)
timing_score     = 0–10 pts  (early_rise > peak > fading)

TOTAL: weighted sum, normalized to 100
Auto-approve threshold: score >= 80 (LISTER publishes directly)
Queue threshold: score >= 60 (Henk decides)
Discard: score < 60
```

**Trend stages:**
- `early_rise`: slope positive, volume still low → best window
- `at_peak`: high volume, slope flattening → high competition
- `fading`: slope negative → avoid

**Learning:**
- Every decision stored in gc_product_outcomes
- Weekly: recalculate feature weights based on actual outcomes
- "Products with trend_score > 22 AND margin > €14 have 82% 30-day success rate"
- Adjust scoring weights monthly

**Output example:**
```json
{
  "type": "product",
  "agent": "SCOUT",
  "name": "Portable Neck Fan",
  "img": "https://...",
  "source": "AliExpress",
  "rating": "4.8 ★",
  "buy": "€8.20",
  "sell": "€29.99",
  "margin": "€18",
  "score": 82,
  "trend": "+340%",
  "trendStage": "early",
  "trendData": [8,10,12,14,18,22,28,36,45,58,72,88],
  "peakWindow": "May – Jun 2026",
  "trendVelocity": "Accelerating fast"
}
```

---

### MIDAS — Finance

**Purpose:** Daily P&L sync. Power the home screen charts and analytics tab.

**Triggers:**
- Cron: daily at 07:00 (after Shopify and Google Ads data settle)

**Data sources:**
- Shopify Admin API → daily revenue per store
- Google Ads API → daily spend per account
- COGS estimate (configurable %) per store

**Outputs:**
- Updates `gc_dashboard_daily` table (revenue, spend, ROAS, profit, per day)
- Powers /dashboard API endpoint
- No approval needed — read-only agent

**Learning:**
- Tracks margin% trends
- Flags if COGS estimate drifts from expected (V2)

---

## Phase 3 — Action agents

### LISTER — Store & Listings

**Purpose:** Take approved products and publish them to Shopify with generated images and optimized copy.

**Triggers:**
- Event: when gc_queue item type='product' is approved

**Flow:**
```
1. Receive approved product payload
2. Generate product images (Gemini image API, 4 product + 3 lifestyle)
3. Write product title, description, bullet points (Claude/GPT)
4. Push to Shopify via Admin API:
   - Create product
   - Upload images
   - Set price, compare_at_price
   - Assign collection
5. Log to gc_product_outcomes (launched=true)
6. Notify Henk via Telegram: "✅ [Product] published to [Store]"
```

**Learning:**
- Tracks CTR and conversion per listing variant
- Tests different title formats (V2 A/B test)

---

### COMMANDER — Google Ads Manager

**Purpose:** Audit campaigns weekly. Find wasted spend. Propose negative keywords and optimizations.

**Triggers:**
- Cron: weekly (Monday 05:00)
- On-demand: triggered by HERALD alert

**Data sources:**
- Google Ads API → search terms report, keyword performance
- gc_store_config → per-store settings

**Logic:**
```
For each active campaign:
  search_terms = get_search_terms(last_14_days)
  wasted = [t for t in search_terms
            if t.clicks >= 5 AND t.conversions == 0]
  savings_estimate = sum(t.cost for t in wasted)

  IF savings_estimate >= 10:
    → queue item type='optimize'
    payload: keywords as [{term, clicks, conv, spend}],
             totalClicks, totalSpend, impact
```

**Approval flow:**
- Henk approves → COMMANDER executes via Google Ads API
- Negative added at campaign level (never account level)
- Confirmation logged to gc_queue (status='approved')

**Learning:**
- Tracks which negative patterns recur across stores
- Builds a "universal waste list" per product category
- "Fashion stores always waste budget on 'cheap' + 'wholesale'"

---

## Phase 4 — Self-learning loop

### Memory architecture

Each agent has two memory layers:

**Layer 1 — Structured memory (Supabase)**
- `gc_agent_memory` table: key-value store per agent
- Examples: `herald.scale_success_rate`, `scout.approval_weights`, `commander.waste_patterns`

**Layer 2 — Narrative memory (files)**
- `/agents/herald/learnings.md` — human-readable patterns
- `/agents/scout/learnings.md`
- `/agents/commander/learnings.md`

### Weekly synthesis (Sunday 20:00)

A synthesis agent runs every Sunday:
```
For each agent:
  1. Pull last 7 days of decisions from gc_queue
  2. Calculate outcome metrics (approval rate, success rate)
  3. Update agent memory weights
  4. Append learnings to learnings.md
  5. Flag any rules that should be updated (queue to Henk if critical)
```

### Cross-agent learning

Agents share context via events:
- HERALD detects a store is scaling well → notifies SCOUT to find more products in that category
- SCOUT finds product with trend score 90 → HERALD monitors that category more closely
- COMMANDER finds waste pattern → HERALD uses it as early warning signal

---

## Phase 5 — Mobile app connection

### Current state
Frontend is built and published (HTML). It uses hardcoded mock data.

### Required changes

**mobile.html:**
- Replace all hardcoded QUEUE data with `fetch('/api/queue')`
- Replace dashboard stats with `fetch('/api/dashboard')`
- Replace agent feed with `fetch('/api/agents')`
- Add WebSocket connection for real-time queue updates
- Approve/decline calls: `POST /api/queue/{id}/approve`

**Config file (mobile-config.js):**
```js
const GC_API = 'https://googleclaw.icarusagency.io';
const GC_TOKEN = 'Bearer <token>';
```

**Hosting:**
- Serve mobile.html via Caddy on VPS
- Domain: `googleclaw.icarusagency.io` → reverse proxy to FastAPI
- HTTPS via Caddy auto-cert

---

## Tech stack

| Layer | Tech |
|---|---|
| Agents | Python 3.11 |
| API server | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) + existing MariaDB |
| Google Ads | google-ads-python |
| Shopify | shopify_python_api |
| Image gen | Gemini 3 Pro Image API |
| Copy gen | Anthropic Claude API |
| Trends | pytrends (Google Trends) |
| AliExpress | aliexpress_api or custom scraper |
| Hosting | VPS 178.16.131.160 (Hostinger) |
| Reverse proxy | Caddy |
| Orchestration | OpenClaw crons |
| Notifications | Telegram Bot API |
| Frontend | HTML/CSS/JS (already built) |

---

## Deployment structure (VPS)

```
/opt/googleclaw/
├── api/
│   ├── main.py          ← FastAPI server
│   └── requirements.txt
├── agents/
│   ├── shared.py        ← common clients, helpers
│   ├── herald.py
│   ├── scout.py
│   ├── midas.py
│   ├── lister.py
│   └── commander.py
├── frontend/
│   └── mobile.html      ← served by Caddy
├── .env                 ← all secrets
└── Caddyfile
```

---

## Cron schedule (OpenClaw on VPS)

| Time | Agent | Task |
|---|---|---|
| 02:00 daily | SCOUT | Product research run |
| 05:00 Mon | COMMANDER | Weekly keyword audit |
| 06:00 daily | HERALD | Performance check + scale/alert decisions |
| 07:00 daily | MIDAS | P&L sync + dashboard update |
| 20:00 Sunday | SYNTHESIS | Weekly learning loop |

---

## Build order (recommended)

1. Supabase schema (Phase 1.1)
2. shared.py — clients, helpers, queue push
3. FastAPI skeleton — all endpoints returning mock data first
4. MIDAS — simplest, read-only, validates data pipeline
5. HERALD — most valuable, drives daily decisions
6. Connect mobile.html to real API (replace mock data)
7. SCOUT — most complex, needs scraper + scoring
8. LISTER — depends on SCOUT approval flow
9. COMMANDER — depends on Google Ads API access
10. Self-learning loop — after V1 is live and generating data

---

## Secrets needed (.env)

```
SUPABASE_URL=
SUPABASE_KEY=
GOOGLE_ADS_DEVELOPER_TOKEN=kQPL6FCpa6yU48oY7BpS3g
GOOGLE_ADS_CLIENT_ID=575134000126-...
GOOGLE_ADS_CLIENT_SECRET=GOCSPX-...
GOOGLE_ADS_REFRESH_TOKEN=1//03mX-...
GOOGLE_ADS_MCC_ID=6869809862
SHOPIFY_ACCESS_TOKEN=  (per store)
ANTHROPIC_API_KEY=
GEMINI_API_KEY=AIzaSyCla-byxYjqilrxYiEsszRj0AtCF_lpSls
TELEGRAM_BOT_TOKEN=7747626582:...
TELEGRAM_CHAT_ID=2128015430
GC_API_TOKEN=  (generate random, store in mobile app)
MARIADB_HOST=mariadb.icarus-software.com
MARIADB_USER=henkjan
MARIADB_PASS=vTqVfOf5NCS0hh8Eauc0yOX4sA6o0n99
MARIADB_DB=icarus_db_01
```

---

## Definition of done (V1 live)

- [ ] Henk opens app in morning → sees real ROAS/revenue from yesterday
- [ ] HERALD queued at least 1 scale or alert from real data
- [ ] SCOUT queued at least 3 product suggestions overnight
- [ ] Approve in app → action executes in Google Ads or Shopify within 30s
- [ ] All agent runs logged in gc_agent_runs
- [ ] Approval decisions stored in gc_queue with full context
- [ ] Weekly synthesis updates agent memory
