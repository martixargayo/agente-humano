from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CASE_FILE = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "optimizador_cases.jsonl"


def save_case(turn: dict[str, Any], family: str, tags: list[str], notes: str) -> dict[str, Any]:
    CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "case_id": f"opt_{turn.get('turn_id')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "tags": tags,
        "notes": notes,
        "turn_id": turn.get("turn_id"),
        "input": turn.get("user_turn", {}).get("raw_text", ""),
        "candidate_output": turn.get("final_reply_text", ""),
        "trace": turn,
    }
    with CASE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def list_cases() -> list[dict[str, Any]]:
    if not CASE_FILE.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in CASE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
