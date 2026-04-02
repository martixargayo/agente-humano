from __future__ import annotations

from typing import Any

from sessions.state import get_session_state

from ..contexts import ensure_session_context
from ..orchestration.flow_config import build_negotiation_pipeline_config
from ..orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from .turn_context_factory import build_api_negociar_turn_context


def run_legacy_negociar_turn(*, user_id: str, session_id: str, message: str, context_id: str | None) -> dict[str, Any]:
    normalized_context_id = (context_id or "").strip()
    if not normalized_context_id:
        raise ValueError("missing_context_id_for_stateful_negociar")

    state = get_session_state(user_id=user_id, session_id=session_id)
    bound_context = ensure_session_context(state=state, requested_context_id=normalized_context_id)
    config = build_negotiation_pipeline_config(context_id=bound_context.context_id, stateful=True)
    turn_context = build_api_negociar_turn_context(state=state, requested_context_id=bound_context.context_id)
    reply, updated_state, meta = execute_turn_with_contract(
        state=state,
        user_message=message,
        config=config,
        contract=TurnEntryContract(
            entry_surface="api_negociar_legacy",
            entrypoint="/negociar",
            overrides_applied=False,
            optimizer_wrapper_used=False,
            new_conversation=False,
            clone_used=False,
        ),
        turn_context=turn_context,
    )
    finish_button_armed = False
    negotiation_canonical = updated_state.world_state.get("negotiation_canonical", {}) if isinstance(updated_state.world_state, dict) else {}
    if isinstance(negotiation_canonical, dict):
        ui_state = negotiation_canonical.get("ui_state", {})
        if isinstance(ui_state, dict):
            finish_button_armed = bool(ui_state.get("finish_button_armed", False))

    return {
        "reply": reply,
        "finish_button_armed": finish_button_armed,
        "meta": meta,
    }
