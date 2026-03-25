from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException

from evaluacion.contracts.communication_models import CommunicationTranscriptRealV1, CommunicationTranscriptSegment


class CommunicationSttProvider(Protocol):
    provider_name: str

    def transcribe(self, *, audio_path: Path, language_hint: str = 'es') -> CommunicationTranscriptRealV1:
        ...


@dataclass(frozen=True)
class CommunicationTranscriptArtifact:
    transcript: CommunicationTranscriptRealV1
    storage_ref: str
    content_hash: str | None = None


class MockWordTimedSttProvider:
    provider_name = 'mock_word_timed_stt'

    def transcribe(self, *, audio_path: Path, language_hint: str = 'es') -> CommunicationTranscriptRealV1:
        base_text = f'Transcripción real de prueba generada desde {audio_path.name}.'
        return CommunicationTranscriptRealV1(
            provider=self.provider_name,
            language=language_hint,
            full_text=base_text,
            segments=[
                CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1800, text=base_text),
            ],
            confidence_global=0.9,
            quality_flags=[],
            explanation='Provider mockeable para entornos de test sin credenciales externas.',
        )


class OpenAiWhisperSttProvider:
    provider_name = 'openai_whisper_api'

    def __init__(self, *, model: str = 'gpt-4o-mini-transcribe') -> None:
        self._model = model

    def transcribe(self, *, audio_path: Path, language_hint: str = 'es') -> CommunicationTranscriptRealV1:
        api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
        if not api_key:
            raise HTTPException(status_code=500, detail={'error': 'stt_provider_not_configured', 'provider': self.provider_name})
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - dependency optional in runtime env
            raise HTTPException(status_code=500, detail={'error': 'openai_sdk_not_available_for_stt'}) from exc

        client = OpenAI(api_key=api_key)
        try:
            with audio_path.open('rb') as stream:
                response = client.audio.transcriptions.create(
                    model=self._model,
                    file=stream,
                    language=language_hint,
                    response_format='verbose_json',
                )
        except Exception as exc:
            if _is_unsupported_verbose_json_error(exc):
                try:
                    with audio_path.open('rb') as stream:
                        response = client.audio.transcriptions.create(
                            model=self._model,
                            file=stream,
                            language=language_hint,
                            response_format='json',
                        )
                except Exception as retry_exc:
                    raise _map_openai_stt_error(retry_exc, provider=self.provider_name, model=self._model) from retry_exc
            else:
                raise _map_openai_stt_error(exc, provider=self.provider_name, model=self._model) from exc

        payload = response.model_dump() if hasattr(response, 'model_dump') else dict(response)  # type: ignore[arg-type]
        return normalize_openai_transcript(payload, provider=self.provider_name, language_hint=language_hint)


def _is_unsupported_verbose_json_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        'response_format' in message
        and 'verbose_json' in message
        and ('unsupported_value' in message or 'not compatible' in message)
    )


def _map_openai_stt_error(exc: Exception, *, provider: str, model: str) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            'error': 'stt_provider_request_failed',
            'provider': provider,
            'model': model,
            'reason': str(exc),
        },
    )


def normalize_openai_transcript(payload: dict[str, Any], *, provider: str, language_hint: str = 'es') -> CommunicationTranscriptRealV1:
    text = str(payload.get('text') or '').strip()
    language = str(payload.get('language') or language_hint or 'es')
    segments_raw = payload.get('segments')
    segments: list[CommunicationTranscriptSegment] = []
    if isinstance(segments_raw, list):
        for idx, item in enumerate(segments_raw, start=1):
            if not isinstance(item, dict):
                continue
            start_sec = float(item.get('start') or 0.0)
            end_sec = float(item.get('end') or start_sec)
            seg_text = str(item.get('text') or '').strip()
            segments.append(
                CommunicationTranscriptSegment(
                    segment_index=idx,
                    start_ms=max(int(round(start_sec * 1000)), 0),
                    end_ms=max(int(round(end_sec * 1000)), max(int(round(start_sec * 1000)), 0)),
                    text=seg_text,
                )
            )

    if not segments and text:
        segments = [CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1000, text=text)]

    if not text:
        raise HTTPException(status_code=409, detail={'error': 'stt_empty_transcript', 'provider': provider})

    quality_flags: list[str] = []
    if not segments:
        quality_flags.append('segments_missing')

    return CommunicationTranscriptRealV1(
        provider=provider,
        language=language,
        full_text=text,
        segments=segments,
        confidence_global=None,
        quality_flags=quality_flags,
        explanation='Transcripción obtenida desde proveedor STT real.',
    )


def normalize_openai_verbose_transcript(payload: dict[str, Any], *, provider: str, language_hint: str = 'es') -> CommunicationTranscriptRealV1:
    return normalize_openai_transcript(payload, provider=provider, language_hint=language_hint)


def resolve_stt_provider() -> CommunicationSttProvider:
    configured = (os.getenv('COMMUNICATION_STT_PROVIDER') or '').strip().lower()
    if configured in ('mock', 'mock_word_timed_stt'):
        return MockWordTimedSttProvider()
    return OpenAiWhisperSttProvider()


def transcribe_audio(*, audio_path: Path, language_hint: str = 'es', provider: CommunicationSttProvider | None = None) -> CommunicationTranscriptArtifact:
    active_provider = provider or resolve_stt_provider()
    transcript = active_provider.transcribe(audio_path=audio_path, language_hint=language_hint)
    return CommunicationTranscriptArtifact(
        transcript=transcript,
        storage_ref=f'memory://stt/{active_provider.provider_name}/{audio_path.name}',
        content_hash=None,
    )
