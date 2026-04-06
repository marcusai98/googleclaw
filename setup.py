#!/usr/bin/env python3
"""
GoogleClaw Setup — V1
Interactive onboarding script.
Creates config.json, workspace folders, and registers OpenClaw crons.
"""

import json
import os
import sys
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import shutil

# ── Colors ──────────────────────────────────────────────────────────────────
class c:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_DARK = "\033[40m"
    PURPLE  = "\033[95m"

def ok(msg):    print(f"  {c.GREEN}✓{c.RESET}  {msg}")
def warn(msg):  print(f"  {c.YELLOW}⚠{c.RESET}  {msg}")
def err(msg):   print(f"  {c.RED}✗{c.RESET}  {msg}")
def info(msg):  print(f"  {c.CYAN}→{c.RESET}  {msg}")
def dim(msg):   print(f"  {c.DIM}{msg}{c.RESET}")

def section(title):
    print()
    print(f"{c.BOLD}{c.WHITE}{'─' * 54}{c.RESET}")
    print(f"{c.BOLD}{c.WHITE}  {title}{c.RESET}")
    print(f"{c.BOLD}{c.WHITE}{'─' * 54}{c.RESET}")
    print()

def ask(prompt, default=None, secret=False):
    if default:
        label = f"{c.CYAN}{prompt}{c.RESET} {c.DIM}[{default}]{c.RESET}: "
    else:
        label = f"{c.CYAN}{prompt}{c.RESET}: "
    try:
        if secret:
            import getpass
            val = getpass.getpass(label)
        else:
            val = input(label).strip()
        if not val and default is not None:
            return default
        return val
    except (KeyboardInterrupt, EOFError):
        print()
        print(f"\n{c.YELLOW}Setup afgebroken.{c.RESET}")
        sys.exit(0)

def ask_bool(prompt, default=True):
    yn = "Y/n" if default else "y/N"
    label = f"{c.CYAN}{prompt}{c.RESET} {c.DIM}[{yn}]{c.RESET}: "
    try:
        val = input(label).strip().lower()
        if not val:
            return default
        return val in ("y", "yes", "ja", "j")
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

def ask_float(prompt, default):
    while True:
        raw = ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            warn("Voer een geldig getal in.")

def ask_int(prompt, default):
    while True:
        raw = ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            warn("Voer een geldig geheel getal in.")

# ── API Tests ─────────────────────────────────────────────────────────────

def test_cj(email, password):
    try:
        data = json.dumps({"email": email, "password": password}).encode()
        req = urllib.request.Request(
            "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        if resp.get("result"):
            return True, "ingelogd ✓"
        return False, resp.get("message", "onbekende fout")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def test_apify(token):
    try:
        url = f"https://api.apify.com/v2/users/me?token={token}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        username = data.get("data", {}).get("username", "?")
        plan     = data.get("data", {}).get("plan", {}).get("id", "?")
        return True, f"account: {username} (plan: {plan})"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def test_shopify(domain, token):
    try:
        url = f"https://{domain}/admin/api/2024-01/shop.json"
        req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            name = data.get("shop", {}).get("name", "onbekend")
            return True, name
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def test_google_ads(customer_id, developer_token, client_id, client_secret, refresh_token):
    try:
        # Get access token
        data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
        with urllib.request.urlopen(req, timeout=8) as r:
            token_data = json.loads(r.read())
        access_token = token_data.get("access_token")
        if not access_token:
            return False, "Kon geen access token ophalen"

        # Quick campaign count check
        clean_id = customer_id.replace("-", "")
        url = f"https://googleads.googleapis.com/v18/customers/{clean_id}/googleAds:search"
        payload = json.dumps({"query": "SELECT customer.descriptive_name FROM customer LIMIT 1"}).encode()
        req2 = urllib.request.Request(url, data=payload, headers={
            "Authorization": f"Bearer {access_token}",
            "developer-token": developer_token,
            "Content-Type": "application/json"
        })
        with urllib.request.urlopen(req2, timeout=8) as r:
            result = json.loads(r.read())
        name = result.get("results", [{}])[0].get("customer", {}).get("descriptiveName", clean_id)
        return True, name
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)

def test_openai(api_key):
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        count = len(data.get("data", []))
        return True, f"{count} modellen beschikbaar"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def test_anthropic(api_key):
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "ping"}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, "verbinding OK"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def test_gemini(api_key):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        count = len(data.get("models", []))
        return True, f"{count} modellen beschikbaar"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def test_manus(api_key):
    try:
        payload = json.dumps({
            "prompt": "Test. Reply with the word OK.",
            "stream": False
        }).encode()
        req = urllib.request.Request(
            "https://api.manus.ai/v1/tasks",
            data=payload,
            headers={
                "API_KEY": api_key,
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        task_id = data.get("task_id", "")
        return True, f"task_id: {task_id[:12]}..."
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def test_openclaw(gateway_url, gateway_token):
    try:
        url = gateway_url.replace("ws://", "http://").replace("wss://", "https://")
        if not url.endswith("/"):
            url += "/"
        req = urllib.request.Request(
            url + "status",
            headers={"Authorization": f"Bearer {gateway_token}"}
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            return True, "gateway bereikbaar"
    except Exception as e:
        # Gateway might not have /status endpoint but connection worked
        if "401" in str(e):
            return False, "ongeldige token"
        return True, "gateway bereikbaar (geen /status endpoint)"

# ── Workspace setup ───────────────────────────────────────────────────────

def create_workspace(workspace_path, config=None):
    dirs = [
        workspace_path,
        os.path.join(workspace_path, "googleclaw"),
        os.path.join(workspace_path, "googleclaw", "self-improving"),
        os.path.join(workspace_path, "googleclaw", "self-improving", "archive"),
        os.path.join(workspace_path, "googleclaw", "agents"),
        os.path.join(workspace_path, "googleclaw", "agents", "trends"),
        os.path.join(workspace_path, "googleclaw", "agents", "midas"),
        os.path.join(workspace_path, "googleclaw", "agents", "scout"),
        os.path.join(workspace_path, "googleclaw", "agents", "lister"),
        os.path.join(workspace_path, "googleclaw", "agents", "feed"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # ── Self-improving memory files ──────────────────────────────────────────
    si_path = os.path.join(workspace_path, "googleclaw", "self-improving")

    global_mem = os.path.join(si_path, "memory.md")
    if not os.path.exists(global_mem):
        with open(global_mem, "w") as f:
            f.write("# GoogleClaw — Global Memory (HOT Tier)\n")
            f.write("*Store-wide patterns. Loaded by all agents at the start of every run.*\n")
            f.write("*Max 80 lines. Promote from agent learnings after 3x repetition.*\n\n---\n\n")
            f.write("## Store Context\n")
            f.write(f"- Niche: {config.get('store', {}).get('niche', '[set during setup]')}\n")
            f.write(f"- Market: {config.get('store', {}).get('market', '[set during setup]')}\n")
            f.write(f"- Language: {config.get('store', {}).get('language', '[set during setup]')}\n\n")
            f.write("## Niche Performance\n*(Empty — agents write here after observing patterns)*\n\n")
            f.write("## Seasonal Patterns\n*(Empty — TRENDS writes here after seasonal observations)*\n\n")
            f.write("## Market Behaviour\n*(Empty — MIDAS/SCOUT write here after pricing observations)*\n\n")
            f.write("## Supplier Patterns\n*(Empty — SCOUT/LISTER write here after CJ observations)*\n\n")
            f.write("## Copy & Creative\n*(Empty — LISTER writes here after copy performance observations)*\n")

    corrections = os.path.join(si_path, "corrections.md")
    if not os.path.exists(corrections):
        with open(corrections, "w") as f:
            f.write("# GoogleClaw — Corrections Log\n")
            f.write("*Append immediately when user corrects agent output. Max 50 entries.*\n\n")
            f.write("| Date | Agent | What went wrong | Correction | Lesson |\n")
            f.write("|------|-------|----------------|------------|--------|\n")

    # Per-agent learnings.md
    for agent in ["trends", "midas", "scout", "lister", "feed"]:
        learnings = os.path.join(workspace_path, "googleclaw", "agents", agent, "learnings.md")
        if not os.path.exists(learnings):
            with open(learnings, "w") as f:
                f.write(f"# {agent.upper()} — Learnings\n")
                f.write("*Written at the end of each run. Load at the start of every run.*\n")
                f.write("*Max 60 lines. Promote to self-improving/memory.md after 3x repetition.*\n\n---\n\n")
                f.write("## What Works\n*(Empty — written after first run)*\n\n")
                f.write("## What to Avoid\n*(Empty — written after first run)*\n\n")
                f.write("## Calibrations\n*(Empty — threshold/scoring adjustments)*\n\n")
                f.write("## Open Questions\n*(Things to watch across next few runs)*\n")

    # Create queue.json, dashboard.json, agent-status.json
    queue_path = os.path.join(workspace_path, "googleclaw", "queue.json")
    dash_path  = os.path.join(workspace_path, "googleclaw", "dashboard.json")
    status_path= os.path.join(workspace_path, "googleclaw", "agent-status.json")

    if not os.path.exists(queue_path):
        with open(queue_path, "w") as f:
            json.dump({"pending": [], "approved": [], "rejected": []}, f, indent=2)

    if not os.path.exists(dash_path):
        with open(dash_path, "w") as f:
            json.dump({"lastUpdated": None, "stores": {}}, f, indent=2)

    if not os.path.exists(status_path):
        with open(status_path, "w") as f:
            json.dump({
                "trends": {"lastRun": None, "status": "idle"},
                "midas":  {"lastRun": None, "status": "idle"},
                "scout":  {"lastRun": None, "status": "idle"},
                "lister": {"lastRun": None, "status": "idle"},
                "feed":   {"lastRun": None, "status": "idle"}
            }, f, indent=2)

    # Create state.md templates per agent
    for agent in ["trends", "midas", "scout", "lister", "feed"]:
        state_dir = os.path.join(workspace_path, "googleclaw", "agents", agent)
        state_path = os.path.join(state_dir, "state.md")
        if not os.path.exists(state_path):
            with open(state_path, "w") as f:
                f.write(f"# {agent.upper()} State\n\n## Last session\n- Status: not yet run\n\n## Memory\n- (leeg)\n")

# ── Cron registration ─────────────────────────────────────────────────────

CRONS = [
    {
        "id":       "trends",
        "name":     "googleclaw-trends",
        "schedule": "0 23 * * 0",
        "label":    "TRENDS — wekelijks zondag 23:00",
        "model":    "openai/gpt-5.1-codex",
        "timeout":  600,
    },
    {
        "id":       "midas",
        "name":     "googleclaw-midas",
        "schedule": "0 7 * * *",
        "label":    "MIDAS — dagelijks 07:00",
        "model":    "openai/gpt-5.1-codex",
        "timeout":  600,
    },
    {
        "id":       "scout",
        "name":     "googleclaw-scout",
        "schedule": "0 6 * * *",
        "label":    "SCOUT — dagelijks 06:00",
        "model":    "openai/gpt-5.1-codex",
        "timeout":  900,
    },
    {
        "id":       "feed",
        "name":     "googleclaw-feed",
        "schedule": "0 6 * * 3",
        "label":    "FEED — woensdags 06:00",
        "model":    "openai/gpt-5.1-codex",
        "timeout":  600,
    },
]

def load_prompt(agent_name, repo_path):
    """Load PROMPT.md for an agent and fill in {{REPO_PATH}}."""
    prompt_path = os.path.join(os.path.dirname(__file__), "agents", agent_name, "PROMPT.md")
    if not os.path.exists(prompt_path):
        return f"Run GoogleClaw {agent_name.upper()} agent. Repo: {repo_path}"
    with open(prompt_path) as f:
        return f.read().replace("{{REPO_PATH}}", repo_path)


def register_crons(crons_to_register, repo_path, timezone):
    registered = []
    failed = []
    for cron in crons_to_register:
        prompt = load_prompt(cron["id"], repo_path)
        model  = cron.get("model", "openai/gpt-5.1-codex")
        try:
            result = subprocess.run(
                ["openclaw", "cron", "add",
                 "--name",            cron["name"],
                 "--cron",            cron["schedule"],
                 "--tz",              timezone,
                 "--message",         prompt,
                 "--session",         "isolated",
                 "--model",           model,
                 "--timeout-seconds", str(cron.get("timeout", 600)),
                 "--description",     cron["label"]],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                registered.append(cron["label"])
            else:
                failed.append((cron["label"], result.stderr.strip() or result.stdout.strip()))
        except FileNotFoundError:
            failed.append((cron["label"], "openclaw CLI niet gevonden"))
        except Exception as e:
            failed.append((cron["label"], str(e)))
    return registered, failed

# ── Main ──────────────────────────────────────────────────────────────────

def main():
    # Header
    print()
    print(f"{c.BOLD}{c.WHITE}╔══════════════════════════════════════════════════════╗{c.RESET}")
    print(f"{c.BOLD}{c.WHITE}║         GoogleClaw — Setup V1                        ║{c.RESET}")
    print(f"{c.BOLD}{c.WHITE}║         Multi-agent orchestrator voor Google Ads     ║{c.RESET}")
    print(f"{c.BOLD}{c.WHITE}╚══════════════════════════════════════════════════════╝{c.RESET}")
    print()
    print(f"  {c.DIM}Dit script maakt config.json aan, test API-verbindingen,{c.RESET}")
    print(f"  {c.DIM}richt de workspace in en registreert OpenClaw crons.{c.RESET}")
    print()

    config = {}

    # ── 1. Store info ──────────────────────────────────────────────────────
    section("1/7 — Store informatie")

    store_name = ask("Store naam (bijv. Sophia Fashion)")
    config["instance"] = {
        "name":     store_name,
        "owner":    ask("Jouw naam"),
        "bot_name": ask("Naam voor je GoogleClaw agent (bijv. ARIA, NOVA, APEX)", f"{store_name} Bot"),
        "timezone": ask("Tijdzone", "Europe/Amsterdam")
    }
    config["store"] = {
        "niche":    ask("Niche (bijv. women's fashion, home decor)"),
        "market":   ask("Markt (bijv. Netherlands, Belgium)"),
        "language": ask("Taal van de store (bijv. Dutch, English)", "Dutch")
    }

    # ── 2. Shopify ─────────────────────────────────────────────────────────
    section("2/7 — Shopify")

    shopify_domain = ask("Shopify store domein (bijv. mijn-store.myshopify.com)")
    shopify_token  = ask("Shopify Admin API access token", secret=True)

    info("Verbinding testen...")
    success, detail = test_shopify(shopify_domain, shopify_token)
    if success:
        ok(f"Shopify verbonden — store: {c.BOLD}{detail}{c.RESET}")
    else:
        warn(f"Shopify test mislukt ({detail}) — toch doorgaan?")
        if not ask_bool("Doorgaan", True):
            sys.exit(1)

    config["shopify"] = {
        "storeDomain": shopify_domain,
        "accessToken": shopify_token
    }

    # ── 3. Google Ads ──────────────────────────────────────────────────────
    section("3/7 — Google Ads")

    gadscid    = ask("Google Ads Customer ID (bijv. 123-456-7890)")
    gads_devt  = ask("Developer Token", secret=True)
    gads_ci    = ask("OAuth Client ID")
    gads_cs    = ask("OAuth Client Secret", secret=True)
    gads_rt    = ask("OAuth Refresh Token", secret=True)

    info("Verbinding testen...")
    success, detail = test_google_ads(gadscid, gads_devt, gads_ci, gads_cs, gads_rt)
    if success:
        ok(f"Google Ads verbonden — account: {c.BOLD}{detail}{c.RESET}")
    else:
        warn(f"Google Ads test mislukt ({detail}) — toch doorgaan?")
        if not ask_bool("Doorgaan", True):
            sys.exit(1)

    config["googleAds"] = {
        "customerId":    gadscid,
        "developerToken": gads_devt,
        "clientId":      gads_ci,
        "clientSecret":  gads_cs,
        "refreshToken":  gads_rt
    }

    # ── 4. CJ Dropshipping ────────────────────────────────────────────────
    section("4/9 — CJ Dropshipping")

    print(f"  {c.DIM}CJ wordt gebruikt door SCOUT (producten zoeken) en LISTER (bestellen + variants).{c.RESET}")
    print(f"  {c.DIM}Heb je nog geen CJ account? → https://cjdropshipping.com{c.RESET}")
    print()

    cj_email = ask("CJ account e-mail")
    cj_pass  = ask("CJ wachtwoord", secret=True)

    info("Verbinding testen...")
    success, detail = test_cj(cj_email, cj_pass)
    if success:
        ok(f"CJ Dropshipping verbonden — {detail}")
    else:
        warn(f"CJ test mislukt ({detail}) — toch doorgaan?")
        if not ask_bool("Doorgaan", True):
            sys.exit(1)

    config["cj"] = {"email": cj_email, "password": cj_pass}

    # ── 5. Apify (Amazon research) ─────────────────────────────────────────
    section("5/9 — Apify (Amazon productonderzoek)")

    print(f"  {c.DIM}Apify wordt gebruikt door SCOUT om Amazon te scrapen voor vraagbewijs (BSR, reviews, prijsplafond).{c.RESET}")
    print(f"  {c.DIM}Geen Amazon-account nodig. Gratis tier beschikbaar op https://apify.com{c.RESET}")
    print()

    apify_token = ask("Apify API token", secret=True)

    info("Verbinding testen...")
    success, detail = test_apify(apify_token)
    if success:
        ok(f"Apify verbonden — {detail}")
    else:
        warn(f"Apify test mislukt ({detail}) — toch doorgaan?")
        if not ask_bool("Doorgaan", True):
            sys.exit(1)

    config["apify"] = {"token": apify_token}

    # ── 6. Competitor research (Google Sheets) ────────────────────────────
    section("6/9 — Competitor research")

    print(f"  {c.DIM}SCOUT leest jouw competitor-onderzoek uit een Google Sheets spreadsheet.{c.RESET}")
    print(f"  {c.DIM}Deel het sheet via: Delen → Iedereen met de link → Viewer.{c.RESET}")
    print(f"  {c.DIM}Verwacht formaat: kolommen Product, URL, Prijs, Niche (headers in rij 1).{c.RESET}")
    print(f"  {c.DIM}Geen sheet? Laat leeg — SCOUT slaat deze bron over.{c.RESET}")
    print()

    sheets_url = ask("Google Sheets sharelink (view-only)", default="")
    sheets_csv_url = ""

    if sheets_url:
        # Extract sheet ID and build CSV export URL
        import re as _re
        match = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheets_url)
        if match:
            sheet_id = match.group(1)
            sheets_csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
            ok(f"Sheet ID: {sheet_id}")
            ok(f"CSV export URL: {sheets_csv_url}")
        else:
            warn("Kon Sheet ID niet herkennen — URL handmatig controleren in config.json.")
            sheets_csv_url = sheets_url
    else:
        dim("Geen competitor sheet — SCOUT gebruikt alleen CJ en Amazon als bronnen.")

    config["scout"] = {
        "minSellingPrice": 40,
        "competitors": {
            "sheetsUrl":    sheets_url,
            "sheetsCsvUrl": sheets_csv_url
        }
    }

    # ── 7. AI providers ────────────────────────────────────────────────────
    section("7/9 — AI providers")

    print(f"  {c.DIM}GoogleClaw gebruikt: OpenAI (SCOUT/MIDAS/FEED), Claude (LISTER copy), Gemini (images), Manus (TRENDS research){c.RESET}")
    print()

    openai_key = ask("OpenAI API key", secret=True)
    info("Verbinding testen...")
    ok_flag, detail = test_openai(openai_key)
    ok(f"OpenAI OK — {detail}") if ok_flag else warn(f"OpenAI test mislukt: {detail}")
    config["openai"] = {"apiKey": openai_key}

    anthropic_key = ask("Anthropic API key", secret=True)
    info("Verbinding testen...")
    ok_flag, detail = test_anthropic(anthropic_key)
    ok(f"Anthropic OK — {detail}") if ok_flag else warn(f"Anthropic test mislukt: {detail}")
    config["anthropic"] = {"apiKey": anthropic_key}

    gemini_key = ask("Gemini API key", secret=True)
    info("Verbinding testen...")
    ok_flag, detail = test_gemini(gemini_key)
    ok(f"Gemini OK — {detail}") if ok_flag else warn(f"Gemini test mislukt: {detail}")
    config["gemini"] = {"apiKey": gemini_key}

    manus_key = ask("Manus API key", secret=True)
    info("Verbinding testen...")
    ok_flag, detail = test_manus(manus_key)
    ok(f"Manus OK — {detail}") if ok_flag else warn(f"Manus test mislukt: {detail}")
    config["manus"] = {"apiKey": manus_key}

    # ── 8. OpenClaw gateway ────────────────────────────────────────────────
    section("8/9 — OpenClaw gateway")

    gw_url   = ask("Gateway URL (bijv. ws://jouw-vps:63783)", "ws://localhost:63783")
    gw_token = ask("Gateway token", secret=True)

    info("Verbinding testen...")
    ok_flag, detail = test_openclaw(gw_url, gw_token)
    ok(f"Gateway OK — {detail}") if ok_flag else warn(f"Gateway test mislukt: {detail}")
    config["openclaw"] = {"gatewayUrl": gw_url, "gatewayToken": gw_token}

    # ── 9. Drempelwaarden & kosten ─────────────────────────────────────────
    section("9/9 — Drempelwaarden & kosten")

    print(f"  {c.DIM}Druk Enter om standaardwaarden te accepteren.{c.RESET}")
    print()

    config["thresholds"] = {
        "scaleTriggerRoas":     ask_float("Scale trigger ROAS (default 3.0)", 3.0),
        "alertTriggerRoas":     ask_float("Alert trigger ROAS (default 1.0)", 1.0),
        "alertAfterDays":       ask_int("Alert na X dagen slecht ROAS (default 3)", 3),
        "scoutAutoPublishScore":ask_int("SCOUT score voor auto-publish (default 75)", 75),
        "scoutInboxMinScore":   ask_int("SCOUT minimum score voor inbox (default 60)", 60),
        "scoutDailyLimit":      ask_int("Max SCOUT producten per dag (default 10)", 10)
    }

    config["costs"] = {
        "shopifyMonthly":                  ask_float("Shopify maandelijkse kosten €", 39.0),
        "shopifyPaymentsFeePercent":        ask_float("Shopify Payments transactie % (default 1.9)", 1.9),
        "shopifyPaymentsFeeFixed":          ask_float("Shopify Payments vaste fee € (default 0.25)", 0.25),
        "thirdPartyGatewayFeePercent":      ask_float("Externe payment gateway % (default 2.9)", 2.9),
        "shopifyTransactionFeePercent":     ask_float("Shopify extra transactietoeslag % (default 0)", 0.0),
        "defaultMarginPercent":             ask_float("Standaard marge % (default 40)", 40.0)
    }

    # Notificaties
    print()
    use_tg = ask_bool("Telegram notificaties inschakelen")
    if use_tg:
        tg_bot  = ask("Telegram bot token", secret=True)
        tg_chat = ask("Telegram chat ID (bijv. 2128015430)")
        config["notifications"] = {
            "telegram": {"enabled": True, "botToken": tg_bot, "chatId": tg_chat}
        }
    else:
        config["notifications"] = {
            "telegram": {"enabled": False, "botToken": "", "chatId": ""}
        }

    # COGS sheet (optional)
    use_cogs = ask_bool("COGS koppelen via Google Sheets")
    if use_cogs:
        config["cogsSheet"] = {
            "spreadsheetId":          ask("Google Spreadsheet ID"),
            "sheetName":              ask("Sheet naam", "Sheet1"),
            "headerRow":              1,
            "productIdentifierColumn":"A",
            "cogsPriceColumn":        "C",
            "matchBy":                ask("Match op (sku / title / id)", "sku"),
            "serviceAccountFile":     ask("Pad naar service account JSON", "service-account.json")
        }
        config["cogsSheet"]["sheetUrl"] = f"https://docs.google.com/spreadsheets/d/{config['cogsSheet']['spreadsheetId']}"
    else:
        config["cogsSheet"] = {}

    config["supplier"] = {
        "name":    ask("Leverancier naam (bijv. CJ Dropshipping)", "CJ Dropshipping"),
        "contact": ask("Leverancier contact (bijv. je@email.com)", "")
    }

    # ── 10. Workspace & crons ──────────────────────────────────────────────
    section("10/10 — Workspace & crons")

    workspace_path = os.path.expanduser(
        ask("OpenClaw workspace pad", "~/.openclaw/workspace")
    )

    info(f"Workspace aanmaken in: {workspace_path}")
    create_workspace(workspace_path, config=config)
    ok("Workspace mappenstructuur aangemaakt")

    # Save config.json
    config_path = os.path.join(workspace_path, "googleclaw", "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    # Harden config.json permissions immediately
    try:
        os.chmod(config_path, 0o600)
        ok(f"config.json opgeslagen en beveiligd: {config_path} (chmod 600)")
    except Exception as e:
        warn(f"config.json opgeslagen maar chmod mislukt: {e}")
        warn(f"Voer handmatig uit: chmod 600 {config_path}")

    # ── Security checklist ─────────────────────────────────────────────────────
    print()
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")
    print(f"{c.BOLD}{c.YELLOW}  Beveiligingschecklist{c.RESET}")
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")
    print()
    print(f"  {c.BOLD}Shopify API scopes (vereist minimum){c.RESET}")
    print(f"  {'✓'} write_products")
    print(f"  {'✓'} read_products")
    print(f"  {c.RED}✗  write_orders     ← NIET nodig, verwijder indien aanwezig{c.RESET}")
    print(f"  {c.RED}✗  read_customers   ← NIET nodig, verwijder indien aanwezig{c.RESET}")
    print(f"  {c.RED}✗  write_customers  ← NIET nodig, verwijder indien aanwezig{c.RESET}")
    print()
    print(f"  {c.BOLD}Google Ads API scopes{c.RESET}")
    print(f"  {'✓'} Alleen lezen voor campagne-data (default)")
    print(f"  {'✓'} Budget-wijzigingen alleen na expliciete goedkeuring")
    print()
    print(f"  {c.BOLD}config.json{c.RESET}")
    print(f"  {'✓'} Staat NIET in git (gitignored)")
    print(f"  {'✓'} Permissies: 600 (alleen jij)")
    print(f"  {c.DIM}Locatie: {config_path}{c.RESET}")
    print()
    print(f"  {c.BOLD}audit.log{c.RESET}")
    print(f"  {'✓'} Alle Shopify writes worden gelogd")
    print(f"  {'✓'} Log is append-only — agents verwijderen hem nooit")
    print()
    print(f"  {c.DIM}Meer info: README.md → Security{c.RESET}")
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")
    print()

    # Install self-improving skill via clawhub
    print()
    si_choice = ask_bool("Self-Improving skill installeren via clawhub (agents leren van elke run)")
    if si_choice:
        info("Installeren via clawhub...")
        try:
            result = subprocess.run(
                ["clawhub", "install", "self-improving", "-g"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                ok("Self-Improving skill geïnstalleerd")
            else:
                warn(f"clawhub install mislukt — memory-bestanden zijn wél aangemaakt in workspace")
                dim("Installeer later handmatig: clawhub install self-improving -g")
        except FileNotFoundError:
            warn("clawhub CLI niet gevonden — memory-bestanden zijn wél aangemaakt in workspace")
            dim("Installeer clawhub via: npm install -g clawhub")
        except Exception as e:
            warn(f"Onverwachte fout: {e}")
    else:
        dim("Self-Improving skill overgeslagen — agents gebruiken alleen de lokale memory-bestanden in workspace.")

    # ── Gateway config: allow sessions_spawn over HTTP ────────────────────
    print()
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")
    print(f"{c.BOLD}{c.YELLOW}  Gateway configuratie{c.RESET}")
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")
    print()
    print(f"  GoogleClaw triggert agents via je OpenClaw gateway.")
    print(f"  Daarvoor moet {c.BOLD}sessions_spawn{c.RESET} toegestaan zijn over HTTP.")
    print()
    print(f"  Voeg dit toe aan je {c.CYAN}openclaw.json{c.RESET}:")
    print()
    print(f"  {c.DIM}{{")
    print(f'    "gateway": {{')
    print(f'      "tools": {{')
    print(f'        "allow": ["sessions_spawn"]')
    print(f'      }}')
    print(f'    }}')
    print(f"  }}{c.RESET}")
    print()

    # Write snippet to file for reference
    snippet_path = os.path.join(workspace_path, "googleclaw", "gateway-config-snippet.json")
    with open(snippet_path, "w") as f:
        json.dump({"gateway": {"tools": {"allow": ["sessions_spawn"]}}}, f, indent=2)
    dim(f"Snippet opgeslagen in: {snippet_path}")
    print()
    ask_bool("Voeg dit nu toe aan openclaw.json en herstart de gateway. Klaar?")
    print(f"  {c.BOLD}{c.GREEN}✓{c.RESET}  Gateway configuratie bevestigd")
    print(f"{c.BOLD}{c.YELLOW}{'─' * 54}{c.RESET}")

    # ── Register crons ────────────────────────────────────────────────────
    print()
    repo_path = os.path.dirname(os.path.abspath(__file__))
    timezone  = config.get("instance", {}).get("timezone", "Europe/Amsterdam")
    register_crons_choice = ask_bool("OpenClaw crons registreren (TRENDS, MIDAS, SCOUT, FEED)")
    if register_crons_choice:
        info("Crons registreren via openclaw CLI...")
        registered, failed = register_crons(CRONS, repo_path=repo_path, timezone=timezone)
        for r in registered:
            ok(r)
        for label, reason in failed:
            warn(f"{label} — {reason}")
        if failed:
            warn("Mislukte crons kun je later handmatig toevoegen via: openclaw cron add ...")
    else:
        dim("Crons overgeslagen — voeg later handmatig toe via openclaw cron add.")

    # ── Generate SOUL.md ───────────────────────────────────────────────────
    print()
    soul_template = os.path.join(os.path.dirname(__file__), "SOUL.template.md")
    soul_out = os.path.join(workspace_dir, "SOUL.md")
    if os.path.exists(soul_template):
        info("SOUL.md genereren uit template...")
        with open(soul_template, "r") as f:
            soul = f.read()
        replacements = {
            "{YOUR_NAME}":   config["instance"]["owner"],
            "{BOT_NAME}":    config["instance"].get("bot_name", config["instance"]["name"] + " Bot"),
            "{STORE_NAME}":  config["instance"]["name"],
            "{NICHE}":       config["store"]["niche"],
            "{MARKET}":      config["store"]["market"],
            "{LANGUAGE}":    config["store"]["language"],
            "{MIN_PRICE}":   str(int(config["thresholds"].get("min_price", 40))),
            "{ALERT_ROAS}":  str(config["thresholds"].get("alert_roas", 1.0)),
            "{SCALE_ROAS}":  str(config["thresholds"].get("scale_roas", 3.0)),
            "{ALERT_DAYS}":  str(int(config["thresholds"].get("alert_days", 3))),
        }
        for placeholder, value in replacements.items():
            soul = soul.replace(placeholder, value)
        with open(soul_out, "w") as f:
            f.write(soul)
        ok(f"SOUL.md geschreven → {soul_out}")
    else:
        warn("SOUL.template.md niet gevonden — SOUL.md overgeslagen.")

    # ── Gateway config for sessions_spawn ──────────────────────────────────
    section("OpenClaw Gateway configuratie")

    print(f"  {c.DIM}De frontend triggert agents via sessions_spawn.{c.RESET}")
    print(f"  {c.DIM}Dit moet expliciet toegestaan worden in je OpenClaw gateway config.{c.RESET}")
    print()
    print(f"  {c.YELLOW}Voeg dit toe aan je openclaw.json (of .openclaw/config.json):{c.RESET}")
    print()
    print(f'    {c.CYAN}{{"gateway": {{"tools": {{"allow": ["sessions_spawn"]}}}}}}{c.RESET}')
    print()

    # Write snippet to workspace for reference
    gateway_snippet = {
        "gateway": {
            "tools": {
                "allow": ["sessions_spawn"]
            }
        }
    }
    snippet_path = os.path.join(workspace_path, "googleclaw", "gateway-config-snippet.json")
    try:
        with open(snippet_path, "w") as f:
            json.dump(gateway_snippet, f, indent=2)
        dim(f"Snippet opgeslagen: {snippet_path}")
    except Exception as e:
        warn(f"Kon snippet niet opslaan: {e}")

    gateway_confirmed = ask_bool("Heb je de gateway config aangepast? (druk Y als gedaan)")
    if gateway_confirmed:
        ok("Gateway config bevestigd")
    else:
        warn("Vergeet niet de gateway config aan te passen voordat je agents vanuit de frontend triggert!")

    # ── OpenClaw crons for agents ──────────────────────────────────────────
    print()
    section("OpenClaw crons voor automatische runs")

    print(f"  {c.DIM}GoogleClaw agents kunnen automatisch draaien via OpenClaw crons.{c.RESET}")
    print(f"  {c.DIM}TRENDS draait wekelijks (zondag 23:00), SCOUT dagelijks (06:00).{c.RESET}")
    print()

    register_agent_crons = ask_bool("OpenClaw crons aanmaken voor automatische runs? (aanbevolen)")
    if register_agent_crons:
        timezone = config["instance"].get("timezone", "Europe/Amsterdam")
        gc_workspace = os.path.join(workspace_path, "googleclaw")

        # Read PROMPT.md files and fill {{REPO_PATH}}
        def load_prompt(agent_name):
            prompt_path = os.path.join(os.path.dirname(__file__), "agents", agent_name, "PROMPT.md")
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as f:
                    content = f.read()
                return content.replace("{{REPO_PATH}}", gc_workspace)
            return None

        cron_jobs = [
            {
                "name":        "gc-trends",
                "cron":        "0 23 * * 0",
                "model":       "openai/gpt-5.1-codex",
                "timeout":     600,
                "description": "GoogleClaw TRENDS — wekelijks zondag 23:00",
                "prompt":      load_prompt("trends"),
            },
            {
                "name":        "gc-scout",
                "cron":        "0 6 * * *",
                "model":       "openai/gpt-5.1-codex",
                "timeout":     900,
                "description": "GoogleClaw SCOUT — dagelijks 06:00",
                "prompt":      load_prompt("scout"),
            },
        ]

        for job in cron_jobs:
            if not job["prompt"]:
                warn(f"{job['name']}: PROMPT.md niet gevonden — overgeslagen")
                continue

            try:
                # Escape quotes in prompt for shell
                escaped_prompt = job["prompt"].replace('"', '\\"').replace("'", "'\\''")

                result = subprocess.run(
                    [
                        "openclaw", "cron", "add",
                        "--name", job["name"],
                        "--cron", job["cron"],
                        "--tz", timezone,
                        "--message", job["prompt"],
                        "--session", "isolated",
                        "--model", job["model"],
                        "--timeout-seconds", str(job["timeout"]),
                        "--description", job["description"],
                    ],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    ok(f"{job['name']}: cron geregistreerd ({job['cron']})")
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip() or "onbekende fout"
                    warn(f"{job['name']}: registratie mislukt — {error_msg}")
            except FileNotFoundError:
                warn(f"openclaw CLI niet gevonden — crons handmatig toevoegen")
                dim(f"Voer uit: openclaw cron add --name {job['name']} --cron \"{job['cron']}\" ...")
                break
            except subprocess.TimeoutExpired:
                warn(f"{job['name']}: timeout bij registratie")
            except Exception as e:
                warn(f"{job['name']}: {e}")
    else:
        dim("Crons overgeslagen — agents draaien alleen handmatig vanuit de frontend.")

    # ── Final summary ──────────────────────────────────────────────────────
    print()
    print(f"{c.BOLD}{c.GREEN}{'═' * 54}{c.RESET}")
    print(f"{c.BOLD}{c.GREEN}  GoogleClaw setup voltooid!{c.RESET}")
    print(f"{c.BOLD}{c.GREEN}{'═' * 54}{c.RESET}")
    print()
    print(f"  {c.WHITE}Store:    {c.RESET}{config['instance']['name']}")
    print(f"  {c.WHITE}Niche:    {c.RESET}{config['store']['niche']}")
    print(f"  {c.WHITE}Markt:    {c.RESET}{config['store']['market']}")
    print(f"  {c.WHITE}Config:   {c.RESET}{config_path}")
    print()
    print(f"  {c.DIM}Agents draaien automatisch via OpenClaw crons.{c.RESET}")
    print(f"  {c.DIM}LISTER wordt alleen getriggerd na handmatige goedkeuring.{c.RESET}")
    print()
    print(f"  {c.CYAN}Volgende stap:{c.RESET} stuur een bericht naar je OpenClaw gateway")
    print(f"  {c.DIM}met 'Run GoogleClaw TRENDS agent' om de eerste scan te starten.{c.RESET}")
    print()

if __name__ == "__main__":
    main()
