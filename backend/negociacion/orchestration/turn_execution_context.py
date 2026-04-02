from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExecutionMode = Literal["stateful", "non_stateful"]
ContextSource = Literal[
    "interfaz_usuario_bootstrap",
    "interfaz_usuario_session_bound",
    "optimizador_session_bound",
    "api_negociar_explicit",
    "internal_non_stateful_default",
    "internal_explicit",
]


@dataclass(frozen=True)
class TurnExecutionContext:
    user_id: str | None
    session_id: str | None
    execution_mode: ExecutionMode
    effective_context_id: str | None
    requested_context_id: str | None
    session_bound_context_id: str | None
    context_source: ContextSource
    entry_surface: str
    entrypoint: str
    context_version: str | None = None
    flow_id: str | None = None
