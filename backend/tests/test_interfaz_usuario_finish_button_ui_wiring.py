from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


APP_JS = ROOT / "interfaz_usuario_app" / "app.js"


def _source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_finish_button_visual_state_uses_arm_flag_for_highlight() -> None:
    src = _source()
    assert "function updateFinishNegotiationButton()" in src
    assert "ui.finishNegotiationBtn.classList.toggle('is-highlighted', finishButtonArmed);" in src


def test_finish_button_arming_is_latched_in_frontend_wiring() -> None:
    src = _source()
    assert "function armFinishButton(nextArmed)" in src
    assert "finishButtonArmed = finishButtonArmed || Boolean(nextArmed);" in src
    assert "if (!wasArmed && finishButtonArmed) startFinishButtonAttentionPulse();" in src


def test_finish_button_false_path_clears_attention_state() -> None:
    src = _source()
    assert "if (!finishButtonArmed) setFinishButtonAttentionActive(false);" in src


def test_turn_response_wires_backend_finish_button_flag_into_ui() -> None:
    src = _source()
    assert "const out = await api('/negociacion/turn'" in src
    assert "armFinishButton(out.finish_button_armed);" in src


def test_finish_confirm_flow_and_evaluation_wiring_stays_guarded() -> None:
    src = _source()
    assert "$('finishConfirmBtn').onclick = async () => {" in src
    assert "if (!canFinalizeConversation() || getActiveSessionBusyState()) return;" in src
    assert "await startFeedbackEvaluation();" in src
