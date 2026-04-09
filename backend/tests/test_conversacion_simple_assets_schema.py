from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import list_official_conversacion_simple_contexts
from conversacion_simple.state import parse_conversation_simple_brief_payload


def test_all_context_briefs_parse_with_runtime_parser() -> None:
    contexts = list_official_conversacion_simple_contexts()
    for context in contexts:
        payload = json.loads(context.conversation_brief_path.read_text(encoding="utf-8"))
        model = parse_conversation_simple_brief_payload(payload)
        assert model.model_dump(mode="json") == payload


def test_initial_contexts_are_json_objects() -> None:
    contexts = {c.context_id: c for c in list_official_conversacion_simple_contexts()}
    baseline = contexts["baseline"]
    sala = contexts["negociacion_sala_reuniones"]

    for path in (
        baseline.persona_path,
        baseline.conversation_brief_path,
        baseline.phase_cards_path,
        sala.persona_path,
        sala.conversation_brief_path,
        sala.phase_cards_path,
    ):
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
