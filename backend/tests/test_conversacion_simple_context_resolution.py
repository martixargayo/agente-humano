from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import (
    list_official_conversacion_simple_contexts,
    resolve_conversacion_simple_context,
    resolve_conversacion_simple_context_from_public_slug,
    resolve_default_conversacion_simple_context,
)
from conversacion_simple.contexts.resolver import ConversationSimpleContextResolutionError


def test_default_context_is_baseline() -> None:
    resolved = resolve_default_conversacion_simple_context()
    assert resolved.context_id == "baseline"
    assert resolved.flow_id == "conversacion_simple"


def test_list_official_contexts_contains_two_initial_contexts() -> None:
    contexts = {c.context_id for c in list_official_conversacion_simple_contexts()}
    assert contexts == {"baseline", "negociacion_sala_reuniones"}


def test_resolve_by_public_slug() -> None:
    resolved = resolve_conversacion_simple_context_from_public_slug("conversacion-simple")
    assert resolved.context_id == "baseline"


def test_resolve_invalid_context_raises() -> None:
    try:
        resolve_conversacion_simple_context("inexistente")
    except ConversationSimpleContextResolutionError:
        return
    raise AssertionError("expected ConversationSimpleContextResolutionError")
