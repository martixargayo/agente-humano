# backend/negotiation/negotiation_graph.py
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, List, Tuple

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

from normalizer import normalize_text
from state import (
    SessionState,
    Message,
    add_message,
    save_session_state,
    DEFAULT_CONTEXT_LIMIT_TURNS,
    DEFAULT_KEEP_LAST_TURNS,
    derive_max_total_cost,
    ensure_exit_option,
)

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from .belief_state_updater import update_belief_state
from .context_utils import (
    build_context_snippet,
    build_memory_context,
    format_memory_block,
    maybe_refresh_summary,
)
from .summary_jobs import (
    SUMMARY_JOBS,
    apply_deferred_hard_trim,
    deferred_summary_enabled,
    make_turn_job,
)
from .config import get_negotiation_model_config, negotiation_effective_model_params
from .gate_utils import (
    gate_belief,
    gate_world,
    input_shape_features,
    interaction_fingerprint,
    loop_flags_changed,
)
from .phase_policy_planner import plan_phase_policy
from .phase_state_updater import postprocess_phase_candidate
from .policies import get_policy, list_policy_ids, policy_phase_catalog, safe_neutral_policy_id
from .policy_planner import (
    _required_inputs_met,
    _violates_hard_constraints,
    allowed_policy_ids,
    repair_policy_by_phase,
)
from .progress_updater import update_progress_state
from .executor import build_strategy_summary, normalize_executor_output, render_executor_output
from .elementos.render import resolve_render_profiles
from .elementos.render.preset_registry import (
    apply_buyer_preset_to_render_state,
    resolve_runtime_buyer_preset_choice,
)
from .elementos.render.constraints_builder import build_constraints_struct
from .validator import validate_and_repair
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_belief_state,
    default_constraints_struct,
    default_policy_decision,
    default_progress_state,
    default_render_state,
    default_world_state,
)
from .mode_inference import update_conversation_mode
from .validation import (
    normalize_belief_state,
    normalize_policy_decision,
    normalize_progress_state,
    normalize_world_state,
)

from .world_state_updater import diff_world_state, update_world_state
from .nodes.world_node import world_updater_node
from .nodes.belief_node import belief_updater_node
from .nodes.policy_progress_node import policy_progress_node
from .nodes.planner_node import phase_policy_planner_node
from .nodes.progress_node import progress_updater_node
from .nodes.executor_node import executor_node
from .telemetry.trace import diff_belief_state, top_evidence_v2
from .telemetry.trace_runtime import finish_node_timer, init_trace_runtime, start_node_timer
from .state.deps import AgentDeps, DEFAULT_DEPS



load_dotenv()
logger = logging.getLogger(__name__)


def _jsonable_belief_bucket_item(item: Any, *, max_text: int = 220) -> dict[str, Any] | None:
    if hasattr(item, "model_dump"):
        try:
            item = item.model_dump()
        except Exception:
            return None
    elif hasattr(item, "dict"):
        try:
            item = item.dict()
        except Exception:
            return None

    if not isinstance(item, dict):
        return None
    text = str(item.get("text", "")).strip()[:max_text]
    if not text:
        return None

    confidence_raw = item.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    status = str(item.get("status", "active")).strip() or "active"
    return {
        "text": text,
        "confidence": confidence,
        "status": status,
    }


def _compact_belief_buckets(belief_state: dict[str, Any] | None) -> dict[str, Any]:
    buckets = (belief_state or {}).get("belief_buckets")
    if not isinstance(buckets, dict):
        return {}
    limits = {
        "hypotheses": 5,
        "strategy_notes": 5,
        "risk_flags": 5,
        "watch_items": 5,
    }
    compact: dict[str, Any] = {key: [] for key in limits}
    for key, limit in limits.items():
        value = buckets.get(key)
        if not isinstance(value, list):
            continue
        items: list[dict[str, Any]] = []
        for raw_item in value[:limit]:
            parsed = _jsonable_belief_bucket_item(raw_item)
            if parsed is None:
                continue
            items.append(parsed)
        compact[key] = items
    return compact


def _trace_belief_snapshot(
    normalized_belief_state: dict[str, Any],
    raw_belief_state: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot = dict(normalized_belief_state or {})
    compact_buckets = _compact_belief_buckets(raw_belief_state)
    if compact_buckets:
        snapshot["belief_buckets"] = compact_buckets
    return snapshot

def _load_negotiation_rag_index(cfg):
    rag_dir = cfg.rag_dir
    if not os.path.isdir(rag_dir):
        logger.warning("rag_dir_not_found=%s", rag_dir)

        return None

    docs: List[Document] = []
    for filename in os.listdir(rag_dir):
        if not filename.lower().endswith((".md", ".txt")):
            continue
        path = os.path.join(rag_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            if not text:
                continue

            policy_hint = filename.replace(".md", "").replace(".txt", "")
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "filename": filename,
                        "policy_hint": policy_hint,
                    },
                )
            )
        except Exception as exc:
            logger.warning("rag_read_error path=%s error=%s", path, exc)

    if not docs:
        logger.warning("rag_docs_not_found dir=%s", rag_dir)
        return None

    try:
        embeddings = OpenAIEmbeddings(model=cfg.embeddings.model)
        vs = FAISS.from_documents(docs, embeddings)
        logger.info("rag_index_loaded count=%s", len(docs))
        return vs
    except Exception as exc:
        logger.warning("rag_index_error=%s", exc)
        return None


_RAG_INDEX_LOCK = threading.Lock()
_NEGOTIATION_RAG_INDEX = None
_NEGOTIATION_RAG_INDEX_KEY: tuple[str, str] | None = None


def get_negotiation_rag_index(cfg=None):
    global _NEGOTIATION_RAG_INDEX, _NEGOTIATION_RAG_INDEX_KEY
    cfg = cfg or get_negotiation_model_config()
    key = (cfg.rag_dir, cfg.embeddings.model)
    if _NEGOTIATION_RAG_INDEX is not None and _NEGOTIATION_RAG_INDEX_KEY == key:
        return _NEGOTIATION_RAG_INDEX

    with _RAG_INDEX_LOCK:
        if _NEGOTIATION_RAG_INDEX is None or _NEGOTIATION_RAG_INDEX_KEY != key:
            _NEGOTIATION_RAG_INDEX = _load_negotiation_rag_index(cfg)
            _NEGOTIATION_RAG_INDEX_KEY = key

    return _NEGOTIATION_RAG_INDEX





class NegotiationTurn(TypedDict):
    summary: str
    history_text: str
    recent_history_text: str
    long_memory: str
    short_memory: str
    memory_meta: dict
    refresh_meta: dict
    user_message: str
    turn_count: int
    input_modality: str
    conversation_mode: str

    objective: str
    constraints: str
    hard_constraints_struct: dict
    exit_option: dict
    max_total_cost: float

    world_state: WorldState
    prev_world_state: WorldState
    world_diff: dict
    belief_state: BeliefState
    prev_belief_state: BeliefState
    progress_state: ProgressState
    policy_hint: dict
    policy_meta: dict
    policy_decision: PolicyDecision
    policy_pre_repair: PolicyDecision | None
    policy_post_repair: PolicyDecision | None
    phase_candidate: dict | None
    phase_effective: dict | None
    policy_plan_judgement: dict | None
    executor_instruction: dict | None
    executed_policy: PolicyDecision | None
    last_policy_executed: PolicyDecision | None
    last_assistant_message: str
    allowed_policy_ids: List[str]
    planner_meta: dict
    phase_meta: dict
    belief_update_meta: dict
    extractor_meta: dict
    gate_meta: dict
    advisor_recs: dict
    advisor_meta: dict
    deps: AgentDeps

    response: str
    assistant_message: str
    executor_output: dict
    executor_render_meta: dict
    strategy_summary: dict
    override_policy_id: str | None
    override_reason: str | None

    trace_runtime: dict
    planner_debug_v2: dict
    executor_debug_v2: dict
    executor_validator_meta: dict

# ---- Utilidades internas ----


def _ensure_objective(state: NegotiationTurn) -> None:
    if not state.get("objective"):
        state["objective"] = (
            "Conseguir comprar este coche de segunda mano por un coste total "
            "inferior a 10.000€ (precio + posibles gastos), manteniendo una "
            "relación cordial con el vendedor."
        )


def _format_messages_as_text(messages: List[Message]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = msg.get("role", "assistant")
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            label = "Vendedor"
        elif role == "assistant":
            label = "Comprador"
        else:
            label = str(role).upper()

        lines.append(f"{label}: {content}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _last_assistant_message(messages: List[Message]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""


# ---- RAG táctico por policy ----


def get_policy_tactics(policy_id: str, context: str, cfg=None) -> str:
    policy = get_policy(policy_id)
    policy_label = policy.description if policy else policy_id

    rag_index = get_negotiation_rag_index(cfg)
    if rag_index is None:
        return (
            f"[RAG FALLBACK] Tácticas para policy {policy_label}:\n"
            "- Mantén claridad y brevedad.\n"
            "- Usa preguntas cortas y concretas.\n"
            "- Refuerza tu objetivo sin confrontar."
        )

    query = f"""
Policy: {policy_id}
Descripción: {policy_label}

Contexto reciente:
{context}

Objetivo: recuperar tácticas concretas para ejecutar esta policy.
"""

    try:
        docs = rag_index.similarity_search(query, k=3)
        if not docs:
            return (
                f"[RAG VACÍO] No se encontraron tácticas específicas para {policy_id}."
            )

        logger.info("rag_policy=%s", policy_id)
        for doc in docs:
            logger.info(
                "rag_doc filename=%s policy_hint=%s",
                doc.metadata.get("filename"),
                doc.metadata.get("policy_hint"),
            )

        snippets: List[str] = []
        for d in docs:
            snippets.append(d.page_content.strip())

        joined = "\n\n---\n\n".join(snippets)
        header = f"Tácticas de apoyo para {policy_id} (RAG):\n"
        return header + joined

    except Exception as exc:
        logger.warning("rag_search_error=%s", exc)
        return (
            f"[RAG ERROR] No se pudieron recuperar tácticas para {policy_id}."
        )


# ---- Construcción del grafo LangGraph ----


def _instrumented_node(node_name: str, node_fn):
    def _wrapped(state: dict):
        started = start_node_timer(state, node_name)
        next_state = node_fn(state)
        skip_key = f"{node_name.split('_')[0]}_skipped"
        skipped = bool((next_state.get("gate_meta") or {}).get(skip_key, False))
        finish_node_timer(next_state, node_name, started, skipped=skipped)
        return next_state

    return _wrapped


workflow = StateGraph(NegotiationTurn)

workflow.add_node("world_updater", _instrumented_node("world_updater", world_updater_node))
workflow.add_node("belief_updater", _instrumented_node("belief_updater", belief_updater_node))
workflow.add_node("policy_progress", _instrumented_node("policy_progress", policy_progress_node))
workflow.add_node("phase_policy_planner", _instrumented_node("phase_policy_planner", phase_policy_planner_node))
workflow.add_node("progress_updater", _instrumented_node("progress_updater", progress_updater_node))
workflow.add_node("executor", _instrumented_node("executor", executor_node))

workflow.add_edge(START, "world_updater")

workflow.add_edge("world_updater", "belief_updater")
workflow.add_edge("belief_updater", "policy_progress")
workflow.add_edge("policy_progress", "phase_policy_planner")
workflow.add_edge("phase_policy_planner", "progress_updater")
workflow.add_edge("progress_updater", "executor")

workflow.add_edge("executor", END)

negotiation_app = workflow.compile()


# ---- Función de alto nivel: usar el grafo con SessionState ----


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    deps: AgentDeps = DEFAULT_DEPS,
    explicit_preset_id: str | None = None,
) -> Tuple[str, SessionState]:
    """
    Ejecuta un turno de negociación:
    - Añade el mensaje del vendedor al historial.
    - Construye el estado para LangGraph.
    - Pasa por world_updater + belief_updater + policy_progress +
      phase_policy_planner + progress_updater + executor.
    - Guarda estados persistentes en SessionState.
    - Añade la respuesta del comprador al historial.
    """

    cfg = get_negotiation_model_config()

    t_turn_start = time.perf_counter()

    add_message(state, role="user", content=user_message)

    if deferred_summary_enabled():
        refresh_meta = {"refreshed": False, "reason": "deferred"}
    else:
        refresh_meta = maybe_refresh_summary(
            state,
            deps=deps,
            context_limit_turns=DEFAULT_CONTEXT_LIMIT_TURNS,
            keep_last_n_turns=DEFAULT_KEEP_LAST_TURNS,
        )

    long_memory, short_memory, memory_meta = build_memory_context(
        state.history,
        state.summary,
        keep_last_n_turns=DEFAULT_KEEP_LAST_TURNS,
    )
    summary_text = long_memory or "Aún no hay resumen de la conversación."
    history_text = _format_messages_as_text(state.history)
    recent_history_text = build_context_snippet(state.history, state.summary, seller_only=True)

    objective = state.negotiation_objective or ""
    exit_option, exit_issues = ensure_exit_option(state)
    margin = float(os.getenv("MAX_TOTAL_COST_MARGIN", "0.0") or 0.0)
    max_total_cost, rule_note = derive_max_total_cost(exit_option, margin=margin)
    constraints = (
        "- Evitar revelar el límite explícitamente salvo necesidad táctica.\n"
        f"- Alternativa de salida: {exit_option['label']}.\n"
        f"- Coste total alternativa: {exit_option['total_cost']:.0f}€.\n"
        f"- Máximo coste total aceptable derivado: ≤ {max_total_cost:.0f}€ {rule_note}.\n"
    )
    hard_constraints_struct = {
        "max_total_cost": max_total_cost,
        "avoid_reveal_own_numbers": True,
        "respect_batna": True,
        "max_total_cost_margin": margin,
    }

    prev_belief_state_raw = state.belief_state if isinstance(state.belief_state, dict) else {}
    world_state_input, world_issues_in = normalize_world_state(state.world_state)
    belief_state_input, belief_issues_in = normalize_belief_state(state.belief_state)
    progress_state_input, progress_issues_in = normalize_progress_state(state.progress_state)
    explicit_runtime_preset = explicit_preset_id
    if explicit_runtime_preset is None:
        explicit_runtime_preset = (
            (progress_state_input.get("render_state") or {}).get("buyer_preset_id")
            if isinstance(progress_state_input, dict)
            else None
        )

    runtime_preset, preset_source = resolve_runtime_buyer_preset_choice(explicit_runtime_preset)
    override_existing = preset_source == "explicit"
    progress_state_input, preset_meta = apply_buyer_preset_to_render_state(
        progress_state_input,
        runtime_preset,
        override_existing=override_existing,
        preset_source=preset_source,
    )
    policy_issues_in: list[str] = []
    last_policy_executed_input = state.last_policy_executed
    if (
        not last_policy_executed_input
        or not isinstance(last_policy_executed_input, dict)
        or not last_policy_executed_input.get("policy_id")
    ):
        last_policy_executed_input = None
    else:
        _, policy_issues_in = normalize_policy_decision(
            last_policy_executed_input, list_policy_ids()
        )

    graph_state: NegotiationTurn = {
        "summary": summary_text,
        "history_text": history_text,
        "recent_history_text": recent_history_text,
        "long_memory": long_memory,
        "short_memory": short_memory,
        "memory_meta": memory_meta,
        "refresh_meta": refresh_meta,
        "user_message": user_message,
        "conversation_mode": progress_state_input.get("conversation_mode", "general"),
        "objective": objective,
        "constraints": constraints,
        "hard_constraints_struct": hard_constraints_struct,
        "exit_option": exit_option,
        "max_total_cost": max_total_cost,
        "world_state": world_state_input,
        "prev_world_state": world_state_input,
        "world_diff": {},
        "belief_state": belief_state_input,
        "prev_belief_state": belief_state_input,
        "progress_state": progress_state_input,
        "policy_hint": {},
        "policy_meta": {},
        "policy_decision": default_policy_decision(),
        "policy_pre_repair": None,
        "policy_post_repair": None,
        "phase_candidate": None,
        "phase_effective": None,
        "policy_plan_judgement": None,
        "executor_instruction": None,
        "executed_policy": None,
        "last_policy_executed": last_policy_executed_input,
        "last_assistant_message": _last_assistant_message(state.history),
        "allowed_policy_ids": [],
        "planner_meta": {},
        "phase_meta": {},
        "belief_update_meta": {},
        "extractor_meta": {},
        "gate_meta": {},
        "advisor_recs": {},
        "advisor_meta": {},
        "turn_count": state.turn_count,
        "deps": deps,
        "response": "",
        "assistant_message": "",
        "executor_output": {},
        "executor_render_meta": {},
        "strategy_summary": {},
        "override_policy_id": None,
        "override_reason": None,
        "trace_runtime": init_trace_runtime(),
    }

    t_before_graph = time.perf_counter()
    new_graph_state = negotiation_app.invoke(graph_state)
    t_after_graph = time.perf_counter()

    state.negotiation_objective = new_graph_state["objective"]
    new_world_state, world_issues_out = normalize_world_state(new_graph_state["world_state"])
    new_belief_state, belief_issues_out = normalize_belief_state(new_graph_state["belief_state"])
    new_policy_state, policy_issues_out = normalize_policy_decision(
        new_graph_state["policy_decision"], list_policy_ids()
    )
    executed_policy_raw = new_graph_state.get("executed_policy") or new_graph_state.get(
        "policy_decision"
    )
    normalized_executed_policy, executed_policy_issues = normalize_policy_decision(
        executed_policy_raw, list_policy_ids()
    )
    new_progress_state, progress_issues_out = normalize_progress_state(
        new_graph_state["progress_state"]
    )

    state.world_state = new_world_state
    state.belief_state = new_belief_state
    state.progress_state = new_progress_state
    state.last_policy_executed = normalized_executed_policy

    reply_text = new_graph_state["response"].strip()

    add_message(state, role="assistant", content=reply_text)
    t_reply_saved = time.perf_counter()

    trace_belief_prev = _trace_belief_snapshot(belief_state_input, prev_belief_state_raw)
    trace_belief_new = _trace_belief_snapshot(new_belief_state, new_graph_state.get("belief_state"))

    summary_enqueue_meta = {"enqueued": False, "source": "none", "hard_trim_applied": False}
    if deferred_summary_enabled():
        hard_trim_turns = DEFAULT_CONTEXT_LIMIT_TURNS + DEFAULT_KEEP_LAST_TURNS
        hard_trim_applied = apply_deferred_hard_trim(state, max_user_turns=hard_trim_turns)
        enqueued = SUMMARY_JOBS.enqueue(
            make_turn_job(
                state,
                context_limit_turns=DEFAULT_CONTEXT_LIMIT_TURNS,
                keep_last_n_turns=DEFAULT_KEEP_LAST_TURNS,
            )
        )
        summary_enqueue_meta = {
            "enqueued": enqueued,
            "source": "run_negotiation_agent",
            "turn_id": state.turn_count,
            "hard_trim_applied": hard_trim_applied,
            "hard_trim_turns": hard_trim_turns,
        }
    t_summary_enqueued = time.perf_counter()

    state.debug_trace.append(
        {
            "turn": state.turn_count,
            "t_turn_start": t_turn_start,
            "t_before_graph": t_before_graph,
            "t_after_graph": t_after_graph,
            "t_reply_saved": t_reply_saved,
            "t_summary_enqueued": t_summary_enqueued,
            "summary_enqueue_meta": summary_enqueue_meta,
            "user_message": user_message,
            "assistant_reply": reply_text,
            "world_prev": graph_state["world_state"],
            "world_new": new_world_state,
            "world_diff": new_graph_state.get("world_diff", {}),
            "belief_prev": trace_belief_prev,
            "belief_new": trace_belief_new,
            "belief_diff": diff_belief_state(trace_belief_prev, trace_belief_new),
            "allowed_policy_ids": new_graph_state.get("allowed_policy_ids", []),
            "policy_decision": new_policy_state,
            "policy_plan_judgement": new_graph_state.get("policy_plan_judgement") or {},
            "policy_pre_repair": new_graph_state.get("policy_pre_repair"),
            "policy_post_repair": new_graph_state.get("policy_post_repair"),
            "phase_candidate": new_graph_state.get("phase_candidate"),
            "phase_effective": new_graph_state.get("phase_effective"),
            "executed_policy_raw": executed_policy_raw,
            "executed_policy_normalized": normalized_executed_policy,
            "executed_policy_issues": executed_policy_issues,
            "override_policy_id": new_graph_state.get("override_policy_id"),
            "override_reason": new_graph_state.get("override_reason"),
            "progress_state": new_progress_state,
            "planner_meta": new_graph_state.get("planner_meta", {}),
            "advisor_recs": new_graph_state.get("advisor_recs", {}),
            "advisor_meta": new_graph_state.get("advisor_meta", {}),
            "planner_debug": new_graph_state.get("planner_debug", {}),
            "gates": new_graph_state.get("gate_meta", {}),
            "belief_update_meta": new_graph_state.get("belief_update_meta", {}),
            "progress_debug": new_graph_state.get("progress_debug", {}),
            "executor_debug": new_graph_state.get("executor_debug", {}),
            "executor_debug_v2": new_graph_state.get("executor_debug_v2", {}),
            "planner_debug_v2": new_graph_state.get("planner_debug_v2", {}),
            "executor_validator_meta": new_graph_state.get("executor_validator_meta", {}),
            "trace_runtime": new_graph_state.get("trace_runtime", init_trace_runtime()),
            "phase_state": new_graph_state.get("progress_state", {}).get("phase_state", {}),
            "phase_meta": new_graph_state.get("planner_meta", {}).get("phase_meta", {}),
            "extractor_used": new_graph_state.get("extractor_meta", {}).get("extractor_used", False),
            "extractor_reasons": new_graph_state.get("extractor_meta", {}).get("extractor_reasons", []),
            "extractor_world_patch_keys": new_graph_state.get("extractor_meta", {}).get("extractor_world_patch_keys", []),
            "merged_changed_paths": new_graph_state.get("extractor_meta", {}).get("merged_changed_paths", []),
            "diff_paths": new_graph_state.get("extractor_meta", {}).get("diff_paths", []),
            "backstop_reasons": new_graph_state.get("extractor_meta", {}).get("backstop_reasons", []),
            "fallback_applied": bool(new_graph_state.get("extractor_meta", {}).get("fallback_applied", False)),
            "fallback_reasons": new_graph_state.get("extractor_meta", {}).get("fallback_reasons", []),
            "extractor_confidence_summary": new_graph_state.get("extractor_meta", {}).get("extractor_confidence_summary", {"min": 0.0, "avg": 0.0}),
            "top_evidence_v2": top_evidence_v2(new_world_state),
            "memory_meta": new_graph_state.get("memory_meta", {}),
            "refresh_meta": new_graph_state.get("refresh_meta", {}),
            "preset_meta": preset_meta,
            "exit_issues": exit_issues,
            "max_total_cost_margin": margin,
            "build_git_sha": (os.getenv("BUILD_GIT_SHA") or os.getenv("GIT_SHA") or "unknown"),
            "validation_issues": {
                "world_in": world_issues_in,
                "belief_in": belief_issues_in,
                "policy_in": policy_issues_in,
                "progress_in": progress_issues_in,
                "world_out": world_issues_out,
                "belief_out": belief_issues_out,
                "policy_out": policy_issues_out,
                "progress_out": progress_issues_out,
            },
            **negotiation_effective_model_params(cfg),
            "planner_failed": new_graph_state.get("planner_meta", {}).get("planner_failed", False),
            "planner_error": new_graph_state.get("planner_meta", {}).get("planner_error", ""),
            "planner_fallback_used": new_graph_state.get("planner_meta", {}).get("planner_fallback_used", False),
            "policy_normalization_changed": new_graph_state.get("planner_meta", {}).get("policy_normalization_changed", False),
            "belief_update_failed": new_graph_state.get("belief_update_meta", {}).get("belief_update_failed", False),
            "belief_update_error": new_graph_state.get("belief_update_meta", {}).get("belief_update_error", ""),
        }
    )
    save_session_state(state)

    return reply_text, state
