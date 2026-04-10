from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import (
    list_official_conversacion_simple_contexts,
    resolve_conversacion_simple_context,
)
from conversacion_simple.contexts.public_mapping import (
    resolve_conversacion_simple_public_context_selection,
    resolve_conversacion_simple_public_slug_to_context_id,
)


CONTEXT_ID = "conversacion-dificil-periodista"
PUBLIC_SLUG = "conversacion-dificil-periodista"


def test_new_context_is_official_and_resolvable_by_context_id() -> None:
    resolved = resolve_conversacion_simple_context(CONTEXT_ID)
    assert resolved.context_id == CONTEXT_ID
    assert resolved.public_slug == PUBLIC_SLUG


def test_new_context_is_resolvable_by_public_slug() -> None:
    context_id = resolve_conversacion_simple_public_slug_to_context_id(PUBLIC_SLUG)
    selection = resolve_conversacion_simple_public_context_selection(public_slug=PUBLIC_SLUG)

    assert context_id == CONTEXT_ID
    assert selection.context_id == CONTEXT_ID
    assert selection.public_slug == PUBLIC_SLUG


def test_new_context_is_listed_in_official_contexts() -> None:
    context_ids = {context.context_id for context in list_official_conversacion_simple_contexts()}
    assert CONTEXT_ID in context_ids
