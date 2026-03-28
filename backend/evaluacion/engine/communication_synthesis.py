from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import openai

from evaluacion.contracts.communication_models import (
    CommunicationGlobalSynthesisInputV1,
    CommunicationGlobalSynthesisLlmOutputV1,
    CommunicationGlobalSynthesisMetaV1,
)
from evaluacion.engine.communication_activation_policy import get_communication_activation_policy
from evaluacion.engine.communication_llm_models import get_global_synthesis_llm_model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / 'prompts' / 'communication_global_synthesis_prompt.txt'
_LOGGER = logging.getLogger(__name__)


def _load_global_synthesis_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding='utf-8')
    return 'Sintetiza score global, resumen corto y recomendaciones en JSON estricto.'


def _is_global_synthesis_llm_enabled() -> bool:
    policy = get_communication_activation_policy()
    return policy.global_synthesis_mode == 'llm'


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
        model=get_global_synthesis_llm_model(),
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


def _normalize_single_paragraph(text: str) -> str:
    chunks = [chunk.strip() for chunk in text.replace('\r', '\n').split('\n') if chunk.strip()]
    normalized = ' '.join(chunks)
    return normalized or 'Tu evaluación ya está disponible y resume tu desempeño global con acciones concretas de mejora.'


def _rule_based_synthesize_global_communication_feedback(*, synthesis_input: CommunicationGlobalSynthesisInputV1) -> CommunicationGlobalSynthesisLlmOutputV1:
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
    placeholder_branches = [
        branch_name
        for branch_name, payload in (
            ('contenido', content),
            ('delivery', delivery),
            ('visual', visual),
        )
        if str(payload.get('status_visual') or '') == 'placeholder'
    ]
    low_signal_mode = len(placeholder_branches) >= 2

    strengths: list[str] = []
    improvements: list[str] = []
    recommendations_payload: list[dict[str, str]] = []
    for payload in (content, delivery, visual):
        recommendations = payload.get('recommendations', [])
        if isinstance(recommendations, list):
            for recommendation in recommendations:
                item = str(recommendation).strip()
                if item and all(existing['description'] != item for existing in recommendations_payload):
                    recommendations_payload.append({
                        'title': f'Prioridad {len(recommendations_payload) + 1}',
                        'description': item,
                    })
                if len(recommendations_payload) >= 4:
                    break
        if len(recommendations_payload) >= 4:
            break

    for label, payload, score in [
        ('contenido', synthesis_input.content_evaluation, content_score),
        ('delivery', synthesis_input.delivery_evaluation, delivery_score),
        ('visual', synthesis_input.visual_evaluation, visual_score),
    ]:
        summary = str(payload.get('summary') or f'Bloque {label} sin resumen explícito.')
        if score >= 75:
            strengths.append(f'{label}: {summary}')
        if score < 70:
            improvements.append(f'{label}: reforzar este bloque para equilibrar el desempeño global.')

    score_reason = 'Tu desempeño global es consistente en los tres bloques principales.'
    if spread > 35:
        score_reason = 'Tu desempeño global es irregular entre bloques y eso reduce la nota final.'
    elif improvements:
        score_reason = 'Tu desempeño global muestra avances, pero todavía hay áreas claras para reforzar.'
    strengths_clause = f' Tu punto más fuerte ahora es {strengths[0]}.' if strengths else ''
    improve_clause = f' Prioriza {improvements[0]}.' if improvements else ''
    summary = _normalize_single_paragraph(
        f'Has obtenido {global_score}/100. {score_reason}{strengths_clause}{improve_clause}'
    )
    if low_signal_mode:
        summary = _normalize_single_paragraph(
            f'{summary} Esta nota es orientativa porque faltó señal real en: {", ".join(placeholder_branches)}.'
        )
        recommendations_payload.insert(0, {
            'title': 'Mejora la captura real',
            'description': f'Para obtener un diagnóstico más fiable, repite la evaluación con señal real en: {", ".join(placeholder_branches)}.',
        })

    return CommunicationGlobalSynthesisLlmOutputV1(
        score_global_100=global_score,
        summary_short_2_3_lines=summary,
        recommendations=recommendations_payload[:4],
    )


def _finalize_llm_output(output: CommunicationGlobalSynthesisLlmOutputV1) -> CommunicationGlobalSynthesisLlmOutputV1:
    return CommunicationGlobalSynthesisLlmOutputV1(
        score_global_100=output.score_global_100,
        summary_short_2_3_lines=_normalize_single_paragraph(output.summary_short_2_3_lines),
        recommendations=output.recommendations[:4],
    )


def synthesize_global_communication_feedback(*, synthesis_input: CommunicationGlobalSynthesisInputV1) -> tuple[CommunicationGlobalSynthesisLlmOutputV1, CommunicationGlobalSynthesisMetaV1]:
    if not _is_global_synthesis_llm_enabled():
        _LOGGER.info('communication_global_synthesis fallback=disabled_policy evaluation_id=%s', synthesis_input.evaluation_id)
        return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input), CommunicationGlobalSynthesisMetaV1(
            mode='fallback',
            fallback_reason='disabled_policy',
        )
    try:
        prompt = _load_global_synthesis_prompt_template()
        payload = _build_synthesis_llm_payload(synthesis_input=synthesis_input)
        llm_output = _run_global_synthesis_llm_openai(prompt=prompt, payload=payload)
        _LOGGER.info('communication_global_synthesis mode=llm evaluation_id=%s', synthesis_input.evaluation_id)
        return _finalize_llm_output(llm_output), CommunicationGlobalSynthesisMetaV1(mode='llm')
    except RuntimeError as exc:
        reason = 'missing_openai_api_key' if str(exc) == 'missing_openai_api_key' else 'unexpected_error'
        _LOGGER.warning(
            'communication_global_synthesis fallback=%s evaluation_id=%s detail=%s',
            reason,
            synthesis_input.evaluation_id,
            str(exc),
        )
        return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input), CommunicationGlobalSynthesisMetaV1(
            mode='fallback',
            fallback_reason=reason,
            detail=str(exc),
        )
    except ValueError as exc:
        _LOGGER.warning(
            'communication_global_synthesis fallback=schema_validation_error evaluation_id=%s detail=%s',
            synthesis_input.evaluation_id,
            str(exc),
        )
        return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input), CommunicationGlobalSynthesisMetaV1(
            mode='fallback',
            fallback_reason='schema_validation_error',
            detail=str(exc),
        )
    except openai.OpenAIError as exc:
        _LOGGER.warning(
            'communication_global_synthesis fallback=openai_error evaluation_id=%s detail=%s',
            synthesis_input.evaluation_id,
            str(exc),
        )
        return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input), CommunicationGlobalSynthesisMetaV1(
            mode='fallback',
            fallback_reason='openai_error',
            detail=str(exc),
        )
    except Exception as exc:
        _LOGGER.exception('communication_global_synthesis fallback=unexpected_error evaluation_id=%s', synthesis_input.evaluation_id)
        return _rule_based_synthesize_global_communication_feedback(synthesis_input=synthesis_input), CommunicationGlobalSynthesisMetaV1(
            mode='fallback',
            fallback_reason='unexpected_error',
            detail=str(exc),
        )


def validate_synthesis_schema(raw_output: dict[str, object]) -> CommunicationGlobalSynthesisLlmOutputV1:
    return CommunicationGlobalSynthesisLlmOutputV1.model_validate(raw_output)
