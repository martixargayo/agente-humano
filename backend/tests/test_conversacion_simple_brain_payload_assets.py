from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import resolve_conversacion_simple_context
from conversacion_simple.nodes import DialogueMessage, TraceMeta
from conversacion_simple.orchestration.pipeline import _build_user_turn, build_brain_input, build_brain_messages
from conversacion_simple.state import build_default_conversation_simple_canonical_state
from negociacion.state.shared_types import ThreadMode


def _extract_brain_input_json(user_message_content: str) -> dict:
    start_token = "<brain_input_json>\n"
    end_token = "\n</brain_input_json>"
    start = user_message_content.index(start_token) + len(start_token)
    end = user_message_content.index(end_token)
    return json.loads(user_message_content[start:end])


def test_brain_payload_includes_phase_cards_and_compacted_summary() -> None:
    context = resolve_conversacion_simple_context("baseline")
    canonical_state = build_default_conversation_simple_canonical_state(
        session_id="s_payload",
        user_id="u_payload",
        thread_mode=ThreadMode.conversation,
        context_id=context.context_id,
    )
    canonical_state.memory_compacted_summary = "resumen compacto acumulado"
    trace_meta = TraceMeta(
        turn_id="turn_payload",
        prompt_version="brain_v1",
        schema_version="brain_input.v1",
        model_target="gpt-5-nano",
    )
    brain_input = build_brain_input(
        canonical_state=canonical_state,
        recent_dialogue=[DialogueMessage(role="user", text="hola")],
        user_turn=_build_user_turn("quiero negociar", "2026-04-08T00:00:00Z"),
        trace_meta=trace_meta,
    )
    brain_prompt = (context.prompts_dir / "brain_prompt.txt").read_text(encoding="utf-8").strip()
    messages = build_brain_messages(brain_prompt, brain_input)

    assert messages[0]["role"] == "developer"
    assert messages[0]["content"] == brain_prompt

    parsed = _extract_brain_input_json(messages[1]["content"])
    assert "conversation_brief" in parsed
    assert "persona" in parsed
    assert "phase_cards" in parsed
    assert parsed["phase_cards"]["phase_cards"]["apertura"]["phase"] == "apertura"
    assert parsed["memory_compacted_summary"] == "resumen compacto acumulado"
    assert "recent_dialogue_short" in parsed
    assert "user_turn" in parsed
