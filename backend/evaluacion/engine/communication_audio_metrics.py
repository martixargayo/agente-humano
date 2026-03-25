from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable

import numpy as np

from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioPauseEvent,
    CommunicationAudioPitchStats,
    CommunicationAudioRawMetricsV1,
)


def _load_wav_samples(audio_path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(audio_path), 'rb') as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        raw = wav_file.readframes(frame_count)

    if sample_width == 2:
        dtype = np.int16
        scale = 32768.0
    elif sample_width == 4:
        dtype = np.int32
        scale = 2147483648.0
    else:
        raise ValueError(f'unsupported_sample_width:{sample_width}')

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    samples = samples / scale
    return samples, sample_rate


def _frame_rms(samples: np.ndarray, frame_size: int) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    usable = (samples.size // frame_size) * frame_size
    if usable <= 0:
        return np.zeros(0, dtype=np.float32)
    framed = samples[:usable].reshape(-1, frame_size)
    return np.sqrt(np.mean(np.square(framed), axis=1))


def extract_pause_metrics(*, rms_values: np.ndarray, frame_ms: int, long_pause_ms: int = 1200) -> tuple[list[CommunicationAudioPauseEvent], int, int]:
    if rms_values.size == 0:
        return [], 0, 0

    threshold = max(float(np.max(rms_values)) * 0.1, 0.005)
    pause_mask = rms_values <= threshold
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


def _estimate_pitch_for_frame(frame: np.ndarray, sample_rate: int) -> float | None:
    if frame.size < 2:
        return None
    frame = frame - np.mean(frame)
    energy = float(np.sqrt(np.mean(np.square(frame))))
    if energy < 0.01:
        return None
    corr = np.correlate(frame, frame, mode='full')[frame.size - 1:]
    min_lag = int(sample_rate / 300)
    max_lag = int(sample_rate / 70)
    if max_lag <= min_lag or max_lag >= corr.size:
        return None
    window = corr[min_lag:max_lag]
    if window.size == 0:
        return None
    lag = int(np.argmax(window)) + min_lag
    if lag <= 0:
        return None
    return float(sample_rate / lag)


def extract_pitch_metrics(*, samples: np.ndarray, sample_rate: int, frame_size: int) -> CommunicationAudioPitchStats:
    usable = (samples.size // frame_size) * frame_size
    if usable <= 0:
        return CommunicationAudioPitchStats()
    framed = samples[:usable].reshape(-1, frame_size)
    pitches = [pitch for pitch in (_estimate_pitch_for_frame(frame, sample_rate) for frame in framed) if pitch is not None]
    if not pitches:
        return CommunicationAudioPitchStats()
    arr = np.array(pitches, dtype=np.float32)
    return CommunicationAudioPitchStats(
        mean_hz=float(np.mean(arr)),
        median_hz=float(np.median(arr)),
        std_hz=float(np.std(arr)),
        min_hz=float(np.min(arr)),
        max_hz=float(np.max(arr)),
        range_hz=float(np.max(arr) - np.min(arr)),
    )


def extract_energy_metrics(*, rms_values: np.ndarray) -> CommunicationAudioEnergyStats:
    if rms_values.size == 0:
        return CommunicationAudioEnergyStats(rms_mean=0.0, rms_std=0.0, rms_min=0.0, rms_max=0.0)
    return CommunicationAudioEnergyStats(
        rms_mean=float(np.mean(rms_values)),
        rms_std=float(np.std(rms_values)),
        rms_min=float(np.min(rms_values)),
        rms_max=float(np.max(rms_values)),
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
    total_time_ms = int((samples.size / max(sample_rate, 1)) * 1000)
    speaking_time_ms = max(total_time_ms - pause_time_ms, 0)
    speech_rate = extract_speaking_rate(transcript_words=transcript_words, speaking_time_ms=speaking_time_ms)
    pitch_stats = extract_pitch_metrics(samples=samples, sample_rate=sample_rate, frame_size=frame_size)
    energy_stats = extract_energy_metrics(rms_values=rms_values)
    voiced_ratio = None
    if rms_values.size > 0:
        voiced_ratio = round(float(np.sum(rms_values > max(float(np.max(rms_values)) * 0.1, 0.005)) / rms_values.size), 4)

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
    clipping_ratio = float(np.mean(np.abs(samples) >= 0.99)) if samples.size > 0 else 0.0
    if clipping_ratio > 0.02:
        quality_flags.append('possible_clipping')
    if raw.voiced_ratio is not None and raw.voiced_ratio < 0.35:
        quality_flags.append('low_voiced_ratio')
    if raw.speech_rate_wpm is None:
        quality_flags.append('speech_rate_unavailable')
    if provider_meta and provider_meta.get('source') == 'fallback_placeholder':
        quality_flags.append('provider_fallback_detected')
    return raw, interpreted, quality_flags
