from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..contexts import resolve_conversacion_simple_context, resolve_default_conversacion_simple_context

CONVERSATION_SIMPLE_MEMORY_KEY = "conversation_simple_canonical"
CONVERSATION_SIMPLE_RECENT_DIALOGUE_KEY = "conversation_simple_canonical_recent_dialogue"
CONVERSATION_SIMPLE_TRACES_KEY = "conversation_simple_canonical_traces"


class ConversationSimpleTurnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str = "conversacion_simple"
    memory_key: str = CONVERSATION_SIMPLE_MEMORY_KEY
    recent_dialogue_key: str = CONVERSATION_SIMPLE_RECENT_DIALOGUE_KEY
    traces_key: str = CONVERSATION_SIMPLE_TRACES_KEY
    context_id: str | None = None
    stateful: bool = False
    prompts_dir: str
    brain_model_target: str = "gpt-5.4"
    summarizer_model_target: str = "gpt-5.4-nano"
    brain_max_output_tokens: int = 1024
    context_limit_turns: int = 20
    keep_last_n_turns: int = 20
    recent_dialogue_short_max_messages: int = 8
    episodic_compaction_trigger_count: int = 30
    episodic_compaction_trigger_chars: int = 6000
    max_episodic_high_resolution_items: int = 24
    maintenance_retry_limit: int = 3
    compacted_summary_max_chars: int = 1600
    maintenance_force_failure: bool = False


def build_conversacion_simple_pipeline_config(*, context_id: str | None = None, stateful: bool = False) -> ConversationSimpleTurnConfig:
    resolved_context = resolve_conversacion_simple_context(context_id) if context_id else resolve_default_conversacion_simple_context()
    return ConversationSimpleTurnConfig(
        flow_id=resolved_context.flow_id,
        memory_key=CONVERSATION_SIMPLE_MEMORY_KEY,
        recent_dialogue_key=CONVERSATION_SIMPLE_RECENT_DIALOGUE_KEY,
        traces_key=CONVERSATION_SIMPLE_TRACES_KEY,
        context_id=resolved_context.context_id,
        stateful=stateful,
        prompts_dir=str(resolved_context.prompts_dir),
        brain_model_target="gpt-5.4",
        summarizer_model_target="gpt-5.4-nano",
        brain_max_output_tokens=1024,
        context_limit_turns=20,
        keep_last_n_turns=20,
        recent_dialogue_short_max_messages=8,
        episodic_compaction_trigger_count=30,
        episodic_compaction_trigger_chars=6000,
        max_episodic_high_resolution_items=24,
        maintenance_retry_limit=3,
        compacted_summary_max_chars=1600,
        maintenance_force_failure=False,
    )
