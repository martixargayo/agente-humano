from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelComponentConfig:
    model: str
    temperature: float
    timeout_s: int
    max_tokens: int
    top_p: float
    presence_penalty: float
    frequency_penalty: float
    retries: int
    structured_output: bool = False
    response_format: str | None = None
    streaming: bool = False
    reasoning_effort: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class EmbeddingsConfig:
    model: str


@dataclass(frozen=True)
class NegotiationModelConfig:
    world: ModelComponentConfig
    belief: ModelComponentConfig
    planner: ModelComponentConfig
    summary: ModelComponentConfig
    executor: ModelComponentConfig
    embeddings: EmbeddingsConfig
    rag_dir: str


def _read_env(
    key: str,
    default: Any,
    cast: Callable[[str], Any],
    *,
    legacy: tuple[str, ...] = (),
    deprecation_warnings: list[str],
) -> Any:
    if key in os.environ:
        return cast(os.environ[key])
    for legacy_key in legacy:
        if legacy_key in os.environ:
            deprecation_warnings.append(
                f"{legacy_key} is deprecated for negotiation model config; use {key} instead."
            )
            return cast(os.environ[legacy_key])
    return default


def _read_component(
    name: str,
    *,
    default_model: str,
    default_temperature: float,
    default_timeout_s: int,
    default_max_tokens: int,
    default_top_p: float = 1.0,
    default_presence_penalty: float = 0.0,
    default_frequency_penalty: float = 0.0,
    default_retries: int = 1,
    default_structured_output: bool = False,
    default_response_format: str | None = None,
    default_streaming: bool = False,
    default_reasoning_effort: str | None = None,
    model_legacy: tuple[str, ...] = (),
    temperature_legacy: tuple[str, ...] = (),
    timeout_legacy: tuple[str, ...] = (),
    max_tokens_legacy: tuple[str, ...] = (),
    top_p_legacy: tuple[str, ...] = (),
    presence_penalty_legacy: tuple[str, ...] = (),
    frequency_penalty_legacy: tuple[str, ...] = (),
    retries_legacy: tuple[str, ...] = (),
    deprecation_warnings: list[str],
) -> ModelComponentConfig:
    prefix = f"NEGOTIATION_{name.upper()}"
    return ModelComponentConfig(
        model=_read_env(
            f"{prefix}_MODEL",
            default_model,
            str,
            legacy=model_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        temperature=_read_env(
            f"{prefix}_TEMPERATURE",
            default_temperature,
            float,
            legacy=temperature_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        timeout_s=_read_env(
            f"{prefix}_TIMEOUT_S",
            default_timeout_s,
            int,
            legacy=timeout_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        max_tokens=_read_env(
            f"{prefix}_MAX_TOKENS",
            default_max_tokens,
            int,
            legacy=max_tokens_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        top_p=_read_env(
            f"{prefix}_TOP_P",
            default_top_p,
            float,
            legacy=top_p_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        presence_penalty=_read_env(
            f"{prefix}_PRESENCE_PENALTY",
            default_presence_penalty,
            float,
            legacy=presence_penalty_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        frequency_penalty=_read_env(
            f"{prefix}_FREQUENCY_PENALTY",
            default_frequency_penalty,
            float,
            legacy=frequency_penalty_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        retries=_read_env(
            f"{prefix}_RETRIES",
            default_retries,
            int,
            legacy=retries_legacy,
            deprecation_warnings=deprecation_warnings,
        ),
        structured_output=default_structured_output,
        response_format=default_response_format,
        streaming=default_streaming,
        reasoning_effort=_read_env(
            f"{prefix}_REASONING_EFFORT",
            default_reasoning_effort,
            str,
            deprecation_warnings=deprecation_warnings,
        ),
        seed=_read_env(
            f"{prefix}_SEED",
            None,
            int,
            deprecation_warnings=deprecation_warnings,
        ),
    )


def _apply_overrides(
    cfg: NegotiationModelConfig,
    overrides: dict[str, dict[str, Any]] | None,
) -> NegotiationModelConfig:
    if not overrides:
        return cfg

    def _override_component(current: ModelComponentConfig, key: str) -> ModelComponentConfig:
        values = overrides.get(key, {})
        if not values:
            return current
        return ModelComponentConfig(
            model=values.get("model", current.model),
            temperature=values.get("temperature", current.temperature),
            timeout_s=values.get("timeout_s", current.timeout_s),
            max_tokens=values.get("max_tokens", current.max_tokens),
            top_p=values.get("top_p", current.top_p),
            presence_penalty=values.get("presence_penalty", current.presence_penalty),
            frequency_penalty=values.get("frequency_penalty", current.frequency_penalty),
            retries=values.get("retries", current.retries),
            structured_output=values.get("structured_output", current.structured_output),
            response_format=values.get("response_format", current.response_format),
            streaming=values.get("streaming", current.streaming),
            reasoning_effort=values.get("reasoning_effort", current.reasoning_effort),
            seed=values.get("seed", current.seed),
        )

    embeddings_values = overrides.get("embeddings", {})
    rag_dir = overrides.get("shared", {}).get("rag_dir", cfg.rag_dir)

    return NegotiationModelConfig(
        world=_override_component(cfg.world, "world"),
        belief=_override_component(cfg.belief, "belief"),
        planner=_override_component(cfg.planner, "planner"),
        summary=_override_component(cfg.summary, "summary"),
        executor=_override_component(cfg.executor, "executor"),
        embeddings=EmbeddingsConfig(model=embeddings_values.get("model", cfg.embeddings.model)),
        rag_dir=rag_dir,
    )


def get_negotiation_model_config(
    overrides: dict[str, dict[str, Any]] | None = None,
) -> NegotiationModelConfig:
    """Precedence: request overrides > env vars > defaults."""
    warnings: list[str] = []

    world = _read_component(
        "world",
        default_model="gpt-4.1-nano",
        default_temperature=0.0,
        default_timeout_s=18,
        default_max_tokens=384,
        model_legacy=("WORLD_EXTRACTOR_MODEL", "WORLD_MODEL", "OPENAI_MODEL_NAME"),
        temperature_legacy=("WORLD_EXTRACTOR_TEMPERATURE",),
        timeout_legacy=("WORLD_EXTRACTOR_TIMEOUT_S",),
        deprecation_warnings=warnings,
    )
    belief = _read_component(
        "belief",
        default_model="gpt-4.1-nano",
        default_temperature=0.0,
        default_timeout_s=18,
        default_max_tokens=384,
        model_legacy=("BELIEF_MODEL_NAME", "SUMMARY_MODEL_NAME", "OPENAI_MODEL_NAME"),
        temperature_legacy=("BELIEF_TEMPERATURE",),
        deprecation_warnings=warnings,
    )
    planner = _read_component(
        "planner",
        default_model="gpt-4.1-nano",
        default_temperature=0.0,
        default_timeout_s=18,
        default_max_tokens=320,
        default_structured_output=True,
        default_response_format="json_schema",
        model_legacy=("PHASE_POLICY_MODEL_NAME", "PLANNER_MODEL_NAME", "SUMMARY_MODEL_NAME", "OPENAI_MODEL_NAME"),
        temperature_legacy=("PHASE_POLICY_TEMPERATURE", "PLANNER_TEMPERATURE"),
        deprecation_warnings=warnings,
    )
    summary = _read_component(
        "summary",
        default_model="gpt-4.1-nano",
        default_temperature=0.0,
        default_timeout_s=15,
        default_max_tokens=256,
        model_legacy=("SUMMARY_MODEL_NAME", "OPENAI_MODEL_NAME"),
        temperature_legacy=("SUMMARY_TEMPERATURE",),
        deprecation_warnings=warnings,
    )
    executor = _read_component(
        "executor",
        default_model="gpt-5-nano",
        default_temperature=0.7,
        default_timeout_s=20,
        default_max_tokens=700,
        default_streaming=True,
        default_reasoning_effort="minimal",
        model_legacy=("EXECUTOR_MODEL_NAME", "OPENAI_MODEL_NAME"),
        temperature_legacy=("EXECUTOR_TEMPERATURE",),
        deprecation_warnings=warnings,
    )

    embeddings = EmbeddingsConfig(
        model=_read_env(
            "NEGOTIATION_EMBEDDINGS_MODEL",
            "text-embedding-3-small",
            str,
            legacy=("EMBEDDINGS_MODEL_NAME",),
            deprecation_warnings=warnings,
        )
    )

    default_rag_dir = ""
    rag_dir = _read_env(
        "NEGOTIATION_RAG_DIR",
        default_rag_dir,
        str,
        legacy=("NEGOCIATION_RAG_DIR",),
        deprecation_warnings=warnings,
    )

    cfg = NegotiationModelConfig(
        world=world,
        belief=belief,
        planner=planner,
        summary=summary,
        executor=executor,
        embeddings=embeddings,
        rag_dir=rag_dir,
    )

    for warning in sorted(set(warnings)):
        logger.warning("negotiation_model_config_deprecated_env var=%s", warning)

    return _apply_overrides(cfg, overrides)


def build_chat_openai_kwargs(component: ModelComponentConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": component.model,
        "temperature": component.temperature,
        "timeout": component.timeout_s,
        "max_tokens": component.max_tokens,
        "top_p": component.top_p,
        "presence_penalty": component.presence_penalty,
        "frequency_penalty": component.frequency_penalty,
        "max_retries": component.retries,
        "streaming": component.streaming,
    }
    if component.seed is not None:
        kwargs["seed"] = component.seed
    if component.reasoning_effort and component.model.startswith("gpt-5"):
        kwargs["model_kwargs"] = {
            **kwargs.get("model_kwargs", {}),
            "reasoning": {"effort": component.reasoning_effort},
        }
    elif component.reasoning_effort:
        logger.warning(
            "negotiation_model_config_reasoning_ignored model=%s effort=%s",
            component.model,
            component.reasoning_effort,
        )
    return kwargs


def negotiation_effective_model_params(cfg: NegotiationModelConfig) -> dict[str, dict[str, Any]]:
    return {
        "models_effective": {
            "world_model": cfg.world.model,
            "belief_model": cfg.belief.model,
            "planner_model": cfg.planner.model,
            "summary_model": cfg.summary.model,
            "executor_model": cfg.executor.model,
            "embeddings_model": cfg.embeddings.model,
        },
        "params_effective": {
            "world": {
                "temperature": cfg.world.temperature,
                "max_tokens": cfg.world.max_tokens,
                "timeout_s": cfg.world.timeout_s,
                "top_p": cfg.world.top_p,
                "presence_penalty": cfg.world.presence_penalty,
                "frequency_penalty": cfg.world.frequency_penalty,
                "retries": cfg.world.retries,
            },
            "belief": {
                "temperature": cfg.belief.temperature,
                "max_tokens": cfg.belief.max_tokens,
                "timeout_s": cfg.belief.timeout_s,
                "top_p": cfg.belief.top_p,
                "presence_penalty": cfg.belief.presence_penalty,
                "frequency_penalty": cfg.belief.frequency_penalty,
                "retries": cfg.belief.retries,
            },
            "planner": {
                "temperature": cfg.planner.temperature,
                "max_tokens": cfg.planner.max_tokens,
                "timeout_s": cfg.planner.timeout_s,
                "top_p": cfg.planner.top_p,
                "presence_penalty": cfg.planner.presence_penalty,
                "frequency_penalty": cfg.planner.frequency_penalty,
                "retries": cfg.planner.retries,
                "structured_output": cfg.planner.structured_output,
                "response_format": cfg.planner.response_format,
            },
            "summary": {
                "temperature": cfg.summary.temperature,
                "max_tokens": cfg.summary.max_tokens,
                "timeout_s": cfg.summary.timeout_s,
                "top_p": cfg.summary.top_p,
                "presence_penalty": cfg.summary.presence_penalty,
                "frequency_penalty": cfg.summary.frequency_penalty,
                "retries": cfg.summary.retries,
            },
            "executor": {
                "temperature": cfg.executor.temperature,
                "max_tokens": cfg.executor.max_tokens,
                "timeout_s": cfg.executor.timeout_s,
                "top_p": cfg.executor.top_p,
                "presence_penalty": cfg.executor.presence_penalty,
                "frequency_penalty": cfg.executor.frequency_penalty,
                "retries": cfg.executor.retries,
                "streaming": cfg.executor.streaming,
                "reasoning_effort": cfg.executor.reasoning_effort,
            },
        },
    }
