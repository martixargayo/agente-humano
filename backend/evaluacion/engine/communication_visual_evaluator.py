from __future__ import annotations

from typing import Any

from evaluacion.contracts.communication_models import (
    CommunicationVisualEvaluationV1,
    CommunicationVisualFeaturesPlaceholder,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualTemporalFinding,
)


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


def validate_visual_eval_schema(raw_llm_output: dict[str, Any]) -> CommunicationVisualEvaluationV1:
    return CommunicationVisualEvaluationV1.model_validate(raw_llm_output)
