from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sessions.state import SessionState

from conversacion_simple.contexts import list_official_conversacion_simple_contexts, resolve_conversacion_simple_context
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.services import build_conversacion_simple_turn_context

from ..contexts import list_official_negotiation_contexts, resolve_negotiation_context
from ..orchestration.flow_config import build_negotiation_pipeline_config
from ..orchestration.turn_contract import TurnEntryContract
from ..services.turn_context_factory import build_optimizador_turn_context


@dataclass(frozen=True)
class FlowCapabilities:
    supports_node_level_prompt_diff: bool
    supports_cross_flow_compare: bool
    supports_guardrails_breakdown: bool
    supports_single_node_trace: bool
    supports_multi_node_trace: bool


class FlowOptimizerAdapter(Protocol):
    flow_id: str

    def capabilities(self) -> FlowCapabilities: ...

    def list_contexts(self) -> list[dict[str, Any]]: ...

    def list_prompts(self, *, context_id: str | None) -> list[dict[str, str]]: ...

    def run_sandbox_turn(
        self,
        *,
        state: SessionState,
        user_message: str,
        context_id: str,
        overrides_applied: bool,
        new_conversation: bool,
        clone_used: bool,
        base_config: Any,
    ) -> tuple[str, SessionState, dict[str, Any]]: ...


class NegotiacionOptimizerAdapter:
    flow_id = "negociacion"

    def capabilities(self) -> FlowCapabilities:
        return FlowCapabilities(
            supports_node_level_prompt_diff=True,
            supports_cross_flow_compare=False,
            supports_guardrails_breakdown=True,
            supports_single_node_trace=False,
            supports_multi_node_trace=True,
        )

    def list_contexts(self) -> list[dict[str, Any]]:
        return [
            {
                "flow_id": ctx.flow_id,
                "context_id": ctx.context_id,
                "context_version": ctx.context_version,
                "public_slug": ctx.public_slug,
                "prompts_dir": str(ctx.prompts_dir),
                "resolution_source": ctx.resolution_source,
            }
            for ctx in list_official_negotiation_contexts()
        ]

    def list_prompts(self, *, context_id: str | None) -> list[dict[str, str]]:
        from .prompts_bridge import list_prompts as negotiation_prompts

        return negotiation_prompts(context_id)

    def run_sandbox_turn(
        self,
        *,
        state: SessionState,
        user_message: str,
        context_id: str,
        overrides_applied: bool,
        new_conversation: bool,
        clone_used: bool,
        base_config: Any,
    ) -> tuple[str, SessionState, dict[str, Any]]:
        turn_context = build_optimizador_turn_context(
            state=state,
            entrypoint="/api/optimizador/sandbox/turn",
            requested_context_id=context_id,
        )
        from . import services as optimizer_services

        return optimizer_services.execute_turn_with_contract(
            state=state,
            user_message=user_message,
            config=base_config,
            contract=TurnEntryContract(
                entry_surface="optimizador",
                entrypoint="/api/optimizador/sandbox/turn",
                overrides_applied=overrides_applied,
                optimizer_wrapper_used=True,
                new_conversation=new_conversation,
                clone_used=clone_used,
            ),
            turn_context=turn_context,
        )


class ConversacionSimpleOptimizerAdapter:
    flow_id = "conversacion_simple"

    def capabilities(self) -> FlowCapabilities:
        return FlowCapabilities(
            supports_node_level_prompt_diff=False,
            supports_cross_flow_compare=False,
            supports_guardrails_breakdown=False,
            supports_single_node_trace=True,
            supports_multi_node_trace=False,
        )

    def list_contexts(self) -> list[dict[str, Any]]:
        return [
            {
                "flow_id": ctx.flow_id,
                "context_id": ctx.context_id,
                "context_version": ctx.context_version,
                "public_slug": ctx.public_slug,
                "prompts_dir": str(ctx.prompts_dir),
                "resolution_source": ctx.resolution_source,
            }
            for ctx in list_official_conversacion_simple_contexts()
        ]

    def list_prompts(self, *, context_id: str | None) -> list[dict[str, str]]:
        resolved = resolve_conversacion_simple_context(context_id)
        prompt_path = resolved.prompts_dir / "brain_prompt.txt"
        return [
            {
                "node": "brain",
                "file": str(prompt_path),
                "base_text": prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "",
                "prompt_version": "brain_base",
            }
        ]

    def run_sandbox_turn(
        self,
        *,
        state: SessionState,
        user_message: str,
        context_id: str,
        overrides_applied: bool,
        new_conversation: bool,
        clone_used: bool,
        base_config: Any,
    ) -> tuple[str, SessionState, dict[str, Any]]:
        _ = (overrides_applied, clone_used)
        turn_context = build_conversacion_simple_turn_context(
            state=state,
            entrypoint="/api/optimizador/sandbox/turn",
            requested_context_id=context_id,
        )
        from . import services as optimizer_services

        reply, updated, cs_meta = optimizer_services.run_conversacion_simple_turn(
            state=state,
            user_message=user_message,
            config=base_config,
            turn_context=turn_context,
        )
        return reply, updated, {
            "entry_contract": {
                "entry_surface": "optimizador",
                "entrypoint": "/api/optimizador/sandbox/turn",
                "overrides_applied": overrides_applied,
                "optimizer_wrapper_used": True,
                "new_conversation": new_conversation,
                "clone_used": clone_used,
            },
            "latest_turn_id": cs_meta.get("turn_id"),
        }


_ADAPTERS = {
    "negociacion": NegotiacionOptimizerAdapter(),
    "conversacion_simple": ConversacionSimpleOptimizerAdapter(),
}


def get_adapter(flow_id: str) -> FlowOptimizerAdapter:
    if flow_id not in _ADAPTERS:
        raise ValueError(f"unsupported_flow_id:{flow_id}")
    return _ADAPTERS[flow_id]


def list_supported_flow_ids() -> list[str]:
    return sorted(_ADAPTERS.keys())
