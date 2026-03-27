from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import openai

from evaluacion.contracts.communication_models import (
    CommunicationAudioFeaturesPlaceholder,
    CommunicationAudioFeaturesRealV1,
    CommunicationDeliveryEvaluationV1,
    CommunicationSpecializedDimensionEvalV1,
)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / 'prompts' / 'communication_delivery_evaluator_prompt.txt'


def build_delivery_llm_input(*, audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1, transcript_excerpt: str | None = None) -> dict[str, Any]:
    transcript_context = (transcript_excerpt or '').strip()
    if isinstance(audio_features, CommunicationAudioFeaturesPlaceholder):
        return {
            'mode': 'placeholder',
            'status': audio_features.status,
            'explanation': audio_features.explanation,
            'transcript_excerpt': transcript_context,
        }
    return {
        'mode': 'real',
        'status': audio_features.status,
        'raw_metrics': audio_features.raw_metrics.model_dump(mode='json'),
        'interpreted_metrics': audio_features.interpreted_metrics.model_dump(mode='json'),
        'quality_flags': list(audio_features.quality_flags),
        'provider_meta': dict(audio_features.provider_meta),
        'transcript_excerpt': transcript_context,
    }


def load_delivery_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding='utf-8')
    return (
        'Evalúa delivery a partir de métricas acústicas verificables. '
        'No inventes hechos fuera de raw_metrics. '
        'Devuelve JSON estricto con score_0_100, subscores, evidence_metrics, observations, recommendations.'
    )


def _score_to_label(score_1_5: int) -> str:
    return {
        1: 'bajo',
        2: 'medio-bajo',
        3: 'medio',
        4: 'medio-alto',
        5: 'alto',
    }.get(int(score_1_5), 'medio')


def _is_audio_llm_enabled() -> bool:
    raw = (os.getenv('COMM_AUDIO_OPENAI_ENABLED') or '').strip().lower()
    return raw in {'1', 'true', 'yes', 'on'}


def _build_openai_client() -> openai.OpenAI:
    api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise RuntimeError('missing_openai_api_key')
    return openai.OpenAI(api_key=api_key)


def _rule_based_specialized_delivery_eval(
    *,
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1,
) -> CommunicationSpecializedDimensionEvalV1:
    if isinstance(audio_features, CommunicationAudioFeaturesPlaceholder):
        return CommunicationSpecializedDimensionEvalV1(
            score_1_5=2,
            label='medio-bajo',
            reason_short='Tu audio no tiene evidencia suficiente para valorar bien tus pausas. Repite con mejor captura para recibir feedback más justo.',
        )

    interp = audio_features.interpreted_metrics
    pause_control = max(1, min(5, int(interp.pause_control_1_5 or 3)))
    expressiveness = max(1, min(5, int(interp.expressiveness_1_5 or 3)))
    adjusted_score = max(1, min(5, pause_control + (1 if expressiveness >= 4 else -1 if expressiveness <= 2 else 0)))
    if 'low_voiced_ratio' in audio_features.quality_flags:
        adjusted_score = max(1, adjusted_score - 1)

    reasons = {
        1: 'Tu patrón de pausas interrumpe la claridad y te resta control. Practica pausas cortas entre ideas para sonar más claro.',
        2: 'Tus pausas todavía son irregulares y eso complica el seguimiento. Gana control separando mejor tus ideas clave.',
        3: 'Tus pausas te permiten sostener el mensaje, pero con altibajos. Si haces pausas más consistentes, tu claridad subirá.',
        4: 'Tus pausas aportan buen control y hacen tu mensaje más claro. Para subir un nivel, afina la variación vocal en ideas clave.',
        5: 'Tus pausas son sólidas y sostienen muy bien la claridad. Mantén esa consistencia y cuida que la voz siga natural.',
    }
    return CommunicationSpecializedDimensionEvalV1(
        score_1_5=adjusted_score,
        label=_score_to_label(adjusted_score),
        reason_short=reasons.get(adjusted_score, reasons[3]),
    )


def _run_audio_specialized_eval_openai(
    *,
    prompt: str,
    payload: dict[str, Any],
) -> CommunicationSpecializedDimensionEvalV1:
    client = _build_openai_client()
    response = client.responses.create(
        model=(os.getenv('COMM_AUDIO_OPENAI_MODEL') or '').strip() or 'gpt-4.1-mini',
        input=[
            {'role': 'developer', 'content': prompt},
            {'role': 'user', 'content': f'BEGIN_INPUT_JSON\n{json.dumps(payload, ensure_ascii=False)}\nEND_INPUT_JSON'},
        ],
        text={
            'format': {
                'type': 'json_schema',
                'name': 'communication_specialized_dimension_eval_v1',
                'schema': CommunicationSpecializedDimensionEvalV1.model_json_schema(),
                'strict': True,
            }
        },
        store=False,
        timeout=20.0,
    )
    raw = getattr(response, 'output_text', '') or '{}'
    return CommunicationSpecializedDimensionEvalV1.model_validate(json.loads(raw))


def validate_delivery_eval_schema(raw_llm_output: dict[str, Any]) -> CommunicationDeliveryEvaluationV1:
    return CommunicationDeliveryEvaluationV1.model_validate(raw_llm_output)


def _map_specialized_to_delivery_eval(
    *,
    specialized_eval: CommunicationSpecializedDimensionEvalV1,
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1,
) -> CommunicationDeliveryEvaluationV1:
    if isinstance(audio_features, CommunicationAudioFeaturesPlaceholder):
        return CommunicationDeliveryEvaluationV1(
            score_0_100=specialized_eval.score_1_5 * 20,
            subscores={'fluency': 2, 'pause_control': specialized_eval.score_1_5, 'expressiveness': 2, 'stability': 2},
            evidence_metrics=[audio_features.explanation],
            observations=[specialized_eval.reason_short],
            recommendations=[specialized_eval.reason_short],
        )
    interp = audio_features.interpreted_metrics
    return CommunicationDeliveryEvaluationV1(
        score_0_100=specialized_eval.score_1_5 * 20,
        subscores={
            'fluency': max(1, min(5, int(interp.fluency_1_5 or specialized_eval.score_1_5))),
            'pause_control': max(1, min(5, int(interp.pause_control_1_5 or specialized_eval.score_1_5))),
            'expressiveness': max(1, min(5, int(interp.expressiveness_1_5 or 3))),
            'stability': max(1, min(5, int(interp.stability_1_5 or 3))),
        },
        evidence_metrics=[
            f'pause_events={len(audio_features.raw_metrics.pause_events)}',
            f'pause_ratio={audio_features.raw_metrics.pause_ratio:.2f}',
            f'long_pauses_count={audio_features.raw_metrics.long_pauses_count}',
        ],
        observations=[specialized_eval.reason_short],
        recommendations=[specialized_eval.reason_short],
    )


def evaluate_delivery_with_specialized_from_audio_metrics(
    *,
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1,
    transcript_excerpt: str | None = None,
) -> tuple[CommunicationDeliveryEvaluationV1, CommunicationSpecializedDimensionEvalV1]:
    prompt = load_delivery_prompt_template()
    payload = build_delivery_llm_input(audio_features=audio_features, transcript_excerpt=transcript_excerpt)
    specialized_eval: CommunicationSpecializedDimensionEvalV1
    if _is_audio_llm_enabled():
        try:
            specialized_eval = _run_audio_specialized_eval_openai(prompt=prompt, payload=payload)
        except Exception:
            specialized_eval = _rule_based_specialized_delivery_eval(audio_features=audio_features)
    else:
        specialized_eval = _rule_based_specialized_delivery_eval(audio_features=audio_features)
    return _map_specialized_to_delivery_eval(specialized_eval=specialized_eval, audio_features=audio_features), specialized_eval


def evaluate_delivery_from_audio_metrics(*, audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1, transcript_excerpt: str | None = None) -> CommunicationDeliveryEvaluationV1:
    evaluated, _ = evaluate_delivery_with_specialized_from_audio_metrics(audio_features=audio_features, transcript_excerpt=transcript_excerpt)
    return evaluated


def evaluate_delivery_specialized_from_audio_metrics(
    *,
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1,
    transcript_excerpt: str | None = None,
) -> CommunicationSpecializedDimensionEvalV1:
    _, specialized = evaluate_delivery_with_specialized_from_audio_metrics(audio_features=audio_features, transcript_excerpt=transcript_excerpt)
    return specialized
