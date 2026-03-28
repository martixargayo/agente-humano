from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import openai

from evaluacion.contracts.communication_models import (
    CommunicationContentAidaBlockEvalV1,
    CommunicationContentAidaEvalV1,
    CommunicationFeedbackInputBundleV1,
)
from evaluacion.engine.communication_activation_policy import get_communication_activation_policy
from evaluacion.engine.communication_llm_models import get_content_llm_model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / 'prompts' / 'communication_content_evaluator_prompt.txt'
_RUBRIC_PATH = Path(__file__).resolve().parents[1] / 'prompts' / 'communication_content_aida_rubric.json'


def _load_content_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding='utf-8')
    return 'Evalúa contenido AIDA con salida JSON estricta.'


def _load_content_aida_rubric() -> dict[str, object]:
    if _RUBRIC_PATH.exists():
        return json.loads(_RUBRIC_PATH.read_text(encoding='utf-8'))
    return {
        'schema_version': 'communication_content_aida_rubric.v1',
        'dimension': 'contenido',
        'framework': 'AIDA',
        'score_scale': {'1': 'mal', '2': 'mejorable', '3': 'correcto'},
        'global_guide': {'core_principle': 'Evalúa presencia y función de atención, interés, desarrollo y acción.'},
        'blocks': {},
    }


def _build_content_llm_input(*, bundle: CommunicationFeedbackInputBundleV1, content_rubric: dict[str, object]) -> dict[str, object]:
    transcript = bundle.transcript
    return {
        'evaluation_id': bundle.evaluation_id,
        'transcript': {
            'status': getattr(transcript, 'status', 'unknown'),
            'language': getattr(transcript, 'language', 'es'),
            'full_text': transcript.full_text,
            'segments': [segment.model_dump(mode='json') for segment in transcript.segments[:12]],
        },
        'content_rubric': content_rubric,
    }


def _is_content_llm_enabled() -> bool:
    policy = get_communication_activation_policy()
    return policy.content_mode == 'llm'


def _build_openai_client() -> openai.OpenAI:
    api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise RuntimeError('missing_openai_api_key')
    return openai.OpenAI(api_key=api_key)


def _run_content_llm_openai(*, prompt: str, payload: dict[str, object]) -> CommunicationContentAidaEvalV1:
    client = _build_openai_client()
    response = client.responses.create(
        model=get_content_llm_model(),
        input=[
            {'role': 'developer', 'content': prompt},
            {'role': 'user', 'content': f'BEGIN_INPUT_JSON\n{json.dumps(payload, ensure_ascii=False)}\nEND_INPUT_JSON'},
        ],
        text={
            'format': {
                'type': 'json_schema',
                'name': 'communication_content_aida_eval_v1',
                'schema': CommunicationContentAidaEvalV1.model_json_schema(),
                'strict': True,
            }
        },
        store=False,
        timeout=20.0,
    )
    raw = getattr(response, 'output_text', '') or '{}'
    return CommunicationContentAidaEvalV1.model_validate(json.loads(raw))


def _label_for_score(score_1_3: int) -> str:
    return {1: 'mal', 2: 'mejorable', 3: 'correcto'}.get(score_1_3, 'mejorable')


def _block(score_1_3: int, reason_short: str) -> CommunicationContentAidaBlockEvalV1:
    return CommunicationContentAidaBlockEvalV1(
        score_1_3=max(1, min(3, int(score_1_3))),
        label=_label_for_score(max(1, min(3, int(score_1_3)))),
        reason_short=reason_short,
    )


def _rule_based_content_eval(*, transcript_text: str, segment_count: int) -> CommunicationContentAidaEvalV1:
    text = transcript_text.strip()
    words = [item for item in text.replace('\n', ' ').split(' ') if item]
    word_count = len(words)
    prefix = ' '.join(words[:25]).lower()
    lowered = text.lower()

    attention = 2 if any(token in prefix for token in ['?', 'imagina', 'hoy', 'te has']) else 1
    if word_count > 70:
        attention = min(3, attention + 1)

    interest = 1
    if any(token in lowered for token in ['te ayuda', 'beneficio', 'problema', 'necesidad', 'importa']):
        interest = 2
    if any(token in lowered for token in ['para ti', 'te permite', 'te sirve']):
        interest = min(3, interest + 1)

    development = 1
    if word_count >= 40:
        development = 2
    if word_count >= 90 and segment_count >= 2:
        development = 3

    action = 1
    if any(token in lowered for token in ['en resumen', 'para terminar', 'conclu', 'te invito', 'prueba', 'haz']):
        action = 2
    if lowered.endswith('.') and any(token in lowered[-200:] for token in ['recuerda', 'empieza', 'aplica', 'actúa']):
        action = min(3, action + 1)

    return CommunicationContentAidaEvalV1(
        attention=_block(attention, 'Tu inicio necesita captar más atención desde la primera idea para enganchar mejor.'),
        interest=_block(interest, 'Puedes conectar más con por qué este tema importa a quien te escucha.'),
        development=_block(development, 'Tu desarrollo puede ganar claridad y orden para que el mensaje se entienda mejor.'),
        action=_block(action, 'Tu cierre puede orientar con más intención hacia un siguiente paso claro.'),
    )


def _map_aida_eval_to_content_output(
    *,
    bundle: CommunicationFeedbackInputBundleV1,
    aida_eval: CommunicationContentAidaEvalV1,
) -> dict[str, Any]:
    transcript = bundle.transcript
    transcript_text = (transcript.full_text or '').strip()
    words = [item for item in transcript_text.replace('\n', ' ').split(' ') if item]
    word_count = len(words)
    segment_count = len(transcript.segments)
    avg_score = (
        aida_eval.attention.score_1_3
        + aida_eval.interest.score_1_3
        + aida_eval.development.score_1_3
        + aida_eval.action.score_1_3
    ) / 4.0
    score_0_100 = max(55, int(round((avg_score / 3.0) * 100)))
    status = 'correcto' if score_0_100 >= 75 else 'mejorable'

    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []
    for block_name, block in (
        ('Atención', aida_eval.attention),
        ('Interés', aida_eval.interest),
        ('Desarrollo', aida_eval.development),
        ('Acción', aida_eval.action),
    ):
        if block.score_1_3 == 3:
            strengths.append(f'{block_name}: {block.reason_short}')
        else:
            weaknesses.append(f'{block_name}: {block.reason_short}')
            recommendations.append(f'{block_name}: {block.reason_short}')

    return {
        'block_id': 'contenido',
        'title': 'Contenido',
        'status_visual': status,
        'score_0_100': score_0_100,
        'summary': f'Evaluación AIDA de contenido basada en transcripción real ({word_count} palabras, {segment_count} segmentos).',
        'details': [
            f'Atención: {aida_eval.attention.reason_short}',
            f'Interés: {aida_eval.interest.reason_short}',
            f'Desarrollo: {aida_eval.development.reason_short}',
            f'Acción: {aida_eval.action.reason_short}',
        ],
        'strengths': strengths,
        'weaknesses': weaknesses,
        'recommendations': recommendations or ['Tu contenido está bien resuelto: mantén el recorrido AIDA con esta consistencia.'],
        'evidence_segments': [
            {
                'segment_index': segment.segment_index,
                'start_ms': segment.start_ms,
                'end_ms': segment.end_ms,
                'text_excerpt': segment.text[:160],
            }
            for segment in transcript.segments[:3]
        ],
        'llm_specialized_evaluation': aida_eval.model_dump(mode='json'),
    }


def evaluate_content_from_transcript(*, bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]:
    transcript_text = (bundle.transcript.full_text or '').strip()
    segment_count = len(bundle.transcript.segments)
    prompt = _load_content_prompt_template()
    content_rubric = _load_content_aida_rubric()
    payload = _build_content_llm_input(bundle=bundle, content_rubric=content_rubric)
    llm_mode = 'rule_based'
    fallback_reason: str | None = None

    if _is_content_llm_enabled():
        try:
            aida_eval = _run_content_llm_openai(prompt=prompt, payload=payload)
            llm_mode = 'llm'
        except RuntimeError as exc:
            aida_eval = _rule_based_content_eval(transcript_text=transcript_text, segment_count=segment_count)
            llm_mode = 'fallback'
            fallback_reason = 'missing_openai_api_key' if str(exc) == 'missing_openai_api_key' else 'openai_error'
        except ValueError:
            aida_eval = _rule_based_content_eval(transcript_text=transcript_text, segment_count=segment_count)
            llm_mode = 'fallback'
            fallback_reason = 'schema_validation_error'
        except openai.OpenAIError:
            aida_eval = _rule_based_content_eval(transcript_text=transcript_text, segment_count=segment_count)
            llm_mode = 'fallback'
            fallback_reason = 'openai_error'
        except Exception:
            aida_eval = _rule_based_content_eval(transcript_text=transcript_text, segment_count=segment_count)
            llm_mode = 'fallback'
            fallback_reason = 'unexpected_error'
    else:
        aida_eval = _rule_based_content_eval(transcript_text=transcript_text, segment_count=segment_count)
        llm_mode = 'fallback'
        fallback_reason = 'disabled_policy'

    output = _map_aida_eval_to_content_output(bundle=bundle, aida_eval=aida_eval)
    transcript_status = getattr(bundle.transcript, 'status', None)
    transcript_provider = getattr(bundle.transcript, 'provider', None)
    output['summary'] = (
        f'Evaluación AIDA de contenido basada en transcripción real ({len([item for item in transcript_text.split() if item])} palabras, {segment_count} segmentos).'
        if transcript_status == 'ready'
        else f'Evaluación AIDA de contenido degradada por ausencia de transcripción real ({segment_count} segmentos placeholder).'
    )
    if transcript_status != 'ready':
        output['status_visual'] = 'placeholder'
        output['details'].append('Transcripción no disponible en modo real; se usó señal placeholder para contenido.')
    else:
        output['details'].append(f'Proveedor STT: {transcript_provider or "desconocido"}.')
    output['runtime_meta'] = {
        'branch_id': 'contenido',
        'mode': ('placeholder' if transcript_status != 'ready' else ('llm' if llm_mode == 'llm' else 'fallback' if llm_mode == 'fallback' else 'rule_based')),
        'reason': ('transcript_placeholder' if transcript_status != 'ready' else fallback_reason),
        'detail': (None if transcript_status == 'ready' else 'content_eval_without_real_transcript'),
    }
    return output
