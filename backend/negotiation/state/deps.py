from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT

from ..elementos.execution_definitions import (
    EXECUTOR_MODEL,
    EXECUTOR_TEMPERATURE,
    SUMMARY_MODEL,
    SUMMARY_TEMPERATURE,
)
from ..phase_policy_planner import plan_phase_policy
from ..belief_state_updater import update_belief_state
from ..schemas import BeliefState, PolicyDecision


PlanFn = Callable[..., Tuple[dict, PolicyDecision, dict]]
BeliefFn = Callable[..., Tuple[BeliefState, dict]]
ExecuteFn = Callable[..., str]
SummarizeFn = Callable[[str, str], str]


executor_llm = ChatOpenAI(
    model=EXECUTOR_MODEL,
    temperature=EXECUTOR_TEMPERATURE,
)

summary_llm = ChatOpenAI(
    model=SUMMARY_MODEL,
    temperature=SUMMARY_TEMPERATURE,
)

summary_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM_PROMPT),
        ("user", SUMMARY_USER_PROMPT),
    ]
)


@dataclass(frozen=True)
class AgentDeps:
    plan_phase_policy: PlanFn
    update_belief_state: BeliefFn
    execute: ExecuteFn
    summarize: Optional[SummarizeFn] = None


def _default_execute(messages: Any) -> str:
    result = executor_llm.invoke(messages)
    return getattr(result, "content", str(result))


def _default_summarize(existing_summary: str, new_block: str) -> str:
    messages = summary_prompt.format_messages(
        existing_summary=existing_summary,
        new_block=new_block,
    )
    result = summary_llm.invoke(messages)
    return getattr(result, "content", str(result)).strip()


DEFAULT_DEPS = AgentDeps(
    plan_phase_policy=plan_phase_policy,
    update_belief_state=update_belief_state,
    execute=_default_execute,
    summarize=_default_summarize,
)
