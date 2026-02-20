from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT

from ..llm_clients import get_executor_llm, get_summary_llm
from ..telemetry.llm_usage import extract_llm_usage
from ..phase_policy_planner import plan_phase_policy
from ..belief_state_updater import update_belief_state
from ..schemas import BeliefState, PolicyDecision


PlanFn = Callable[..., Tuple[dict, PolicyDecision, dict]]
_LAST_EXECUTE_META: dict[str, Any] = {}
BeliefFn = Callable[..., Tuple[BeliefState, dict]]
ExecuteFn = Callable[..., str]
SummarizeFn = Callable[[str, str], str]



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
    global _LAST_EXECUTE_META
    result = get_executor_llm().invoke(messages)
    _LAST_EXECUTE_META = extract_llm_usage(result)
    return getattr(result, "content", str(result))


def get_last_execute_meta() -> dict[str, Any]:
    return dict(_LAST_EXECUTE_META)


def _default_summarize(existing_summary: str, new_block: str) -> str:
    messages = summary_prompt.format_messages(
        existing_summary=existing_summary,
        new_block=new_block,
    )
    result = get_summary_llm().invoke(messages)
    return getattr(result, "content", str(result)).strip()


DEFAULT_DEPS = AgentDeps(
    plan_phase_policy=plan_phase_policy,
    update_belief_state=update_belief_state,
    execute=_default_execute,
    summarize=_default_summarize,
)
