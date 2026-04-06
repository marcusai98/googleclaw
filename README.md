# GoogleClaw

Multi-agent orchestrator for Google Ads dropshipping stores on Shopify.
Built on OpenClaw — no standalone servers, no databases, no extra infrastructure.

---

## Quickstart

```bash
git clone https://github.com/marcusai98/googleclaw
cd googleclaw
python3 setup.py      # guided onboarding — creates config.json, registers crons, generates SOUL.md
python3 serve.py      # start local server + open frontend in browser
```

---

## API Checklist

Complete this before running `setup.py`. All keys are entered during onboarding and stored in `config.json` (gitignored).

### AI Models

| # | API | Used by | How to get | Free tier |
|---|-----|---------|-----------|-----------|
| 1 | **OpenAI** | MIDAS, SCOUT, FEED | [platform.openai.com](https://platform.openai.com) → API keys | $5 credit on signup |
| 2 | **Anthropic (Claude)** | LISTER | [console.anthropic.com](https://console.anthropic.com) → API keys | $5 credit on signup |
| 3 | **Google Gemini** | LISTER, FEED | [aistudio.google.com](https://aistudio.google.com) → Get API key | Free tier available |
| 4 | **Manus AI** | TRENDS | [manus.ai](https://manus.ai) → API access | Paid plan required |

### Data & E-commerce

| # | API | Used by | How to get | Free tier |
|---|-----|---------|-----------|-----------|
| 5 | **Google Ads API** | MIDAS, FEED | [developers.google.com/google-ads](https://developers.google.com/google-ads) → OAuth2 + developer token | Free (spend required) |
| 6 | **Google Keyword Planner** | TRENDS | Included in Google Ads API — same credentials | Free with Google Ads account |
| 7 | **Google Trends (pytrends)** | TRENDS | No API key — uses `pytrends` library (`pip install pytrends`) | Free, unofficial |
| 8 | **Shopify Admin API** | LISTER, FEED | Shopify Admin → Apps → Develop apps → Create app | Free per store |
| 9 | **CJ Dropshipping API** | SCOUT | [cjdropshipping.com](https://cjdropshipping.com) → Developers → API access | Free, verification needed for higher limits |
| 10 | **Apify** | SCOUT | [apify.com](https://apify.com) → Sign up → API token | $5 free credit/month |

### Infrastructure

| # | Service | Used by | How to get | Free tier |
|---|---------|---------|-----------|-----------|
| 11 | **OpenClaw Gateway** | All agents | Already running if you're using OpenClaw | ✅ Included |
| 12 | **Telegram Bot** | MIDAS (alerts) | [t.me/BotFather](https://t.me/BotFather) → /newbot | ✅ Free |

---

## Notes

- **Google Trends (pytrends)** — unofficial library, no API key needed. Install: `pip install pytrends`. Rate-limited by Google; TRENDS processes in batches of 5 keywords.
- **Google Keyword Planner** — uses the same OAuth credentials as Google Ads API. Requires an active Google Ads account (any spend level).
- **CJ Dropshipping** — free account gives 1 req/sec, 1,000 calls/day. Verification (submit business docs) increases limits. SCOUT only uses CJ for product discovery — not orders or fulfillment.
- **Competitor Shopify stores** — public HTTP requests, no API key needed. URLs are configured during setup.
- **config.json** — always gitignored. Never commit it. Contains all API keys and store credentials.

---

## Agents

| Agent | Schedule | Model | Role |
|-------|----------|-------|------|
| TRENDS | Sunday 23:00 | Manus AI | Market trend research |
| MIDAS | Daily 07:00 | GPT | Performance monitoring + alerts |
| SCOUT | Daily 06:00 | GPT | Product discovery + scoring |
| LISTER | On approval | Claude | Product listing + publishing |
| FEED | Wednesday 06:00 | GPT | Feed optimization |

## Architecture

- **State**: workspace JSON files (`queue.json`, `dashboard.json`, `agent-status.json`)
- **Orchestration**: OpenClaw sessions + crons
- **Frontend**: `frontend/web.html` served via `serve.py`
- **Config**: `config.json` (local only, never committed)
- **Memory**: `self-improving/memory.md` (global) + `agents/{name}/learnings.md` (per-agent)
