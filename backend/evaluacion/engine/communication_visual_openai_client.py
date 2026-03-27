from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import openai

from evaluacion.contracts.communication_models import CommunicationVisualBatchEvalInputV1, CommunicationVisualBatchEvalV2
from evaluacion.engine.communication_visual_config import COMM_VISUAL_DETAIL


class CommunicationVisualLlmError(RuntimeError):
    def __init__(self, *, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


_MAX_FRAME_BYTES = 220 * 1024
_MAX_BATCH_BYTES = int(5.5 * 1024 * 1024)
_MAX_BATCH_SERIALIZED_BYTES = int(7.5 * 1024 * 1024)
_MIN_USABLE_FRAMES_PER_BATCH = 6


def _build_openai_client() -> openai.OpenAI:
    api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise CommunicationVisualLlmError(kind='config', message='missing_openai_api_key')
    try:
        return openai.OpenAI(api_key=api_key)
    except Exception as exc:  # pragma: no cover - sdk dependent
        raise CommunicationVisualLlmError(kind='config', message=f'openai_client_init_failed:{exc}') from exc


def _resolve_frame_local_path(frame_ref: str) -> Path:
    parsed = urlparse((frame_ref or '').strip())
    if parsed.scheme in ('', 'file'):
        path = Path(parsed.path if parsed.scheme == 'file' else frame_ref).expanduser()
        if path.exists() and path.is_file():
            return path.resolve()
    raise CommunicationVisualLlmError(kind='serialization', message=f'frame_ref_not_accessible:{frame_ref}')


def _transcode_with_ffmpeg(*, source_path: Path, max_side: int, quality_qscale: int) -> bytes:
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise CommunicationVisualLlmError(kind='serialization', message='ffmpeg_missing_for_frame_normalization')
    with tempfile.TemporaryDirectory(prefix='comm_visual_frame_') as tmpdir:
        output_path = Path(tmpdir) / 'normalized.jpg'
        scale_filter = (
            f"scale='if(gte(iw,ih),min(iw,{max_side}),-2)':"
            f"'if(gte(iw,ih),-2,min(ih,{max_side}))'"
        )
        command = [
            ffmpeg,
            '-hide_banner',
            '-loglevel',
            'error',
            '-y',
            '-i',
            str(source_path),
            '-vf',
            scale_filter,
            '-q:v',
            str(quality_qscale),
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise CommunicationVisualLlmError(kind='serialization', message=f'frame_ffmpeg_transcode_failed:{exc.stderr or exc}') from exc
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise CommunicationVisualLlmError(kind='serialization', message='frame_transcode_empty')
        return output_path.read_bytes()


def _load_and_normalize_frame_as_data_url(frame_ref: str) -> tuple[str, int]:
    source_path = _resolve_frame_local_path(frame_ref)
    attempts = [
        (960, 5),
        (800, 7),
        (640, 9),
    ]
    last_size = 0
    for max_side, qscale in attempts:
        payload = _transcode_with_ffmpeg(source_path=source_path, max_side=max_side, quality_qscale=qscale)
        last_size = len(payload)
        if last_size <= _MAX_FRAME_BYTES:
            encoded = base64.b64encode(payload).decode('ascii')
            return f'data:image/jpeg;base64,{encoded}', last_size
    raise CommunicationVisualLlmError(kind='serialization', message=f'frame_oversize_after_normalization:{last_size}')


def _build_multimodal_input_for_batch(*, batch_input: CommunicationVisualBatchEvalInputV1, developer_prompt: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    usable_frames: list[dict[str, Any]] = []
    total_binary_bytes = 0
    total_serialized_bytes = 0
    dropped_frames = 0

    for frame in batch_input.frames:
        try:
            image_data_url, frame_bytes = _load_and_normalize_frame_as_data_url(frame.frame_ref)
        except CommunicationVisualLlmError:
            dropped_frames += 1
            continue

        tentative_binary = total_binary_bytes + frame_bytes
        tentative_serialized = total_serialized_bytes + len(image_data_url.encode('utf-8'))
        if tentative_binary > _MAX_BATCH_BYTES or tentative_serialized > _MAX_BATCH_SERIALIZED_BYTES:
            dropped_frames += 1
            continue

        usable_frames.append(
            {
                'frame_id': frame.frame_id,
                'timestamp_ms': frame.timestamp_ms,
                'image_data_url': image_data_url,
            }
        )
        total_binary_bytes = tentative_binary
        total_serialized_bytes = tentative_serialized

    if len(usable_frames) < _MIN_USABLE_FRAMES_PER_BATCH:
        raise CommunicationVisualLlmError(
            kind='payload',
            message=(
                f'batch_usable_frames_below_threshold:{len(usable_frames)}<'
                f'{_MIN_USABLE_FRAMES_PER_BATCH};dropped={dropped_frames}'
            ),
        )

    payload_summary = {
        'frames_total': len(batch_input.frames),
        'frames_usable': len(usable_frames),
        'dropped_frames': dropped_frames,
        'binary_bytes': total_binary_bytes,
        'serialized_bytes': total_serialized_bytes,
    }

    user_payload = {
        'evaluation_id': batch_input.evaluation_id,
        'recording_id': batch_input.recording_id,
        'batch_index': batch_input.batch_index,
        'total_batches': batch_input.total_batches,
        'video_duration_ms': batch_input.video_duration_ms,
        'sampling_strategy': batch_input.sampling_strategy.model_dump(mode='json'),
        'rubric': dict(batch_input.rubric),
        'frame_coverage_summary_hint': {
            'frames_total': len(batch_input.frames),
            'frames_usable': len(usable_frames),
        },
        'frames': [
            {
                'frame_id': item['frame_id'],
                'timestamp_ms': item['timestamp_ms'],
                'detail': COMM_VISUAL_DETAIL,
            }
            for item in usable_frames
        ],
    }

    content: list[dict[str, Any]] = [
        {'type': 'input_text', 'text': f'BEGIN_INPUT_JSON\n{json.dumps(user_payload, ensure_ascii=False)}\nEND_INPUT_JSON'}
    ]
    for item in usable_frames:
        content.append({'type': 'input_image', 'image_url': item['image_data_url'], 'detail': COMM_VISUAL_DETAIL})

    message_input = [
        {'role': 'developer', 'content': developer_prompt},
        {'role': 'user', 'content': content},
    ]
    return message_input, payload_summary


def _is_transient_error(exc: Exception) -> bool:
    lower = str(exc).lower()
    return any(marker in lower for marker in ('timeout', 'rate', '429', 'temporar', 'connection', '503', '502', '504'))


def run_visual_batch_openai(
    *,
    batch_input: CommunicationVisualBatchEvalInputV1,
    developer_prompt: str,
    model: str,
    timeout_s: float,
    max_retries: int,
    client: openai.OpenAI | None = None,
) -> CommunicationVisualBatchEvalV2:
    message_input, _summary = _build_multimodal_input_for_batch(batch_input=batch_input, developer_prompt=developer_prompt)
    openai_client = client or _build_openai_client()
    schema = CommunicationVisualBatchEvalV2.model_json_schema()

    attempts = max_retries + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = openai_client.responses.create(
                model=model,
                input=message_input,
                text={
                    'format': {
                        'type': 'json_schema',
                        'name': 'communication_visual_batch_eval_v2',
                        'schema': schema,
                        'strict': True,
                    }
                },
                store=False,
                timeout=timeout_s,
            )
            raw_text = getattr(response, 'output_text', '') or '{}'
            parsed = json.loads(raw_text)
            return CommunicationVisualBatchEvalV2.model_validate(parsed)
        except CommunicationVisualLlmError:
            raise
        except json.JSONDecodeError as exc:
            raise CommunicationVisualLlmError(kind='schema', message=f'batch_output_json_decode_failed:{exc}') from exc
        except Exception as exc:  # pragma: no cover - runtime/sdk dependent
            last_error = exc
            if _is_transient_error(exc) and attempt < attempts:
                time.sleep(0.25 * attempt)
                continue
            kind = 'transient' if _is_transient_error(exc) else 'schema'
            raise CommunicationVisualLlmError(kind=kind, message=f'openai_batch_request_failed:{exc}') from exc

    raise CommunicationVisualLlmError(kind='transient', message=f'openai_batch_request_failed:{last_error}')
