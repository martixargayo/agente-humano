from __future__ import annotations

from evaluacion.contracts.communication_models import CommunicationFeedbackInputBundleV1
from evaluacion.engine.communication_content_evaluator import evaluate_content_from_transcript
from evaluacion.engine.communication_delivery_evaluator import evaluate_delivery_from_audio_metrics
from evaluacion.engine.communication_synthesis import (
    build_global_synthesis_input,
    synthesize_global_communication_feedback,
)
from evaluacion.engine.communication_visual_evaluator import evaluate_visual_from_features


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


def evaluate_communication_visual(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    evaluated = evaluate_visual_from_features(visual_features=bundle.visual_features)
    status_visual = 'mejorable'
    if evaluated.score_0_100 >= 75:
        status_visual = 'correcto'
    elif getattr(bundle.visual_features, 'status', None) == 'placeholder':
        status_visual = 'placeholder'
    return {
        'block_id': 'visual',
        'title': 'Visual',
        'status_visual': status_visual,
        'score_0_100': evaluated.score_0_100,
        'summary': 'Evaluación visual real basada en frames extraídos.' if getattr(bundle.visual_features, 'status', None) == 'ready' else 'Evaluación visual degradada por indisponibilidad de frames.',
        'details': evaluated.observations + [finding.finding for finding in evaluated.temporal_findings],
        'subscores': evaluated.subscores,
        'recommendations': evaluated.recommendations,
        'evidence_frames': evaluated.evidence_frames,
    }


def evaluate_communication_synthesis(
    *,
    bundle: CommunicationFeedbackInputBundleV1,
    content_output: dict[str, object],
    delivery_output: dict[str, object],
    visual_output: dict[str, object],
) -> dict[str, object]:
    synthesis_input = build_global_synthesis_input(
        evaluation_id=bundle.evaluation_id,
        content_output=content_output,
        delivery_output=delivery_output,
        visual_output=visual_output,
    )
    synthesized = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
    return synthesized.model_dump(mode='json')
