from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Sequence

from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioPauseEvent,
    CommunicationAudioPitchStats,
    CommunicationAudioRawMetricsV1,
)


def _load_wav_samples(audio_path: Path) -> tuple[list[float], int]:
    with wave.open(str(audio_path), 'rb') as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        raw = wav_file.readframes(frame_count)

    if sample_width == 2:
        fmt = '<h'
        scale = 32768.0
    elif sample_width == 4:
        fmt = '<i'
        scale = 2147483648.0
    else:
        raise ValueError(f'unsupported_sample_width:{sample_width}')

    values = [float(sample[0]) / scale for sample in struct.iter_unpack(fmt, raw)]
    samples = values
    if channels > 1:
        mono: list[float] = []
        for idx in range(0, len(values), channels):
            chunk = values[idx:idx + channels]
            if not chunk:
                continue
            mono.append(sum(chunk) / len(chunk))
        samples = mono
    return samples, sample_rate


def _frame_rms(samples: Sequence[float], frame_size: int) -> list[float]:
    if not samples:
        return []
    usable = (len(samples) // frame_size) * frame_size
    if usable <= 0:
        return []
    rms_values: list[float] = []
    for idx in range(0, usable, frame_size):
        frame = samples[idx:idx + frame_size]
        if not frame:
            continue
        mean_square = sum(sample * sample for sample in frame) / len(frame)
        rms_values.append(math.sqrt(mean_square))
    return rms_values


def extract_pause_metrics(*, rms_values: Sequence[float], frame_ms: int, long_pause_ms: int = 1200) -> tuple[list[CommunicationAudioPauseEvent], int, int]:
    if not rms_values:
        return [], 0, 0

    threshold = max(max(rms_values) * 0.1, 0.005)
    pause_mask = [value <= threshold for value in rms_values]
    events: list[CommunicationAudioPauseEvent] = []
    start_idx: int | None = None
    for idx, is_pause in enumerate(pause_mask):
        if is_pause and start_idx is None:
            start_idx = idx
        elif not is_pause and start_idx is not None:
            end_idx = idx - 1
            duration = (end_idx - start_idx + 1) * frame_ms
            if duration >= 200:
                events.append(
                    CommunicationAudioPauseEvent(
                        start_ms=start_idx * frame_ms,
                        end_ms=(end_idx + 1) * frame_ms,
                        duration_ms=duration,
                    )
                )
            start_idx = None
    if start_idx is not None:
        end_idx = len(pause_mask) - 1
        duration = (end_idx - start_idx + 1) * frame_ms
        if duration >= 200:
            events.append(
                CommunicationAudioPauseEvent(
                    start_ms=start_idx * frame_ms,
                    end_ms=(end_idx + 1) * frame_ms,
                    duration_ms=duration,
                )
            )

    pause_time_ms = int(sum(event.duration_ms for event in events))
    long_pauses = sum(1 for event in events if event.duration_ms >= long_pause_ms)
    return events, pause_time_ms, long_pauses


def extract_speaking_rate(*, transcript_words: int, speaking_time_ms: int) -> float | None:
    if transcript_words <= 0 or speaking_time_ms <= 0:
        return None
    minutes = speaking_time_ms / 60000.0
    if minutes <= 0:
        return None
    return round(transcript_words / minutes, 2)


def _estimate_pitch_for_frame(frame: Sequence[float], sample_rate: int) -> float | None:
    if len(frame) < 2:
        return None
    frame_mean = fmean(frame)
    centered = [sample - frame_mean for sample in frame]
    energy = math.sqrt(sum(sample * sample for sample in centered) / len(centered))
    if energy < 0.01:
        return None
    min_lag = int(sample_rate / 300)
    max_lag = int(sample_rate / 70)
    if max_lag <= min_lag or max_lag >= len(centered):
        return None
    best_lag: int | None = None
    best_value: float | None = None
    for lag in range(min_lag, max_lag):
        corr = 0.0
        for idx in range(0, len(centered) - lag):
            corr += centered[idx] * centered[idx + lag]
        if best_value is None or corr > best_value:
            best_value = corr
            best_lag = lag
    if best_lag is None or best_lag <= 0:
        return None
    return float(sample_rate / best_lag)


def extract_pitch_metrics(*, samples: Sequence[float], sample_rate: int, frame_size: int) -> CommunicationAudioPitchStats:
    usable = (len(samples) // frame_size) * frame_size
    if usable <= 0:
        return CommunicationAudioPitchStats()
    pitches: list[float] = []
    for idx in range(0, usable, frame_size):
        frame = samples[idx:idx + frame_size]
        pitch = _estimate_pitch_for_frame(frame, sample_rate)
        if pitch is not None:
            pitches.append(pitch)
    if not pitches:
        return CommunicationAudioPitchStats()
    return CommunicationAudioPitchStats(
        mean_hz=float(fmean(pitches)),
        median_hz=float(median(pitches)),
        std_hz=float(pstdev(pitches)),
        min_hz=float(min(pitches)),
        max_hz=float(max(pitches)),
        range_hz=float(max(pitches) - min(pitches)),
    )


def extract_energy_metrics(*, rms_values: Sequence[float]) -> CommunicationAudioEnergyStats:
    if not rms_values:
        return CommunicationAudioEnergyStats(rms_mean=0.0, rms_std=0.0, rms_min=0.0, rms_max=0.0)
    return CommunicationAudioEnergyStats(
        rms_mean=float(fmean(rms_values)),
        rms_std=float(pstdev(rms_values)),
        rms_min=float(min(rms_values)),
        rms_max=float(max(rms_values)),
    )


def derive_interpreted_delivery_scales(raw: CommunicationAudioRawMetricsV1) -> CommunicationAudioInterpretedMetricsV1:
    fluency = 3
    pause_control = 3
    expressiveness = 3
    stability = 3

    if raw.pause_ratio > 0.28:
        fluency = 2
        pause_control = 2
    elif raw.pause_ratio < 0.12:
        fluency = 4
        pause_control = 4

    if raw.pitch_stats.std_hz is not None:
        if raw.pitch_stats.std_hz < 18:
            expressiveness = 2
        elif raw.pitch_stats.std_hz > 45:
            expressiveness = 4

    if raw.energy_stats.rms_std < 0.02:
        stability = 2
    elif raw.energy_stats.rms_std < 0.06:
        stability = 4

    return CommunicationAudioInterpretedMetricsV1(
        fluency_1_5=max(1, min(5, fluency)),
        pause_control_1_5=max(1, min(5, pause_control)),
        expressiveness_1_5=max(1, min(5, expressiveness)),
        stability_1_5=max(1, min(5, stability)),
    )


def build_audio_features_real(*, audio_path: Path, transcript_words: int, provider_meta: dict[str, object] | None = None) -> tuple[CommunicationAudioRawMetricsV1, CommunicationAudioInterpretedMetricsV1, list[str]]:
    samples, sample_rate = _load_wav_samples(audio_path)
    frame_ms = 20
    frame_size = max(int(sample_rate * (frame_ms / 1000.0)), 1)
    rms_values = _frame_rms(samples, frame_size)
    events, pause_time_ms, long_pauses = extract_pause_metrics(rms_values=rms_values, frame_ms=frame_ms)
    total_time_ms = int((len(samples) / max(sample_rate, 1)) * 1000)
    speaking_time_ms = max(total_time_ms - pause_time_ms, 0)
    speech_rate = extract_speaking_rate(transcript_words=transcript_words, speaking_time_ms=speaking_time_ms)
    pitch_stats = extract_pitch_metrics(samples=samples, sample_rate=sample_rate, frame_size=frame_size)
    energy_stats = extract_energy_metrics(rms_values=rms_values)
    voiced_ratio = None
    if rms_values:
        voiced_threshold = max(max(rms_values) * 0.1, 0.005)
        voiced_count = sum(1 for sample in rms_values if sample > voiced_threshold)
        voiced_ratio = round(float(voiced_count / len(rms_values)), 4)

    pause_mean = None if not events else round(sum(event.duration_ms for event in events) / len(events), 2)
    pause_max = None if not events else max(event.duration_ms for event in events)
    pause_ratio = round((pause_time_ms / max(total_time_ms, 1)), 4)

    raw = CommunicationAudioRawMetricsV1(
        pause_events=events,
        speech_rate_wpm=speech_rate,
        speaking_time_ms=speaking_time_ms,
        pause_time_ms=pause_time_ms,
        pause_ratio=pause_ratio,
        pause_mean_ms=pause_mean,
        pause_max_ms=pause_max,
        long_pauses_count=long_pauses,
        pitch_stats=pitch_stats,
        energy_stats=energy_stats,
        voiced_ratio=voiced_ratio,
    )
    interpreted = derive_interpreted_delivery_scales(raw)
    quality_flags: list[str] = []
    clipping_ratio = (sum(1 for sample in samples if abs(sample) >= 0.99) / len(samples)) if samples else 0.0
    if clipping_ratio > 0.02:
        quality_flags.append('possible_clipping')
    if raw.voiced_ratio is not None and raw.voiced_ratio < 0.35:
        quality_flags.append('low_voiced_ratio')
    if raw.speech_rate_wpm is None:
        quality_flags.append('speech_rate_unavailable')
    if provider_meta and provider_meta.get('source') == 'fallback_placeholder':
        quality_flags.append('provider_fallback_detected')
    return raw, interpreted, quality_flags
