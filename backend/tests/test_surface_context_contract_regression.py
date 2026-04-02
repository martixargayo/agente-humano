from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interfaz_usuario import services as iu_services
from negociacion.optimizador import services as opt_services
from sessions.state import SESSIONS


def setup_function() -> None:
    SESSIONS.clear()


def test_interfaz_session_same_context_stays_ok() -> None:
    first = iu_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    second = iu_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    assert first["context_id"] == "baseline_current"
    assert second["context_id"] == "baseline_current"


def test_interfaz_session_context_switch_returns_409() -> None:
    iu_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    with pytest.raises(HTTPException) as exc:
        iu_services.ensure_session(user_id="u", session_id="s", context_id="sala_reuniones")
    assert exc.value.status_code == 409


def test_optimizer_session_same_context_stays_ok() -> None:
    first = opt_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    second = opt_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    assert first["base_context"]["context_id"] == "baseline_current"
    assert second["base_context"]["context_id"] == "baseline_current"


def test_optimizer_session_context_switch_returns_409() -> None:
    opt_services.ensure_session(user_id="u", session_id="s", context_id="baseline_current")
    with pytest.raises(HTTPException) as exc:
        opt_services.ensure_session(user_id="u", session_id="s", context_id="sala_reuniones")
    assert exc.value.status_code == 409
