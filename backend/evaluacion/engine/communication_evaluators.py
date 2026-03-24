from __future__ import annotations

from evaluacion.contracts.communication_models import CommunicationFeedbackInputBundleV1


def evaluate_communication_content(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, object]:
    transcript_segment = bundle.transcript.segments[0].text if bundle.transcript.segments else 'Sin segmentos todavía.'
    return {
        'block_id': 'contenido',
        'title': 'Contenido',
        'status_visual': 'mejorable',
        'score_0_100': 55,
        'summary': 'El contenido todavía se resume a partir de metadata y un transcript placeholder; sirve para cerrar el circuito submit -> report.',
        'details': [
            f'Contexto activo: {bundle.domain_context.context_id} ({bundle.domain_context.context_version}).',
            f'Segmento placeholder disponible: {transcript_segment}',
            bundle.transcript.explanation,
        ],
    }


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
