"""A small, self-contained requirement-quality linter.

This is a stand-in for the kind of *authoring* value elm-mcp v2 adds on top of
the hub's primitives: it runs with zero ELM access (pure text analysis), so it
works in standalone mode too. The intended flow is: the AI drafts a requirement
-> lints it here -> only then commits it via the hub's `create_requirement`.

Checks are intentionally conservative (high precision) so the output is
actionable, not noisy.
"""
from __future__ import annotations

import re

# Vague / un-testable words that make a requirement unverifiable.
_WEASEL = [
    "user-friendly", "easy", "fast", "quickly", "efficient", "flexible",
    "robust", "seamless", "intuitive", "appropriate", "adequate", "as needed",
    "etc", "and/or", "support", "handle", "manage", "optimize", "minimize",
    "maximize", "approximately", "about", "some", "several", "many", "few",
    "better", "improved", "state-of-the-art", "where possible", "if necessary",
]
# Modal verbs — "shall" is the testable-requirement convention.
_GOOD_MODALS = ("shall",)
_WEAK_MODALS = ("should", "may", "could", "will", "can", "might", "must")


def lint_requirement(text: str) -> dict:
    """Return a structured quality report for one requirement statement.

    {ok, score(0-100), issues:[{level, code, message}], suggestions:[str]}
    """
    t = (text or "").strip()
    issues: list[dict] = []

    def add(level, code, msg):
        issues.append({"level": level, "code": code, "message": msg})

    if not t:
        return {"ok": False, "score": 0,
                "issues": [{"level": "error", "code": "empty",
                            "message": "Requirement text is empty."}],
                "suggestions": ["Provide a single, testable 'The <subject> shall <action>' statement."]}

    low = t.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z\-/]*", low)

    # 1. testable modal
    if not any(re.search(rf"\b{m}\b", low) for m in _GOOD_MODALS):
        weak = [m for m in _WEAK_MODALS if re.search(rf"\b{m}\b", low)]
        if weak:
            add("warn", "weak-modal",
                f"Uses '{weak[0]}' instead of 'shall'. 'shall' states a verifiable obligation.")
        else:
            add("warn", "no-modal",
                "No 'shall' — a requirement should state a testable obligation ('The system shall …').")

    # 2. vague / un-testable words
    found_weasel = sorted({w for w in _WEASEL if re.search(rf"\b{re.escape(w)}\b", low)})
    if found_weasel:
        add("warn", "vague",
            f"Vague / un-testable wording: {', '.join(found_weasel)}. Replace with measurable criteria.")

    # 3. compound requirement (and / or joining two obligations)
    if re.search(r"\bshall\b.*\b(and|or)\b.*\bshall\b", low) or low.count(" and ") >= 2:
        add("info", "compound",
            "Looks like it bundles multiple obligations. Prefer one requirement per statement.")

    # 4. passive voice (rough heuristic)
    if re.search(r"\b(is|are|be|been|being)\b\s+\w+ed\b", low):
        add("info", "passive",
            "Possibly passive voice — name the responsible subject ('The system shall …').")

    # 5. length / vagueness
    n = len(words)
    if n < 4:
        add("warn", "too-short", "Very short — likely missing a subject, action, or object.")
    elif n > 60:
        add("info", "too-long", f"Long ({n} words) — consider splitting for testability.")

    # 6. missing measurable criterion where a perf-y word appears
    if re.search(r"\b(within|less than|no more than|at least|<=|>=|\d+\s*(ms|s|sec|seconds|%|percent))\b", low):
        pass  # has a number — good
    elif any(w in low for w in ("response", "latency", "throughput", "performance", "time", "load")):
        add("info", "no-metric",
            "Mentions performance but no measurable threshold (e.g. 'within 200 ms').")

    score = 100
    for i in issues:
        score -= {"error": 50, "warn": 20, "info": 8}.get(i["level"], 10)
    score = max(0, score)

    suggestions = []
    if any(i["code"] in ("no-modal", "weak-modal") for i in issues):
        suggestions.append("Rewrite as 'The <subject> shall <observable action> [under <condition>].'")
    if any(i["code"] == "vague" for i in issues):
        suggestions.append("Swap vague adjectives for measurable acceptance criteria.")
    if any(i["code"] == "compound" for i in issues):
        suggestions.append("Split into one obligation per requirement so each is independently testable.")

    return {"ok": not any(i["level"] == "error" for i in issues),
            "score": score, "issues": issues, "suggestions": suggestions}


def format_report(text: str, rep: dict) -> str:
    icon = {"error": "🔴", "warn": "🟠", "info": "🔵"}
    lines = [f"**Requirement quality: {rep['score']}/100**",
             f"> {text.strip()[:200]}", ""]
    if not rep["issues"]:
        lines.append("✅ No issues — clear, testable, single-obligation.")
    else:
        for i in rep["issues"]:
            lines.append(f"{icon.get(i['level'],'•')} **{i['code']}** — {i['message']}")
    if rep["suggestions"]:
        lines.append("\n**Suggestions:**")
        for s in rep["suggestions"]:
            lines.append(f"- {s}")
    return "\n".join(lines)
