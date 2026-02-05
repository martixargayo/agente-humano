# backend/negotiation/negotiation_graph.py
from __future__ import annotations

import logging
import os
import threading
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
from .elementos.execution_definitions import (
    EMBEDDINGS_MODEL,
    EXECUTOR_MODEL,
    EXECUTOR_TEMPERATURE,
    RAG_DIR,
    SUMMARY_MODEL,
    SUMMARY_TEMPERATURE,
)
from .gate_utils import (
    gate_belief,
    gate_phase_policy,
    gate_world,
    input_shape_features,
    interaction_fingerprint,
    loop_flags_changed,
    precedence_signature,
    select_policy_id_on_skip,
    stable_allowed_ids_hash,
    universal_state_fingerprint,
)
from .intent_manager import update_intent_state
from .phase_policy_planner import plan_phase_policy
from .phase_state_updater import postprocess_phase_candidate
from .precedence import compute_precedence
from .policies import get_policy, list_policy_ids, policy_phase_catalog, safe_neutral_policy_id
from .policy_planner import (
    _required_inputs_met,
    _violates_hard_constraints,
    allowed_policy_ids,
    apply_intent_constraints,
    apply_precedence_constraints,
    repair_policy_by_phase,
)
from .progress_updater import update_progress_state
from .executor import build_strategy_summary, normalize_executor_output, render_executor_output
from .elementos.render import resolve_render_profiles
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
from .world_state_updater import (
    _previous_user_message,
    diff_world_state,
    extract_interaction_signals,
    update_world_state,
)
from .nodes.world_node import world_updater_node
from .nodes.belief_node import belief_updater_node
from .nodes.precedence_node import precedence_node
from .nodes.intent_node import intent_manager_node
from .nodes.planner_node import phase_policy_planner_node
from .nodes.progress_node import progress_updater_node
from .nodes.executor_node import executor_node
from .telemetry.trace import diff_belief_state, top_evidence_v2
from .state.deps import AgentDeps, DEFAULT_DEPS


load_dotenv()
logger = logging.getLogger(__name__)

def _load_negotiation_rag_index():
    if not os.path.isdir(RAG_DIR):
        logger.warning("rag_dir_not_found=%s", RAG_DIR)
        return None

    docs: List[Document] = []
    for filename in os.listdir(RAG_DIR):
        if not filename.lower().endswith((".md", ".txt")):
            continue
        path = os.path.join(RAG_DIR, filename)
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
        logger.warning("rag_docs_not_found dir=%s", RAG_DIR)
        return None

    try:
        embeddings = OpenAIEmbeddings(model=EMBEDDINGS_MODEL)
        vs = FAISS.from_documents(docs, embeddings)
        logger.info("rag_index_loaded count=%s", len(docs))
        return vs
    except Exception as exc:
        logger.warning("rag_index_error=%s", exc)
        return None


_RAG_INDEX_LOCK = threading.Lock()
_NEGOTIATION_RAG_INDEX = None


def get_negotiation_rag_index():
    global _NEGOTIATION_RAG_INDEX
    # Fast path (sin lock) si ya está inicializado.
    if _NEGOTIATION_RAG_INDEX is not None:
        return _NEGOTIATION_RAG_INDEX

    # Slow path con lock para evitar doble init concurrente.
    with _RAG_INDEX_LOCK:
        if _NEGOTIATION_RAG_INDEX is None:
            _NEGOTIATION_RAG_INDEX = _load_negotiation_rag_index()

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
    constraints_struct: dict
    exit_option: dict
    max_total_cost: float

    world_state: WorldState
    prev_world_state: WorldState
    world_diff: dict
    belief_state: BeliefState
    prev_belief_state: BeliefState
    progress_state: ProgressState
    intent_hint: dict
    intent_meta: dict
    policy_decision: PolicyDecision
    policy_pre_repair: PolicyDecision | None
    policy_post_repair: PolicyDecision | None
    phase_candidate: dict | None
    phase_effective: dict | None
    executed_policy: PolicyDecision | None
    last_policy_executed: PolicyDecision | None
    last_assistant_message: str
    allowed_policy_ids: List[str]
    planner_meta: dict
    phase_meta: dict
    belief_update_meta: dict
    extractor_meta: dict
    gate_meta: dict
    precedence: dict
    precedence_signature: str
    deps: AgentDeps

    response: str
    assistant_message: str
    executor_output: dict
    executor_render_meta: dict
    strategy_summary: dict
    override_policy_id: str | None
    override_reason: str | None


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


def get_policy_tactics(policy_id: str, context: str) -> str:
    policy = get_policy(policy_id)
    policy_label = policy.description if policy else policy_id

    rag_index = get_negotiation_rag_index()
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

workflow = StateGraph(NegotiationTurn)

workflow.add_node("world_updater", world_updater_node)
workflow.add_node("belief_updater", belief_updater_node)
workflow.add_node("precedence", precedence_node)
workflow.add_node("intent_manager", intent_manager_node)
workflow.add_node("phase_policy_planner", phase_policy_planner_node)
workflow.add_node("progress_updater", progress_updater_node)
workflow.add_node("executor", executor_node)

workflow.add_edge(START, "world_updater")

workflow.add_edge("world_updater", "belief_updater")
workflow.add_edge("belief_updater", "precedence")
workflow.add_edge("precedence", "intent_manager")
workflow.add_edge("intent_manager", "phase_policy_planner")
workflow.add_edge("phase_policy_planner", "progress_updater")
workflow.add_edge("progress_updater", "executor")

workflow.add_edge("executor", END)

negotiation_app = workflow.compile()


# ---- Función de alto nivel: usar el grafo con SessionState ----


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    deps: AgentDeps = DEFAULT_DEPS,
) -> Tuple[str, SessionState]:
    """
    Ejecuta un turno de negociación:
    - Añade el mensaje del vendedor al historial.
    - Construye el estado para LangGraph.
    - Pasa por world_updater + belief_updater + precedence + intent_manager +
      phase_policy_planner + progress_updater + executor.
    - Guarda estados persistentes en SessionState.
    - Añade la respuesta del comprador al historial.
    """

    add_message(state, role="user", content=user_message)

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
    constraints_struct = {
        "max_total_cost": max_total_cost,
        "avoid_reveal_own_numbers": True,
        "respect_batna": True,
        "max_total_cost_margin": margin,
    }

    world_state_input, world_issues_in = normalize_world_state(state.world_state)
    belief_state_input, belief_issues_in = normalize_belief_state(state.belief_state)
    progress_state_input, progress_issues_in = normalize_progress_state(state.progress_state)
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
        "constraints_struct": constraints_struct,
        "exit_option": exit_option,
        "max_total_cost": max_total_cost,
        "world_state": world_state_input,
        "prev_world_state": world_state_input,
        "world_diff": {},
        "belief_state": belief_state_input,
        "prev_belief_state": belief_state_input,
        "progress_state": progress_state_input,
        "intent_hint": {},
        "intent_meta": {},
        "policy_decision": default_policy_decision(),
        "policy_pre_repair": None,
        "policy_post_repair": None,
        "phase_candidate": None,
        "phase_effective": None,
        "executed_policy": None,
        "last_policy_executed": last_policy_executed_input,
        "last_assistant_message": _last_assistant_message(state.history),
        "allowed_policy_ids": [],
        "planner_meta": {},
        "phase_meta": {},
        "belief_update_meta": {},
        "extractor_meta": {},
        "gate_meta": {},
        "precedence": {},
        "precedence_signature": "",
        "turn_count": state.turn_count,
        "deps": deps,
        "response": "",
        "assistant_message": "",
        "executor_output": {},
        "executor_render_meta": {},
        "strategy_summary": {},
        "override_policy_id": None,
        "override_reason": None,
    }

    new_graph_state = negotiation_app.invoke(graph_state)

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
    state.debug_trace.append(
        {
            "turn": state.turn_count,
            "world_prev": graph_state["world_state"],
            "world_new": new_world_state,
            "world_diff": new_graph_state.get("world_diff", {}),
            "belief_prev": graph_state["belief_state"],
            "belief_new": new_belief_state,
            "belief_diff": diff_belief_state(graph_state["belief_state"], new_belief_state),
            "allowed_policy_ids": new_graph_state.get("allowed_policy_ids", []),
            "policy_decision": new_policy_state,
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
            "intent_prev": new_graph_state.get("planner_meta", {}).get("intent_meta", {}).get(
                "intent_prev", {}
            ),
            "intent_new": new_graph_state.get("planner_meta", {}).get("intent_meta", {}).get(
                "intent_new", {}
            ),
            "intent_decision": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("intent_decision", ""),
            "intent_transition": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("intent_transition", ""),
            "intent_slots_delta": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("slots_filled_delta", {}),
            "intent_step_kind": new_graph_state.get("intent_hint", {}).get("step_kind", ""),
            "intent_target_slot": new_graph_state.get("intent_hint", {}).get("target_slot", ""),
            "intent_pivot_reason": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("pivot_reason", ""),
            "intent_pivot_strategy": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("pivot_strategy", ""),
            "intent_success_reasons": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("success_reasons", []),
            "intent_commitment_level": new_graph_state.get("planner_meta", {}).get(
                "intent_meta", {}
            ).get("commitment_level", ""),
            "planner_meta": new_graph_state.get("planner_meta", {}),
            "gates": new_graph_state.get("gate_meta", {}),
            "belief_update_meta": new_graph_state.get("belief_update_meta", {}),
            "phase_state": new_graph_state.get("progress_state", {}).get("phase_state", {}),
            "phase_meta": new_graph_state.get("planner_meta", {}).get("phase_meta", {}),
            "extractor_used": new_graph_state.get("extractor_meta", {}).get(
                "extractor_used", False
            ),
            "extractor_reasons": new_graph_state.get("extractor_meta", {}).get(
                "extractor_reasons", []
            ),
            "extractor_world_patch_keys": new_graph_state.get("extractor_meta", {}).get(
                "extractor_world_patch_keys", []
            ),
            "extractor_confidence_summary": new_graph_state.get("extractor_meta", {}).get(
                "extractor_confidence_summary", {"min": 0.0, "avg": 0.0}
            ),
            "top_evidence_v2": top_evidence_v2(new_world_state),
            "unknown_claims_count": len(
                (new_world_state.get("world_state_meta") or {}).get("unknown_claims", [])
            ),
            "memory_meta": new_graph_state.get("memory_meta", {}),
            "refresh_meta": new_graph_state.get("refresh_meta", {}),
            "exit_issues": exit_issues,
            "max_total_cost_margin": margin,
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
            "planner_failed": new_graph_state.get("planner_meta", {}).get("planner_failed", False),
            "planner_error": new_graph_state.get("planner_meta", {}).get("planner_error", ""),
            "planner_fallback_used": new_graph_state.get("planner_meta", {}).get(
                "planner_fallback_used", False
            ),
            "policy_normalization_changed": new_graph_state.get("planner_meta", {}).get(
                "policy_normalization_changed", False
            ),
            "belief_update_failed": new_graph_state.get("belief_update_meta", {}).get(
                "belief_update_failed", False
            ),
            "belief_update_error": new_graph_state.get("belief_update_meta", {}).get(
                "belief_update_error", ""
            ),
        }
    )
    save_session_state(state)

    return reply_text, state
