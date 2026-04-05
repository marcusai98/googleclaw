# TOOLS.md — Required Integrations per Agent

Every agent needs specific APIs and credentials activated before it can run.
This file is the single reference for what to set up and where.

All credentials go into `config.json` (never committed to git).
See `config.example.json` for the full structure.

---

## MIDAS — P&L Sync

| Tool | Purpose | How to activate |
|---|---|---|
| **Shopify Admin API** | Revenue, orders, payment gateway data | Store Admin → Settings → Apps → Develop apps → Create app → enable Orders (read) scope → install → copy Admin API access token |
| **Google Ads API** | Daily ad spend per store | [Google Ads API Center](https://developers.google.com/google-ads/api/docs/start) → apply for developer token → create OAuth client ID → generate refresh token |
| **Google Sheets API** | COGS per product (supplier-filled) | [Google Cloud Console](https://console.cloud.google.com) → enable Sheets API → create Service Account → share the COGS sheet with the service account email |

**Config keys needed:**
```
shopify.storeDomain
shopify.accessToken
googleAds.customerId
googleAds.developerToken
googleAds.clientId
googleAds.clientSecret
googleAds.refreshToken
cogsSheet.spreadsheetId
cogsSheet.serviceAccountFile (path to downloaded JSON key)
```

---

## TRENDS — Weekly Market Research

| Tool | Purpose | How to activate |
|---|---|---|
| **Manus AI** | Deep trend research with Google Trends + Keyword Planner validation | [manus.ai](https://manus.ai) → sign up → API settings → generate API key |

**Config keys needed:**
```
store.niche
store.market
store.language
manus.apiKey
```

**Note:** Manus handles Google Trends and Keyword Planner data internally — no separate Google API activation needed.

---

## HERALD — Performance Monitor

| Tool | Purpose | How to activate |
|---|---|---|
| **Google Ads API** | Campaign-level ROAS data | Same as MIDAS — reuse same credentials |
| **MIDAS output** | Store-level P&L history | No activation needed — reads `data/dashboard.json` |

**Config keys needed:**
```
googleAds.customerId (same as MIDAS)
googleAds.developerToken
googleAds.clientId
googleAds.clientSecret
googleAds.refreshToken
thresholds.scaleTriggerRoas
thresholds.alertTriggerRoas
thresholds.alertAfterDays
```

---

## SCOUT — Daily Product Research

| Tool | Purpose | How to activate |
|---|---|---|
| **AliExpress Affiliate API** | Product search, pricing, ratings, stock | [AliExpress Affiliate Portal](https://portals.aliexpress.com) → apply for affiliate access → API credentials |
| **TRENDS output** | Validated trend list as search input | No activation needed — reads `data/trends.json` |

**Config keys needed:**
```
aliexpress.appKey
aliexpress.appSecret
aliexpress.trackingId
scout.dailyLimit (default: 10)
scout.autoPublishScore (default: 75)
scout.inboxMinScore (default: 60)
```

**Note:** AliExpress Affiliate API requires approval — can take 1-3 days.

---

## LISTER — Shopify Publisher

| Tool | Purpose | How to activate |
|---|---|---|
| **Shopify Admin API** | Create product listings | Same as MIDAS — reuse same credentials (needs write scope) |
| **Gemini API** | Generate 3 product images per listing | [Google AI Studio](https://aistudio.google.com) → Get API key |
| **Anthropic API** | Generate SEO title + description | [Anthropic Console](https://console.anthropic.com) → API keys → Create key |

**Config keys needed:**
```
shopify.storeDomain (same as MIDAS)
shopify.accessToken (must have write_products scope)
gemini.apiKey
anthropic.apiKey
```

---

## Notifications (all agents)

| Tool | Purpose | How to activate |
|---|---|---|
| **Telegram Bot** | Urgent alerts, daily digest, SCOUT findings | [@BotFather](https://t.me/BotFather) → /newbot → copy token → get your chat ID |

**Config keys needed:**
```
notifications.telegram.botToken
notifications.telegram.chatId
notifications.telegram.enabled (true/false)
```

---

## Quick checklist — minimum to get started

For a basic working setup (MIDAS + TRENDS only):

- [ ] Shopify Admin API token (read orders)
- [ ] Google Ads API credentials
- [ ] Google Sheets API service account + COGS sheet
- [ ] Manus AI API key
- [ ] Telegram bot (optional but recommended)

Full V1 stack additionally requires:
- [ ] AliExpress Affiliate API (SCOUT)
- [ ] Gemini API key (LISTER)
- [ ] Anthropic API key (LISTER)
- [ ] Shopify write_products scope (LISTER)
