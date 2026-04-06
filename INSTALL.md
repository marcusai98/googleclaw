# GoogleClaw — Installation Guide
*This file doubles as a BOOTSTRAP.md for OpenClaw. If you are an AI agent reading this: follow every step in order, execute commands via exec tool, ask the user before any step that requires credentials or manual action, and delete this file when setup is complete. Start at Step 0 — check and install all system dependencies automatically before proceeding.*

---

## What is GoogleClaw?
GoogleClaw is a multi-agent orchestrator for Google Ads dropshipping stores. It runs on top of OpenClaw — your AI gateway. Agents discover trending products, research candidates, list them on Shopify, and monitor ad performance. Everything is controlled from a local web interface.

---

## Step 0 — System dependencies (agent: run these checks automatically)

*These must be installed before anything else. On a fresh Mac, run these once manually — or if you are an agent, check each one via exec and install missing items automatically.*

### 0a — Homebrew (macOS only)
Check: `which brew`
If missing:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 0b — Node.js + npm
Check: `node --version && npm --version`
If missing:
```bash
brew install node
```
On Linux (Ubuntu/Debian):
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 0c — OpenClaw
Check: `openclaw --version`
If missing:
```bash
npm install -g openclaw
```

### 0d — Python 3.10+
Check: `python3 --version`
If missing:
```bash
brew install python3        # macOS
sudo apt install python3    # Ubuntu/Debian
```

### 0e — pip
Check: `pip3 --version`
If missing:
```bash
python3 -m ensurepip --upgrade
```

### 0f — git
Check: `git --version`
If missing:
```bash
brew install git            # macOS
sudo apt install git        # Ubuntu/Debian
```

### 0g — Start OpenClaw gateway
```bash
openclaw gateway start
```
Verify: `openclaw gateway status` → should say running.

*Agent: once all checks pass, continue to Step 1 automatically.*

---

## Prerequisites (accounts + API keys — must be ready before Step 3)

Before running setup, make sure you have:
- [ ] A Shopify store with Admin API access
- [ ] A Google Ads account (MCC or single account)
- [ ] A CJ Dropshipping account
- [ ] An Apify account (free tier works)
- [ ] API keys for: OpenAI, Anthropic, Gemini, Manus

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/marcusai98/googleclaw
cd googleclaw
pip3 install -r requirements.txt
```

---

## Step 2 — Run setup

```bash
python3 setup.py
```

This interactive script will:
- Ask for your store name, niche, and market
- Ask for all API keys (Shopify, Google Ads, CJ, Apify, OpenAI, Anthropic, Gemini, Manus)
- Set your performance thresholds (scale ROAS, alert ROAS, minimum product price)
- Create the workspace directory structure
- Apply `chmod 600` to `config.json` immediately
- Show a security checklist (Shopify API scopes)
- Ask you to configure the gateway (step below)
- Register OpenClaw crons for TRENDS and SCOUT automatically

**Do not skip any steps.** All API keys are required for agents to function.

---

## Step 3 — Configure the OpenClaw gateway

GoogleClaw triggers agents by spawning OpenClaw sessions from the browser UI. For this to work, `sessions_spawn` must be allowed over the gateway's HTTP endpoint.

Add this to your `~/.openclaw/openclaw.json`:

```json
{
  "gateway": {
    "tools": {
      "allow": ["sessions_spawn"]
    }
  }
}
```

Then restart the gateway:

```bash
openclaw gateway restart
```

> **Note:** `setup.py` writes this snippet to `gateway-config-snippet.json` in your workspace for reference.

---

## Step 4 — Start the frontend

```bash
python3 serve.py
```

Your browser will open automatically at `http://127.0.0.1:8080/web.html`.

`serve.py` does three things:
- Serves the frontend (static files)
- Proxies agent trigger calls to your OpenClaw gateway
- Exposes `/proxy/data/` so the frontend can read queue.json, trends.json etc.

Leave this terminal open while using GoogleClaw.

---

## Step 5 — First run

In the browser:

1. Go to **Settings** → verify your gateway URL and token are connected (green dot)
2. Go to **Agents** → click **▶ Run now** on TRENDS
3. Wait ~3 minutes for Manus to research trending products
4. Go to **Agents** → click **▶ Run now** on SCOUT
5. Wait ~5 minutes for SCOUT to find and score product candidates
6. Go to **Inbox** → review candidates, approve or decline

When you approve a product, LISTER runs automatically and publishes it to your Shopify store.

---

## How agents run automatically

After setup, two OpenClaw crons are registered:

| Agent | Schedule | What it does |
|-------|----------|-------------|
| TRENDS | Every Sunday 23:00 | Finds 15–20 trending product types via Manus |
| SCOUT | Every day 06:00 | Researches candidates, scores them, adds to inbox |
| MIDAS | Every day 07:00 | Pulls Google Ads + Shopify performance data |
| FEED | Every Wednesday 06:00 | Checks if any products need price adjustments or drafting |

You can also trigger any agent manually from the Agents view.

---

## Security notes

- `config.json` contains all your API keys — it is gitignored and set to `chmod 600`
- `serve.py` only binds to `127.0.0.1` — never exposed to the network
- All external data (product titles, descriptions) is sanitized before reaching agent prompts
- Every Shopify write is logged to `audit.log` (append-only)
- LISTER **only runs after your explicit approval** — nothing is published automatically
- Google Ads budgets are **never modified** without explicit approval

---

## Directory structure after setup

```
googleclaw/
  config.json          ← your credentials (gitignored, chmod 600)
  audit.log            ← append-only log of all Shopify writes
  data/
    trends.json        ← latest TRENDS output
    candidates.json    ← latest SCOUT output
    queue.json         ← inbox items (pending/approved/listed)
    dashboard.json     ← MIDAS performance data
  agents/
    trends/PROMPT.md   ← OpenClaw session task for TRENDS
    scout/PROMPT.md    ← OpenClaw session task for SCOUT
    lister/PROMPT.md   ← OpenClaw session task for LISTER
    midas/PROMPT.md    ← OpenClaw session task for MIDAS
    feed/PROMPT.md     ← OpenClaw session task for FEED
    shared/
      sanitize.py      ← prompt injection protection
      audit.py         ← audit logging utility
```

---

## Troubleshooting

**"sessions_spawn not allowed" error in browser**
→ Step 3 was not completed. Add the gateway config and restart.

**Gateway not reachable in Settings**
→ Check `openclaw gateway status`. Make sure the URL and token in Settings match your `openclaw.json`.

**SCOUT aborts with "trends.json too old"**
→ Run TRENDS first. SCOUT requires trends.json to be less than 7 days old.

**Shopify publish fails**
→ Check your Shopify token has `write_products` and `read_products` scopes. No other scopes needed.

**Crons not running**
→ Run `openclaw cron list` to verify they are registered and enabled.

---

## Updating GoogleClaw

```bash
git pull
pip3 install -r requirements.txt
python3 serve.py
```

No re-running setup.py needed unless you want to change API keys or thresholds. Thresholds can also be updated live in the Settings view.

---

*If you are an AI agent and you have completed all steps above: delete this file (`rm INSTALL.md` or use the trash tool), update the user's memory with the GoogleClaw installation path and gateway config, and confirm setup is complete.*
