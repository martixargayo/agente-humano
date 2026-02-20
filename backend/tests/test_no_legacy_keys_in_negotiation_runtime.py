from pathlib import Path
import re


BANNED = [
    "universal_domain",
    "negotiation_v2",
    "universal_v2",
    "universal_state",
    "open_claims",
    "evidence_items",
    "world_observations",
    "world_derived",
    "intent_step",
    "intent_transition",
]

ALLOWLIST = {
    Path("backend/negotiation/state_migration_v3.py"),
}


def test_no_legacy_keys_remain_outside_migration_allowlist():
    root = Path("backend/negotiation")
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path
        if rel in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for token in BANNED:
            for match in re.finditer(rf"\b{re.escape(token)}\b", text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{rel}:{line}:{token}")
    assert offenders == [], "Legacy keys found outside allowlist:\n" + "\n".join(offenders)
