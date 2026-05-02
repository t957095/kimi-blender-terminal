"""
Knowledge Base — Personal RAG for Kimi Blender Terminal.

Learns from every successful interaction, stores workflows, preferences,
and corrections. Retrieves relevant context to augment prompts.

No external dependencies. Uses keyword overlap + recency + success scoring.
Storage: ~/.kimi/blender-terminal/knowledge_base.json
"""

import json
import os
import re
import time
from collections import Counter

KB_DIR = os.path.expanduser(r"~\.kimi\blender-terminal")
KB_FILE = os.path.join(KB_DIR, "knowledge_base.json")
MAX_ENTRIES = 500
RETRIEVAL_TOP_K = 5


def _ensure_dir():
    os.makedirs(KB_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if os.path.isfile(KB_FILE):
        try:
            with open(KB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"entries": [], "user_profile": {}, "version": 1}


def _save(data: dict):
    _ensure_dir()
    try:
        with open(KB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _tokenize(text: str) -> set:
    """Extract lowercase alphanumeric tokens."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score_entry(entry: dict, query_tokens: set, now: float) -> float:
    """Compute relevance score for an entry against query tokens."""
    prompt_tokens = set(entry.get("prompt_tokens", []))
    code_tokens = set(entry.get("code_tokens", []))
    all_tokens = prompt_tokens | code_tokens

    if not all_tokens or not query_tokens:
        return 0.0

    overlap = len(query_tokens & all_tokens)
    union = len(query_tokens | all_tokens)
    jaccard = overlap / union if union else 0.0

    # Recency decay: half-life of 30 days
    age_days = (now - entry.get("timestamp", now)) / 86400.0
    recency = 0.5 ** (age_days / 30.0)

    # Success bonus
    success = 1.5 if entry.get("outcome") == "success" else 1.0

    # Correction bonus (learned from user feedback)
    corrected = 1.3 if entry.get("user_corrected") else 1.0

    # Frequency bonus (how often this pattern has been reused)
    reuse = 1.0 + 0.05 * min(entry.get("reuse_count", 0), 10)

    return jaccard * recency * success * corrected * reuse


# ── Public API ──

def store_entry(
    prompt: str,
    code: str = "",
    outcome: str = "success",
    scene_description: str = "",
    user_correction: str = "",
    tags: list = None,
):
    """Store a new knowledge entry from an interaction."""
    data = _load()
    entries = data.get("entries", [])
    now = time.time()

    entry = {
        "id": f"{int(now * 1000)}",
        "timestamp": now,
        "prompt": prompt,
        "prompt_tokens": list(_tokenize(prompt)),
        "code": code[:2000],
        "code_tokens": list(_tokenize(code)),
        "outcome": outcome,
        "scene_description": scene_description,
        "user_corrected": bool(user_correction),
        "user_correction": user_correction,
        "tags": tags or [],
        "reuse_count": 0,
    }

    entries.append(entry)

    # Prune old entries
    if len(entries) > MAX_ENTRIES:
        entries.sort(key=lambda e: _score_entry(e, set(), now), reverse=True)
        entries = entries[:MAX_ENTRIES]

    data["entries"] = entries
    _save(data)


def retrieve_context(query: str, top_k: int = RETRIEVAL_TOP_K) -> list:
    """Retrieve the most relevant past entries for a query prompt."""
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return []

    query_tokens = _tokenize(query)
    now = time.time()

    scored = []
    for entry in entries:
        score = _score_entry(entry, query_tokens, now)
        if score > 0.01:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def format_context(entries: list) -> str:
    """Format retrieved entries into a context string for the prompt."""
    if not entries:
        return ""

    lines = ["\n[Personal Knowledge Base — learned from past sessions]\n"]
    for i, entry in enumerate(entries, 1):
        lines.append(f"--- Pattern {i} ---")
        lines.append(f"User request: {entry['prompt'][:200]}")
        if entry.get("code"):
            lines.append(f"What worked: {entry['code'][:300]}")
        if entry.get("user_correction"):
            lines.append(f"Correction learned: {entry['user_correction']}")
        if entry.get("scene_description"):
            lines.append(f"Scene context: {entry['scene_description'][:150]}")
        lines.append("")

    return "\n".join(lines)


def increment_reuse(entry_id: str):
    """Mark an entry as reused (improves its score)."""
    data = _load()
    for entry in data.get("entries", []):
        if entry.get("id") == entry_id:
            entry["reuse_count"] = entry.get("reuse_count", 0) + 1
            break
    _save(data)


def get_stats() -> dict:
    """Return knowledge base stats for UI display."""
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return {"count": 0, "patterns": 0, "corrections": 0}

    corrections = sum(1 for e in entries if e.get("user_corrected"))
    # Count unique patterns by prompt similarity (simple)
    unique = set()
    for e in entries:
        tokens = tuple(sorted(e.get("prompt_tokens", []))[:8])
        unique.add(tokens)

    return {
        "count": len(entries),
        "patterns": len(unique),
        "corrections": corrections,
    }


def record_correction(original_prompt: str, correction: str):
    """Record a user correction to refine future behavior."""
    data = _load()
    entries = data.get("entries", [])
    now = time.time()

    # Find the most recent entry matching this prompt
    for entry in reversed(entries):
        if entry.get("prompt") == original_prompt:
            entry["user_corrected"] = True
            entry["user_correction"] = correction
            entry["timestamp"] = now
            break
    else:
        # No match — store as a new correction-only entry
        store_entry(
            prompt=original_prompt,
            outcome="corrected",
            user_correction=correction,
        )
        return

    _save(data)


def update_user_profile(key: str, value):
    """Store a user preference (e.g., preferred style, color palette)."""
    data = _load()
    profile = data.setdefault("user_profile", {})
    profile[key] = value
    _save(data)


def get_user_profile() -> dict:
    """Retrieve stored user preferences."""
    data = _load()
    return data.get("user_profile", {})


def format_profile() -> str:
    """Format user profile into a string for system prompt injection."""
    profile = get_user_profile()
    if not profile:
        return ""

    lines = ["\n[User Preferences]\n"]
    for k, v in profile.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"


def clear_knowledge_base():
    """Wipe all learned knowledge. Use with caution."""
    _save({"entries": [], "user_profile": {}, "version": 1})
