from __future__ import annotations

import json
import os
from pathlib import Path

import openai

from evaluacion.contracts.communication_models import (
    CommunicationGlobalSynthesisInputV1,
    CommunicationGlobalSynthesisLlmOutputV1,
    CommunicationGlobalSynthesisOutputV1,
)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / 'prompts' / 'communication_global_synthesis_prompt.txt'


def _load_global_synthesis_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding='utf-8')
    return 'Sintetiza score global, resumen corto y recomendaciones en JSON estricto.'


def _is_global_synthesis_llm_enabled() -> bool:
    raw = (os.getenv('COMM_SYNTHESIS_OPENAI_ENABLED') or '').strip().lower()
    return raw in {'1', 'true', 'yes', 'on'}


def _build_openai_client() -> openai.OpenAI:
    api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise RuntimeError('missing_openai_api_key')
    return openai.OpenAI(api_key=api_key)


def _build_synthesis_llm_payload(*, synthesis_input: CommunicationGlobalSynthesisInputV1) -> dict[str, object]:
    return {
        'evaluation_id': synthesis_input.evaluation_id,
        'content_evaluation': synthesis_input.content_evaluation,
        'delivery_evaluation': synthesis_input.delivery_evaluation,
        'visual_evaluation': synthesis_input.visual_evaluation,
        'evidence_summary': synthesis_input.evidence_summary,
    }


def _run_global_synthesis_llm_openai(*, prompt: str, payload: dict[str, object]) -> CommunicationGlobalSynthesisLlmOutputV1:
    client = _build_openai_client()
    response = client.responses.create(
        model=(os.getenv('COMM_SYNTHESIS_OPENAI_MODEL') or '').strip() or 'gpt-4.1-mini',
        input=[
            {'role': 'developer', 'content': prompt},
            {'role': 'user', 'content': f'BEGIN_INPUT_JSON\n{json.dumps(payload, ensure_ascii=False)}\nEND_INPUT_JSON'},
        ],
        text={
            'format': {
                'type': 'json_schema',
                'name': 'communication_global_synthesis_llm_output_v1',
                'schema': CommunicationGlobalSynthesisLlmOutputV1.model_json_schema(),
                'strict': True,
            }
        },
        store=False,
        timeout=20.0,
    )
    raw = getattr(response, 'output_text', '') or '{}'
    return CommunicationGlobalSynthesisLlmOutputV1.model_validate(json.loads(raw))


def _safe_score(payload: dict[str, object], default: int = 60) -> int:
    value = payload.get('score_0_100')
    if isinstance(value, int):
        return max(0, min(100, value))
    if isinstance(value, float):
        return max(0, min(100, int(round(value))))
    return default


def build_global_synthesis_input(
    *,
    evaluation_id: str,
    content_output: dict[str, object],
    delivery_output: dict[str, object],
    visual_output: dict[str, object],
) -> CommunicationGlobalSynthesisInputV1:
    evidence_summary = [
        f"content_score={_safe_score(content_output)} status={content_output.get('status_visual', 'mejorable')}",
        f"delivery_score={_safe_score(delivery_output)} status={delivery_output.get('status_visual', 'mejorable')}",
        f"visual_score={_safe_score(visual_output)} status={visual_output.get('status_visual', 'mejorable')}",
    ]
    for key, source in [('content', content_output), ('delivery', delivery_output), ('visual', visual_output)]:
        details = source.get('details', [])
        if isinstance(details, list):
            for detail in details[:2]:
                evidence_summary.append(f'{key}_detail={detail}')
    return CommunicationGlobalSynthesisInputV1(
        evaluation_id=evaluation_id,
        content_evaluation=content_output,
        delivery_evaluation=delivery_output,
        visual_evaluation=visual_output,
        evidence_summary=evidence_summary,
    )


def _derive_global_diagnosis(score: int) -> str:
    if score >= 85:
        return 'Comunicación sólida y consistente en contenido, delivery y presencia visual.'
    if score >= 70:
        return 'Buen desempeño general con oportunidades puntuales de mejora.'
    if score >= 55:
        return 'Desempeño intermedio: conviene reforzar prioridades clave para subir consistencia.'
    return 'Desempeño inicial: requiere un plan de mejora guiado en contenido, delivery y visual.'


def _rule_based_synthesize_global_communication_feedback(*, synthesis_input: CommunicationGlobalSynthesisInputV1) -> CommunicationGlobalSynthesisOutputV1:
    content = synthesis_input.content_evaluation
    delivery = synthesis_input.delivery_evaluation
    visual = synthesis_input.visual_evaluation

    content_score = _safe_score(content)
    delivery_score = _safe_score(delivery)
    visual_score = _safe_score(visual)

    weighted = (content_score * 0.45) + (delivery_score * 0.35) + (visual_score * 0.20)
    spread = max(content_score, delivery_score, visual_score) - min(content_score, delivery_score, visual_score)
    consistency_penalty = 10 if spread > 50 else 5 if spread > 35 else 0
    global_score = max(0, min(100, int(round(weighted - consistency_penalty))))

    strengths: list[str] = []
    improvements: list[str] = []
    consistency_notes: list[str] = []

    for label, payload, score in [
        ('contenido', content, content_score),
        ('delivery', delivery, delivery_score),
        ('visual', visual, visual_score),
    ]:
        summary = str(payload.get('summary') or f'Bloque {label} sin resumen explícito.')
        if score >= 75:
            strengths.append(f'{label}: {summary}')
        if score < 65:
            improvements.append(f'{label}: priorizar mejora (score={score}).')
        if payload.get('status_visual') == 'placeholder':
            consistency_notes.append(f'{label}: evaluación degradada por datos parciales/placeholder.')

    if spread > 35:
        consistency_notes.append('Se detecta dispersión entre bloques; priorizar equilibrio entre claridad, delivery y componente visual.')

    actions: list[str] = []
    for payload in (content, delivery, visual):
        recommendations = payload.get('recommendations', [])
        if isinstance(recommendations, list):
            for recommendation in recommendations:
                item = str(recommendation).strip()
                if item and item not in actions:
                    actions.append(item)
                if len(actions) >= 5:
                    break
        if len(actions) >= 5:
            break
    if not actions:
        actions = [
            'Define una apertura y cierre con mensaje central explícito.',
            'Ajusta ritmo y pausas para mejorar claridad.',
            'Revisa encuadre e iluminación antes de grabar.',
        ]

    if not strengths:
        strengths.append('Hay una base de avance identificable, aunque todavía sin fortaleza dominante consistente.')
    if not improvements:
        improvements.append('Mantener consistencia entre contenido, delivery y visual para sostener el rendimiento global.')

    friendly_summary = (
        f'Resultado global {global_score}/100. '
        f'Fortalezas destacadas: {min(len(strengths), 2)}. '
        f'Prioridades de mejora: {min(len(improvements), 2)}.'
    )

    return CommunicationGlobalSynthesisOutputV1(
        global_score_0_100=global_score,
        global_diagnosis=_derive_global_diagnosis(global_score),
        top_strengths=strengths[:3],
        priority_improvements=improvements[:3],
        action_plan=actions[:5],
        friendly_summary=friendly_summary,
        consistency_notes=consistency_notes[:4],
    )


def _map_llm_output_to_synthesis_output(
    *,
    synthesis_input: CommunicationGlobalSynthesisInputV1,
    llm_output: CommunicationGlobalSynthesisLlmOutputV1,
) -> CommunicationGlobalSynthesisOutputV1:
    content_score = _safe_score(synthesis_input.content_evaluation)
    delivery_score = _safe_score(synthesis_input.delivery_evaluation)
    visual_score = _safe_score(synthesis_input.visual_evaluation)
    spread = max(content_score, delivery_score, visual_score) - min(content_score, delivery_score, visual_score)

    top_strengths: list[str] = []
    priority_improvements: list[str] = []
    for label, payload, score in [
        ('contenido', synthesis_input.content_evaluation, content_score),
        ('delivery', synthesis_input.delivery_evaluation, delivery_score),
        ('visual', synthesis_input.visual_evaluation, visual_score),
    ]:
        summary = str(payload.get('summary') or f'Bloque {label} sin resumen explícito.')
        if score >= 75:
            top_strengths.append(f'{label}: {summary}')
        if score < 70:
            priority_improvements.append(f'{label}: reforzar este bloque para equilibrar el desempeño global.')

    consistency_notes: list[str] = []
    if spread > 35:
        consistency_notes.append('Se detecta dispersión entre bloques; conviene equilibrar contenido, delivery y visual.')

    action_plan = [f'{item.title}: {item.description}' for item in llm_output.recommendations]
    if not top_strengths:
        top_strengths.append('Hay una base de avance identificable, aunque todavía sin fortaleza dominante consistente.')
    if not priority_improvements and llm_output.score_global_100 < 90:
        priority_improvements.append('Refuerza la consistencia entre contenido, delivery y presencia visual para subir tu nota global.')

    return CommunicationGlobalSynthesisOutputV1(
        global_score_0_100=llm_output.score_global_100,
        global_diagnosis=_derive_global_diagnosis(llm_output.score_global_100),
        top_strengths=top_strengths[:3],
        priority_improvements=priority_improvements[:3],
        action_plan=action_plan[:4],
        friendly_summary=llm_output.summary_short_2_3_lines,
        consistency_notes=consistency_notes[:4],
    )


def synthesize_global_communication_feedback(*, synthesis_input: CommunicationGlobalSynthesisInputV1) -> CommunicationGlobalSynthesisOutputV1:
    if _is_global_synthesis_llm_enabled():
        prompt = _load_global_synthesis_prompt_template()
        payload = _build_synthesis_llm_payload(synthesis_input=synthesis_input)
        try:
            llm_output = _run_global_synthesis_llm_openai(prompt=prompt, payload=payload)
            return _map_llm_output_to_synthesis_output(synthesis_input=synthesis_input, llm_output=llm_output)
        except Exception:
            pass
    return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input)


def validate_synthesis_schema(raw_output: dict[str, object]) -> CommunicationGlobalSynthesisOutputV1:
    return CommunicationGlobalSynthesisOutputV1.model_validate(raw_output)
