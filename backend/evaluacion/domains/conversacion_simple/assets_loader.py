from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from conversacion_simple.contexts import resolve_conversacion_simple_context, resolve_default_conversacion_simple_context

from evaluacion.contracts.models import DomainContext

from .context_resolver import ConversationSimpleEvaluationContext, resolve_evaluation_context_from_domain_context

LEGACY_EVALUATION_DIR = Path(__file__).resolve().parents[2] / 'prompts'
LEGACY_RUBRIC_PATH = Path(__file__).resolve().parents[1] / 'negotiation' / 'rubrics' / 'negotiation_rubric_v1.json'


class ConversationSimpleEvaluationAssets(BaseModel):
    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

    flow_id: str
    context_id: str
    context_version: str
    core_prompt_path: Path
    trajectory_prompt_path: Path
    rubric_path: Path
    resolution_source: str
    fallback_used: bool = False


@lru_cache(maxsize=8)
def _resolve_assets_for_context_id(context_id: str) -> ConversationSimpleEvaluationAssets:
    resolved = resolve_conversacion_simple_context(context_id) if context_id else resolve_default_conversacion_simple_context()
    evaluation_dir = resolved.context_dir / 'evaluation'
    core_prompt_path = evaluation_dir / 'core_evaluator_prompt.txt'
    trajectory_prompt_path = evaluation_dir / 'trajectory_evaluator_prompt.txt'
    rubric_path = evaluation_dir / 'rubric.json'

    if core_prompt_path.exists() and trajectory_prompt_path.exists() and rubric_path.exists():
        return ConversationSimpleEvaluationAssets(
            flow_id=resolved.flow_id,
            context_id=resolved.context_id,
            context_version=resolved.context_version,
            core_prompt_path=core_prompt_path,
            trajectory_prompt_path=trajectory_prompt_path,
            rubric_path=rubric_path,
            resolution_source='context_evaluation_assets',
            fallback_used=False,
        )

    return ConversationSimpleEvaluationAssets(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=resolved.context_version,
        core_prompt_path=LEGACY_EVALUATION_DIR / 'core_evaluator_prompt.txt',
        trajectory_prompt_path=LEGACY_EVALUATION_DIR / 'trajectory_evaluator_prompt.txt',
        rubric_path=LEGACY_RUBRIC_PATH,
        resolution_source='legacy_fallback',
        fallback_used=True,
    )


def resolve_conversacion_simple_evaluation_assets(domain_context: DomainContext | None) -> ConversationSimpleEvaluationAssets:
    context: ConversationSimpleEvaluationContext = resolve_evaluation_context_from_domain_context(domain_context)
    assets = _resolve_assets_for_context_id(context.context_id)
    return assets.model_copy(update={
        'flow_id': context.flow_id or assets.flow_id,
        'context_id': context.context_id,
        'context_version': context.context_version or assets.context_version,
    })
