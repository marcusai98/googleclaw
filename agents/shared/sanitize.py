#!/usr/bin/env python3
"""
GoogleClaw — Shared utility: prompt sanitization
Strips instruction-injection attempts from external data (product titles,
descriptions, sheet rows) before they are included in agent prompts.

Usage:
    from agents.shared.sanitize import sanitize, is_suspicious

    safe_title = sanitize(raw_title)
    if is_suspicious(raw_description):
        skip product
"""

import re

# Patterns that indicate potential prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|prior|all)\s+instructions?",
    r"forget\s+(everything|all|previous)",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(a|an)\s+\w+",
    r"(system|assistant|user)\s*:",
    r"<\s*(system|prompt|instruction)",
    r"\[\s*(system|inst|instruction)",
    r"do\s+not\s+(follow|obey|use)\s+(your|the)\s+(rules|instructions|guidelines)",
    r"new\s+(instruction|directive|task|objective)",
    r"override\s+(your|the|all)",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

MAX_FIELD_LENGTH = 500  # Truncate any external field beyond this length


def is_suspicious(text: str) -> bool:
    """
    Returns True if the text contains patterns that look like prompt injection.
    Call this before including external data in a prompt — skip the item if True.
    """
    if not text:
        return False
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize(text: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """
    Clean an external string for safe inclusion in an agent prompt.
    - Truncates to max_length
    - Removes null bytes and control characters
    - Collapses excessive whitespace
    """
    if not text:
        return ""
    # Remove null bytes and non-printable control characters (keep newlines/tabs)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text))
    # Collapse excessive whitespace
    cleaned = re.sub(r"[ \t]{3,}", "  ", cleaned)
    # Truncate
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "…"
    return cleaned.strip()


def sanitize_product(product: dict) -> dict:
    """
    Sanitize all string fields of a product candidate dict.
    Returns sanitized copy. Raises ValueError if injection detected.
    """
    text_fields = ["title", "name", "description", "body_html", "englishName",
                   "matchedTrend", "notes", "competitorUrl"]
    result = dict(product)
    for field in text_fields:
        val = result.get(field)
        if val and isinstance(val, str):
            if is_suspicious(val):
                raise ValueError(
                    f"[sanitize] Injection pattern detected in field '{field}': "
                    f"{val[:80]!r} — product skipped"
                )
            result[field] = sanitize(val)
    return result


def sanitize_batch(products: list, agent: str = "UNKNOWN") -> list:
    """
    Sanitize a list of product dicts. Logs and drops any suspicious items.
    Returns safe list.
    """
    safe = []
    for p in products:
        try:
            safe.append(sanitize_product(p))
        except ValueError as e:
            print(f"[{agent}/sanitize] ⚠  {e}")
    if len(safe) < len(products):
        dropped = len(products) - len(safe)
        print(f"[{agent}/sanitize] Dropped {dropped} suspicious product(s)")
    return safe
