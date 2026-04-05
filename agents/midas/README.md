# MIDAS — P&L Sync Agent

Calculates daily P&L for one Shopify dropshipping store.
Runs every morning at 07:00 and writes results to `data/dashboard.json`.

## Data sources

| Source | Data | Auth |
|---|---|---|
| Shopify Admin API | Revenue, orders, payment gateway | Access token |
| Google Ads API | Ad spend | OAuth refresh token |
| Google Sheets | COGS per product (filled by supplier) | Service account or OAuth |

## Setup

### 1. Install dependencies
```bash
pip3 install -r scripts/requirements.txt
```

### 2. Configure
Copy `../../config.example.json` to `config.json` in this folder and fill in:
- `shopify.storeDomain` + `shopify.accessToken`
- `googleAds.customerId` + credentials
- `cogsSheet.spreadsheetId` + mapping columns
- `costs.shopifyMonthly` (your Shopify plan cost)
- `costs.shopifyPaymentsFeePercent` (e.g. 1.9 for Shopify Payments)
- `costs.defaultMarginPercent` (fallback if product not in COGS sheet)

### 3. Google Sheets COGS format
Your supplier fills in a sheet with at minimum:
- Column A: Product identifier (SKU or product title)
- Column C: Cost price (€)

Configure which columns in `config.json → cogsSheet`:
```json
"cogsSheet": {
  "spreadsheetId": "YOUR_SHEET_ID",
  "sheetName": "Sheet1",
  "headerRow": 1,
  "productIdentifierColumn": "A",
  "cogsPriceColumn": "C",
  "matchBy": "sku"
}
```
`matchBy` options: `"sku"` or `"title"`

### 4. Register cron in OpenClaw
```
openclaw cron add \
  --name "midas-{store-name}" \
  --schedule "0 7 * * *" \
  --task "$(cat prompt.md)" \
  --model "openai/gpt-4o-mini"
```

### 5. First run (backfill)
```bash
python3 scripts/fetch.py --config config.json --output data/dashboard.json --backfill
```

## Output: dashboard.json

```json
{
  "store": "my-store.myshopify.com",
  "lastUpdated": "2026-04-05T07:00:00Z",
  "history": [
    {
      "date": "2026-04-04",
      "revenue": 1842.50,
      "orders": 23,
      "cogs": 734.20,
      "adSpend": 620.00,
      "transactionFees": 48.30,
      "shopifySubscription": 1.30,
      "netProfit": 438.70,
      "roas": 2.97,
      "margin": 0.238
    }
  ],
  "products": {
    "ALI-12345": {
      "title": "Portable Neck Fan",
      "sku": "ALI-12345",
      "revenue": 420.00,
      "cogs": 131.20,
      "units": 16
    }
  }
}
```

## Troubleshooting

- **Google Ads returns 0**: Check customer ID format (no dashes) and that refresh token is valid
- **COGS all 0**: Check sheet column mapping in config + that matchBy matches your sheet
- **Missing yesterday**: Shopify API uses UTC — orders near midnight may fall on different day
