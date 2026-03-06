from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .agents_pipeline import NegotiationPipelineConfig


class FlowDetails(TypedDict):
    flow_name: str
    memory_key: str
    summarizer_model: str
    planner_model: str
    executor_model: str
    context_limit: int
    keep_last_n_turns: int


BASE_DIR = Path(__file__).resolve().parent

NEGOTIATION_FLOW_DETAILS: FlowDetails = {
    "flow_name": "negociacion",
    "memory_key": "negotiation_memory",
    "summarizer_model": "gpt-5-nano",
    "planner_model": "o4-mini",
    "executor_model": "gpt-5-nano",
    "context_limit": 6,
    "keep_last_n_turns": 3,
}


def build_negotiation_pipeline_config() -> NegotiationPipelineConfig:
    return NegotiationPipelineConfig(
        memory_key=NEGOTIATION_FLOW_DETAILS["memory_key"],
        prompts_dir=BASE_DIR / "prompts",
        planner_schema_path=Path(__file__).resolve().parent.parent / "openai_production" / "schemas" / "planner_output.schema.json",
        planner_model=NEGOTIATION_FLOW_DETAILS["planner_model"],
        summarizer_model=NEGOTIATION_FLOW_DETAILS["summarizer_model"],
        executor_model=NEGOTIATION_FLOW_DETAILS["executor_model"],
        context_limit=NEGOTIATION_FLOW_DETAILS["context_limit"],
        keep_last_n_turns=NEGOTIATION_FLOW_DETAILS["keep_last_n_turns"],
    )
