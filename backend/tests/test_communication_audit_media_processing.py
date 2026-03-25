from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from comunicacion.storage.models import RecordingRecord
from evaluacion.engine.communication_media_processing import extract_audio_track, resolve_recording_media_source


class CommunicationAuditMediaProcessingTests(unittest.TestCase):
    def _recording(self, *, video_ref: str) -> RecordingRecord:
        return RecordingRecord(
            recording_id='rec_media_audit',
            attempt_id='att_media_audit',
            user_id='iu_media_audit',
            session_id='sess_media_audit',
            mime_type='video/mp4',
            duration_ms=3000,
            video_ref=video_ref,
            created_at=datetime.now(timezone.utc),
        )

    def test_resolve_media_source_accepts_local_file_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix='comm_media_') as tmpdir:
            video_path = Path(tmpdir) / 'sample.webm'
            video_path.write_bytes(b'dummy')
            source = resolve_recording_media_source(recording=self._recording(video_ref=str(video_path)))
        self.assertTrue(source.local_path.name.endswith('sample.webm'))

    def test_resolve_media_source_rejects_remote_scheme(self) -> None:
        with self.assertRaises(HTTPException) as exc:
            resolve_recording_media_source(recording=self._recording(video_ref='https://example.com/video.webm'))
        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(exc.exception.detail['error'], 'recording_media_scheme_not_supported')

    def test_extract_audio_track_requires_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory(prefix='comm_media_') as tmpdir:
            video_path = Path(tmpdir) / 'sample.webm'
            video_path.write_bytes(b'dummy')
            source = resolve_recording_media_source(recording=self._recording(video_ref=str(video_path)))
            with patch('evaluacion.engine.communication_media_processing.shutil.which', return_value=None):
                with self.assertRaises(HTTPException) as exc:
                    extract_audio_track(media_source=source, recording=self._recording(video_ref=str(video_path)))
        self.assertEqual(exc.exception.status_code, 500)
        self.assertEqual(exc.exception.detail['error'], 'ffmpeg_not_available_for_audio_extraction')

    def test_extract_audio_track_success_path_creates_wav_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix='comm_media_') as tmpdir:
            video_path = Path(tmpdir) / 'sample.webm'
            video_path.write_bytes(b'dummy')
            source = resolve_recording_media_source(recording=self._recording(video_ref=str(video_path)))

            def fake_run(command, check, capture_output, text):
                output_path = Path(command[-1])
                output_path.write_bytes(b'RIFF0000WAVEfmt ')

                class _Completed:
                    stdout = ''
                    stderr = ''

                return _Completed()

            with patch('evaluacion.engine.communication_media_processing.shutil.which', return_value='/usr/bin/ffmpeg'), patch(
                'evaluacion.engine.communication_media_processing.subprocess.run', side_effect=fake_run
            ):
                artifact = extract_audio_track(media_source=source, recording=self._recording(video_ref=str(video_path)))
        self.assertEqual(artifact.mime_type, 'audio/wav')
        self.assertTrue(artifact.audio_path.exists())


if __name__ == '__main__':
    unittest.main()
