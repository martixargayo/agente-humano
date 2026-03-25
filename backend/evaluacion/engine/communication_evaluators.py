from __future__ import annotations

from evaluacion.contracts.communication_models import CommunicationFeedbackInputBundleV1
from evaluacion.engine.communication_content_evaluator import evaluate_content_from_transcript


def evaluate_communication_content(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    return evaluate_content_from_transcript(bundle=bundle)


def evaluate_communication_delivery(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    speech_rate = bundle.audio_features.speech_rate_wpm
    return {
        'block_id': 'delivery',
        'title': 'Delivery',
        'status_visual': 'mejorable',
        'score_0_100': 52,
        'summary': 'El delivery se basa en métricas sintéticas mínimas; no representa todavía una evaluación acústica real.',
        'details': [
            f'Speech rate placeholder: {speech_rate} wpm.' if speech_rate is not None else 'Speech rate placeholder no disponible.',
            f'Pause segments placeholder: {len(bundle.audio_features.pause_segments)}.',
            bundle.audio_features.explanation,
        ],
    }


def evaluate_communication_visual_placeholder(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    return {
        'block_id': 'visual',
        'title': 'Visual placeholder',
        'status_visual': 'placeholder',
        'score_0_100': None,
        'summary': bundle.visual_features.summary,
        'details': [bundle.visual_features.explanation],
    }
