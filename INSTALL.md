# GoogleClaw — Installation Guide

*This file doubles as a BOOTSTRAP.md for OpenClaw.*

---

## FOR HUMANS — Two terminal commands, then everything via browser

```bash
git clone https://github.com/marcusai98/googleclaw
cp googleclaw/INSTALL.md ~/.openclaw/workspace/BOOTSTRAP.md
```

Open your OpenClaw chat (Telegram). The agent will handle everything from here.

---

## FOR THE AGENT — Read this and execute every step conversationally

You are setting up GoogleClaw for the owner. Do NOT run setup.py — instead, ask each question via chat message, collect the answers, and write config.json yourself using the write tool. This is the preferred onboarding path.

Work through the steps below in order. After each group of questions, confirm before moving to the next.

---

### STEP 0 — Check system dependencies

Run these checks via exec tool. Install anything missing automatically.

```bash
# Check and install each:
which brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
node --version || brew install node || (curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs)
python3 --version || (brew install python3 2>/dev/null || apt install -y python3)
pip3 --version || python3 -m ensurepip --upgrade
git --version || (brew install git 2>/dev/null || apt install -y git)
```

Then install Python dependencies:
```bash
cd ~/googleclaw && pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt
```

Confirm OpenClaw gateway is running:
```bash
openclaw gateway status
```

Tell the owner which dependencies were installed and confirm all checks passed.

---

### STEP 1 — Ask store information (via chat)

Ask the owner (one message, not separate messages):

> "Laten we GoogleClaw instellen. Ik heb een paar dingen nodig:
> 1. Store naam (bijv. Sophia Fashion)
> 2. Jouw naam
> 3. Naam voor je GoogleClaw agent (bijv. ARIA, NOVA, APEX)
> 4. Tijdzone (standaard: Europe/Amsterdam)
> 5. Niche (bijv. women's fashion, home decor)
> 6. Markt (bijv. Netherlands, Belgium)
> 7. Taal van de store (bijv. Dutch)"

Wait for all answers before continuing.

---

### STEP 2 — Ask Shopify credentials (via chat)

Explain first:
> "Voor Shopify heb ik je **Client ID** en **Client Secret** nodig (geen statische token meer — dit is de nieuwe methode sinds 2026).
>
> Ga naar: Shopify Admin → Settings → Apps → **Develop apps** → Create app → naam: GoogleClaw
> Configuration → Admin API → vink aan: ✅ write_products ✅ read_products
> Sla op → API credentials → kopieer **Client ID** en **Client secret**
>
> Ook nodig: je store domein (bijv. mijn-store.myshopify.com)"

Wait for: storeDomain, clientId, clientSecret.

Test the connection via exec:
```bash
python3 -c "
import requests, json
cfg = {'shopify': {'storeDomain': 'DOMAIN', 'clientId': 'CID', 'clientSecret': 'CSECRET'}}
r = requests.post('https://DOMAIN/admin/oauth/access_token', json={'client_id':'CID','client_secret':'CSECRET','grant_type':'client_credentials'})
t = r.json().get('access_token','')
s = requests.get('https://DOMAIN/admin/api/2024-01/shop.json', headers={'X-Shopify-Access-Token': t})
print(s.json().get('shop',{}).get('name','ERROR'))
"
```
Confirm store name or report error.

---

### STEP 3 — Ask Google Ads credentials (via chat)

> "Google Ads credentials:
> 1. Customer ID (bijv. 123-456-7890)
> 2. Developer Token
> 3. Client ID (OAuth)
> 4. Client Secret (OAuth)
> 5. Refresh Token"

---

### STEP 4 — Ask supplier credentials (via chat)

> "CJ Dropshipping:
> 1. Email
> 2. Wachtwoord
>
> Apify token (voor Amazon scraping — gratis account werkt)"

---

### STEP 5 — Ask AI API keys (via chat)

> "API keys:
> 1. OpenAI API key
> 2. Anthropic API key
> 3. Gemini API key
> 4. Manus API key"

---

### STEP 6 — Ask OpenClaw gateway (via chat)

> "OpenClaw gateway:
> 1. Gateway URL (bijv. ws://jouw-vps-ip:63783)
> 2. Gateway token"

Also ask:
> "Telegram bot token en chat ID voor notificaties?"

---

### STEP 7 — Ask competitor research sheet (via chat)

> "Google Sheets URL met concurrent-producten (optioneel — SCOUT gebruikt dit voor marktonderzoek). Laat leeg om over te slaan."

---

### STEP 8 — Write config.json

Once all answers are collected, write the config file:

Path: `~/googleclaw/config.json`

```json
{
  "instance": {
    "name": "{store_name}",
    "owner": "{owner_name}",
    "bot_name": "{bot_name}",
    "timezone": "{timezone}"
  },
  "store": {
    "niche": "{niche}",
    "market": "{market}",
    "language": "{language}"
  },
  "shopify": {
    "storeDomain": "{shopify_domain}",
    "clientId": "{shopify_client_id}",
    "clientSecret": "{shopify_client_secret}"
  },
  "googleAds": {
    "customerId": "{gads_customer_id}",
    "developerToken": "{gads_dev_token}",
    "clientId": "{gads_client_id}",
    "clientSecret": "{gads_client_secret}",
    "refreshToken": "{gads_refresh_token}"
  },
  "cj": {
    "email": "{cj_email}",
    "password": "{cj_password}"
  },
  "apify": {
    "token": "{apify_token}"
  },
  "openai": { "apiKey": "{openai_key}" },
  "anthropic": { "apiKey": "{anthropic_key}" },
  "gemini": { "apiKey": "{gemini_key}" },
  "manus": { "apiKey": "{manus_key}" },
  "openclaw": {
    "gatewayUrl": "{gateway_url}",
    "gatewayToken": "{gateway_token}"
  },
  "notifications": {
    "telegram": {
      "enabled": true,
      "botToken": "{telegram_bot_token}",
      "chatId": "{telegram_chat_id}"
    }
  },
  "competitorSheet": "{competitor_sheet_url}",
  "thresholds": {
    "scale_roas": 3.0,
    "alert_roas": 1.0,
    "alert_days": 3,
    "min_price": 40,
    "autopub_score": 75,
    "daily_limit": 10
  }
}
```

After writing: `chmod 600 ~/googleclaw/config.json`

Confirm: "config.json aangemaakt en beveiligd (chmod 600)."

---

### STEP 9 — Gateway config

Tell the owner:
> "Eén handmatige stap: voeg dit toe aan je `~/.openclaw/openclaw.json` en herstart de gateway:
> ```json
> { \"gateway\": { \"tools\": { \"allow\": [\"sessions_spawn\"] } } }
> ```
> Dan: `openclaw gateway restart`"

Wait for confirmation.

---

### STEP 10 — Register crons

Run via exec:
```bash
# Read PROMPT.md files and register crons
REPO=~/googleclaw
TZ=$(python3 -c "import json; print(json.load(open('$REPO/config.json'))['instance']['timezone'])")

openclaw cron add --name "gc-trends" --cron "0 23 * * 0" --tz "$TZ" \
  --message "$(cat $REPO/agents/trends/PROMPT.md)" \
  --session isolated --model "openai/gpt-5.1-codex" \
  --timeout-seconds 600 --description "GoogleClaw TRENDS — wekelijks zondag 23:00"

openclaw cron add --name "gc-scout" --cron "0 6 * * *" --tz "$TZ" \
  --message "$(cat $REPO/agents/scout/PROMPT.md)" \
  --session isolated --model "openai/gpt-5.1-codex" \
  --timeout-seconds 900 --description "GoogleClaw SCOUT — dagelijks 06:00"

openclaw cron add --name "gc-midas" --cron "0 7 * * *" --tz "$TZ" \
  --message "$(cat $REPO/agents/midas/PROMPT.md)" \
  --session isolated --model "openai/gpt-5.1-codex" \
  --timeout-seconds 600 --description "GoogleClaw MIDAS — dagelijks 07:00"

openclaw cron add --name "gc-feed" --cron "0 6 * * 3" --tz "$TZ" \
  --message "$(cat $REPO/agents/feed/PROMPT.md)" \
  --session isolated --model "openai/gpt-5.1-codex" \
  --timeout-seconds 600 --description "GoogleClaw FEED — woensdags 06:00"
```

Confirm each cron registered or report errors.

---

### STEP 11 — Start serve.py

```bash
cd ~/googleclaw && python3 serve.py --no-browser &
```

Tell the owner:
> "GoogleClaw draait op poort 8080. Open de UI via SSH tunnel:
> ```
> ssh -L 8080:127.0.0.1:8080 root@{vps_ip}
> ```
> Dan: http://localhost:8080/web.html"

---

### STEP 12 — Cleanup

Delete this file:
```bash
rm ~/.openclaw/workspace/BOOTSTRAP.md
```

Send a final message to the owner:
> "✅ GoogleClaw is klaar. Agents draaien automatisch via cron. Open de UI voor het inbox en handmatige runs."

---

*Setup complete. Do not restart this flow unless explicitly asked.*
