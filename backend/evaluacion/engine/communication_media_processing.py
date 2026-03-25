from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException

from comunicacion.storage.models import RecordingRecord


@dataclass(frozen=True)
class CommunicationMediaSource:
    source_ref: str
    local_path: Path
    is_temporary: bool = False


@dataclass(frozen=True)
class CommunicationAudioTrackArtifact:
    source_ref: str
    audio_path: Path
    mime_type: str
    is_temporary: bool = True


def resolve_recording_media_source(*, recording: RecordingRecord) -> CommunicationMediaSource:
    raw_ref = (recording.video_ref or '').strip()
    if not raw_ref:
        raise HTTPException(status_code=409, detail={'error': 'recording_video_ref_missing', 'recording_id': recording.recording_id})

    parsed = urlparse(raw_ref)
    if parsed.scheme in ('', 'file'):
        path = Path(parsed.path if parsed.scheme == 'file' else raw_ref).expanduser()
        if not path.exists():
            raise HTTPException(
                status_code=409,
                detail={'error': 'recording_media_not_accessible', 'recording_id': recording.recording_id, 'video_ref': raw_ref},
            )
        return CommunicationMediaSource(source_ref=raw_ref, local_path=path.resolve(), is_temporary=False)

    raise HTTPException(
        status_code=409,
        detail={
            'error': 'recording_media_scheme_not_supported',
            'recording_id': recording.recording_id,
            'video_ref': raw_ref,
            'scheme': parsed.scheme,
        },
    )


def extract_audio_track(*, media_source: CommunicationMediaSource, recording: RecordingRecord) -> CommunicationAudioTrackArtifact:
    ffmpeg_binary = shutil.which('ffmpeg')
    if ffmpeg_binary is None:
        raise HTTPException(status_code=500, detail={'error': 'ffmpeg_not_available_for_audio_extraction'})

    output_dir = Path(tempfile.mkdtemp(prefix='comm_audio_extract_'))
    output_path = output_dir / f'{recording.recording_id}.wav'
    command = [
        ffmpeg_binary,
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-i',
        str(media_source.local_path),
        '-vn',
        '-ac',
        '1',
        '-ar',
        '16000',
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - system dependent
        stderr = (exc.stderr or '').strip()
        raise HTTPException(
            status_code=409,
            detail={'error': 'audio_extraction_failed', 'recording_id': recording.recording_id, 'reason': stderr or 'ffmpeg_failed'},
        ) from exc

    if not output_path.exists() or os.path.getsize(output_path) == 0:
        raise HTTPException(
            status_code=409,
            detail={'error': 'audio_extraction_empty_output', 'recording_id': recording.recording_id},
        )

    return CommunicationAudioTrackArtifact(
        source_ref=f'file://{output_path}',
        audio_path=output_path,
        mime_type='audio/wav',
        is_temporary=True,
    )
