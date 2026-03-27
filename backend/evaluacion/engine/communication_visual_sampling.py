from __future__ import annotations

from math import floor
from typing import TypeVar

T = TypeVar('T')


def build_candidate_timestamps_1fps(duration_ms: int) -> list[int]:
    """Build deterministic 1fps candidate timestamps from a recording duration.

    Policy (from planning addendum):
    - N_raw = floor(duration_ms / 1000)
    - N = max(1, N_raw)
    - timestamps = [i * 1000 for i in range(N)]

    A partial final second does not create an extra candidate frame.
    """

    if duration_ms < 0:
        raise ValueError('duration_ms_must_be_non_negative')
    total_candidates = max(1, duration_ms // 1000)
    return [index * 1000 for index in range(total_candidates)]


def _nearest_available_index(*, target: int, total_candidates: int, used: set[int]) -> int | None:
    if target not in used and 0 <= target < total_candidates:
        return target
    for radius in range(1, total_candidates + 1):
        left = target - radius
        if 0 <= left < total_candidates and left not in used:
            return left
        right = target + radius
        if 0 <= right < total_candidates and right not in used:
            return right
    return None


def select_uniform_indices(total_candidates: int, max_frames: int = 90) -> list[int]:
    """Select uniform indices using center-bin sampling with defensive de-dup fill.

    - If total_candidates <= max_frames -> [0..N-1]
    - Else K=max_frames, idx_j=floor((j+0.5) * N / K)
    - Defensive pass ensures exactly K unique indices.
    """

    if total_candidates <= 0:
        raise ValueError('total_candidates_must_be_positive')
    if max_frames <= 0:
        raise ValueError('max_frames_must_be_positive')

    if total_candidates <= max_frames:
        return list(range(total_candidates))

    desired = max_frames
    raw_indices = [min(max(floor((position + 0.5) * total_candidates / desired), 0), total_candidates - 1) for position in range(desired)]
    raw_indices[0] = 0

    selected: list[int] = []
    used: set[int] = set()
    for index in raw_indices:
        resolved = _nearest_available_index(target=index, total_candidates=total_candidates, used=used)
        if resolved is None:
            continue
        selected.append(resolved)
        used.add(resolved)

    if len(selected) < desired:
        for candidate in range(total_candidates):
            if candidate in used:
                continue
            selected.append(candidate)
            used.add(candidate)
            if len(selected) == desired:
                break

    selected.sort()
    return selected[:desired]


def select_uniform_timestamps_from_candidates(candidate_timestamps: list[int], max_frames: int = 90) -> list[int]:
    """Select uniformly-distributed timestamps from precomputed candidates."""

    if not candidate_timestamps:
        raise ValueError('candidate_timestamps_must_not_be_empty')
    indices = select_uniform_indices(total_candidates=len(candidate_timestamps), max_frames=max_frames)
    return [candidate_timestamps[index] for index in indices]


def partition_frame_batches(frames: list[T], target_batch_size: int = 30, min_tail_batch: int = 6) -> list[list[T]]:
    """Partition frames into batches and merge small tail (< min_tail_batch).

    Rules:
    - chunks of target_batch_size
    - if final remainder < min_tail_batch and there is a previous chunk, merge it into previous
    """

    if target_batch_size <= 0:
        raise ValueError('target_batch_size_must_be_positive')
    if min_tail_batch <= 0:
        raise ValueError('min_tail_batch_must_be_positive')

    chunks = [frames[index:index + target_batch_size] for index in range(0, len(frames), target_batch_size)]
    if len(chunks) >= 2 and len(chunks[-1]) < min_tail_batch:
        chunks[-2].extend(chunks[-1])
        chunks.pop()
    return chunks
