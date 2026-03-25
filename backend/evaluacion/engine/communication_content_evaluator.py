from __future__ import annotations

from typing import Any

from evaluacion.contracts.communication_models import CommunicationFeedbackInputBundleV1


def evaluate_content_from_transcript(*, bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]:
    transcript = bundle.transcript
    transcript_text = (transcript.full_text or '').strip()
    words = [item for item in transcript_text.replace('\n', ' ').split(' ') if item]
    word_count = len(words)
    segment_count = len(transcript.segments)
    has_clear_closing = transcript_text.endswith('.') or transcript_text.endswith('!') or transcript_text.endswith('?')

    if word_count >= 110:
        score = 82
        status = 'correcto'
    elif word_count >= 60:
        score = 72
        status = 'mejorable'
    elif word_count >= 25:
        score = 64
        status = 'mejorable'
    else:
        score = 55
        status = 'mejorable'

    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []

    if segment_count >= 2:
        strengths.append('La transcripción contiene más de un tramo, lo que facilita identificar estructura del contenido.')
    else:
        weaknesses.append('La intervención aparece muy concentrada en un único tramo textual.')
        recommendations.append('Estructura tu mensaje en introducción, desarrollo y cierre para mejorar claridad.')

    if word_count >= 60:
        strengths.append('La cantidad de contenido verbal permite desarrollar una idea principal con contexto.')
    else:
        weaknesses.append('La extensión del contenido parece limitada para sostener una argumentación completa.')
        recommendations.append('Amplía ejemplos concretos para reforzar tu idea principal.')

    if has_clear_closing:
        strengths.append('Hay un cierre reconocible en la formulación final.')
    else:
        weaknesses.append('No se detecta un cierre textual claramente marcado.')
        recommendations.append('Incluye una frase final explícita que refuerce la conclusión.')

    primary_segment = transcript.segments[0].text if transcript.segments else transcript_text
    evidence_excerpt = primary_segment[:200] if primary_segment else 'Sin evidencia textual utilizable.'

    return {
        'block_id': 'contenido',
        'title': 'Contenido',
        'status_visual': status,
        'score_0_100': score,
        'summary': (
            f'Evaluación de contenido basada en transcripción real ({word_count} palabras, {segment_count} segmentos).'
        ),
        'details': [
            f'Proveedor STT: {getattr(transcript, "provider", "desconocido")}.',
            f'Idioma detectado: {getattr(transcript, "language", "es")}.',
            f'Evidencia principal: {evidence_excerpt}',
        ],
        'strengths': strengths,
        'weaknesses': weaknesses,
        'recommendations': recommendations or ['Sigue reforzando tus ideas clave con ejemplos concretos y cierre explícito.'],
        'evidence_segments': [
            {
                'segment_index': segment.segment_index,
                'start_ms': segment.start_ms,
                'end_ms': segment.end_ms,
                'text_excerpt': segment.text[:160],
            }
            for segment in transcript.segments[:3]
        ],
    }
