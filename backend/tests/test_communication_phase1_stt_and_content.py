from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
from evaluacion.contracts.communication_models import CommunicationTranscriptRealV1, CommunicationTranscriptSegment
from evaluacion.engine.communication_bundle_builder import build_communication_feedback_input_bundle
from evaluacion.engine.communication_content_evaluator import evaluate_content_from_transcript
from evaluacion.engine.communication_media_processing import resolve_recording_media_source
from evaluacion.engine.communication_service import persist_transcript_artifact
from evaluacion.engine.communication_stt import OpenAiWhisperSttProvider, normalize_openai_transcript, normalize_openai_verbose_transcript


class CommunicationPhase1SttAndContentTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def _seed_attempt_and_recording(self) -> tuple[AttemptRecord, RecordingRecord]:
        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id='att_phase1',
            user_id='iu_phase1',
            session_id='sess_phase1',
            context_id='baseline_current',
            status='uploaded',
            recording_id='rec_phase1',
            created_at=now,
            updated_at=now,
        )
        recording = RecordingRecord(
            recording_id='rec_phase1',
            attempt_id='att_phase1',
            user_id='iu_phase1',
            session_id='sess_phase1',
            mime_type='video/webm',
            duration_ms=17000,
            video_ref='file:///tmp/nonexistent_phase1.webm',
            capture_meta={'provisional_client_ref': True},
            created_at=now,
        )
        REPOSITORY.create_attempt(attempt)
        REPOSITORY.attach_recording(recording)
        return attempt, recording

    def test_openai_verbose_transcript_normalization_keeps_timestamps(self) -> None:
        payload = {
            'text': 'Hola mundo',
            'language': 'es',
            'segments': [
                {'start': 0.0, 'end': 1.3, 'text': 'Hola'},
                {'start': 1.3, 'end': 2.0, 'text': 'mundo'},
            ],
        }
        out = normalize_openai_verbose_transcript(payload, provider='openai_whisper_api', language_hint='es')
        self.assertEqual(out.status, 'ready')
        self.assertEqual(out.provider, 'openai_whisper_api')
        self.assertEqual(out.language, 'es')
        self.assertEqual(out.full_text, 'Hola mundo')
        self.assertEqual(len(out.segments), 2)
        self.assertEqual(out.segments[0].start_ms, 0)
        self.assertEqual(out.segments[1].end_ms, 2000)

    def test_openai_json_transcript_normalization_builds_minimum_segment_when_segments_absent(self) -> None:
        payload = {
            'text': 'Hola mundo desde json simple',
            'language': 'es',
        }
        out = normalize_openai_transcript(payload, provider='openai_whisper_api', language_hint='es')
        self.assertEqual(out.status, 'ready')
        self.assertEqual(out.full_text, 'Hola mundo desde json simple')
        self.assertEqual(len(out.segments), 1)
        self.assertEqual(out.segments[0].start_ms, 0)
        self.assertEqual(out.segments[0].end_ms, 1000)

    def test_stt_provider_retries_with_json_when_verbose_json_is_rejected(self) -> None:
        class _FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self._payload = payload

            def model_dump(self) -> dict[str, object]:
                return self._payload

        class _FakeBadRequestError(Exception):
            pass

        class _FakeTranscriptions:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                response_format = kwargs.get('response_format')
                self.calls.append(str(response_format))
                if response_format == 'verbose_json':
                    raise _FakeBadRequestError(
                        "response_format 'verbose_json' is not compatible with model 'gpt-4o-mini-transcribe-api-ev3'. code=unsupported_value"
                    )
                return _FakeResponse({'text': 'texto desde fallback json', 'language': 'es'})

        fake_transcriptions = _FakeTranscriptions()
        fake_client = SimpleNamespace(audio=SimpleNamespace(transcriptions=fake_transcriptions))
        fake_openai_module = SimpleNamespace(OpenAI=lambda api_key: fake_client)

        with TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / 'sample.wav'
            audio_path.write_bytes(b'RIFFxxxxWAVEfmt ')
            provider = OpenAiWhisperSttProvider(model='gpt-4o-mini-transcribe')
            with patch.dict('sys.modules', {'openai': fake_openai_module}), patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                out = provider.transcribe(audio_path=audio_path, language_hint='es')

        self.assertEqual(fake_transcriptions.calls, ['verbose_json', 'json'])
        self.assertEqual(out.status, 'ready')
        self.assertEqual(out.full_text, 'texto desde fallback json')
        self.assertEqual(len(out.segments), 1)

    def test_stt_provider_maps_provider_error_to_http_exception(self) -> None:
        class _FakeTranscriptions:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError('network timeout')

        fake_client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_FakeTranscriptions()))
        fake_openai_module = SimpleNamespace(OpenAI=lambda api_key: fake_client)

        with TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / 'sample.wav'
            audio_path.write_bytes(b'RIFFxxxxWAVEfmt ')
            provider = OpenAiWhisperSttProvider(model='gpt-4o-mini-transcribe')
            with patch.dict('sys.modules', {'openai': fake_openai_module}), patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                with self.assertRaises(Exception) as exc:
                    provider.transcribe(audio_path=audio_path, language_hint='es')

        self.assertEqual(getattr(exc.exception, 'status_code', None), 502)
        self.assertEqual(exc.exception.detail['error'], 'stt_provider_request_failed')

    def test_bundle_uses_real_transcript_when_extractor_returns_ready_transcript(self) -> None:
        self._seed_attempt_and_recording()
        transcript_real = CommunicationTranscriptRealV1(
            provider='mock_word_timed_stt',
            language='es',
            full_text='Introducción con idea principal y cierre claro.',
            segments=[
                CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=2000, text='Introducción con idea principal.'),
                CommunicationTranscriptSegment(segment_index=2, start_ms=2000, end_ms=4200, text='Cierre claro de la intervención.'),
            ],
            confidence_global=0.94,
            quality_flags=[],
            explanation='ok',
        )
        with patch('evaluacion.engine.communication_bundle_builder.build_real_transcript', return_value=transcript_real):
            bundle = build_communication_feedback_input_bundle(evaluation_id='eval_phase1', attempt_id='att_phase1')
        self.assertEqual(bundle.transcript.status, 'ready')
        content = evaluate_content_from_transcript(bundle=bundle)
        self.assertEqual(content['block_id'], 'contenido')
        self.assertIn('transcripción real', content['summary'].lower())
        self.assertGreaterEqual(content['score_0_100'], 55)
        self.assertIn('llm_specialized_evaluation', content)
        specialized = content['llm_specialized_evaluation']
        self.assertEqual(set(specialized.keys()), {'attention', 'interest', 'development', 'action'})
        self.assertIn(specialized['attention']['score_1_3'], [1, 2, 3])
        self.assertIn(specialized['attention']['label'], ['mal', 'mejorable', 'correcto'])

    def test_bundle_degrades_to_placeholder_when_stt_provider_fails(self) -> None:
        self._seed_attempt_and_recording()
        with patch(
            'evaluacion.engine.communication_bundle_builder.build_real_transcript',
            side_effect=HTTPException(status_code=502, detail={'error': 'stt_provider_request_failed'}),
        ):
            bundle = build_communication_feedback_input_bundle(evaluation_id='eval_phase1', attempt_id='att_phase1')
        self.assertEqual(bundle.transcript.status, 'placeholder')
        self.assertTrue(bundle.transcript.explanation)

    def test_persist_transcript_artifact_registers_transcript_real_kind(self) -> None:
        transcript_real = CommunicationTranscriptRealV1(
            provider='mock_word_timed_stt',
            language='es',
            full_text='Texto transcrito.',
            segments=[CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1000, text='Texto transcrito.')],
            confidence_global=0.9,
            quality_flags=[],
            explanation='ok',
        )

        class _Bundle:
            transcript = transcript_real

            class attempt_ref:
                recording_id = 'rec_phase1'

            class recording:
                duration_ms = 1000

        persist_transcript_artifact(evaluation_id='eval_phase1', bundle=_Bundle())
        artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_phase1', 'transcript_real')
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].kind, 'transcript_real')
        self.assertEqual(artifacts[0].version, 'communication_transcript_real.v1')

    def test_resolve_recording_media_source_requires_local_or_file_ref(self) -> None:
        _, recording = self._seed_attempt_and_recording()
        with self.assertRaises(Exception):
            resolve_recording_media_source(recording=recording)
