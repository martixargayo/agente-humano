from __future__ import annotations

from evaluacion.contracts.models import DomainContext
from evaluacion.domains.conversacion_simple.assets_loader import resolve_conversacion_simple_evaluation_assets


def test_conversacion_simple_assets_load_from_context_evaluation_dir() -> None:
    assets = resolve_conversacion_simple_evaluation_assets(
        DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='baseline', context_version='1.0.0')
    )

    assert assets.context_id == 'baseline'
    assert assets.resolution_source == 'context_evaluation_assets'
    assert assets.fallback_used is False
    assert 'conversacion_simple/contexts/baseline/evaluation' in str(assets.core_prompt_path)


def test_conversacion_simple_assets_reject_flow_mismatch() -> None:
    try:
        resolve_conversacion_simple_evaluation_assets(
            DomainContext(domain='conversacion_simple', flow_id='negociacion', context_id='baseline', context_version='1.0.0')
        )
        assert False, 'expected flow mismatch error'
    except RuntimeError as exc:
        assert 'evaluation_flow_context_mismatch' in str(exc)


def test_conversacion_simple_assets_fallback_when_context_assets_missing(monkeypatch) -> None:
    from types import SimpleNamespace
    from pathlib import Path

    from evaluacion.domains.conversacion_simple import assets_loader as mod

    fake = SimpleNamespace(flow_id='conversacion_simple', context_id='baseline', context_version='1.0.0', context_dir=Path('/tmp/context_without_eval'))
    monkeypatch.setattr(mod, 'resolve_conversacion_simple_context', lambda context_id: fake)
    monkeypatch.setattr(mod, 'resolve_default_conversacion_simple_context', lambda: fake)
    mod._resolve_assets_for_context_id.cache_clear()

    assets = mod.resolve_conversacion_simple_evaluation_assets(
        DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='baseline', context_version='1.0.0')
    )

    assert assets.resolution_source == 'legacy_fallback'
    assert assets.fallback_used is True
