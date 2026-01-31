# backend/negotiation/negotiation_graph.py
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from normalizer import normalize_text
from prompts import BASE_PERSONALITY_PROMPT, SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
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
from .gate_utils import (
    gate_belief,
    gate_phase_policy,
    gate_world,
    input_shape_features,
    loop_flags_changed,
    precedence_signature,
    select_policy_id_on_skip,
    stable_allowed_ids_hash,
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
from .response_validator import validate_and_repair
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from .validation import (
    normalize_belief_state,
    normalize_policy_decision,
    normalize_progress_state,
    normalize_world_state,
)
from .world_state_updater import diff_world_state, update_world_state


load_dotenv()
logger = logging.getLogger(__name__)

# ---- Configuración RAG para técnicas de negociación por policy ----

EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-3-small")

DEFAULT_RAG_DIR = os.path.join(
    os.path.dirname(__file__),
    "policy_docs",
)

RAG_DIR = os.getenv("NEGOTIATION_RAG_DIR", DEFAULT_RAG_DIR)


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

# ---- Modelo principal (executor) ----

EXECUTOR_MODEL = os.getenv(
    "EXECUTOR_MODEL_NAME",
    os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
)

EXECUTOR_TEMPERATURE = float(os.getenv("EXECUTOR_TEMPERATURE", "0.7"))

executor_llm = ChatOpenAI(
    model=EXECUTOR_MODEL,
    temperature=EXECUTOR_TEMPERATURE,
)

# ---- Modelo de resumen ----

SUMMARY_MODEL = os.getenv(
    "SUMMARY_MODEL_NAME",
    os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
)
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.2"))

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

# Tipos “paper-grade”: narrow y explícitos
PlanFn = Callable[..., Tuple[dict, PolicyDecision, dict]]
BeliefFn = Callable[..., Tuple[BeliefState, dict]]
ExecuteFn = Callable[..., str]
SummarizeFn = Callable[[str, str], str]


@dataclass(frozen=True)
class AgentDeps:
    plan_phase_policy: PlanFn
    update_belief_state: BeliefFn
    execute: ExecuteFn
    summarize: Optional[SummarizeFn] = None


def _default_execute(messages: Any) -> str:
    # Mantén la lógica real actual, pero encapsulada para injection
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


def _diff_belief_state(prev: BeliefState, new: BeliefState) -> dict:
    diff: dict = {}
    if prev.get("stance") != new.get("stance"):
        diff["stance"] = {"before": prev.get("stance"), "after": new.get("stance")}
    if prev.get("dynamics") != new.get("dynamics"):
        diff["dynamics"] = {"before": prev.get("dynamics"), "after": new.get("dynamics")}
    if prev.get("reasons") != new.get("reasons"):
        diff["reasons"] = {"before": prev.get("reasons"), "after": new.get("reasons")}
    if prev.get("hypotheses") != new.get("hypotheses"):
        diff["hypotheses"] = {"before": prev.get("hypotheses"), "after": new.get("hypotheses")}
    if prev.get("tom") != new.get("tom"):
        diff["tom"] = {"before": prev.get("tom"), "after": new.get("tom")}
    return diff


def _top_evidence_v2(world_state: WorldState) -> list[dict]:
    claims = (world_state.get("world_observations_v2") or {}).get("claims", []) or []
    top = sorted(
        claims,
        key=lambda rec: (
            float(rec.get("confidence", 0.0)),
            int((rec.get("provenance") or {}).get("turn_idx") or 0),
        ),
        reverse=True,
    )[:5]
    compact = []
    for record in top:
        claim = record.get("claim", {}) or {}
        provenance = record.get("provenance", {}) or {}
        compact.append(
            {
                "path": claim.get("path"),
                "value": claim.get("value"),
                "confidence": record.get("confidence"),
                "turn_idx": provenance.get("turn_idx"),
                "text_prefix": str(provenance.get("text", ""))[:60],
            }
        )
    return compact


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


# ---- Nodos del grafo ----


def world_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    prev_world = state.get("world_state") or default_world_state()
    state["prev_world_state"] = prev_world
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    user_message = state.get("user_message", "")
    turn_count = state.get("turn_count", 0) or 0
    current_features = input_shape_features(user_message)
    world_skipped, skip_reason, gate_meta = gate_world(
        user_message=user_message,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_world_refresh_turn", 0) or 0),
        prev_features=gate_state.get("input_shape_prev") or {},
        current_features=current_features,
        interval=int(os.getenv("WORLD_REFRESH_INTERVAL_TURNS", "3")),
    )
    gate_state["input_shape_prev"] = current_features
    if world_skipped:
        gate_state["world_skip_count"] = int(gate_state.get("world_skip_count", 0) or 0) + 1
        state["world_state"] = prev_world
        state["world_diff"] = {}
        state["extractor_meta"] = {
            "extractor_used": False,
            "extractor_skipped": True,
            "skip_reason": skip_reason,
            "world_gate_features": gate_meta,
        }
    else:
        force_llm = skip_reason == "interval_expired"
        world_state, extractor_meta = update_world_state(
            prev_world,
            user_message,
            recent_history=state.get("recent_history_text", ""),
            belief_state=state.get("belief_state") or {},
            turn_count=turn_count,
            force_llm=force_llm,
        )
        gate_state["last_world_refresh_turn"] = turn_count
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, state["world_state"])
        extractor_meta["world_gate_features"] = gate_meta
        extractor_meta["extractor_skipped"] = False
        state["extractor_meta"] = extractor_meta
    state["progress_state"]["gate_state"] = gate_state
    return state


def belief_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    deps = state.get("deps", DEFAULT_DEPS)
    prev_belief = state.get("belief_state") or default_belief_state()
    state["prev_belief_state"] = prev_belief
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    turn_count = state.get("turn_count", 0) or 0
    belief_skipped, skip_reason = gate_belief(
        world_diff=state.get("world_diff", {}),
        prev_world=state.get("prev_world_state", {}),
        world=state.get("world_state", {}),
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_belief_refresh_turn", 0) or 0),
        interval=int(os.getenv("BELIEF_REFRESH_INTERVAL_TURNS", "3")),
    )
    if belief_skipped:
        gate_state["belief_skip_count"] = int(gate_state.get("belief_skip_count", 0) or 0) + 1
        belief_state = prev_belief
        belief_meta = {
            "belief_update_failed": False,
            "belief_update_error": "",
            "belief_update_skipped": True,
            "skip_reason": skip_reason,
        }
    else:
        belief_state, belief_meta = deps.update_belief_state(
            prev_belief_state=prev_belief,
            prev_world_state=state["prev_world_state"],
            world_state=state["world_state"],
            world_diff=state.get("world_diff", {}),
            last_policy_executed=state.get("last_policy_executed"),
            last_assistant_message=state.get("last_assistant_message", ""),
            user_message=state.get("user_message", ""),
            context_snippet=state.get("recent_history_text", ""),
            extractor_meta=state.get("extractor_meta", {}),
            force_update=True,
        )
        gate_state["last_belief_refresh_turn"] = turn_count
    state["belief_state"] = belief_state
    state["belief_update_meta"] = belief_meta
    state["progress_state"]["gate_state"] = gate_state
    return state


def intent_manager_node(state: NegotiationTurn) -> NegotiationTurn:
    intent_state, intent_meta, intent_hint = update_intent_state(
        prev_intent=state.get("progress_state", {}).get("intent_state"),
        prev_world_state=state.get("prev_world_state"),
        world_state=state["world_state"],
        belief_state=state["belief_state"],
        progress_state=state["progress_state"],
        user_message=state.get("user_message", ""),
        turn_count=state.get("turn_count", 0),
        precedence=state.get("precedence"),
    )
    state["progress_state"]["intent_state"] = intent_state
    state["intent_hint"] = intent_hint
    state["intent_meta"] = intent_meta
    return state


def precedence_node(state: NegotiationTurn) -> NegotiationTurn:
    prec = compute_precedence(
        world=state["world_state"],
        belief=state["belief_state"],
        intent=state.get("progress_state", {}).get("intent_state"),
    )
    state["precedence"] = {
        "mode": prec.mode,
        "reason": prec.reason,
        "min_policy_tags": list(prec.min_policy_tags),
        "block_policy_tags": list(prec.block_policy_tags),
        "phase_floor": prec.phase_floor,
        "allow_closing": prec.allow_closing,
    }
    state["precedence_signature"] = precedence_signature(state["precedence"])
    return state


def phase_policy_planner_node(state: NegotiationTurn) -> NegotiationTurn:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    progress_state = state.get("progress_state", {})
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    turn_count = state.get("turn_count", 0) or 0

    allowed_base = allowed_policy_ids(
        state["world_state"], state["belief_state"], state["progress_state"]
    )
    allowed_prec, prec_meta = apply_precedence_constraints(allowed_base, state.get("precedence"))
    allowed_final, preferred, intent_meta = apply_intent_constraints(
        allowed_prec, state.get("intent_hint")
    )
    required_filtered = [
        pid for pid in allowed_final if _required_inputs_met(pid, state["world_state"])
    ]
    if required_filtered:
        allowed_final = required_filtered
    allowed_final = [
        pid
        for pid in allowed_final
        if not _violates_hard_constraints(
            pid, state["world_state"], state.get("constraints_struct")
        )
    ]
    if not allowed_final:
        allowed_final = [safe_neutral_policy_id()]

    allowed_hash = stable_allowed_ids_hash(allowed_final)
    prev_allowed_hash = gate_state.get("allowed_ids_hash_prev", "")
    allowed_hash_changed = allowed_hash != prev_allowed_hash
    stable_count = int(gate_state.get("allowed_ids_hash_stable_count", 0) or 0)
    stable_count = stable_count + 1 if allowed_hash == prev_allowed_hash else 0

    current_signature = state.get("precedence_signature", "")
    prev_signature = gate_state.get("precedence_signature_prev", "")
    precedence_changed = current_signature != prev_signature
    loop_flags_prev = gate_state.get("loop_flags_prev", [])
    loop_flags_current = progress_state.get("loop_flags", [])
    loop_flags_changed_flag = loop_flags_changed(loop_flags_prev, loop_flags_current)
    intent_transition = (state.get("intent_meta") or {}).get("intent_transition")
    intent_transition_present = bool(intent_transition and intent_transition != "none")

    planner_skipped, skip_reason = gate_phase_policy(
        world_diff=state.get("world_diff", {}),
        precedence_changed=precedence_changed,
        intent_transition_present=intent_transition_present,
        loop_flags_changed_flag=loop_flags_changed_flag,
        allowed_ids_hash_changed=allowed_hash_changed,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_planner_refresh_turn", 0) or 0),
        interval=int(os.getenv("PHASE_POLICY_REFRESH_INTERVAL_TURNS", "2")),
    )

    phase_candidate = None
    phase_effective = progress_state.get("phase_state")
    policy_pre_repair = None
    policy_post_repair = None
    policy_decision = default_policy_decision()
    planner_meta: dict = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "planner_skipped": planner_skipped,
        "planner_skip_reason": skip_reason,
        "allowed_policy_ids": allowed_final,
        "allowed_policy_ids_base": allowed_base,
        "allowed_policy_ids_after_precedence": allowed_prec,
        "allowed_policy_ids_after_intent": allowed_final,
        "allowed_policy_ids_after_required_inputs": required_filtered,
        "intent_preferred_policy_ids": preferred,
        "allowed_ids_hash": allowed_hash,
        "allowed_ids_hash_prev": prev_allowed_hash,
        "allowed_ids_hash_stable_count": stable_count,
    }
    planner_meta.update(prec_meta)
    planner_meta.update(intent_meta)

    if planner_skipped:
        chosen_id, skip_mode = select_policy_id_on_skip(
            last_policy_chosen=progress_state.get("last_chosen_policy_id", ""),
            allowed_policy_ids=allowed_final,
            policy_attempts=progress_state.get("policy_attempts", {}),
            loop_flags=loop_flags_current,
            safe_neutral_policy_id=safe_neutral_policy_id(),
            max_attempts=int(os.getenv("PLANNER_SKIP_MAX_ATTEMPTS", "3")),
        )
        policy_decision = {
            "policy_id": chosen_id,
            "reason": "Planner skipped; fallback policy selected.",
            "micro_goal": "Mantener conversación abierta con una pregunta breve.",
            "risk_posture": "low",
            "why_short": "",
            "inputs_used": [],
        }
        planner_meta["planner_skip_mode"] = skip_mode
    else:
        phase_candidate, policy_decision, planner_call_meta = deps.plan_phase_policy(
            world_state=state["world_state"],
            world_diff=state.get("world_diff", {}),
            belief_state=state["belief_state"],
            progress_state=progress_state,
            intent_hint=state.get("intent_hint"),
            precedence=state.get("precedence"),
            objective=state["objective"],
            constraints=state.get("constraints", ""),
            constraints_struct=state.get("constraints_struct", {}),
            recent_context=state.get("recent_history_text", ""),
            allowed_policy_ids=allowed_final,
        )
        planner_meta.update(planner_call_meta)
        phase_effective, phase_meta = postprocess_phase_candidate(
            prev_phase_state=progress_state.get("phase_state"),
            phase_candidate=phase_candidate,
            turn_count=turn_count,
            precedence=state.get("precedence"),
        )
        phase_effective["last_updated_turn"] = turn_count
        policy_pre_repair = dict(policy_decision)
        commitment = (state.get("intent_hint") or {}).get("commitment_level")
        repaired_id, repair_meta = repair_policy_by_phase(
            policy_decision.get("policy_id", ""),
            allowed_final,
            policy_phase_catalog(),
            phase_effective.get("phase", "opening"),
            preferred,
            commitment,
            policy_attempts=progress_state.get("policy_attempts", {}),
        )
        if repaired_id and repaired_id != policy_decision.get("policy_id"):
            policy_decision["policy_id"] = repaired_id
        planner_meta.update(repair_meta)
        normalized_policy, issues = normalize_policy_decision(policy_decision, allowed_final)
        if issues:
            planner_meta["policy_normalization_changed"] = True
            planner_meta["issues"] = planner_meta.get("issues", []) + issues
        policy_decision = normalized_policy
        policy_post_repair = dict(policy_decision)
        state["phase_meta"] = phase_meta

    if not phase_effective:
        phase_effective = progress_state.get("phase_state") or default_progress_state()["phase_state"]
    progress_state["phase_state"] = phase_effective

    if planner_skipped:
        gate_state["planner_skip_count"] = int(gate_state.get("planner_skip_count", 0) or 0) + 1
    else:
        gate_state["last_planner_refresh_turn"] = turn_count
    gate_state["allowed_ids_hash_prev"] = allowed_hash
    gate_state["allowed_ids_hash_stable_count"] = stable_count
    gate_state["precedence_signature_prev"] = current_signature
    gate_state["loop_flags_prev"] = list(loop_flags_current)
    progress_state["gate_state"] = gate_state

    if not state.get("phase_meta"):
        state["phase_meta"] = {
            "phase_update_used": False,
            "phase_update_reason": "planner_skip" if planner_skipped else "planner",
        }
    planner_meta["intent_meta"] = state.get("intent_meta", {})
    planner_meta["phase_meta"] = state.get("phase_meta", {})
    planner_meta["phase_state"] = progress_state.get("phase_state", {})

    state["phase_candidate"] = phase_candidate
    state["phase_effective"] = phase_effective
    state["policy_pre_repair"] = policy_pre_repair
    state["policy_post_repair"] = policy_post_repair or policy_decision
    state["policy_decision"] = policy_decision
    state["planner_meta"] = planner_meta
    state["allowed_policy_ids"] = allowed_final
    state["progress_state"] = progress_state
    state["gate_meta"] = {
        "world_skipped": state.get("extractor_meta", {}).get("extractor_skipped", False),
        "belief_skipped": state.get("belief_update_meta", {}).get("belief_update_skipped", False),
        "planner_skipped": planner_skipped,
        "skip_reasons": {
            "world": state.get("extractor_meta", {}).get("skip_reason", ""),
            "belief": state.get("belief_update_meta", {}).get("skip_reason", ""),
            "planner": skip_reason,
        },
        "skip_counters": {
            "world": gate_state.get("world_skip_count", 0),
            "belief": gate_state.get("belief_skip_count", 0),
            "planner": gate_state.get("planner_skip_count", 0),
        },
        "last_refresh_turn": {
            "world": gate_state.get("last_world_refresh_turn", 0),
            "belief": gate_state.get("last_belief_refresh_turn", 0),
            "planner": gate_state.get("last_planner_refresh_turn", 0),
        },
        "world_gate_features": state.get("extractor_meta", {}).get("world_gate_features", {}),
        "allowed_ids_hash": allowed_hash,
        "allowed_ids_hash_prev": prev_allowed_hash,
        "allowed_ids_hash_stable_count": stable_count,
    }
    return state


def progress_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    state["progress_state"] = update_progress_state(
        prev_progress=state.get("progress_state"),
        policy_decision=state["policy_decision"],
        last_policy_executed=state.get("last_policy_executed"),
        prev_world_state=state["prev_world_state"],
        world_state=state["world_state"],
        prev_belief_state=state.get("prev_belief_state"),
        belief_state=state["belief_state"],
    )
    return state


def executor_node(state: NegotiationTurn) -> NegotiationTurn:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    summary_text = state.get("summary") or "Aún no hay resumen de la conversación."
    history_text = state.get("history_text") or "(sin historial reciente)"
    long_memory = state.get("long_memory") or ""
    short_memory = state.get("short_memory") or ""
    memory_block = format_memory_block(long_memory, short_memory)
    user_message = state.get("user_message") or ""

    objective = state.get("objective") or ""
    constraints = state.get("constraints") or ""

    # --- Policy: fuente única ejecutada ---
    policy_decision = state.get("policy_decision") or default_policy_decision()

    # Si nadie la ha cambiado antes, lo ejecutado = lo elegido
    state["executed_policy"] = state.get("executed_policy") or policy_decision
    executed = state["executed_policy"] or default_policy_decision()

    policy_id = executed.get("policy_id", "rapport_build")
    micro_goal = executed.get("micro_goal", "")
    risk_posture = executed.get("risk_posture", "low")

    phase_state = state.get("progress_state", {}).get("phase_state", {})
    phase = phase_state.get("phase", "opening")
    phase_confidence = phase_state.get("confidence", 0.6)
    phase_reasons = phase_state.get("reasons", [])
    policy = get_policy(policy_id)
    policy_phase_hints = (policy.phase_hints if policy else [])
    policy_target_slots = policy.target_slots if policy else []
    policy_expected_effects = policy.expected_effects if policy else []
    policy_failure_modes = policy.failure_modes if policy else []

    rag_context = f"""
Resumen: {summary_text}
Historial reciente:
{history_text}

Policy actual: {policy_id}
Micro-objetivo: {micro_goal}
Riesgo: {risk_posture}
"""

    techniques_text = get_policy_tactics(policy_id, rag_context)

    posture_instructions = {
        "low": "Mantén prudencia y suavidad, sin ceder de más.",
        "mid": "Equilibra firmeza y cordialidad.",
        "high": "Sé más firme y directo, sin agresividad.",
    }

    prec = state.get("precedence", {}) or {}
    prec_mode = prec.get("mode", "unknown")
    prec_reason = prec.get("reason", "n/a")
    precedence_line = f"Control precedence: {prec_mode} ({prec_reason})."
    phase_context_line = f"Current phase: {phase} (conf {phase_confidence})."
    phase_reasons_line = f"Phase reasons: {phase_reasons}."
    policy_phase_line = f"Policy phase hints: {policy_phase_hints}."
    policy_targets_line = f"Policy target slots: {policy_target_slots}."
    policy_effects_line = f"Expected effects: {policy_expected_effects}."
    policy_failures_line = f"Failure modes: {policy_failure_modes}."
    intent_hint = state.get("intent_hint", {}) or {}
    intent_goal = intent_hint.get("intent_goal", "")
    step_kind = intent_hint.get("step_kind", "")
    target_slot = intent_hint.get("target_slot", "")
    next_action_hint = intent_hint.get("next_action_hint", "")
    slots_missing = intent_hint.get("slots_missing", [])
    commitment_level = intent_hint.get("commitment_level", "")

    exit_option = state.get("exit_option") or {}
    max_total_cost = state.get("max_total_cost") or exit_option.get("total_cost", 0.0)
    executor_system = f"""
{BASE_PERSONALITY_PROMPT}

<scene_context>
Escenario de la negociación:
- Estás en persona con el vendedor, frente a frente.
- Os habéis reunido para ver un coche de segunda mano que te interesa.
- Estáis hablando cara a cara, en un entorno tranquilo (por ejemplo, el concesionario o un parking).
- Has visto el coche físicamente y podéis comentar detalles mirando el coche, sus papeles, etc.

Reglas de escena:
- Toda la interacción ocurre como una conversación oral, presencial.
- No hables de "chat", "pantalla", "mensajes", "escribir" ni nada digital,
  a menos que el usuario lo introduzca explícitamente.
- Si el usuario escribe como si fuera chat, interprétalo como palabras
  que te dice en voz alta.
- Habla siempre como si estuvieras allí, mirándole a los ojos y respondiendo en tiempo real.
</scene_context>

<role_context>
Contexto personal interno:
- Tienes una alternativa segura: {exit_option.get("label", "una alternativa de salida")}.
- Ese coche cuesta {float(exit_option.get("total_cost", 0.0)):.0f}€ en total.
- Preferirías evitar esa opción si encuentras algo mejor aquí.

Límites y objetivos:
- Tu límite mental es no superar {float(max_total_cost):.0f}€ de coste total con este coche
  (precio + posibles arreglos/sorpresas).
- Quieres conseguir un acuerdo que esté por debajo de ese umbral.
- Quieres que la negociación sea cordial y razonable, sin conflicto.

Directrices adicionales:
- Tu intención actual es la policy "{policy_id}".
- Tu micro-objetivo inmediato: {micro_goal}
- {posture_instructions.get(risk_posture, posture_instructions["low"])}
- {precedence_line}
- {phase_context_line}
- {phase_reasons_line}
- {policy_phase_line}
- {policy_targets_line}
- {policy_effects_line}
- {policy_failures_line}
- Intención activa: {intent_goal}
- Paso actual: {step_kind}
- Slot objetivo: {target_slot}
- Siguiente foco: {next_action_hint}
- Slots pendientes: {slots_missing}
- Compromiso: {commitment_level}
- Regla: 2 frases, 1 pregunta, y la pregunta debe pedir {target_slot}.
- Si {target_slot} está vacío, pregunta por el primer slot de {slots_missing} o pide un detalle verificable alineado con el paso actual.

Manual táctico de RAG para esta policy:
{techniques_text}

Reglas de estilo para tus respuestas al vendedor:
- Debes obedecer siempre las <style_rules_absolute>.
- Hablas como Daniel-comprador, nunca como IA.
- Responde como si estuvierais hablando en persona, cara a cara.
- No uses listas ni bullets en tu respuesta al vendedor.
- Evita sonar académico o técnico; habla como una persona normal.
</role_context>
"""

    executor_user = f"""
[MEMORY]
{memory_block}

[OBJETIVO INTERNO]
{objective}

[CONSTRAINTS INTERNOS]
{constraints}

[DECISIÓN OPERATIVA]
{policy_decision}

[MENSAJE ACTUAL DEL VENDEDOR]
{user_message}

Tarea:
1) Responde como Daniel-comprador al vendedor, cumpliendo la policy actual.
2) Sé humano, estratégico y colaborativo.
3) No digas que sigues un plan ni hables de "policies".
"""

    messages = [
        SystemMessage(content=executor_system),
        HumanMessage(content=executor_user),
    ]

    full_text = deps.execute(messages).strip()

    logger.info("raw_executor_output=%s", full_text)

    normalized_response = normalize_text(full_text, user_message)

    logger.info("normalized_executor_output=%s", normalized_response)

    constraints_struct = state.get("constraints_struct", {})
    repaired_response, violations, validator_meta = validate_and_repair(
        normalized_response,
        constraints_struct,
        executed,
        state.get("world_state", {}),
    )
    if violations:
        logger.info("executor_response_repaired=%s violations=%s", repaired_response, violations)
    override_policy_id = validator_meta.get("override_policy_id")
    override_reason = validator_meta.get("override_reason")
    if override_policy_id:
        executed = dict(executed)
        executed["policy_id"] = override_policy_id
        state["executed_policy"] = executed
    state["response"] = repaired_response
    state["executor_validator_meta"] = validator_meta
    state["override_policy_id"] = override_policy_id
    state["override_reason"] = override_reason
    return state


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
            "belief_diff": _diff_belief_state(graph_state["belief_state"], new_belief_state),
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
            "top_evidence_v2": _top_evidence_v2(new_world_state),
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
