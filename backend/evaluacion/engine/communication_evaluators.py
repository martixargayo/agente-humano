from __future__ import annotations

from evaluacion.contracts.communication_models import CommunicationFeedbackInputBundleV1
from evaluacion.engine.communication_content_evaluator import evaluate_content_from_transcript
from evaluacion.engine.communication_delivery_evaluator import evaluate_delivery_from_audio_metrics


def evaluate_communication_content(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    return evaluate_content_from_transcript(bundle=bundle)


def evaluate_communication_delivery(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    transcript_excerpt = bundle.transcript.segments[0].text if bundle.transcript.segments else ''
    evaluated = evaluate_delivery_from_audio_metrics(audio_features=bundle.audio_features, transcript_excerpt=transcript_excerpt)
    status_visual = 'mejorable'
    if evaluated.score_0_100 >= 75:
        status_visual = 'correcto'
    elif evaluated.score_0_100 < 45:
        status_visual = 'placeholder' if getattr(bundle.audio_features, 'status', None) == 'placeholder' else 'mejorable'
    return {
        'block_id': 'delivery',
        'title': 'Delivery',
        'status_visual': status_visual,
        'score_0_100': evaluated.score_0_100,
        'summary': 'Evaluación de delivery basada en métricas acústicas reales.' if getattr(bundle.audio_features, 'status', None) == 'ready' else 'Evaluación de delivery degradada por disponibilidad/calidad de audio.',
        'details': evaluated.evidence_metrics + evaluated.observations,
        'subscores': evaluated.subscores,
        'recommendations': evaluated.recommendations,
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
