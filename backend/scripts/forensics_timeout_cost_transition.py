from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _minute(ts: str | None) -> str | None:
    if not isinstance(ts, str) or len(ts) < 16:
        return None
    return ts[:16] + ":00+00:00"


def _index_traces(turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(t.get("turn_id")): t for t in turns if isinstance(t, dict) and t.get("turn_id")}


def _load_csv(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            minute = row.get("minute_utc") or row.get("minute")
            if not minute:
                continue
            out[minute] = row
    return out


def _turn_bundle(trace: dict[str, Any]) -> dict[str, Any]:
    nodes = trace.get("nodes", {}) if isinstance(trace.get("nodes"), dict) else {}
    provider_calls = trace.get("provider_calls", []) if isinstance(trace.get("provider_calls"), list) else []
    prompt_chars = {n: (v.get("prompt_artifacts") or {}).get("payload_chars", 0) for n, v in nodes.items() if isinstance(v, dict)}
    payload_hashes = {n: (v.get("prompt_artifacts") or {}).get("payload_hash") for n, v in nodes.items() if isinstance(v, dict)}
    return {
        "turn_id": trace.get("turn_id"),
        "status": trace.get("final_status"),
        "turn_started_at": trace.get("turn_started_at"),
        "turn_finished_at": trace.get("turn_finished_at"),
        "conversation_id_before": trace.get("conversation_id_before"),
        "conversation_id_after": trace.get("conversation_id_after"),
        "previous_response_id_before": trace.get("previous_response_id_before"),
        "previous_response_id_after": trace.get("previous_response_id_after"),
        "recent_dialogue_count": ((nodes.get("planner") or {}).get("input_summary") or {}).get("recent_dialogue_count"),
        "selected_memory_count": ((nodes.get("planner") or {}).get("input_summary") or {}).get("selected_memory_count"),
        "payload_chars_by_node": prompt_chars,
        "payload_hash_by_node": payload_hashes,
        "provider_call_count": len(provider_calls),
        "provider_models": sorted({c.get("model") for c in provider_calls if isinstance(c, dict) and c.get("model")}),
        "provider_call_subtypes": sorted({c.get("call_subtype") for c in provider_calls if isinstance(c, dict) and c.get("call_subtype")}),
        "side_effect_hooks": trace.get("side_effect_hooks", []),
    }


def build_report(*, attempts: list[dict[str, Any]], turns: list[dict[str, Any]], timeout_error_id: str, csv_by_minute: dict[str, dict[str, Any]]) -> dict[str, Any]:
    traces = _index_traces(turns)
    timeout_idx = next((i for i, a in enumerate(attempts) if a.get("error_id") == timeout_error_id), -1)
    if timeout_idx < 0:
        raise ValueError(f"timeout_error_id not found: {timeout_error_id}")

    pre = attempts[timeout_idx - 1] if timeout_idx - 1 >= 0 else None
    err = attempts[timeout_idx]
    post = [a for a in attempts[timeout_idx + 1 : timeout_idx + 4]]

    focused = [item for item in [pre, err, *post] if isinstance(item, dict)]
    turn_rows: list[dict[str, Any]] = []
    for attempt in focused:
        trace = traces.get(str(attempt.get("latest_turn_id") or ""), {})
        bundle = _turn_bundle(trace) if trace else {}
        minute = _minute(bundle.get("turn_started_at") if bundle else attempt.get("attempt_started_at"))
        turn_rows.append(
            {
                "backend_turn_attempt_id": attempt.get("backend_turn_attempt_id"),
                "logical_user_message_id": attempt.get("logical_user_message_id"),
                "logical_attempt_index": attempt.get("logical_attempt_index"),
                "status": attempt.get("status"),
                "error_category": attempt.get("error_category"),
                "failing_stage": attempt.get("failing_stage"),
                "diagnostic": attempt.get("diagnostic"),
                "trace_count_before": attempt.get("trace_count_before"),
                "trace_count_after": attempt.get("trace_count_after"),
                "provider_calls_in_attempt": attempt.get("provider_calls_in_attempt"),
                "side_effect_hooks_in_attempt": attempt.get("side_effect_hooks_in_attempt"),
                "turn_bundle": bundle,
                "csv_minute": minute,
                "csv_row": csv_by_minute.get(minute),
            }
        )

    hypothesis = defaultdict(lambda: "open")
    hypothesis["H1_session_incoherent_after_timeout"] = "confirmed" if any((r.get("error_category") == "upstream_write_timeout" and r.get("status") == "failed") for r in turn_rows) else "open"
    hypothesis["H3_hidden_extra_calls"] = "confirmed" if any(int(r.get("provider_calls_in_attempt") or 0) > int((r.get("turn_bundle") or {}).get("provider_call_count") or 0) for r in turn_rows) else "open"
    hypothesis["H5_partial_replay"] = "open"

    return {
        "timeout_error_id": timeout_error_id,
        "window": {
            "pre_attempt": pre,
            "error_attempt": err,
            "post_attempts": post,
        },
        "turn_rows": turn_rows,
        "hypotheses": dict(hypothesis),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Forensic timeout/cost transition report")
    parser.add_argument("--attempts-json", required=True)
    parser.add_argument("--turns-json", required=True)
    parser.add_argument("--timeout-error-id", required=True)
    parser.add_argument("--csv-minute", required=False)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    attempts = _load_json(Path(args.attempts_json))
    turns = _load_json(Path(args.turns_json))
    csv_by_minute = _load_csv(Path(args.csv_minute)) if args.csv_minute else {}

    report = build_report(attempts=attempts, turns=turns, timeout_error_id=args.timeout_error_id, csv_by_minute=csv_by_minute)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
