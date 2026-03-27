from __future__ import annotations

from pathlib import Path

from evaluacion.contracts.communication_models import (
    CommunicationFrameManifestV1,
    CommunicationVisualBatchEvalInputV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualBatchFrameRefV1,
    CommunicationVisualSamplingStrategyV1,
)
from evaluacion.engine.communication_visual_config import (
    COMM_VISUAL_BATCH_TARGET,
    COMM_VISUAL_MAX_FRAMES,
    COMM_VISUAL_TAIL_MIN,
    get_visual_openai_max_retries,
    get_visual_openai_model,
    get_visual_openai_timeout_s,
)
from evaluacion.engine.communication_visual_openai_client import run_visual_batch_openai
from evaluacion.engine.communication_visual_sampling import partition_frame_batches, select_uniform_indices
from evaluacion.engine.runners.common import load_prompt_text

_BATCH_PROMPT_PATH = Path(__file__).resolve().parent.parent / 'prompts' / 'communication_visual_batch_evaluator_prompt.txt'

_DEFAULT_RUBRIC = {
    'hand_use': 'Evalúa visibilidad y uso de manos (1-5).',
    'facial_expression': 'Evalúa expresividad facial observable (1-5).',
    'posture_openness': 'Evalúa postura y apertura corporal visible (1-5).',
    'visual_support': 'Evalúa apoyo visual visible del mensaje (1-5).',
}


def build_visual_batch_inputs_from_manifest(
    *,
    evaluation_id: str,
    recording_id: str,
    video_duration_ms: int,
    manifest: CommunicationFrameManifestV1,
    max_frames: int = COMM_VISUAL_MAX_FRAMES,
    batch_target: int = COMM_VISUAL_BATCH_TARGET,
    min_tail_batch: int = COMM_VISUAL_TAIL_MIN,
) -> list[CommunicationVisualBatchEvalInputV1]:
    frames = sorted(manifest.frames, key=lambda item: item.timestamp_ms)
    if not frames:
        return []

    selected_indices = select_uniform_indices(total_candidates=len(frames), max_frames=max_frames)
    selected_frames = [frames[index] for index in selected_indices]
    partitions = partition_frame_batches(selected_frames, target_batch_size=batch_target, min_tail_batch=min_tail_batch)

    sampling_strategy = CommunicationVisualSamplingStrategyV1(
        max_frames=max_frames,
        batch_target=batch_target,
        tail_merge_threshold=min_tail_batch,
    )

    total_batches = len(partitions)
    out: list[CommunicationVisualBatchEvalInputV1] = []
    for idx, partition in enumerate(partitions, start=1):
        batch_frames = [
            CommunicationVisualBatchFrameRefV1(
                frame_id=frame.frame_id,
                timestamp_ms=frame.timestamp_ms,
                frame_ref=frame.frame_ref,
            )
            for frame in partition
        ]
        out.append(
            CommunicationVisualBatchEvalInputV1(
                evaluation_id=evaluation_id,
                recording_id=recording_id,
                batch_index=idx,
                total_batches=total_batches,
                video_duration_ms=video_duration_ms,
                sampling_strategy=sampling_strategy,
                frames=batch_frames,
                rubric=dict(_DEFAULT_RUBRIC),
            )
        )
    return out


def evaluate_visual_batches_openai(
    *,
    batch_inputs: list[CommunicationVisualBatchEvalInputV1],
    model: str | None = None,
    timeout_s: float | None = None,
    max_retries: int | None = None,
) -> list[CommunicationVisualBatchEvalV2]:
    if not batch_inputs:
        return []

    developer_prompt = load_prompt_text(_BATCH_PROMPT_PATH)
    selected_model = model or get_visual_openai_model()
    selected_timeout = timeout_s if timeout_s is not None else get_visual_openai_timeout_s()
    selected_retries = max_retries if max_retries is not None else get_visual_openai_max_retries()

    outputs: list[CommunicationVisualBatchEvalV2] = []
    for batch_input in batch_inputs:
        outputs.append(
            run_visual_batch_openai(
                batch_input=batch_input,
                developer_prompt=developer_prompt,
                model=selected_model,
                timeout_s=selected_timeout,
                max_retries=selected_retries,
            )
        )
    return outputs
