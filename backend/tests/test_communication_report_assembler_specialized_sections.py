from __future__ import annotations

import unittest

from evaluacion.contracts.communication_models import (
    CommunicationAttemptRef,
    CommunicationAudioFeaturesPlaceholder,
    CommunicationContentAidaEvalV1,
    CommunicationDomainContext,
    CommunicationFeedbackInputBundleV1,
    CommunicationGlobalSynthesisLlmOutputV1,
    CommunicationRecordingMetadata,
    CommunicationSpecializedDimensionEvalV1,
    CommunicationTranscriptPlaceholder,
    CommunicationVisualFeaturesPlaceholder,
)
from evaluacion.contracts.models import SessionRef
from evaluacion.engine.communication_report_assembler import assemble_communication_report


def _bundle() -> CommunicationFeedbackInputBundleV1:
    return CommunicationFeedbackInputBundleV1(
        evaluation_id='eval_assembler_specialized',
        session_ref=SessionRef(user_id='iu', session_id='sess'),
        attempt_ref=CommunicationAttemptRef(attempt_id='att', recording_id='rec'),
        domain_context=CommunicationDomainContext(context_id='baseline_current', context_version='1'),
        recording=CommunicationRecordingMetadata(
            duration_ms=12000,
            mime_type='video/webm',
            video_ref='client-temp://sess/att/video.webm',
            playback_url='/api/comunicacion/recordings/rec/video',
            poster_frame_ref=None,
            capture_meta={},
        ),
        transcript=CommunicationTranscriptPlaceholder(explanation='placeholder transcript'),
        audio_features=CommunicationAudioFeaturesPlaceholder(explanation='placeholder audio'),
        visual_features=CommunicationVisualFeaturesPlaceholder(
            summary='placeholder visual',
            explanation='placeholder visual',
        ),
    )


class CommunicationReportAssemblerSpecializedSectionsTests(unittest.TestCase):
    def test_report_wires_specialized_sections_from_exact_sources(self) -> None:
        content_specialized = CommunicationContentAidaEvalV1(
            attention={'score_1_3': 2, 'label': 'mejorable', 'reason_short': 'Atención mejorable.'},
            interest={'score_1_3': 3, 'label': 'correcto', 'reason_short': 'Interés correcto.'},
            development={'score_1_3': 2, 'label': 'mejorable', 'reason_short': 'Desarrollo mejorable.'},
            action={'score_1_3': 1, 'label': 'mal', 'reason_short': 'Acción mal resuelta.'},
        )
        audio_specialized = CommunicationSpecializedDimensionEvalV1(
            score_1_5=3,
            label='medio',
            reason_short='Pausas funcionales con margen de mejora.',
        )
        visual_specialized = CommunicationSpecializedDimensionEvalV1(
            score_1_5=4,
            label='medio-alto',
            reason_short='Gesticulación útil y bastante consistente.',
        )
        synthesis = CommunicationGlobalSynthesisLlmOutputV1(
            score_global_100=77,
            summary_short_2_3_lines='Resumen global.',
            recommendations=[{'title': 'R1', 'description': 'D1'}],
        )

        report = assemble_communication_report(
            bundle=_bundle(),
            content_output={
                'block_id': 'contenido',
                'title': 'Contenido',
                'status_visual': 'mejorable',
                'score_0_100': 70,
                'summary': 'Contenido',
                'details': ['d1'],
                'recommendations': ['r1'],
                'llm_specialized_evaluation': content_specialized.model_dump(mode='json'),
            },
            delivery_output={
                'block_id': 'delivery',
                'title': 'Delivery',
                'status_visual': 'mejorable',
                'score_0_100': 65,
                'summary': 'Delivery',
                'details': ['d2'],
                'recommendations': ['r2'],
                'llm_specialized_evaluation': audio_specialized.model_dump(mode='json'),
            },
            visual_output={
                'block_id': 'visual',
                'title': 'Visual',
                'status_visual': 'mejorable',
                'score_0_100': 60,
                'summary': 'Visual',
                'details': ['d3'],
                'recommendations': ['r3'],
                'evidence_frames': [],
                'llm_specialized_evaluation': visual_specialized.model_dump(mode='json'),
            },
            synthesis_output=synthesis.model_dump(mode='json'),
            synthesis_meta={'mode': 'llm', 'fallback_reason': None, 'detail': None},
        )

        self.assertEqual(report.content_aida_feedback, content_specialized)
        self.assertEqual(report.audio_specialized_feedback, audio_specialized)
        self.assertEqual(report.visual_specialized_feedback, visual_specialized)

    def test_report_keeps_compat_and_returns_null_specialized_when_missing_or_invalid(self) -> None:
        report = assemble_communication_report(
            bundle=_bundle(),
            content_output={
                'block_id': 'contenido',
                'title': 'Contenido',
                'status_visual': 'placeholder',
                'score_0_100': 40,
                'summary': 'Contenido degradado',
                'details': ['d1'],
                'recommendations': ['r1'],
                'llm_specialized_evaluation': {'attention': {'broken': True}},
            },
            delivery_output={
                'block_id': 'delivery',
                'title': 'Delivery',
                'status_visual': 'placeholder',
                'score_0_100': 40,
                'summary': 'Delivery degradado',
                'details': ['d2'],
                'recommendations': ['r2'],
            },
            visual_output={
                'block_id': 'visual',
                'title': 'Visual',
                'status_visual': 'placeholder',
                'score_0_100': 40,
                'summary': 'Visual degradado',
                'details': ['d3'],
                'recommendations': ['r3'],
                'evidence_frames': [],
                'llm_specialized_evaluation': {'score_1_5': 99},
            },
            synthesis_output={
                'score_global_100': 40,
                'summary_short_2_3_lines': 'Resumen degradado.',
                'recommendations': [],
            },
            synthesis_meta={'mode': 'fallback', 'fallback_reason': 'disabled_policy', 'detail': None},
        )

        self.assertIsNone(report.content_aida_feedback)
        self.assertIsNone(report.audio_specialized_feedback)
        self.assertIsNone(report.visual_specialized_feedback)
        # Compatibilidad explícita
        self.assertEqual(len(report.block_cards), 3)
        self.assertIsNotNone(report.header)
        self.assertIsNotNone(report.recommendations)
        self.assertIsNotNone(report.global_synthesis)


if __name__ == '__main__':
    unittest.main()

