from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluacion.contracts.communication_models import (
    CommunicationAudioFeaturesPlaceholder,
    CommunicationAudioFeaturesRealV1,
    CommunicationDeliveryEvaluationV1,
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


def _rule_based_delivery_evaluation(*, audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1) -> CommunicationDeliveryEvaluationV1:
    if isinstance(audio_features, CommunicationAudioFeaturesPlaceholder):
        return CommunicationDeliveryEvaluationV1(
            score_0_100=52,
            subscores={'fluency': 2, 'pause_control': 2, 'expressiveness': 2, 'stability': 3},
            evidence_metrics=[audio_features.explanation],
            observations=['No hay métricas acústicas reales disponibles todavía en esta ejecución.'],
            recommendations=['Verifica disponibilidad de audio para habilitar evaluación de delivery basada en señal real.'],
        )

    raw = audio_features.raw_metrics
    interp = audio_features.interpreted_metrics
    fluency = int(interp.fluency_1_5 or 3)
    pause_control = int(interp.pause_control_1_5 or 3)
    expressiveness = int(interp.expressiveness_1_5 or 3)
    stability = int(interp.stability_1_5 or 3)
    normalized = round(((fluency + pause_control + expressiveness + stability) / 20) * 100)

    evidence = [
        f'speech_rate_wpm={raw.speech_rate_wpm}',
        f'pause_ratio={raw.pause_ratio}',
        f'long_pauses_count={raw.long_pauses_count}',
        f'pitch_std_hz={raw.pitch_stats.std_hz}',
        f'energy_rms_std={raw.energy_stats.rms_std}',
    ]
    observations = [
        'El diagnóstico de delivery se basa en métricas acústicas reales extraídas de la señal.',
        f'Se detectaron {len(raw.pause_events)} pausas y un ratio de pausa de {raw.pause_ratio:.2f}.',
    ]
    if raw.long_pauses_count > 0:
        observations.append('Se observan pausas largas que pueden afectar continuidad.')
    if raw.pitch_stats.std_hz is not None and raw.pitch_stats.std_hz < 18:
        observations.append('La variabilidad tonal es baja, posible monotonía.')
    if raw.speech_rate_wpm is not None and raw.speech_rate_wpm > 190:
        observations.append('Ritmo de habla alto; podría dificultar claridad.')

    recommendations = [
        'Introduce micro-pausas cortas entre ideas para mantener fluidez sin cortes largos.',
        'Ajusta el ritmo para priorizar claridad en frases clave.',
        'Varía ligeramente la entonación en ideas principales para mejorar expresividad.',
    ]
    if 'low_voiced_ratio' in audio_features.quality_flags:
        recommendations.append('Revisa calidad de captura de audio; el tramo hablado útil parece limitado.')

    return CommunicationDeliveryEvaluationV1(
        score_0_100=max(0, min(100, int(normalized))),
        subscores={
            'fluency': max(1, min(5, fluency)),
            'pause_control': max(1, min(5, pause_control)),
            'expressiveness': max(1, min(5, expressiveness)),
            'stability': max(1, min(5, stability)),
        },
        evidence_metrics=evidence,
        observations=observations,
        recommendations=recommendations,
    )


def validate_delivery_eval_schema(raw_llm_output: dict[str, Any]) -> CommunicationDeliveryEvaluationV1:
    return CommunicationDeliveryEvaluationV1.model_validate(raw_llm_output)


def evaluate_delivery_from_audio_metrics(*, audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1, transcript_excerpt: str | None = None) -> CommunicationDeliveryEvaluationV1:
    _ = load_delivery_prompt_template()
    _ = build_delivery_llm_input(audio_features=audio_features, transcript_excerpt=transcript_excerpt)
    # Fase 2: se mantiene una interpretación determinista y trazable de métricas reales.
    # El hook para proveedor LLM queda acotado al contrato de entrada/salida sin romper compatibilidad.
    return _rule_based_delivery_evaluation(audio_features=audio_features)
