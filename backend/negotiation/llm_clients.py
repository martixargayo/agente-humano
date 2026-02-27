from __future__ import annotations

from functools import lru_cache
import os

from langchain_openai import ChatOpenAI

from .config import build_chat_openai_kwargs, get_negotiation_model_config


@lru_cache(maxsize=1)
def get_world_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.world))


@lru_cache(maxsize=1)
def get_belief_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.belief))


@lru_cache(maxsize=1)
def get_planner_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    kwargs = build_chat_openai_kwargs(cfg.planner)
    kwargs["max_tokens"] = max(int(kwargs.get("max_tokens", 0) or 0), 900)
    return ChatOpenAI(**kwargs)




@lru_cache(maxsize=1)
def get_advisor_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    kwargs = build_chat_openai_kwargs(cfg.planner)
    advisor_model = str(os.getenv("NEGOTIATION_ADVISOR_MODEL", "") or "").strip()
    if advisor_model:
        kwargs["model"] = advisor_model
    kwargs["temperature"] = float(os.getenv("NEGOTIATION_ADVISOR_TEMPERATURE", "0") or 0)
    kwargs["max_tokens"] = int(
        os.getenv(
            "NEGOTIATION_ADVISOR_MAX_TOKENS",
            str(max(int(kwargs.get("max_tokens", 0) or 0), 520)),
        )
        or 520
    )
    return ChatOpenAI(**kwargs)

@lru_cache(maxsize=1)
def get_executor_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.executor))


@lru_cache(maxsize=1)
def get_executor_finalizer_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    kwargs = build_chat_openai_kwargs(cfg.executor)
    finalizer_model = str(os.getenv("NEGOTIATION_EXECUTOR_FINALIZER_MODEL", "") or "").strip()
    if finalizer_model:
        kwargs["model"] = finalizer_model
    finalizer_temp = os.getenv("NEGOTIATION_EXECUTOR_FINALIZER_TEMPERATURE", "")
    if finalizer_temp.strip():
        kwargs["temperature"] = float(finalizer_temp)
    return ChatOpenAI(**kwargs)


@lru_cache(maxsize=1)
def get_summary_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.summary))


def reset_negotiation_llm_caches() -> None:
    get_world_llm.cache_clear()
    get_belief_llm.cache_clear()
    get_planner_llm.cache_clear()
    get_advisor_llm.cache_clear()
    get_executor_llm.cache_clear()
    get_executor_finalizer_llm.cache_clear()
    get_summary_llm.cache_clear()
