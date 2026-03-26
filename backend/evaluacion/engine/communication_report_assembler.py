from __future__ import annotations

import hashlib
import html
import json
import textwrap
from typing import Any

from evaluacion.contracts.communication_models import (
    CommunicationGlobalSynthesisOutputV1,
    CommunicationFeedbackInputBundleV1,
    CommunicationKeyMoment,
    CommunicationKeyMoments,
    CommunicationRecommendationExample,
    CommunicationRecommendationItem,
    CommunicationRecommendations,
    CommunicationReportBlock,
    CommunicationReportCheck,
    CommunicationReportExports,
    CommunicationReportHeader,
    CommunicationReportMediaBlock,
    CommunicationReportProvenance,
    CommunicationTimeline,
    CommunicationTimelineSegment,
    CommunicationVideoPanel,
    UiCommunicationReportV1,
)


def _stable_hash(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return f'sha256:{hashlib.sha256(raw).hexdigest()}'


def build_report_media_block(bundle: CommunicationFeedbackInputBundleV1) -> CommunicationReportMediaBlock:
    return CommunicationReportMediaBlock(
        recording_id=bundle.attempt_ref.recording_id,
        video_ref=bundle.recording.video_ref,
        playback_url=bundle.recording.playback_url,
        poster_frame_ref=bundle.recording.poster_frame_ref,
        duration_ms=bundle.recording.duration_ms,
        mime_type=bundle.recording.mime_type,
    )


def _build_header(*, score_global_100: int, content_output: dict[str, Any], delivery_output: dict[str, Any], synthesis_output: CommunicationGlobalSynthesisOutputV1 | None = None) -> CommunicationReportHeader:
    summary = str(
        (synthesis_output.friendly_summary if synthesis_output is not None else None)
        or content_output.get('summary')
        or delivery_output.get('summary')
        or 'La evaluación ya es legible y reutilizable.'
    )
    return CommunicationReportHeader(
        report_title='Evaluación de tu comunicación oral',
        activity_name='Presentación breve grabada',
        score_global_100=score_global_100,
        stars_0_5=round(score_global_100 / 20.0, 1),
        summary_2_3_lines=summary,
    )


def _build_block(output: dict[str, Any]) -> CommunicationReportBlock:
    details = [str(item) for item in output.get('details', [])]
    checks = [
        CommunicationReportCheck(
            polarity='placeholder' if output.get('status_visual') == 'placeholder' else 'note',
            micro_explanation=detail,
            evidence_segment_ids=[],
        )
        for detail in details
    ]
    return CommunicationReportBlock(
        block_id=str(output['block_id']),
        title=str(output['title']),
        status_visual=str(output.get('status_visual') or 'mejorable'),
        score_0_100=output.get('score_0_100'),
        checks=checks,
        block_verdict=str(output.get('summary') or output.get('title') or ''),
        summary=str(output.get('summary') or ''),
        details=details,
    )


def _build_timeline(bundle: CommunicationFeedbackInputBundleV1, block_cards: list[CommunicationReportBlock]) -> CommunicationTimeline:
    segments: list[CommunicationTimelineSegment] = []
    default_score = next((block.score_0_100 for block in block_cards if block.score_0_100 is not None), 60)
    transcript_is_real = getattr(bundle.transcript, 'status', None) == 'ready'
    for segment in bundle.transcript.segments:
        segments.append(
            CommunicationTimelineSegment(
                segment_id=f'seg_{segment.segment_index}',
                label=('Segmento transcrito' if transcript_is_real else 'Segmento placeholder') if segment.segment_index == 1 else f'Segmento {segment.segment_index}',
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                score_0_100=default_score,
                summary=segment.text or ('Sin texto transcrito real todavía.' if not transcript_is_real else 'Sin texto disponible en segmento transcrito.'),
                signals=['transcript_real', 'fase_1_multimodal'] if transcript_is_real else ['transcript_placeholder', 'fase_5_report'],
            )
        )
    if not segments:
        segments.append(
            CommunicationTimelineSegment(
                segment_id='seg_1',
                label='Grabación completa',
                start_ms=0,
                end_ms=bundle.recording.duration_ms,
                score_0_100=default_score,
                summary='No hay segmentación real todavía; se usa una ventana única compatible con el report final.',
                signals=['single_window_placeholder'],
            )
        )
    return CommunicationTimeline(segments=segments)


def _build_key_moments(timeline: CommunicationTimeline) -> CommunicationKeyMoments:
    first = timeline.segments[0]
    last = timeline.segments[-1]
    middle = timeline.segments[len(timeline.segments) // 2]
    return CommunicationKeyMoments(
        best_moment=CommunicationKeyMoment(segment_id=first.segment_id, label=first.label, why='Aquí empieza la explicación utilizable del informe.', impact='Sirve como referencia inicial para revisar tu vídeo.'),
        most_delicate_moment=CommunicationKeyMoment(segment_id=last.segment_id, label=last.label, why='El cierre sigue siendo heurístico y conviene revisarlo junto al vídeo.', impact='Te ayuda a detectar cómo termina tu exposición.'),
        turning_point=CommunicationKeyMoment(segment_id=middle.segment_id, label=middle.label, why='Marca el punto en el que el informe cambia de resumen a lectura detallada.', impact='Facilita contrastar observaciones y grabación.'),
    )


def _build_recommendations(bundle: CommunicationFeedbackInputBundleV1, synthesis_output: CommunicationGlobalSynthesisOutputV1 | None = None) -> CommunicationRecommendations:
    if synthesis_output is not None and synthesis_output.action_plan:
        return CommunicationRecommendations(items=[
            CommunicationRecommendationItem(
                title=f'Prioridad {idx + 1}',
                description=plan_item,
                example=None,
            )
            for idx, plan_item in enumerate(synthesis_output.action_plan[:3])
        ])
    first_excerpt = bundle.transcript.segments[0].text if bundle.transcript.segments else 'Mensaje inicial placeholder.'
    return CommunicationRecommendations(items=[
        CommunicationRecommendationItem(
            title='Haz visible tu cierre',
            description='Añade una frase final más concreta para que el mensaje principal quede claro incluso en una evaluación mínima.',
            example=CommunicationRecommendationExample(
                original_excerpt=first_excerpt,
                better_rephrase='En resumen, esta es la idea principal que quiero que recuerdes.',
            ),
        ),
        CommunicationRecommendationItem(
            title='Usa el vídeo como contraste',
            description='Reproduce tu grabación mientras lees cada bloque para validar si el ritmo y la claridad percibidos encajan con lo observado.',
            example=None,
        ),
    ])


def _serialize_report_markup(*, header: CommunicationReportHeader, media: CommunicationReportMediaBlock, video_panel: CommunicationVideoPanel, block_cards: list[CommunicationReportBlock], timeline: CommunicationTimeline, recommendations: CommunicationRecommendations) -> str:
    resolved_video_src = media.playback_url or media.video_ref
    block_markup = ''.join(
        f"<article class='comm-report-card'><h3>{html.escape(block.title)}</h3><p>{html.escape(block.summary)}</p><ul>" + ''.join(f"<li>{html.escape(detail)}</li>" for detail in block.details) + '</ul></article>'
        for block in block_cards
    )
    timeline_markup = ''.join(
        f"<li><strong>{html.escape(segment.label)}</strong>: {html.escape(segment.summary)}</li>"
        for segment in timeline.segments
    )
    recommendations_markup = ''.join(
        f"<li><strong>{html.escape(item.title)}</strong>: {html.escape(item.description)}</li>"
        for item in recommendations.items
    )
    poster_attr = f" poster='{html.escape(media.poster_frame_ref)}'" if media.poster_frame_ref else ''
    return textwrap.dedent(f"""
    <section class="comm-report-export">
      <header>
        <h1>{html.escape(header.report_title)}</h1>
        <p>{html.escape(header.summary_2_3_lines)}</p>
      </header>
      <section class="comm-report-top">
        <div>
          <p>Puntuación global: <strong>{header.score_global_100}/100</strong></p>
          <p>Actividad: {html.escape(header.activity_name)}</p>
        </div>
        <div>
          <h2>{html.escape(video_panel.title)}</h2>
          <p>{html.escape(video_panel.help_text)}</p>
          <video controls preload="metadata"{poster_attr}><source src="{html.escape(resolved_video_src)}" type="{html.escape(media.mime_type)}"></video>
        </div>
      </section>
      <section><h2>Bloques</h2>{block_markup}</section>
      <section><h2>Timeline</h2><ol>{timeline_markup}</ol></section>
      <section><h2>Recomendaciones</h2><ol>{recommendations_markup}</ol></section>
    </section>
    """).strip()


def _build_snapshot_png_data_url(*, header: CommunicationReportHeader) -> str:
    tiny_png_base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9VEWilQAAAAASUVORK5CYII='
    return f'data:image/png;base64,{tiny_png_base64}'


def assemble_communication_report(
    *,
    bundle: CommunicationFeedbackInputBundleV1,
    content_output: dict[str, Any],
    delivery_output: dict[str, Any],
    visual_output: dict[str, Any],
    synthesis_output: dict[str, Any] | None = None,
) -> UiCommunicationReportV1:
    synthesis = CommunicationGlobalSynthesisOutputV1.model_validate(synthesis_output) if synthesis_output is not None else None
    block_cards = [_build_block(content_output), _build_block(delivery_output), _build_block(visual_output)]
    scored = [block.score_0_100 for block in block_cards if block.score_0_100 is not None]
    score_global_100 = synthesis.global_score_0_100 if synthesis is not None else (int(round(sum(scored) / len(scored))) if scored else 60)
    header = _build_header(score_global_100=score_global_100, content_output=content_output, delivery_output=delivery_output, synthesis_output=synthesis)
    media = build_report_media_block(bundle)
    video_panel = CommunicationVideoPanel(
        title='Tu grabación',
        help_text='Reproduce tu vídeo mientras lees la evaluación para contrastar cada observación.',
        default_mode='embedded_small_player',
    )
    timeline = _build_timeline(bundle, block_cards)
    key_moments = _build_key_moments(timeline)
    recommendations = _build_recommendations(bundle, synthesis_output=synthesis)
    markup = _serialize_report_markup(
        header=header,
        media=media,
        video_panel=video_panel,
        block_cards=block_cards,
        timeline=timeline,
        recommendations=recommendations,
    )
    provenance = CommunicationReportProvenance(
        evaluation_id=bundle.evaluation_id,
        recording_id=bundle.attempt_ref.recording_id,
        flow_id=bundle.domain_context.flow_id,
        context_id=bundle.domain_context.context_id,
        context_version=bundle.domain_context.context_version,
        bundle_hash=_stable_hash(bundle.model_dump(mode='json')),
        content_output_hash=_stable_hash(content_output),
        delivery_output_hash=_stable_hash(delivery_output),
        visual_output_hash=_stable_hash(visual_output),
    )
    report = UiCommunicationReportV1(
        evaluation_id=bundle.evaluation_id,
        attempt_id=bundle.attempt_ref.attempt_id,
        recording_id=bundle.attempt_ref.recording_id,
        header=header,
        media=media,
        video_panel=video_panel,
        block_cards=block_cards,
        timeline=timeline,
        key_moments=key_moments,
        recommendations=recommendations,
        global_synthesis=synthesis,
        provenance=provenance,
        exports=CommunicationReportExports(
            report_json={},
            summary_html=f'<!doctype html><html lang="es"><body>{markup}</body></html>',
            report_snapshot_png_data_url=_build_snapshot_png_data_url(header=header),
        ),
        placeholders={
            'transcript': bundle.transcript.explanation,
            'audio_features': bundle.audio_features.explanation,
            'visual_features': bundle.visual_features.explanation,
            'snapshot_png': 'El PNG final se captura en cliente desde el DOM del feedback al emitir final_result; este campo documenta el comportamiento de fallback.',
        },
    )
    report.exports.report_json = report.model_dump(mode='json', exclude={'exports'})
    return report
