from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts.public_mapping import (
    ConversationSimplePublicConflictError,
    resolve_conversacion_simple_public_context_selection,
)


def test_public_mapping_default_selection() -> None:
    selection = resolve_conversacion_simple_public_context_selection()
    assert selection.context_id == "baseline"


def test_public_mapping_conflict_raises() -> None:
    with pytest.raises(ConversationSimplePublicConflictError):
        resolve_conversacion_simple_public_context_selection(
            context_id="baseline",
            public_slug="conversacion-simple-sala-reuniones",
        )
