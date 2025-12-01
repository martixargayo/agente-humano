# backend/negotiation/negotiation_graph.py
from __future__ import annotations

import json
import os
from typing import List, Tuple

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

from prompts import BASE_PERSONALITY_PROMPT
from state import SessionState, Message, add_message, save_session_state

load_dotenv()

# ---- Modelos para planner y ejecutor ----

# --- Configuración de modelos DEL NEGOCIADOR (vía .env) ---

# Si no se define PLANNER_MODEL_NAME, usamos el modelo de resumen
# (SUMMARY_MODEL_NAME) como fallback razonable.
PLANNER_MODEL = os.getenv(
    "PLANNER_MODEL_NAME",
    os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"),
)

# Si no se define EXECUTOR_MODEL_NAME, usamos el modelo principal
# (OPENAI_MODEL_NAME) como fallback.
EXECUTOR_MODEL = os.getenv(
    "EXECUTOR_MODEL_NAME",
    os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
)

# Temperaturas con defaults seguros (pero siempre overrideables)
PLANNER_TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.0"))
EXECUTOR_TEMPERATURE = float(os.getenv("EXECUTOR_TEMPERATURE", "0.7"))


planner_llm = ChatOpenAI(
    model=PLANNER_MODEL,
    temperature=PLANNER_TEMPERATURE,
)

executor_llm = ChatOpenAI(
    model=EXECUTOR_MODEL,
    temperature=EXECUTOR_TEMPERATURE,
)


# ---- Plan base de negociación (fases) ----

BASE_NEGOTIATION_PLAN: List[str] = [
    "Fase 1 – Crear clima y confianza con el vendedor.",
    "Fase 2 – Preguntar y descubrir: intereses del vendedor y situación real del coche.",
    "Fase 3 – Encontrar una solución creativa que beneficie a ambos.",
    "Fase 4 – Concesiones, modificaciones y ajustes hasta una oferta de acuerdo.",
    "Fase 5 – Recapitulación detallada de lo acordado y confirmación final.",
]


# ---- Estado para LangGraph ----

class PlanExecute(TypedDict):
    """
    Estado interno del grafo de negociación para un turno.
    """
    summary: str
    history_text: str
    user_message: str

    objective: str
    plan: List[str]
    current_step_index: int
    step_results: List[Tuple[str, str]]

    response: str


# ---- Utilidades internas ----

def _ensure_plan_initialized(state: PlanExecute) -> None:
    """
    Si aún no hay objetivo/plan, los inicializa.
    """
    if not state.get("objective"):
        state["objective"] = (
            "Conseguir comprar este coche de segunda mano por un coste total "
            "inferior a 10.000€ (precio + posibles gastos), manteniendo una "
            "relación cordial con el vendedor."
        )

    if not state.get("plan"):
        state["plan"] = BASE_NEGOTIATION_PLAN.copy()
        state["current_step_index"] = 0
        state["step_results"] = []


def _get_current_phase(state: PlanExecute) -> str:
    plan = state.get("plan") or []
    if not plan:
        return "Fase desconocida"
    idx = state.get("current_step_index", 0)
    idx = max(0, min(idx, len(plan) - 1))
    return plan[idx]


def _format_plan(plan: List[str]) -> str:
    return "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan)) or "(sin plan)"


def _format_messages_as_text(messages: List[Message]) -> str:
    """
    Convierte la lista de mensajes en texto etiquetado,
    vista desde fuera: user = Vendedor, assistant = Comprador.
    """
    lines: List[str] = []
    for msg in messages:
        role = msg["role"]
        label = "Vendedor" if role == "user" else "Comprador"
        lines.append(f"{label}: {msg['content']}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


# ---- Hook para RAG de técnicas (stub, lo conectarás tú) ----

def get_phase_techniques(phase_name: str, context: str) -> str:
    """
    TODO: Conectar aquí tu RAG real (vector store con documentos por fase).

    De momento devuelve un texto de ejemplo para que el sistema funcione.
    """
    return (
        f"Técnicas recomendadas para {phase_name}:\n"
        "- Haz preguntas abiertas y escucha con atención.\n"
        "- Mantén un tono calmado y colaborativo.\n"
        "- Usa reformulaciones para demostrar que entiendes al vendedor.\n"
        "- Evita precipitarte con el precio si la fase aún no va de eso."
    )


# ---- Nodo PLANNER (decide fase) ----

def planner_node(state: PlanExecute) -> PlanExecute:
    """
    Decide en qué fase del plan debemos estar ahora.
    """

    _ensure_plan_initialized(state)

    plan = state["plan"]
    plan_text = _format_plan(plan)
    current_phase = _get_current_phase(state)

    summary_text = state.get("summary") or "(sin resumen aún)"
    history_text = state.get("history_text") or "(sin historial reciente)"
    user_message = state.get("user_message") or ""

    planner_system = """
Eres el planner interno de un comprador de coche de segunda mano.
No hablas con el vendedor; solo decides en qué fase del plan de negociación
debe centrarse ahora el comprador.

Plan base de negociación (no lo inventes, úsalo tal cual):
{plan_text}

La Fase 1 es crear clima, la Fase 2 es descubrir información,
la Fase 3 es construir soluciones creativas,
la Fase 4 es negociar concesiones y precios,
la Fase 5 es recapitular y cerrar.

Información interna del comprador:
- Tiene una opción alternativa: coche de su hermana por ~10.000€ (8.000 + 2.000 en arreglos).
- No quiere sobrepasar 10.000€ de coste total en este coche (precio + posibles gastos).
- Quiere negociar con calma, sin quemar la relación.

Tu tarea:
- Usando el resumen, el historial y el mensaje actual del vendedor,
  decide en qué fase del plan debería estar el comprador ahora.
- Mantén una progresión razonable (no saltes de Fase 1 a 5 sin sentido).
- Puedes quedarte en la misma fase si aún no se ha cumplido su objetivo.
- Si el vendedor ha sacado precio directo muy pronto, puede tener sentido
  pasar antes a Fase 4 (concesiones).

Devuelve SOLO un objeto JSON con:
  - "new_current_step_index": índice de fase (0 = Fase 1, 1 = Fase 2, ...),
  - "reason": explicación breve de tu decisión.
"""

    planner_user = f"""
[Resumen interno de la conversación]
{summary_text}

[Historial reciente]
{history_text}

[Plan actual]
{plan_text}

[Fase actual antes de tu decisión]
{current_phase}

[Mensaje actual del vendedor]
{user_message}

Responde SOLO con un JSON del tipo:
{{
  "new_current_step_index": 0,
  "reason": "..."
}}
"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", planner_system),
            ("user", "{input}"),
        ]
    )

    messages = prompt.format_messages(
        input=planner_user,
        plan_text=plan_text,
    )

    result = planner_llm.invoke(messages)
    raw = (result.content or "").strip()

    try:
        data = json.loads(raw)
        new_idx = int(data.get("new_current_step_index", state["current_step_index"]))
    except Exception:
        new_idx = state["current_step_index"]

    if plan:
        new_idx = max(0, min(new_idx, len(plan) - 1))
    else:
        new_idx = 0

    state["current_step_index"] = new_idx
    return state


# ---- Nodo EXECUTOR (responde como Daniel-comprador) ----

def executor_node(state: PlanExecute) -> PlanExecute:
    """
    Genera la respuesta del comprador al vendedor.
    """

    _ensure_plan_initialized(state)

    summary_text = state.get("summary") or "Aún no hay resumen de la conversación."
    history_text = state.get("history_text") or "(sin historial reciente)"
    user_message = state.get("user_message") or ""

    objective = state.get("objective") or ""
    plan = state["plan"]
    plan_text = _format_plan(plan)
    current_phase = _get_current_phase(state)

    # Contexto simplificado para el RAG
    rag_context = f"""
Resumen: {summary_text}
Historial reciente:
{history_text}

Fase actual: {current_phase}
"""

    techniques_text = get_phase_techniques(current_phase, rag_context)

    executor_system = f"""
{BASE_PERSONALITY_PROMPT}

<role_context>
Ahora interpretas a Daniel en el rol de COMPRADOR de un coche de segunda mano.

Contexto interno:
- Tienes una opción segura con tu hermana: coche del mismo año por ~10.000€ (8.000 + 2.000 en arreglos).
- Tu límite mental es no superar 10.000€ de coste total con este coche
  (precio + arreglos/posibles sorpresas).
- Tu objetivo es conseguir un acuerdo que esté por debajo de ese umbral,
  manteniendo una relación cordial con el vendedor.

Objetivo interno de esta negociación:
{objective}

Plan de negociación en fases:
{plan_text}

Fase actual en la que debes centrarte:
{current_phase}

Usa el siguiente "manual interno de técnicas" para guiar tu forma de hablar
en esta fase. Procede como si fueran tus notas privadas:

{techniques_text}

Reglas:
- Hablas como Daniel-comprador, nunca como IA.
- Cada mensaje debe suponer un pequeño avance en la fase actual,
  no resolver todo de golpe.
- No menciones explícitamente el plan ni las fases.
- No menciones a la hermana de forma explícita salvo que tenga mucho sentido.
- Puedes hacer preguntas, proponer opciones o hacer pequeñas concesiones,
  siempre con estrategia.
- Al final de tu mensaje, añade UNA línea con:
  PLAN_STATE: {{ "step_summary": "...", "phase_done": true/false }}
  describiendo brevemente qué has avanzado en esta fase y si la das por cumplida.
</role_context>
"""

    executor_user = f"""
[RESUMEN INTERNO DE LA SESIÓN]
{summary_text}

[HISTORIAL RECIENTE]
{history_text}

[OBJETIVO INTERNO DE LA NEGOCIACIÓN]
{objective}

[FASE ACTUAL]
{current_phase}

[MENSAJE ACTUAL DEL VENDEDOR]
{user_message}

Tarea:
1. Responde como Daniel-comprador al vendedor, avanzando la fase actual.
2. Sé humano, estratégico y colaborativo.
3. No digas que sigues un plan ni hables de "fases".
4. Al final de tu mensaje añade la línea:
   PLAN_STATE: {{ "step_summary": "...", "phase_done": true/false }}
"""

    exec_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", executor_system),
            ("user", "{input}"),
        ]
    )

    messages = exec_prompt.format_messages(input=executor_user)
    result = executor_llm.invoke(messages)
    full_text = (result.content or "").strip()

    step_summary = ""
    phase_done = False

    if "PLAN_STATE:" in full_text:
        visible_text, state_part = full_text.split("PLAN_STATE:", 1)
        visible_text = visible_text.strip()
        state_part = state_part.strip()

        try:
            data = json.loads(state_part)
            step_summary = data.get("step_summary", "")
            phase_done = bool(data.get("phase_done", False))
        except Exception:
            pass
    else:
        visible_text = full_text

    # Actualizar progreso de fase
    current_phase_name = _get_current_phase(state)
    if step_summary:
        state.setdefault("step_results", [])
        state["step_results"].append((current_phase_name, step_summary))

    # Si la fase se marca como completada, avanzamos a la siguiente
    plan = state.get("plan") or []
    if phase_done and plan:
        idx = state.get("current_step_index", 0)
        if idx < len(plan) - 1:
            state["current_step_index"] = idx + 1

    state["response"] = visible_text
    return state


# ---- Construcción del grafo LangGraph ----

workflow = StateGraph(PlanExecute)

workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)

workflow.add_edge(START, "planner")
workflow.add_edge("planner", "executor")
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
    - Pasa por planner + executor.
    - Guarda objetivo/plan/fase/progreso en SessionState.
    - Añade la respuesta del comprador al historial.
    """

    # 1) Añadir mensaje del vendedor al historial
    add_message(state, role="user", content=user_message)

    # 2) Construir textos de contexto
    summary_text = state.summary or "Aún no hay resumen de la conversación."
    history_text = _format_messages_as_text(state.history)

    # 3) Estado inicial para el grafo
    graph_state: PlanExecute = {
        "summary": summary_text,
        "history_text": history_text,
        "user_message": user_message,
        "objective": state.negotiation_objective,
        "plan": state.negotiation_plan,
        "current_step_index": state.current_step_index,
        "step_results": state.step_results,
        "response": "",
    }

    # 4) Ejecutar grafo (planner + executor)
    new_graph_state = negotiation_app.invoke(graph_state)

    # 5) Volcar cambios de vuelta al SessionState
    state.negotiation_objective = new_graph_state["objective"]
    state.negotiation_plan = new_graph_state["plan"]
    state.current_step_index = new_graph_state["current_step_index"]
    state.step_results = new_graph_state["step_results"]

    reply_text = new_graph_state["response"].strip()

    # 6) Añadir respuesta del comprador al historial
    add_message(state, role="assistant", content=reply_text)

    # 7) Guardar estado
    save_session_state(state)

    return reply_text, state
