from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import importlib.util
import openai

from sessions.state import SessionState, add_message, save_session_state

logger = logging.getLogger(__name__)

SUMMARY_SHADOW_PROMPT = "Summarize the conversation we had so far."
ROLE_USER = "user"

def _load_session_base() -> type:
    if importlib.util.find_spec("agents") is None:
        class _SessionFallback:
            async def get_items(self, limit: int | None = None):
                raise NotImplementedError
            async def add_items(self, items):
                raise NotImplementedError
            async def pop_item(self):
                raise NotImplementedError
            async def clear_session(self):
                raise NotImplementedError
        return _SessionFallback

    from agents.memory.session import SessionABC as _SessionABC
    return _SessionABC


SessionBase = _load_session_base()

@dataclass
class NegotiationPipelineConfig:
    memory_key: str
    prompts_dir: Path
    planner_schema_path: Path
    planner_model: str = "o4-mini"
    summarizer_model: str = "o4-mini"
    executor_model: str = "gpt-5-nano"
    context_limit: int = 6
    keep_last_n_turns: int = 3


class LLMSummarizer:
    def __init__(self, client: openai.OpenAI | None, model: str, system_prompt: str, max_tokens: int = 450):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    async def summarize(self, messages: List[Dict[str, Any]]) -> Tuple[str, str]:
        if not messages:
            return SUMMARY_SHADOW_PROMPT, "Sin historial previo para resumir."

        compact = "\n".join(
            f"{(m.get('role') or 'assistant').upper()}: {(m.get('content') or '').strip()}"
            for m in messages
            if (m.get("content") or "").strip()
        )
        if not compact:
            return SUMMARY_SHADOW_PROMPT, "Sin historial previo para resumir."

        if self.client is None:
            return SUMMARY_SHADOW_PROMPT, compact[-1500:]

        try:
            result = await asyncio.to_thread(
                self.client.responses.create,
                model=self.model,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": compact},
                ],
                reasoning={"effort": "low"},
                text={"verbosity": "low"},
                max_output_tokens=self.max_tokens,
                store=False,
            )
            summary = (getattr(result, "output_text", "") or "").strip()
            return SUMMARY_SHADOW_PROMPT, summary or "Resumen no disponible."
        except Exception as exc:
            logger.warning("negotiation_summarizer_error=%s", exc)
            return SUMMARY_SHADOW_PROMPT, "Resumen no disponible."


class SummarizingSession(SessionBase):
    _ALLOWED_KEYS = {"role", "content", "name"}

    def __init__(
        self,
        session_id: str,
        summarizer: LLMSummarizer,
        keep_last_n_turns: int = 3,
        context_limit: int = 6,
        seed_records: Optional[List[Dict[str, Any]]] = None,
    ):
        self.session_id = session_id
        self.summarizer = summarizer
        self.keep_last_n_turns = max(1, keep_last_n_turns)
        self.context_limit = max(1, context_limit)
        if self.keep_last_n_turns > self.context_limit:
            self.keep_last_n_turns = self.context_limit
        self._records: List[Dict[str, Any]] = list(seed_records or [])
        self._lock = asyncio.Lock()

    @staticmethod
    def _sanitize_msg(item: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in item.items() if k in SummarizingSession._ALLOWED_KEYS}

    @staticmethod
    def _split_msg_and_meta(item: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        msg = {k: v for k, v in item.items() if k in SummarizingSession._ALLOWED_KEYS}
        extra = {k: v for k, v in item.items() if k not in SummarizingSession._ALLOWED_KEYS}
        metadata = dict(extra.pop("metadata", {})) if isinstance(extra.get("metadata", {}), dict) else {}
        metadata.update(extra)
        msg.setdefault("role", "user")
        msg.setdefault("content", "")
        if msg["role"] in {"user", "assistant"} and "synthetic" not in metadata:
            metadata["synthetic"] = False
        return msg, metadata

    @staticmethod
    def _is_real_user_start(rec: Dict[str, Any]) -> bool:
        return rec.get("message", {}).get("role") == ROLE_USER and not bool(rec.get("metadata", {}).get("synthetic"))

    def _real_user_indices(self) -> List[int]:
        return [idx for idx, rec in enumerate(self._records) if self._is_real_user_start(rec)]

    async def get_items(self, limit: int | None = None) -> List[Dict[str, Any]]:
        async with self._lock:
            items = [self._sanitize_msg(rec.get("message", {})) for rec in self._records]
        if limit is not None and limit >= 0:
            return items[-limit:]
        return items

    async def add_items(self, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        async with self._lock:
            for item in items:
                msg, metadata = self._split_msg_and_meta(item)
                self._records.append({"message": msg, "metadata": metadata})

            user_indices = self._real_user_indices()
            if len(user_indices) <= self.context_limit:
                return
            boundary = user_indices[-self.keep_last_n_turns]
            if boundary <= 0:
                return
            prefix_messages = [rec.get("message", {}) for rec in self._records[:boundary]]

        user_shadow, summary_text = await self.summarizer.summarize(prefix_messages)

        async with self._lock:
            user_indices = self._real_user_indices()
            if len(user_indices) <= self.context_limit:
                return
            boundary = user_indices[-self.keep_last_n_turns]
            if boundary <= 0:
                return

            suffix = self._records[boundary:]
            self._records = [
                {
                    "message": {"role": "user", "content": user_shadow},
                    "metadata": {
                        "synthetic": True,
                        "kind": "history_summary_prompt",
                        "summary_for_turns": f"< all before idx {boundary} >",
                    },
                },
                {
                    "message": {"role": "assistant", "content": summary_text},
                    "metadata": {
                        "synthetic": True,
                        "kind": "history_summary",
                        "summary_for_turns": f"< all before idx {boundary} >",
                    },
                },
                *suffix,
            ]

    async def pop_item(self) -> Dict[str, Any] | None:
        async with self._lock:
            if not self._records:
                return None
            rec = self._records.pop()
            return self._sanitize_msg(rec.get("message", {}))

    async def clear_session(self) -> None:
        async with self._lock:
            self._records.clear()

    async def get_items_with_metadata(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "message": dict(rec.get("message", {})),
                    "metadata": dict(rec.get("metadata", {})),
                }
                for rec in self._records
            ]


def _read_text(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8").strip()
    return text if text else fallback


def _build_client() -> openai.OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("openai_api_key_missing negotiation_pipeline_fallback=true")
        return None
    try:
        return openai.OpenAI()
    except Exception as exc:
        logger.warning("openai_client_init_error=%s", exc)
        return None


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


def _history_to_text(items: List[Dict[str, Any]], max_items: int = 12) -> str:
    lines: List[str] = []
    for item in items[-max_items:]:
        role = str(item.get("role", "assistant")).upper()
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip() or "(sin historial)"


def _summary_text_from_items(items: List[Dict[str, Any]]) -> str:
    if len(items) >= 2 and (items[0].get("content") or "").strip() == SUMMARY_SHADOW_PROMPT:
        return (items[1].get("content") or "").strip()
    return ""


def _planner_fallback() -> Dict[str, Any]:
    return {
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


def _run_planner(
    client: openai.OpenAI | None,
    model: str,
    system_prompt: str,
    schema: Dict[str, Any],
    user_message: str,
    summary_text: str,
    recent_history: str,
) -> Dict[str, Any]:
    if client is None:
        return _planner_fallback()
    planner_input = (
        f"Resumen:\n{summary_text or '(sin resumen)'}\n\n"
        f"Historial reciente:\n{recent_history}\n\n"
        f"Mensaje usuario:\n{user_message}"
    )
    try:
        result = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": planner_input},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "planner_v1",
                    "schema": schema,
                    "strict": True,
                },
                "verbosity": "low",
            },
            reasoning={"effort": "low"},
            max_output_tokens=700,
            store=False,
        )
        parsed = json.loads((getattr(result, "output_text", "") or "{}").strip())
        return parsed if isinstance(parsed, dict) else _planner_fallback()
    except Exception as exc:
        logger.warning("negotiation_planner_error=%s", exc)
        return _planner_fallback()


def _run_executor(
    client: openai.OpenAI | None,
    model: str,
    system_prompt: str,
    user_message: str,
    summary_text: str,
    recent_history: str,
    plan: Dict[str, Any],
) -> str:
    if plan.get("needs_clarification") and plan.get("clarifying_question"):
        return str(plan.get("clarifying_question"))

    if client is None:
        return "Entendido. Te respondo de forma clara y directa."

    max_output_tokens = int(plan.get("max_output_tokens_executor", 500) or 500)
    effort_value = str(plan.get("reasoning_effort_executor", "low") or "low").lower()
    if effort_value not in {"none", "low", "medium"}:
        effort_value = "low"
    effort = cast(str, effort_value)
    verbosity = (
        "low" if plan.get("response_style") == "concise"
        else "high" if plan.get("response_style") == "detailed"
        else "medium"
    )
    brief = str(plan.get("executor_brief", "Responder en español de forma útil y concreta."))

    executor_input = (
        f"Plan JSON:\n{json.dumps(plan, ensure_ascii=False)}\n\n"
        f"Resumen:\n{summary_text or '(sin resumen)'}\n\n"
        f"Historial reciente:\n{recent_history}\n\n"
        f"Mensaje usuario:\n{user_message}\n\n"
        f"Instrucciones del planner:\n{brief}"
    )

    try:
        result = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
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
        logger.warning("negotiation_executor_error=%s", exc)
        return "Entendido. Seguimos."


def run_negotiation_agents_sdk_turn(state: SessionState, user_message: str, config: NegotiationPipelineConfig) -> Tuple[str, SessionState]:
    prompts_dir = config.prompts_dir
    summarizer_prompt = _read_text(prompts_dir / "summarizer_prompt.txt", "Resume conversación sin inventar datos.")
    planner_prompt = _read_text(prompts_dir / "planner_prompt.txt", "Devuelve EXCLUSIVAMENTE JSON válido según schema planner_v1.")
    executor_prompt = _read_text(prompts_dir / "executor_prompt.txt", "Responde en español con tono humano, directo y útil.")

    add_message(state, role="user", content=user_message)

    client = _build_client()
    schema = _load_schema(config.planner_schema_path)

    existing = state.world_state.get(config.memory_key, {}) if isinstance(state.world_state, dict) else {}
    seed_records = existing.get("records", []) if isinstance(existing, dict) else []
    if not isinstance(seed_records, list):
        seed_records = []

    summarizer = LLMSummarizer(client=client, model=config.summarizer_model, system_prompt=summarizer_prompt)
    session = SummarizingSession(
        session_id=f"{state.user_id}:{state.session_id}",
        summarizer=summarizer,
        keep_last_n_turns=config.keep_last_n_turns,
        context_limit=config.context_limit,
        seed_records=seed_records,
    )

    asyncio.run(session.add_items([{"role": "user", "content": user_message, "metadata": {"synthetic": False}}]))
    items = asyncio.run(session.get_items())
    summary_text = _summary_text_from_items(items)
    recent_history = _history_to_text(items)

    plan = _run_planner(
        client=client,
        model=config.planner_model,
        system_prompt=planner_prompt,
        schema=schema,
        user_message=user_message,
        summary_text=summary_text,
        recent_history=recent_history,
    )

    reply = _run_executor(
        client=client,
        model=config.executor_model,
        system_prompt=executor_prompt,
        user_message=user_message,
        summary_text=summary_text,
        recent_history=recent_history,
        plan=plan,
    )

    add_message(state, role="assistant", content=reply)
    asyncio.run(session.add_items([{"role": "assistant", "content": reply, "metadata": {"synthetic": False}}]))

    state.world_state[config.memory_key] = {
        "records": asyncio.run(session.get_items_with_metadata()),
        "context_limit": config.context_limit,
        "keep_last_n_turns": config.keep_last_n_turns,
        "backend": "agents_sdk_session",
    }
    state.world_state[f"{config.memory_key}_last_plan"] = plan
    save_session_state(state)
    return reply, state
