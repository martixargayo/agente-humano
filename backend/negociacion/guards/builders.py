from __future__ import annotations

from ..nodes.executor_node import ExecutorOutput


def build_input_block_response() -> str:
    return "No puedo continuar con ese mensaje tal como está. ¿Puedes reformularlo de forma segura y concreta?"


def build_output_rewrite_response() -> str:
    return "Prefiero responder con cautela para mantener seguridad y precisión. Si quieres, lo reformulo en términos generales."


def build_output_block_response() -> str:
    return "No puedo dar esa salida en este momento. Puedo ayudarte con una alternativa segura y general."


def apply_safe_output(executor_output: ExecutorOutput, *, rewritten_text: str, status: str = "clarify", refusal_reason: str = "guardrail_enforced") -> ExecutorOutput:
    return executor_output.model_copy(update={"spoken_text": rewritten_text, "status": status, "refusal_reason": refusal_reason})
