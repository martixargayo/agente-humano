from __future__ import annotations

from dataclasses import dataclass, field

from sessions.state import SessionState

from ..contexts import read_bound_context_from_session, resolve_context_for_prompts_dir
from .context_errors import (
    ContextMismatchError,
    ImplicitContextForbiddenError,
    InvalidConfigContextError,
    MissingTurnContextError,
    StatefulContextRequiredError,
)
from .flow_config import NegotiationTurnConfig, derive_config_context_id
from .turn_execution_context import TurnExecutionContext


@dataclass(frozen=True)
class ValidatedTurnContext:
    effective_context_id: str
    session_bound_context_id: str
    config_context_id: str
    trace_context_id: str
    context_version: str | None = None
    context_source: str | None = None
    execution_mode: str = "stateful"
    reason_codes: list[str] = field(default_factory=lambda: ["ctx_precheck_ok"])


def validate_turn_context_pre_execution(
    *,
    state: SessionState,
    config: NegotiationTurnConfig,
    turn_context: TurnExecutionContext | None,
) -> ValidatedTurnContext:
    if turn_context is None:
        if config.stateful:
            raise MissingTurnContextError(message="turn_context_required_for_stateful")
        bound = read_bound_context_from_session(state)
        fallback_context_id = derive_config_context_id(config)
        if bound is None or not fallback_context_id:
            raise MissingTurnContextError(message="turn_context_required")
        return ValidatedTurnContext(
            effective_context_id=fallback_context_id,
            session_bound_context_id=bound.context_id,
            config_context_id=fallback_context_id,
            trace_context_id=fallback_context_id,
            context_version=bound.context_version,
            context_source="internal_non_stateful_default",
            execution_mode="non_stateful",
            reason_codes=["ctx_precheck_compat_non_stateful"],
        )

    if turn_context.execution_mode == "stateful":
        if not turn_context.effective_context_id:
            raise StatefulContextRequiredError(message="stateful_turn_requires_effective_context")
    elif turn_context.effective_context_id is None:
        raise ImplicitContextForbiddenError(message="non_stateful_turn_requires_explicit_context_marker")

    effective_context_id = str(turn_context.effective_context_id or "").strip()
    if not effective_context_id:
        raise StatefulContextRequiredError(message="effective_context_id_empty")

    bound = read_bound_context_from_session(state)
    if bound is None:
        raise ContextMismatchError(message="session_context_not_bound", expected=effective_context_id, actual=None)

    if bound.context_id != effective_context_id:
        raise ContextMismatchError(
            message="session_bound_context_mismatch",
            expected=bound.context_id,
            actual=effective_context_id,
            entry_surface=turn_context.entry_surface,
            entrypoint=turn_context.entrypoint,
        )

    config_context_id = derive_config_context_id(config)
    if not config_context_id:
        raise InvalidConfigContextError(message="config_context_missing", expected=effective_context_id, actual=config_context_id)
    if config_context_id != effective_context_id:
        raise InvalidConfigContextError(
            message="config_effective_context_mismatch",
            expected=effective_context_id,
            actual=config_context_id,
            entry_surface=turn_context.entry_surface,
            entrypoint=turn_context.entrypoint,
        )

    resolved_for_prompts = resolve_context_for_prompts_dir(config.prompts_dir)
    if resolved_for_prompts is None or resolved_for_prompts.context_id != config_context_id:
        raise InvalidConfigContextError(
            message="config_prompts_dir_context_mismatch",
            expected=config_context_id,
            actual=resolved_for_prompts.context_id if resolved_for_prompts is not None else None,
            entry_surface=turn_context.entry_surface,
            entrypoint=turn_context.entrypoint,
        )

    reason_codes = ["ctx_precheck_ok"]
    # context_version is observability-only in this phase: it never blocks, but drift is traced.
    if turn_context.context_version and bound.context_version and turn_context.context_version != bound.context_version:
        reason_codes.append("ctx_context_version_drift_observed")

    return ValidatedTurnContext(
        effective_context_id=effective_context_id,
        session_bound_context_id=bound.context_id,
        config_context_id=config_context_id,
        trace_context_id=effective_context_id,
        context_version=bound.context_version,
        context_source=turn_context.context_source,
        execution_mode=turn_context.execution_mode,
        reason_codes=reason_codes,
    )
