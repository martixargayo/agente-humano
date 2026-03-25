from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException

from comunicacion.storage.models import RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationFrameWindow,
)
from evaluacion.engine.communication_media_processing import CommunicationMediaSource


def _probe_image_dimensions(image_path: Path) -> tuple[int | None, int | None]:
    ffprobe_binary = shutil.which('ffprobe')
    if ffprobe_binary is None:
        return None, None
    command = [
        ffprobe_binary,
        '-v',
        'error',
        '-select_streams',
        'v:0',
        '-show_entries',
        'stream=width,height',
        '-of',
        'csv=p=0:s=x',
        str(image_path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return None, None
    dims = (completed.stdout or '').strip()
    if 'x' not in dims:
        return None, None
    raw_w, raw_h = dims.split('x', 1)
    try:
        return int(raw_w), int(raw_h)
    except ValueError:
        return None, None


def _build_windows(*, frames: list[CommunicationFrameSample], window_size: int) -> list[CommunicationFrameWindow]:
    windows: list[CommunicationFrameWindow] = []
    if not frames:
        return windows
    for start in range(0, len(frames), max(window_size, 1)):
        chunk = frames[start:start + window_size]
        windows.append(
            CommunicationFrameWindow(
                window_id=f'window_{len(windows) + 1}',
                start_ms=chunk[0].timestamp_ms,
                end_ms=chunk[-1].timestamp_ms,
                frame_ids=[frame.frame_id for frame in chunk],
            )
        )
    return windows


def extract_video_frames(
    *,
    media_source: CommunicationMediaSource,
    recording: RecordingRecord,
    sample_every_ms: int = 1500,
    max_frames: int = 12,
    window_size: int = 4,
) -> CommunicationFrameManifestV1:
    ffmpeg_binary = shutil.which('ffmpeg')
    if ffmpeg_binary is None:
        raise HTTPException(status_code=500, detail={'error': 'ffmpeg_not_available_for_frame_extraction'})

    frame_output_dir = Path(tempfile.mkdtemp(prefix='comm_frame_extract_'))
    output_pattern = str(frame_output_dir / 'frame_%03d.jpg')
    fps = 1.0 / max(sample_every_ms / 1000.0, 0.2)
    command = [
        ffmpeg_binary,
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-i',
        str(media_source.local_path),
        '-vf',
        f'fps={fps}',
        '-frames:v',
        str(max_frames),
        output_pattern,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or '').strip()
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'frame_extraction_failed',
                'recording_id': recording.recording_id,
                'reason': stderr or 'ffmpeg_failed',
            },
        ) from exc

    frame_paths = sorted(frame_output_dir.glob('frame_*.jpg'))
    if not frame_paths:
        raise HTTPException(status_code=409, detail={'error': 'frame_extraction_empty_output', 'recording_id': recording.recording_id})

    frames: list[CommunicationFrameSample] = []
    for idx, frame_path in enumerate(frame_paths):
        ts = min(int(idx * sample_every_ms), max(recording.duration_ms - 1, 0))
        byte_size = os.path.getsize(frame_path)
        width, height = _probe_image_dimensions(frame_path)
        quality = 'ok' if byte_size >= 8_000 else 'low_detail'
        frames.append(
            CommunicationFrameSample(
                frame_id=f'frame_{idx + 1:03d}',
                timestamp_ms=ts,
                frame_ref=f'file://{frame_path}',
                width=width,
                height=height,
                byte_size=byte_size,
                quality=quality,
            )
        )

    windows = _build_windows(frames=frames, window_size=window_size)
    return CommunicationFrameManifestV1(
        source_ref=media_source.source_ref,
        sampling_policy={
            'sample_every_ms': sample_every_ms,
            'max_frames': max_frames,
            'window_size': window_size,
            'extractor': 'ffmpeg_fps_sampler',
            'temp_dir': str(frame_output_dir),
        },
        frames=frames,
        windows=windows,
    )
