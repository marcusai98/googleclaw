# TOOLS.md — Required Integrations per Agent

Every agent needs specific APIs and credentials before it can run.
All credentials go into `config.json` (never committed to git).
See `config.example.json` for the full structure.

---

## TRENDS — Daily Market Research
> Schedule: Daily 00:00 | Model: Manus + GPT

| Tool | Purpose | Activate |
|---|---|---|
| **Manus AI** | Deep trend research (TikTok, Reddit, seasonal) | [manus.ai](https://manus.ai) → API settings → generate key |
| **pytrends** | Google Trends curve validation | `pip install pytrends` — no API key needed |
| **Google Ads API** | Keyword Planner volume + CPC | Reuse MIDAS credentials |

```
manus.apiKey
store.niche
store.market
store.language
googleAds.*  (reuse from MIDAS)
```

---

## MIDAS — Daily P&L Sync
> Schedule: Daily 07:00 | Model: GPT

| Tool | Purpose | Activate |
|---|---|---|
| **Shopify Admin API** | Revenue, orders, payment gateway | Admin → Settings → Apps → Develop apps → read_orders scope |
| **Google Ads API** | Daily ad spend | [Google Ads API Center](https://developers.google.com/google-ads/api/docs/start) → developer token + OAuth |
| **Google Sheets API** | COGS per product | Cloud Console → enable Sheets API → Service Account → share sheet |

```
shopify.storeDomain
shopify.accessToken
googleAds.customerId
googleAds.developerToken
googleAds.clientId
googleAds.clientSecret
googleAds.refreshToken
cogsSheet.spreadsheetId
cogsSheet.serviceAccountFile
```

---

## SCOUT — Daily Product Research
> Schedule: Daily 10:00 | Model: GPT

| Tool | Purpose | Activate |
|---|---|---|
| **CJ Dropshipping API** | Product search, pricing, stock, shipping | [developers.cjdropshipping.com](https://developers.cjdropshipping.com) → register account → use email + password in config |
| **Amazon PA-API** | BSR (demand proof), pricing ceiling | [Amazon Associates](https://affiliate-program.amazon.com) → apply → Tools → PA-API credentials |
| **Competitor stores** | Shopify /products.json (public) | No API needed — just add competitor URLs in config |
| **TRENDS output** | Validated trend list | No activation — reads `data/trends.json` |

```
cj.email
cj.password
amazon.accessKey
amazon.secretKey
amazon.partnerTag
scout.minSellingPrice       (default: 40)
scout.candidatesPerMethod   (default: 10)
scout.methods.cj.enabled
scout.methods.amazon.enabled
scout.methods.competitors.enabled
scout.competitors.urls      (list of competitor Shopify store URLs)
```

---

## LISTER — On-Approval Product Publisher
> Trigger: User approval | Model: Claude

| Tool | Purpose | Activate |
|---|---|---|
| **Shopify Admin API** | Create product + upload images | Same credentials as MIDAS — needs **write_products** scope |
| **CJ Dropshipping API** | Full product data, all variants, images | Same as SCOUT |
| **Anthropic API** | SEO copy (title, description, tags, meta) | [console.anthropic.com](https://console.anthropic.com) → API Keys → Create |
| **Gemini API** | Generate lifestyle product images | [aistudio.google.com](https://aistudio.google.com) → Get API key |

```
shopify.storeDomain
shopify.accessToken          (write_products scope required)
cj.email
cj.password
anthropic.apiKey
gemini.apiKey
lister.publishStatus         ("active" | "draft")
lister.imageMode             ("supplement" | "optimize_all")
lister.cogsMultiplier        (default: 3.0)
lister.minMarginMultiplier   (default: 2.0)
lister.useAiPriceSuggestion  (default: true)
```

---

## FEED — Weekly Feed Optimizer
> Schedule: Wednesday 06:00 | Model: GPT

| Tool | Purpose | Activate |
|---|---|---|
| **Shopify Admin API** | Read + update products, upload images | Same credentials — needs read/write_products scope |
| **Google Ads API** | Product-level ad spend (Shopping) | Same as MIDAS |
| **Gemini API** | Generate new lifestyle images | Same as LISTER |
| **OpenAI API** | Fill missing product fields | [platform.openai.com](https://platform.openai.com) → API keys |
| **MIDAS dashboard.json** | ROAS per product | No activation — reads `data/dashboard.json` |
| **TRENDS history** | Trend direction per product | No activation — reads `data/trends-history.json` |

```
shopify.storeDomain
shopify.accessToken
googleAds.*
gemini.apiKey
openai.apiKey
feed.priceReduction          (default: 5.0)
feed.priceFloorMultiplier    (default: 2.0)
feed.imageRefreshCount       (default: 2)
```

---

## Notifications (all agents)

| Tool | Purpose | Activate |
|---|---|---|
| **Telegram Bot** | Alerts, SCOUT findings, FEED summary | [@BotFather](https://t.me/BotFather) → /newbot → copy token + get chat ID |

```
notifications.telegram.botToken
notifications.telegram.chatId
notifications.telegram.enabled
```

---

## Quick setup checklist

**Minimum (MIDAS + TRENDS only):**
- [ ] Shopify Admin API token (read_orders)
- [ ] Google Ads API credentials
- [ ] Google Sheets API + service account + COGS sheet
- [ ] Manus AI API key
- [ ] Telegram bot (recommended)

**Full V1:**
- [ ] CJ Dropshipping account (SCOUT + LISTER)
- [ ] Amazon PA-API approval (SCOUT)
- [ ] Competitor store URLs (SCOUT)
- [ ] Anthropic API key (LISTER)
- [ ] Gemini API key (LISTER + FEED)
- [ ] OpenAI API key (FEED + pricing)
- [ ] Shopify write_products scope (LISTER + FEED)
