from __future__ import annotations

import json

from ..elementos.render import resolve_render_profiles
from ..elementos.render.constraints_builder import build_constraints_struct
from ..progress_updater import update_progress_state
from ..schemas import default_render_state


def _safe_get_path(payload: dict, path: str):
    cur = payload
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def progress_updater_node(state: dict) -> dict:
    frozen_checks = [
        "policy_plan_judgement",
        "progress_state.active_plan",
        "executor_instruction",
        "progress_state.policy_state.planner_request",
    ]
    frozen_before = {path: _safe_get_path(state, path) for path in frozen_checks}
    prev_progress = state.get("progress_state") or {}
    progress_state, progress_core_debug = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=state["policy_decision"],
        last_policy_executed=state.get("last_policy_executed"),
        prev_world_state=state["prev_world_state"],
        world_state=state["world_state"],
        prev_belief_state=state.get("prev_belief_state"),
        belief_state=state["belief_state"],
        turn_count=state.get("turn_count", 0),
        include_debug=True,
        policy_plan_judgement=state.get("policy_plan_judgement") if isinstance(state.get("policy_plan_judgement"), dict) else None,
        user_message=str(state.get("user_message", "") or ""),
        active_plan=state.get("progress_state", {}).get("active_plan") if isinstance(state.get("progress_state"), dict) else None,
        executor_output=state.get("executor_output") if isinstance(state.get("executor_output"), dict) else None,
        last_assistant_message=str(state.get("last_assistant_message", "") or ""),
        advisor_signals=state.get("advisor_signals") if isinstance(state.get("advisor_signals"), dict) else None,
    )
    render_state = progress_state.get("render_state") or default_render_state()
    persona, scene, style = resolve_render_profiles(render_state)
    render_constraints_struct = build_constraints_struct(
        world=state.get("world_state", {}),
        belief=state.get("belief_state", {}),
        progress=progress_state,
        decision=state.get("policy_decision", {}),
        persona=persona,
        scene=scene,
        style=style,
    )
    progress_state["render_constraints_struct"] = render_constraints_struct
    frozen_after = {path: _safe_get_path({**state, "progress_state": progress_state}, path) for path in frozen_checks}
    frozen_summary = []
    frozen_error = False
    for path in frozen_checks:
        changed = frozen_before.get(path) != frozen_after.get(path)
        frozen_summary.append({"path": path, "changed": changed})
        if changed:
            frozen_error = True

    loop_flags = [str(x) for x in (progress_state.get("loop_flags") or []) if str(x).strip()]
    persistence_paths = []
    for key in sorted(set(prev_progress.keys()) | set(progress_state.keys())):
        if prev_progress.get(key) != progress_state.get(key):
            persistence_paths.append(f"progress_state.{key}")

    state["progress_debug"] = {
        "frozen_fields_check": frozen_summary,
        "frozen_fields_error": frozen_error,
        "anti_loop_signals": {
            **(progress_core_debug.get("anti_loop_signals") or {}),
        },
        "telemetry_updates": {
            "counters_incremented": [p for p in persistence_paths if p.endswith("turns_in_same_mode") or p.endswith("plan_id_changes_window") or p.endswith("no_progress_same_step_turns") or p.endswith("same_step_no_progress_turns")],
            "next_turn_flags": loop_flags,
        },
        "persistence_summary": {
            "modified_paths": persistence_paths[:40],
            "modified_paths_count": len(persistence_paths),
            "fingerprint": hash(json.dumps(persistence_paths, ensure_ascii=False)),
        },
    }
    state["progress_state"] = progress_state
    return state
