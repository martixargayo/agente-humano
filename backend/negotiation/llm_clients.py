from __future__ import annotations

from functools import lru_cache

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
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.planner))


@lru_cache(maxsize=1)
def get_executor_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.executor))


@lru_cache(maxsize=1)
def get_summary_llm() -> ChatOpenAI:
    cfg = get_negotiation_model_config()
    return ChatOpenAI(**build_chat_openai_kwargs(cfg.summary))


def reset_negotiation_llm_caches() -> None:
    get_world_llm.cache_clear()
    get_belief_llm.cache_clear()
    get_planner_llm.cache_clear()
    get_executor_llm.cache_clear()
    get_summary_llm.cache_clear()
