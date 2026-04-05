# GoogleClaw

> Run your dropshipping business from your phone. Zero employees.

GoogleClaw is an OpenClaw-native agent stack + frontend UI for Google Ads dropshipping store owners.

## What's inside

```
frontend/         → Web UI (web.html) + Mobile UI (mobile.html)
agents/
  midas/          → Daily P&L sync
  scout/          → Daily product research
  herald/         → ROAS monitoring + alerts
  lister/         → Shopify publisher (triggered on approval)
  trends/         → Weekly trend research (Manus)
```

## Requirements

- [OpenClaw](https://openclaw.ai) installed and running
- Shopify store with Admin API access
- Google Ads account with API access
- OpenAI API key (SCOUT, HERALD, MIDAS)
- Anthropic API key (LISTER)
- Gemini API key (LISTER visuals)

## Setup

1. Clone this repo
2. Copy `config.example.json` → `config.json` and fill in your credentials
3. Follow `setup.md` to register crons in OpenClaw
4. Open `frontend/web.html` in your browser (or serve via Caddy)

## Agent schedule

| Agent | Runs | Model |
|---|---|---|
| TRENDS | Weekly (Mon 02:00) | Manus |
| SCOUT | Daily (03:00) | GPT |
| HERALD | Daily (06:00) | GPT |
| MIDAS | Daily (07:00) | GPT |
| LISTER | On approval | Claude + Gemini |

## Access

This repo is private. To request access, contact the maintainer.
