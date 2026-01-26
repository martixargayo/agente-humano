# backend/negotiation/negotiation_graph.py
from __future__ import annotations

import os
from typing import List, Tuple

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from normalizer import normalize_text
from prompts import BASE_PERSONALITY_PROMPT
from state import SessionState, Message, add_message, save_session_state

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from .belief_state_updater import update_belief_state
from .context_utils import build_context_snippet
from .policies import get_policy, list_policy_ids
from .policy_planner import plan_policy
from .progress_updater import update_progress_state
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
from .world_state_updater import update_world_state


load_dotenv()

# ---- Configuración RAG para técnicas de negociación por policy ----

EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-3-small")

DEFAULT_RAG_DIR = os.path.join(
    os.path.dirname(__file__),
    "policy_docs",
)

RAG_DIR = os.getenv("NEGOTIATION_RAG_DIR", DEFAULT_RAG_DIR)


def _load_negotiation_rag_index():
    if not os.path.isdir(RAG_DIR):
        print(f"[RAG] Directorio no encontrado: {RAG_DIR}. Usaré fallback simple.")
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
            print(f"[RAG] Error leyendo {path}: {exc}")

    if not docs:
        print(f"[RAG] No se encontraron documentos de técnicas en {RAG_DIR}.")
        return None

    try:
        embeddings = OpenAIEmbeddings(model=EMBEDDINGS_MODEL)
        vs = FAISS.from_documents(docs, embeddings)
        print(f"[RAG] Index de negociación cargado con {len(docs)} documentos.")
        return vs
    except Exception as exc:
        print(f"[RAG] Error creando el índice FAISS: {exc}")
        return None


NEGOTIATION_RAG_INDEX = _load_negotiation_rag_index()

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


class NegotiationTurn(TypedDict):
    summary: str
    history_text: str
    recent_history_text: str
    user_message: str

    objective: str
    constraints: str

    world_state: WorldState
    belief_state: BeliefState
    progress_state: ProgressState
    policy_decision: PolicyDecision

    response: str


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
        role = msg["role"]
        label = "Vendedor" if role == "user" else "Comprador"
        lines.append(f"{label}: {msg['content']}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


# ---- RAG táctico por policy ----


def get_policy_tactics(policy_id: str, context: str) -> str:
    policy = get_policy(policy_id)
    policy_label = policy.description if policy else policy_id

    if NEGOTIATION_RAG_INDEX is None:
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
        docs = NEGOTIATION_RAG_INDEX.similarity_search(query, k=3)
        if not docs:
            return (
                f"[RAG VACÍO] No se encontraron tácticas específicas para {policy_id}."
            )

        print("\n[RAG] Policy:", policy_id)
        for d in docs:
            print("  - Doc:", d.metadata.get("filename"), "| policy_hint:", d.metadata.get("policy_hint"))
        print("----------\n", flush=True)

        snippets: List[str] = []
        for d in docs:
            snippets.append(d.page_content.strip())

        joined = "\n\n---\n\n".join(snippets)
        header = f"Tácticas de apoyo para {policy_id} (RAG):\n"
        return header + joined

    except Exception as exc:
        print(f"[RAG] Error durante la búsqueda de tácticas: {exc}")
        return (
            f"[RAG ERROR] No se pudieron recuperar tácticas para {policy_id}."
        )


# ---- Nodos del grafo ----


def world_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    prev_world = state.get("world_state") or default_world_state()
    state["world_state"] = update_world_state(prev_world, state.get("user_message", ""))
    return state


def belief_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    prev_belief = state.get("belief_state") or default_belief_state()
    state["belief_state"] = update_belief_state(
        prev_belief_state=prev_belief,
        world_state=state["world_state"],
        user_message=state.get("user_message", ""),
        context_snippet=state.get("recent_history_text", ""),
    )
    return state


def policy_planner_node(state: NegotiationTurn) -> NegotiationTurn:
    _ensure_objective(state)
    state["policy_decision"] = plan_policy(
        world_state=state["world_state"],
        belief_state=state["belief_state"],
        progress_state=state["progress_state"],
        objective=state["objective"],
        constraints=state.get("constraints", ""),
        recent_context=state.get("recent_history_text", ""),
    )
    return state


def progress_updater_node(state: NegotiationTurn) -> NegotiationTurn:
    state["progress_state"] = update_progress_state(
        prev_progress=state.get("progress_state"),
        policy_decision=state["policy_decision"],
        world_state=state["world_state"],
        belief_state=state["belief_state"],
    )
    return state


def executor_node(state: NegotiationTurn) -> NegotiationTurn:
    _ensure_objective(state)

    summary_text = state.get("summary") or "Aún no hay resumen de la conversación."
    history_text = state.get("history_text") or "(sin historial reciente)"
    user_message = state.get("user_message") or ""

    objective = state.get("objective") or ""
    constraints = state.get("constraints") or ""

    policy_decision = state.get("policy_decision") or default_policy_decision()
    policy_id = policy_decision.get("policy_id", "rapport_build")
    micro_goal = policy_decision.get("micro_goal", "")
    risk_posture = policy_decision.get("risk_posture", "low")

    policy = get_policy(policy_id)
    phase_hint = policy.phase_hint if policy else None

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

    phase_line = f"Phase hint: {phase_hint}." if phase_hint else ""

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
- Tienes una alternativa segura: un coche del mismo año que te ofrecería tu hermana.
- Ese coche cuesta 8.000€, pero necesitaría al menos 2.000€ de arreglos, por lo que serían 10.000€ en total.
- Preferirías evitar esa opción si encuentras algo mejor aquí.

Límites y objetivos:
- Tu límite mental es no superar 10.000€ de coste total con este coche
  (precio + posibles arreglos/sorpresas).
- Quieres conseguir un acuerdo que esté por debajo de ese umbral.
- Quieres que la negociación sea cordial y razonable, sin conflicto.

Directrices adicionales:
- Tu intención actual es la policy "{policy_id}".
- Tu micro-objetivo inmediato: {micro_goal}
- {posture_instructions.get(risk_posture, posture_instructions["low"])}
- {phase_line}

Manual táctico de RAG para esta policy:
{techniques_text}

Reglas de estilo para tus respuestas al vendedor:
- Debes obedecer siempre las <style_rules_absolute>.
- Máximo 2 frases por turno, sin excepciones.
- Solo una pregunta por turno, al final de la última frase.
- Si te salen dos preguntas, fusiónalas en una sola que cubra lo esencial.
- Hablas como Daniel-comprador, nunca como IA.
- Responde como si estuvierais hablando en persona, cara a cara.
- No uses listas ni bullets en tu respuesta al vendedor.
- Evita sonar académico o técnico; habla como una persona normal.
</role_context>
"""

    executor_user = f"""
[RESUMEN INTERNO DE LA SESIÓN]
{summary_text}

[HISTORIAL RECIENTE]
{history_text}

[OBJETIVO INTERNO DE LA NEGOCIACIÓN]
{objective}

[CONSTRAINTS INTERNOS]
{constraints}

[POLICY DECISION]
{policy_decision}

[MENSAJE ACTUAL DEL VENDEDOR]
{user_message}

Tarea:
1. Responde como Daniel-comprador al vendedor, cumpliendo la policy actual.
2. Sé humano, estratégico y colaborativo.
3. No digas que sigues un plan ni hables de "policies".
"""

    messages = [
        SystemMessage(content=executor_system),
        HumanMessage(content=executor_user),
    ]

    result = executor_llm.invoke(messages)
    full_text = (result.content or "").strip()

    print("\n===== RAW_EXECUTOR_OUTPUT =====")
    print(full_text)
    print("===== END_RAW_EXECUTOR_OUTPUT =====\n", flush=True)

    normalized_response = normalize_text(full_text, user_message)

    print("\n===== NORMALIZED_EXECUTOR_OUTPUT =====")
    print(normalized_response)
    print("===== END_NORMALIZED_EXECUTOR_OUTPUT =====\n", flush=True)

    state["response"] = normalized_response
    return state


# ---- Construcción del grafo LangGraph ----

workflow = StateGraph(NegotiationTurn)

workflow.add_node("world_updater", world_updater_node)
workflow.add_node("belief_updater", belief_updater_node)
workflow.add_node("policy_planner", policy_planner_node)
workflow.add_node("progress_updater", progress_updater_node)
workflow.add_node("executor", executor_node)

workflow.add_edge(START, "world_updater")
workflow.add_edge("world_updater", "belief_updater")
workflow.add_edge("belief_updater", "policy_planner")
workflow.add_edge("policy_planner", "progress_updater")
workflow.add_edge("progress_updater", "executor")
workflow.add_edge("executor", END)

negotiation_app = workflow.compile()


# ---- Función de alto nivel: usar el grafo con SessionState ----


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
) -> Tuple[str, SessionState]:
    """
    Ejecuta un turno de negociación:
    - Añade el mensaje del vendedor al historial.
    - Construye el estado para LangGraph.
    - Pasa por world_updater + belief_updater + policy_planner + executor.
    - Guarda estados persistentes en SessionState.
    - Añade la respuesta del comprador al historial.
    """

    add_message(state, role="user", content=user_message)

    summary_text = state.summary or "Aún no hay resumen de la conversación."
    history_text = _format_messages_as_text(state.history)
    recent_history_text = build_context_snippet(state.history, state.summary)

    objective = state.negotiation_objective or ""
    constraints = (
        "- Límite total 10.000€ (precio + arreglos).\n"
        f"- Alternativa hermana: {state.sister_option_price:.0f}€ + "
        f"{state.sister_option_repairs:.0f}€ arreglos.\n"
        "- Evitar revelar el límite de 10k explícitamente."
    )

    graph_state: NegotiationTurn = {
        "summary": summary_text,
        "history_text": history_text,
        "recent_history_text": recent_history_text,
        "user_message": user_message,
        "objective": objective,
        "constraints": constraints,
        "world_state": normalize_world_state(state.world_state)[0],
        "belief_state": normalize_belief_state(state.belief_state)[0],
        "progress_state": normalize_progress_state(state.progress_state)[0],
        "policy_decision": normalize_policy_decision(
            state.policy_state, list_policy_ids()
        )[0],
        "response": "",
    }

    new_graph_state = negotiation_app.invoke(graph_state)

    state.negotiation_objective = new_graph_state["objective"]
    state.world_state = normalize_world_state(new_graph_state["world_state"])[0]
    state.belief_state = normalize_belief_state(new_graph_state["belief_state"])[0]
    state.policy_state = normalize_policy_decision(
        new_graph_state["policy_decision"], list_policy_ids()
    )[0]
    state.progress_state = normalize_progress_state(new_graph_state["progress_state"])[0]

    reply_text = new_graph_state["response"].strip()

    add_message(state, role="assistant", content=reply_text)
    save_session_state(state)

    return reply_text, state
