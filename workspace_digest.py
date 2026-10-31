"""Public, minimal, read-only daily digest contract for Personal Workspace.

Do not include prompts, API keys, mail settings, full source articles or HTML.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
MAX_ITEMS = 20
PUBLIC_CATEGORIES = frozenset({"生态与鸟类", "国际新闻", "人文社会", "AI 与科技"})


def public_item(category: str, source: str, title: str, summary: str, url: str):
    """Return an allowlisted, plain-text item, or None for unsafe/empty links."""
    if category not in PUBLIC_CATEGORIES:
        return None
    if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\x00-\x20\x7f]", url):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None

    def plain(value, limit):
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", " ", value).strip()[:limit]

    name = plain(title, 160)
    explanation = plain(summary, 400)
    source_name = plain(source, 80)
    if not name or not source_name:
        return None
    return {
        "id": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "category": category,
        "source": source_name,
        "title": name,
        "summary": explanation,
        "url": url,
    }


def write_public_digest(items, destination="docs/daily-digest.json", now=None):
    """Atomically write the bounded public snapshot; never overwrite on empty input."""
    unique = []
    seen = set()
    for item in items:
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
        if len(unique) >= MAX_ITEMS:
            break
    if not unique:
        return False
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    current = current.astimezone(timezone.utc)
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceApp": "RSS-GPT",
        "generatedAt": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "reportDate": current.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "timeZone": "Asia/Shanghai",
        "items": unique,
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".digest-", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return True
