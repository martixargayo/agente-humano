from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BASELINE_PROMPT = ROOT / "conversacion_simple" / "contexts" / "baseline" / "prompts" / "brain_prompt.txt"
SALA_PROMPT = ROOT / "conversacion_simple" / "contexts" / "negociacion_sala_reuniones" / "prompts" / "brain_prompt.txt"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_baseline_prompt_contains_explicit_closure_readiness_guardrails() -> None:
    text = _read(BASELINE_PROMPT)
    assert "closure_readiness" in text
    assert "no es un objetivo del turno" in text
    assert "ante duda usa `not_ready`" in text or "ante duda usa not_ready" in text
    assert "aceptado de forma suficientemente explícita por ambas partes" in text
    assert "propuesta unilateral" in text


def test_sala_prompt_contains_anti_bias_and_conservative_activation_rules() -> None:
    text = _read(SALA_PROMPT)
    assert "closure_readiness" in text
    assert "esta señal es observacional, no teleológica" in text
    assert "no es objetivo del turno" in text
    assert "ante duda, usa `not_ready`" in text or "ante duda, usa not_ready" in text
    assert "aceptación mutua clara" in text
    assert "solo haya propuesta, acercamiento o buena predisposición" in text
