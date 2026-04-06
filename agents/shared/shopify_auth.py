#!/usr/bin/env python3
"""
GoogleClaw — Shared utility: Shopify OAuth authentication
Handles the Client Credentials Grant flow (new Shopify method since Jan 2026).

Static access tokens are no longer available for new apps. This module
exchanges Client ID + Client Secret for a 24h access token and caches it.

Usage:
    from agents.shared.shopify_auth import get_shopify_token

    token = get_shopify_token(cfg)  # auto-refreshes when expired
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
"""

import json
import os
import time
import requests

# Token cache lives next to config.json
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CACHE_FILE  = os.path.join(REPO_ROOT, "data", ".shopify_token_cache.json")
EXPIRE_BUFFER = 3600  # refresh 1h before actual expiry (tokens last 24h)


def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(token: str, expires_at: float) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"token": token, "expires_at": expires_at}, f)
        os.chmod(CACHE_FILE, 0o600)
    except Exception as e:
        print(f"[shopify_auth] ⚠  Could not cache token: {e}")


def get_shopify_token(cfg: dict) -> str:
    """
    Get a valid Shopify Admin API access token.
    Uses cached token if still valid, otherwise fetches a new one.

    Supports both:
    - New method (Jan 2026+): client_id + client_secret → OAuth token
    - Legacy method: static access_token (for stores created before Jan 2026)
    """
    shopify_cfg = cfg.get("shopify", {})
    domain      = shopify_cfg.get("storeDomain", "").rstrip("/")
    client_id   = shopify_cfg.get("clientId", "")
    client_secret = shopify_cfg.get("clientSecret", "")
    static_token  = shopify_cfg.get("accessToken", "")

    # Legacy: static token still present (pre-2026 stores)
    if static_token and not client_id:
        return static_token

    if not client_id or not client_secret:
        raise ValueError(
            "[shopify_auth] Missing clientId or clientSecret in config.json. "
            "Create a Custom App in your Shopify Dev Dashboard to get these."
        )

    if not domain:
        raise ValueError("[shopify_auth] Missing storeDomain in config.json.")

    # Check cache
    cache = _load_cache()
    if cache.get("token") and cache.get("expires_at", 0) > time.time() + EXPIRE_BUFFER:
        return cache["token"]

    # Fetch new token via Client Credentials Grant
    url = f"https://{domain}/admin/oauth/access_token"
    payload = {
        "client_id":     client_id,
        "client_secret": client_secret,
        "grant_type":    "client_credentials",
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        raise RuntimeError(
            f"[shopify_auth] Token request failed: {e.response.status_code} — {e.response.text}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"[shopify_auth] Token request error: {e}") from e

    token      = data.get("access_token")
    expires_in = int(data.get("expires_in", 86400))  # default 24h

    if not token:
        raise RuntimeError(f"[shopify_auth] No access_token in response: {data}")

    expires_at = time.time() + expires_in
    _save_cache(token, expires_at)

    print(f"[shopify_auth] ✓ New token acquired (expires in {expires_in // 3600}h)")
    return token
