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
        assert model.schema_version == "conversation_brief.v1"


def test_initial_contexts_are_structurally_equivalent() -> None:
    contexts = {c.context_id: c for c in list_official_conversacion_simple_contexts()}
    baseline = contexts["baseline"]
    sala = contexts["negociacion_sala_reuniones"]

    assert json.loads(baseline.persona_path.read_text(encoding="utf-8")) == json.loads(sala.persona_path.read_text(encoding="utf-8"))
    assert json.loads(baseline.conversation_brief_path.read_text(encoding="utf-8")) == json.loads(sala.conversation_brief_path.read_text(encoding="utf-8"))
    assert json.loads(baseline.phase_cards_path.read_text(encoding="utf-8")) == json.loads(sala.phase_cards_path.read_text(encoding="utf-8"))
