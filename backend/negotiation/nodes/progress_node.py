from __future__ import annotations

from ..elementos.render import resolve_render_profiles
from ..elementos.render.constraints_builder import build_constraints_struct
from ..progress_updater import update_progress_state
from ..schemas import default_render_state


def progress_updater_node(state: dict) -> dict:
    progress_state = update_progress_state(
        prev_progress=state.get("progress_state"),
        policy_decision=state["policy_decision"],
        last_policy_executed=state.get("last_policy_executed"),
        prev_world_state=state["prev_world_state"],
        world_state=state["world_state"],
        prev_belief_state=state.get("prev_belief_state"),
        belief_state=state["belief_state"],
    )
    render_state = progress_state.get("render_state") or default_render_state()
    persona, scene, style = resolve_render_profiles(render_state)
    constraints_struct = build_constraints_struct(
        world=state.get("world_state", {}),
        belief=state.get("belief_state", {}),
        progress=progress_state,
        decision=state.get("policy_decision", {}),
        persona=persona,
        scene=scene,
        style=style,
    )
    progress_state["constraints_struct"] = constraints_struct
    state["progress_state"] = progress_state
    return state
