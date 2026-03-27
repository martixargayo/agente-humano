from __future__ import annotations

import json
from pathlib import Path

import openai

from evaluacion.contracts.communication_models import CommunicationVisualBatchEvalV2, CommunicationVisualFinalEvalV1
from evaluacion.engine.communication_visual_config import (
    get_visual_openai_max_retries,
    get_visual_openai_model,
    get_visual_openai_timeout_s,
)
from evaluacion.engine.communication_visual_openai_client import CommunicationVisualLlmError, _build_openai_client
from evaluacion.engine.runners.common import load_prompt_text

_SYNTHESIS_PROMPT_PATH = Path(__file__).resolve().parent.parent / 'prompts' / 'communication_visual_synthesis_prompt.txt'


def build_visual_synthesis_input(
    *,
    evaluation_id: str,
    recording_id: str,
    video_duration_ms: int,
    batch_outputs: list[CommunicationVisualBatchEvalV2],
) -> dict[str, object]:
    return {
        'evaluation_id': evaluation_id,
        'recording_id': recording_id,
        'video_duration_ms': video_duration_ms,
        'batch_count': len(batch_outputs),
        'batch_outputs': [item.model_dump(mode='json') for item in batch_outputs],
    }


def run_visual_synthesis_openai(
    *,
    evaluation_id: str,
    recording_id: str,
    video_duration_ms: int,
    batch_outputs: list[CommunicationVisualBatchEvalV2],
    model: str | None = None,
    timeout_s: float | None = None,
    max_retries: int | None = None,
    client: openai.OpenAI | None = None,
) -> CommunicationVisualFinalEvalV1:
    if not batch_outputs:
        raise CommunicationVisualLlmError(kind='schema', message='cannot_synthesize_without_batches')

    prompt = load_prompt_text(_SYNTHESIS_PROMPT_PATH)
    payload = build_visual_synthesis_input(
        evaluation_id=evaluation_id,
        recording_id=recording_id,
        video_duration_ms=video_duration_ms,
        batch_outputs=batch_outputs,
    )
    schema = CommunicationVisualFinalEvalV1.model_json_schema()

    selected_model = model or get_visual_openai_model()
    selected_timeout = timeout_s if timeout_s is not None else get_visual_openai_timeout_s()
    selected_retries = max_retries if max_retries is not None else get_visual_openai_max_retries()
    openai_client = client or _build_openai_client()

    attempts = selected_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            response = openai_client.responses.create(
                model=selected_model,
                input=[
                    {'role': 'developer', 'content': prompt},
                    {'role': 'user', 'content': f'BEGIN_INPUT_JSON\n{json.dumps(payload, ensure_ascii=False)}\nEND_INPUT_JSON'},
                ],
                text={
                    'format': {
                        'type': 'json_schema',
                        'name': 'communication_visual_final_eval_v1',
                        'schema': schema,
                        'strict': True,
                    }
                },
                store=False,
                timeout=selected_timeout,
            )
            raw = getattr(response, 'output_text', '') or '{}'
            parsed = json.loads(raw)
            return CommunicationVisualFinalEvalV1.model_validate(parsed)
        except json.JSONDecodeError as exc:
            raise CommunicationVisualLlmError(kind='schema', message=f'visual_synthesis_json_decode_failed:{exc}') from exc
        except CommunicationVisualLlmError:
            raise
        except Exception as exc:  # pragma: no cover - sdk dependent
            if attempt < attempts and any(marker in str(exc).lower() for marker in ('timeout', 'rate', '429', 'temporar', '503', '502', '504')):
                continue
            kind = 'transient' if any(marker in str(exc).lower() for marker in ('timeout', 'rate', '429', 'temporar', '503', '502', '504')) else 'schema'
            raise CommunicationVisualLlmError(kind=kind, message=f'visual_synthesis_failed:{exc}') from exc

    raise CommunicationVisualLlmError(kind='transient', message='visual_synthesis_failed_retries_exhausted')
