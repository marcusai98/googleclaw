#!/usr/bin/env python3
"""
GoogleClaw — Shared utility: audit log
Append-only log of all agent writes and consequential reads.
Log is never deleted or modified by agents.

Usage:
    from agents.shared.audit import audit_log

    audit_log(agent="LISTER", action="shopify_create", resource="product/123456789",
              detail="Kant jurk — CJ #4401", result="ok")

    audit_log(agent="MIDAS", action="gads_read", resource="campaign/12345",
              detail="PMAX NL", result="ok")
"""

import json
import os
from datetime import datetime, timezone

# Audit log lives in the workspace root alongside config.json
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(os.path.dirname(SCRIPT_DIR))          # agents/shared → agents → repo root
WORKSPACE_DIR = os.environ.get("GOOGLECLAW_WORKSPACE", REPO_ROOT)
AUDIT_LOG    = os.path.join(WORKSPACE_DIR, "audit.log")


def audit_log(
    agent:    str,
    action:   str,
    resource: str,
    detail:   str = "",
    result:   str = "ok",
    extra:    dict = None,
) -> None:
    """
    Append one audit entry to audit.log.
    Format: JSON lines (one object per line) — easy to grep and parse.

    Fields:
        ts        ISO 8601 UTC timestamp
        agent     e.g. LISTER, MIDAS, SCOUT, FEED
        action    e.g. shopify_create, shopify_update, shopify_draft,
                       gads_read, gads_budget_change, config_write
        resource  e.g. product/123456, campaign/456789, config.json
        detail    human-readable summary
        result    ok | error | skipped
        extra     optional dict with additional context
    """
    entry = {
        "ts":       datetime.now(timezone.utc).isoformat(),
        "agent":    agent,
        "action":   action,
        "resource": resource,
        "detail":   detail[:200] if detail else "",
        "result":   result,
    }
    if extra:
        entry["extra"] = extra

    line = json.dumps(entry, ensure_ascii=False)

    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        # Never crash an agent because of audit logging — just print
        print(f"[audit] ⚠  Failed to write audit log: {e}")
        print(f"[audit] Entry: {line}")


def audit_shopify_create(agent: str, product_id: str, title: str, result: str = "ok") -> None:
    audit_log(agent=agent, action="shopify_create", resource=f"product/{product_id}",
              detail=title, result=result)

def audit_shopify_update(agent: str, product_id: str, field: str, result: str = "ok") -> None:
    audit_log(agent=agent, action="shopify_update", resource=f"product/{product_id}",
              detail=f"field: {field}", result=result)

def audit_shopify_draft(agent: str, product_id: str, title: str, reason: str = "", result: str = "ok") -> None:
    audit_log(agent=agent, action="shopify_draft", resource=f"product/{product_id}",
              detail=f"{title} | reason: {reason}", result=result)

def audit_gads_read(agent: str, customer_id: str, detail: str = "") -> None:
    audit_log(agent=agent, action="gads_read", resource=f"customer/{customer_id}",
              detail=detail, result="ok")

def audit_config_write(agent: str, field: str, result: str = "ok") -> None:
    audit_log(agent=agent, action="config_write", resource="config.json",
              detail=f"field updated: {field}", result=result)
