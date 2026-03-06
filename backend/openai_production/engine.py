from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple, cast

import openai

from state import SessionState, add_message, save_session_state

logger = logging.getLogger(__name__)

SUMMARY_SHADOW_PROMPT = "Summarize the conversation we had so far."


@dataclass
class PipelineConfig:
    memory_key: str
    prompts_dir: Path
    planner_schema_path: Path
    planner_model: str = "gpt-5-nano"
    summarizer_model: str = "gpt-5-nano"
    executor_model: str = "gpt-5-nano"
    context_limit: int = 6
    keep_last_n_turns: int = 3
    llm_order: Tuple[Literal["summarizer", "planner", "executor"], ...] = (
        "summarizer",
        "planner",
        "executor",
    )


def _read_text(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8").strip()
    return text if text else fallback


def _build_client() -> openai.OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("openai_api_key_missing production_pipeline_fallback=true")
        return None
    try:
        return openai.OpenAI()
    except Exception as exc:
        logger.warning("openai_client_init_error=%s", exc)
        return None


class SessionMemoryManager:
    def __init__(self, state: SessionState, key: str, context_limit: int, keep_last_n_turns: int):
        self.state = state
        self.key = key
        self.context_limit = max(1, context_limit)
        self.keep_last_n_turns = max(1, min(keep_last_n_turns, context_limit))
        self.records = self._load_records()

    def _load_records(self) -> List[Dict[str, Any]]:
        block = self.state.world_state.get(self.key, {}) if isinstance(self.state.world_state, dict) else {}
        records = block.get("records", []) if isinstance(block, dict) else []
        return records if isinstance(records, list) else []

    def save(self) -> None:
        self.state.world_state[self.key] = {
            "records": self.records,
            "context_limit": self.context_limit,
            "keep_last_n_turns": self.keep_last_n_turns,
        }

    def add_message(self, role: str, content: str, synthetic: bool = False, kind: str | None = None) -> None:
        content = (content or "").strip()
        if not content:
            return
        metadata: Dict[str, Any] = {"synthetic": synthetic}
        if kind:
            metadata["kind"] = kind
        self.records.append({"message": {"role": role, "content": content}, "metadata": metadata})

    def get_model_items(self) -> List[Dict[str, str]]:
        return [
            {
                "role": rec.get("message", {}).get("role", "assistant"),
                "content": rec.get("message", {}).get("content", ""),
            }
            for rec in self.records
            if (rec.get("message", {}).get("content") or "").strip()
        ]

    def get_summary_text(self) -> str:
        items = self.get_model_items()
        if len(items) >= 2 and items[0].get("content") == SUMMARY_SHADOW_PROMPT:
            return (items[1].get("content") or "").strip()
        return ""

    def _real_user_indices(self) -> List[int]:
        indices: List[int] = []
        for idx, rec in enumerate(self.records):
            message = rec.get("message", {})
            meta = rec.get("metadata", {})
            if message.get("role") == "user" and not bool(meta.get("synthetic", False)):
                indices.append(idx)
        return indices

    def maybe_trim_and_summarize(self, summarizer: "SummarizerNode") -> None:
        user_indices = self._real_user_indices()
        if len(user_indices) <= self.context_limit:
            return

        boundary = user_indices[-self.keep_last_n_turns]
        if boundary <= 0:
            return

        prefix = [rec.get("message", {}) for rec in self.records[:boundary]]
        user_shadow, summary_text = summarizer.run(prefix)

        suffix = self.records[boundary:]
        self.records = [
            {
                "message": {"role": "user", "content": user_shadow},
                "metadata": {"synthetic": True, "kind": "history_summary_prompt"},
            },
            {
                "message": {"role": "assistant", "content": summary_text},
                "metadata": {"synthetic": True, "kind": "history_summary"},
            },
            *suffix,
        ]


class SummarizerNode:
    def __init__(self, client: openai.OpenAI | None, model: str, system_prompt: str):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt

    def run(self, prefix_messages: List[Dict[str, str]]) -> Tuple[str, str]:
        if not prefix_messages:
            return SUMMARY_SHADOW_PROMPT, "Sin historial previo para resumir."

        compact = "\n".join(
            f"{m.get('role', 'assistant').upper()}: {(m.get('content') or '').strip()}"
            for m in prefix_messages
            if (m.get("content") or "").strip()
        )
        if self.client is None:
            return SUMMARY_SHADOW_PROMPT, compact[-1500:] or "Resumen no disponible."

        try:
            result = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": compact},
                ],
                reasoning={"effort": "low"},
                text={"verbosity": "low"},
                max_output_tokens=450,
                store=False,
            )
            summary = (getattr(result, "output_text", "") or "").strip()
            return SUMMARY_SHADOW_PROMPT, summary or "Resumen no disponible."
        except Exception as exc:
            logger.warning("summarizer_invoke_error=%s", exc)
            return SUMMARY_SHADOW_PROMPT, "Resumen no disponible."


class PlannerNode:
    def __init__(self, client: openai.OpenAI | None, model: str, system_prompt: str, schema: Dict[str, Any]):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.schema = schema

    def run(self, *, user_message: str, summary_text: str, recent_history: str) -> Dict[str, Any]:
        fallback = {
            "schema_version": "planner_v1",
            "intent": "answer_user",
            "language": "es-ES",
            "needs_clarification": False,
            "clarifying_question": None,
            "safety_risk": "low",
            "hitl_required": False,
            "executor_brief": "Responder de forma clara y útil, sin divagar.",
            "response_style": "normal",
            "voice": "cedar",
            "tts_instructions": None,
            "max_output_tokens_executor": 500,
            "reasoning_effort_executor": "low",
            "memory_directives": {
                "use_context_summary": True,
                "preserve_last_n_turns": 3,
                "do_not_repeat_summary": True,
                "note_conflicts": True,
            },
        }

        if self.client is None:
            return fallback

        planner_input = (
            f"Resumen:\n{summary_text or '(sin resumen)'}\n\n"
            f"Historial reciente:\n{recent_history}\n\n"
            f"Mensaje usuario:\n{user_message}"
        )

        try:
            result = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": planner_input},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "planner_v1",
                        "schema": self.schema,
                        "strict": True,
                    },
                    "verbosity": "low",
                },
                reasoning={"effort": "low"},
                max_output_tokens=700,
                store=False,
            )
            data = json.loads((getattr(result, "output_text", "") or "{}").strip())
            return data if isinstance(data, dict) else fallback
        except Exception as exc:
            logger.warning("planner_invoke_error=%s", exc)
            return fallback


class ExecutorNode:
    def __init__(self, client: openai.OpenAI | None, model: str, system_prompt: str):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt

    def run(self, *, user_message: str, summary_text: str, recent_history: str, plan: Dict[str, Any]) -> str:
        if plan.get("needs_clarification") and plan.get("clarifying_question"):
            return str(plan.get("clarifying_question"))

        if self.client is None:
            return "Entendido. Te respondo de forma clara y directa."

        max_output_tokens = int(plan.get("max_output_tokens_executor", 500) or 500)
        effort_value = str(plan.get("reasoning_effort_executor", "low") or "low").lower()
        if effort_value not in {"none", "low", "medium"}:
            effort_value = "low"
        effort = cast(Literal["none", "low", "medium"], effort_value)

        verbosity_value = (
            "low" if plan.get("response_style") == "concise"
            else "high" if plan.get("response_style") == "detailed"
            else "medium"
        )
        verbosity = cast(Literal["low", "medium", "high"], verbosity_value)
        brief = str(plan.get("executor_brief", "Responder en español de forma útil y concreta."))

        executor_input = (
            f"Plan JSON:\n{json.dumps(plan, ensure_ascii=False)}\n\n"
            f"Resumen:\n{summary_text or '(sin resumen)'}\n\n"
            f"Historial reciente:\n{recent_history}\n\n"
            f"Mensaje usuario:\n{user_message}\n\n"
            f"Instrucciones del planner:\n{brief}"
        )

        try:
            result = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": executor_input},
                ],
                reasoning={"effort": effort},
                text={"verbosity": verbosity},
                max_output_tokens=max_output_tokens,
                store=False,
            )
            text = (getattr(result, "output_text", "") or "").strip()
            return text or "Entendido. Seguimos."
        except Exception as exc:
            logger.warning("executor_invoke_error=%s", exc)
            return "Entendido. Seguimos."


def _history_to_text(items: List[Dict[str, str]], max_items: int = 12) -> str:
    lines: List[str] = []
    for item in items[-max_items:]:
        role = item.get("role", "assistant").upper()
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip() or "(sin historial)"


def _load_schema(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version"],
            "properties": {"schema_version": {"type": "string"}},
        }


def run_three_llm_turn(state: SessionState, user_message: str, config: PipelineConfig) -> Tuple[str, SessionState]:
    prompts_dir = config.prompts_dir
    summarizer_prompt = _read_text(prompts_dir / "summarizer_prompt.txt", "PROMPT PENDIENTE DE PEGAR")
    planner_prompt = _read_text(prompts_dir / "planner_prompt.txt", "PROMPT PENDIENTE DE PEGAR")
    executor_prompt = _read_text(prompts_dir / "executor_prompt.txt", "PROMPT PENDIENTE DE PEGAR")

    if summarizer_prompt.lower() == "prompt pendiente de pegar":
        summarizer_prompt = "Resume conversación sin inventar datos. Señala acuerdos y próximos pasos."
    if planner_prompt.lower() == "prompt pendiente de pegar":
        planner_prompt = "Devuelve EXCLUSIVAMENTE JSON válido según schema planner_v1."
    if executor_prompt.lower() == "prompt pendiente de pegar":
        executor_prompt = "Responde en español con tono humano, directo y útil."

    add_message(state, role="user", content=user_message)

    client = _build_client()
    schema = _load_schema(config.planner_schema_path)

    memory = SessionMemoryManager(
        state=state,
        key=config.memory_key,
        context_limit=config.context_limit,
        keep_last_n_turns=config.keep_last_n_turns,
    )

    memory.add_message("user", user_message, synthetic=False)

    summarizer = SummarizerNode(client=client, model=config.summarizer_model, system_prompt=summarizer_prompt)
    planner = PlannerNode(client=client, model=config.planner_model, system_prompt=planner_prompt, schema=schema)
    executor = ExecutorNode(client=client, model=config.executor_model, system_prompt=executor_prompt)

    items = memory.get_model_items()
    summary_text = memory.get_summary_text()
    recent_history = _history_to_text(items)

    plan: Dict[str, Any] | None = None
    reply: str | None = None

    for node_name in config.llm_order:
        if node_name == "summarizer":
            memory.maybe_trim_and_summarize(summarizer)
            items = memory.get_model_items()
            summary_text = memory.get_summary_text()
            recent_history = _history_to_text(items)
            continue

        if node_name == "planner":
            items = memory.get_model_items()
            summary_text = memory.get_summary_text()
            recent_history = _history_to_text(items)
            plan = planner.run(
                user_message=user_message,
                summary_text=summary_text,
                recent_history=recent_history,
            )
            continue

        if node_name == "executor":
            if plan is None:
                plan = planner.run(
                    user_message=user_message,
                    summary_text=summary_text,
                    recent_history=recent_history,
                )
            reply = executor.run(
                user_message=user_message,
                summary_text=summary_text,
                recent_history=recent_history,
                plan=plan,
            )
            continue

    if plan is None:
        plan = planner.run(
            user_message=user_message,
            summary_text=summary_text,
            recent_history=recent_history,
        )

    if reply is None:
        reply = executor.run(
            user_message=user_message,
            summary_text=summary_text,
            recent_history=recent_history,
            plan=plan,
        )

    add_message(state, role="assistant", content=reply)
    memory.add_message("assistant", reply, synthetic=False)

    state.world_state[f"{config.memory_key}_last_plan"] = plan
    memory.save()
    save_session_state(state)
    return reply, state
