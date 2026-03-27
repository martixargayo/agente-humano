from __future__ import annotations

from collections import Counter
from typing import Any

from evaluacion.contracts.communication_models import (
    CommunicationSpecializedDimensionEvalV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualEvaluationV1,
    CommunicationVisualFeaturesPlaceholder,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualTemporalFinding,
)
from evaluacion.engine.communication_visual_batch_runner import (
    build_visual_batch_inputs_from_manifest,
    evaluate_visual_batches_openai,
)
from evaluacion.engine.communication_visual_openai_client import CommunicationVisualLlmError
from evaluacion.engine.communication_visual_synthesizer import run_visual_synthesis_openai


def _normalize_score(*, composition: int, stability: int, coverage: int) -> int:
    score = round(((composition + stability + coverage) / 15) * 100)
    return max(0, min(100, int(score)))


def _evaluate_from_real_features(visual_features: CommunicationVisualFeaturesRealV1) -> CommunicationVisualEvaluationV1:
    frames = visual_features.frame_manifest.frames
    windows = visual_features.frame_manifest.windows
    low_detail = sum(1 for frame in frames if frame.quality == 'low_detail')
    coverage_ratio = float(visual_features.coverage_stats.get('coverage_ratio', 0.0) or 0.0)

    composition = 3 if low_detail <= len(frames) // 3 else 2
    stability = 4 if len(frames) >= 6 else 3
    coverage = 4 if coverage_ratio >= 0.7 else 3
    if coverage_ratio < 0.35:
        coverage = 2

    findings: list[CommunicationVisualTemporalFinding] = []
    for window in windows[:3]:
        findings.append(
            CommunicationVisualTemporalFinding(
                window_id=window.window_id,
                start_ms=window.start_ms,
                end_ms=window.end_ms,
                finding='Ventana visual analizada con muestreo temporal estable.',
                evidence_frame_ids=window.frame_ids[:2],
            )
        )

    observations = [
        f'Se analizaron {len(frames)} frames en {len(windows)} ventanas temporales.',
        f'Cobertura estimada de la grabación: {coverage_ratio:.2f}.',
    ]
    if low_detail:
        observations.append(f'Se detectaron {low_detail} frames con bajo detalle visual.')

    recommendations = [
        'Mantén encuadre y distancia constantes durante toda la intervención.',
        'Asegura iluminación frontal suficiente para mejorar legibilidad facial.',
    ]
    if low_detail:
        recommendations.append('Incrementa resolución/calidad de cámara para mejorar evidencia visual.')

    evidence_frames = [frame.frame_id for frame in frames[:5]]
    return CommunicationVisualEvaluationV1(
        score_0_100=_normalize_score(composition=composition, stability=stability, coverage=coverage),
        subscores={
            'composition': composition,
            'stability': stability,
            'coverage': coverage,
        },
        temporal_findings=findings,
        observations=observations,
        recommendations=recommendations,
        evidence_frames=evidence_frames,
    )


def evaluate_visual_from_features(*, visual_features: CommunicationVisualFeaturesPlaceholder | CommunicationVisualFeaturesRealV1) -> CommunicationVisualEvaluationV1:
    if isinstance(visual_features, CommunicationVisualFeaturesPlaceholder):
        return CommunicationVisualEvaluationV1(
            score_0_100=50,
            subscores={'composition': 2, 'stability': 2, 'coverage': 2},
            temporal_findings=[],
            observations=['No hay frame manifest real disponible; evaluación visual degradada a modo placeholder.'],
            recommendations=['Verifica acceso al archivo de video para habilitar extracción real de frames.'],
            evidence_frames=[],
        )
    return _evaluate_from_real_features(visual_features)


def _aggregate_batches_to_visual_eval(
    *,
    batch_outputs: list[CommunicationVisualBatchEvalV2],
    final_eval: CommunicationSpecializedDimensionEvalV1 | None = None,
) -> CommunicationVisualEvaluationV1:
    if not batch_outputs:
        raise CommunicationVisualLlmError(kind='schema', message='no_batch_outputs_to_aggregate')

    mean_score_1_5 = sum(item.batch_score_1_5 for item in batch_outputs) / len(batch_outputs)
    if final_eval is not None:
        score_0_100 = max(0, min(100, int(round(final_eval.score_1_5 * 20))))
    else:
        score_0_100 = max(0, min(100, int(round(mean_score_1_5 * 20))))

    sufficiency_counts = Counter(item.evidence_sufficiency for item in batch_outputs)
    dominant_sufficiency = max(sufficiency_counts.items(), key=lambda entry: entry[1])[0]

    observations = [
        f'Se evaluaron {len(batch_outputs)} lotes visuales con salida estructurada.',
        f'Suficiencia dominante de evidencia: {dominant_sufficiency}.',
    ]
    observations.extend(
        f'Lote {item.batch_index}/{item.total_batches}: score={item.batch_score_1_5}/5 confidence={item.confidence:.2f}'
        for item in batch_outputs
    )
    if final_eval is not None:
        observations.append(f'Evaluación global de gesticulación: {final_eval.reason_short}')

    recommendations: list[str] = []
    evidence_frames: list[str] = []
    for item in batch_outputs:
        recommendations.extend(item.weaknesses[:2])
        recommendations.extend(item.limitations[:1])
        evidence_frames.extend(item.cited_frame_ids[:3])
    if final_eval is not None:
        recommendations.append(final_eval.reason_short)
    dedup_recommendations = list(dict.fromkeys(recommendations))[:8] or ['Mantén encuadre, iluminación y visibilidad de manos para mejorar la observabilidad.']
    dedup_evidence = list(dict.fromkeys(evidence_frames))[:10]

    return CommunicationVisualEvaluationV1(
        score_0_100=score_0_100,
        subscores={
            'batch_quality': max(1, min(5, int(round(mean_score_1_5)))),
            'gesticulation_global': final_eval.score_1_5 if final_eval is not None else max(1, min(5, int(round(mean_score_1_5)))),
            'evidence_consistency': 4 if dominant_sufficiency == 'high' else (3 if dominant_sufficiency == 'medium' else 2),
            'coverage': 4 if len(batch_outputs) >= 2 else 3,
        },
        temporal_findings=[],
        observations=observations,
        recommendations=dedup_recommendations,
        evidence_frames=dedup_evidence,
    )


def evaluate_visual_llm_v1_from_features(
    *,
    evaluation_id: str,
    recording_id: str,
    video_duration_ms: int,
    visual_features: CommunicationVisualFeaturesPlaceholder | CommunicationVisualFeaturesRealV1,
) -> tuple[CommunicationVisualEvaluationV1, list[CommunicationVisualBatchEvalV2], CommunicationSpecializedDimensionEvalV1]:
    if isinstance(visual_features, CommunicationVisualFeaturesPlaceholder):
        raise CommunicationVisualLlmError(kind='payload', message='visual_features_placeholder_not_supported_for_llm_v1')

    batch_inputs = build_visual_batch_inputs_from_manifest(
        evaluation_id=evaluation_id,
        recording_id=recording_id,
        video_duration_ms=video_duration_ms,
        manifest=visual_features.frame_manifest,
    )
    if not batch_inputs:
        raise CommunicationVisualLlmError(kind='payload', message='no_batch_inputs_for_llm_v1')
    batch_outputs = evaluate_visual_batches_openai(batch_inputs=batch_inputs)
    final_eval = run_visual_synthesis_openai(
        evaluation_id=evaluation_id,
        recording_id=recording_id,
        video_duration_ms=video_duration_ms,
        batch_outputs=batch_outputs,
    )
    return _aggregate_batches_to_visual_eval(batch_outputs=batch_outputs, final_eval=final_eval), batch_outputs, final_eval


def validate_visual_eval_schema(raw_llm_output: dict[str, Any]) -> CommunicationVisualEvaluationV1:
    return CommunicationVisualEvaluationV1.model_validate(raw_llm_output)
