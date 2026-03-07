from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from infra.openai import PipelineConfig

LLMNodeName = Literal["summarizer", "planner", "executor"]


class FlowDetails(TypedDict):
    flow_name: str
    memory_key: str
    llm_order: tuple[LLMNodeName, ...]
    summarizer_model: str
    planner_model: str
    executor_model: str
    context_limit: int
    keep_last_n_turns: int


BASE_DIR = Path(__file__).resolve().parent

CHAT_FLOW_DETAILS: FlowDetails = {
    "flow_name": "chat",
    "memory_key": "chat_memory",
    "llm_order": ("summarizer", "planner", "executor"),
    "summarizer_model": "gpt-5-nano",
    "planner_model": "gpt-5-nano",
    "executor_model": "gpt-5-nano",
    "context_limit": 6,
    "keep_last_n_turns": 3,
}


def build_chat_pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        memory_key=CHAT_FLOW_DETAILS["memory_key"],
        prompts_dir=BASE_DIR / "prompts",
        planner_schema_path=Path(__file__).resolve().parent.parent / "infra" / "openai" / "schemas" / "planner_output.schema.json",
        planner_model=CHAT_FLOW_DETAILS["planner_model"],
        summarizer_model=CHAT_FLOW_DETAILS["summarizer_model"],
        executor_model=CHAT_FLOW_DETAILS["executor_model"],
        context_limit=CHAT_FLOW_DETAILS["context_limit"],
        keep_last_n_turns=CHAT_FLOW_DETAILS["keep_last_n_turns"],
        llm_order=CHAT_FLOW_DETAILS["llm_order"],
    )
