from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT

from ..belief_compat import update_belief_state_compat
from ..llm_clients import get_executor_llm, get_summary_llm
from ..phase_policy_planner import plan_phase_policy
from ..schemas import BeliefState, PolicyDecision
from ..telemetry.llm_usage import extract_llm_usage

PlanFn = Callable[..., Tuple[dict, PolicyDecision, dict]]
_LAST_EXECUTE_META: dict[str, Any] = {}
_LAST_SUMMARIZE_META: dict[str, Any] = {}
BeliefFn = Callable[..., Tuple[BeliefState, dict]]
ExecuteFn = Callable[..., str]
SummarizeFn = Callable[[str, str], str]

summary_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM_PROMPT),
        ("user", SUMMARY_USER_PROMPT),
    ]
)


def update_belief_state_compat_adapter(*args, **kwargs):
    """Stable adapter for deps/tests; decoupled from legacy belief_state_updater module."""
    return update_belief_state_compat(*args, **kwargs)


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
    rendered_messages: list[dict[str, str]] = []
    if isinstance(messages, list):
        for message in messages:
            role = getattr(message, "type", None) or getattr(message, "role", None) or "user"
            content = getattr(message, "content", "")
            rendered_messages.append({"role": str(role), "content": str(content)})
    _LAST_EXECUTE_META["rendered_messages"] = rendered_messages
    _LAST_EXECUTE_META["input_prompt_rendered"] = "\n\n".join(
        f"[{item['role']}]\n{item['content']}" for item in rendered_messages
    )
    output_text = getattr(result, "content", str(result))
    _LAST_EXECUTE_META["output_text_rendered"] = str(output_text)
    return output_text


def get_last_execute_meta() -> dict[str, Any]:
    return dict(_LAST_EXECUTE_META)


def get_last_summarize_meta() -> dict[str, Any]:
    return dict(_LAST_SUMMARIZE_META)


def _default_summarize(existing_summary: str, new_block: str) -> str:
    global _LAST_SUMMARIZE_META
    messages = summary_prompt.format_messages(
        existing_summary=existing_summary,
        new_block=new_block,
    )
    result = get_summary_llm().invoke(messages)
    usage = extract_llm_usage(result)
    rendered_messages: list[dict[str, str]] = []
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", None) or "user"
        content = getattr(message, "content", "")
        rendered_messages.append({"role": str(role), "content": str(content)})
    output_text = getattr(result, "content", str(result)).strip()
    _LAST_SUMMARIZE_META = {
        **usage,
        "rendered_messages": rendered_messages,
        "input_prompt_rendered": "\n\n".join(f"[{item['role']}]\n{item['content']}" for item in rendered_messages),
        "output_text_rendered": str(output_text),
    }
    return output_text


DEFAULT_DEPS = AgentDeps(
    plan_phase_policy=plan_phase_policy,
    update_belief_state=update_belief_state_compat_adapter,
    execute=_default_execute,
    summarize=_default_summarize,
)
