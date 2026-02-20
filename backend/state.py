# backend/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Literal, Tuple, TypedDict

from negotiation.state_migration_v3 import migrate_belief_state_to_v3, migrate_world_state_to_v3

# ---- Tipos básicos ----

Role = Literal["user", "assistant", "system", "tool"]


class HistoryItem(TypedDict, total=False):
    role: Role
    content: str
    name: str
    synthetic: bool


Message = HistoryItem


class ExitOption(TypedDict):
    label: str
    total_cost: float
    notes: str


SessionKey = Tuple[str, str]


def default_exit_option() -> ExitOption:
    return {
        "label": "Coche hermana",
        "total_cost": 0.0,
        "notes": "",
    }


def _merge_nested(base: Dict, incoming: Dict) -> Dict:
    if not isinstance(incoming, dict):
        return base
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged.get(key, {}), **value}
        else:
            merged[key] = value
    return merged


@dataclass
class SessionState:
    user_id: str
    session_id: str

    # Resumen acumulado de todo lo "antiguo"
    summary: str = ""
    summary_meta: Dict = field(default_factory=dict)

    # Historial corto: últimos N turnos (ventana recortada)
    history: List[HistoryItem] = field(default_factory=list)

    # ---- NUEVO: estado explícito de negociación ----
    world_state: Dict = field(default_factory=dict)
    belief_state: Dict = field(default_factory=dict)
    policy_state: Dict = field(default_factory=dict)
    last_policy_executed: Dict | None = None
    progress_state: Dict = field(default_factory=dict)
    debug_trace: List[Dict] = field(default_factory=list)

    # ---- NUEVO: estado de negociación / planificación ----
    # Objetivo interno del agente (comprador)
    negotiation_objective: str = ""

    # Lista de fases del plan de negociación
    negotiation_plan: List[str] = field(default_factory=list)

    # Índice de la fase actual dentro de negotiation_plan (0 = Fase 1)
    current_step_index: int = 0

    # Progreso por fase: lista de (nombre_fase, resumen_progreso)
    step_results: List[Tuple[str, str]] = field(default_factory=list)

    # Datos internos del comprador (escenario coche)
    sister_option_price: float = 8000.0      # coche hermana
    sister_option_repairs: float = 2000.0    # reparaciones esperadas
    max_total_cost: float = 10000.0          # legacy read-only (backfill)
    exit_option: ExitOption = field(default_factory=default_exit_option)

    # Info auxiliar
    turn_count: int = 0
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# Almacén global en RAM (MVP, sin DB)
SESSIONS: Dict[SessionKey, SessionState] = {}

# Si algún día quieres leer estos valores desde env, puedes moverlos a agent.py.
# Aquí solo documentamos que son "parámetros de diseño".
DEFAULT_CONTEXT_LIMIT_TURNS: int = 12        # a partir de cuántos turnos totales empezamos a resumir
DEFAULT_KEEP_LAST_TURNS: int = 4            # cuántos turnos recientes guardamos "enteros"


def normalize_exit_option(
    raw: Dict | None,
    legacy_base_price: float,
    legacy_repairs: float,
    legacy_total_cost: float,
    fallback_turn: int,
) -> Tuple[ExitOption, List[str]]:
    issues: List[str] = []
    data = raw if isinstance(raw, dict) else {}

    label = data.get("label")
    if not isinstance(label, str) or not label.strip():
        label = "Coche hermana"
        issues.append("label_backfill_default")
    label = label.strip()

    total_cost = data.get("total_cost")
    if not isinstance(total_cost, (int, float)) or total_cost <= 0:
        backfill_total = 0.0
        if legacy_base_price or legacy_repairs:
            backfill_total = float(legacy_base_price) + float(legacy_repairs)
            issues.append("total_cost_backfill_legacy_components")
        elif legacy_total_cost > 0:
            backfill_total = float(legacy_total_cost)
            issues.append("total_cost_backfill_legacy_total")
        else:
            issues.append("total_cost_missing")
        total_cost = backfill_total

    notes = data.get("notes")
    if not isinstance(notes, str):
        notes = ""

    if issues:
        issues_note = ",".join(issues)
        notes = f"{notes}|backfill:{issues_note}@turn:{fallback_turn}".strip("|")

    normalized: ExitOption = {
        "label": label,
        "total_cost": float(total_cost),
        "notes": notes,
    }
    return normalized, issues


def ensure_exit_option(state: SessionState) -> Tuple[ExitOption, List[str]]:
    exit_option, issues = normalize_exit_option(
        state.exit_option,
        legacy_base_price=state.sister_option_price,
        legacy_repairs=state.sister_option_repairs,
        legacy_total_cost=state.max_total_cost,
        fallback_turn=state.turn_count,
    )
    state.exit_option = exit_option
    return exit_option, issues


def derive_max_total_cost(exit_option: ExitOption, margin: float = 0.0) -> Tuple[float, str]:
    margin = max(0.0, float(margin))
    total_cost = float(exit_option.get("total_cost", 0.0) or 0.0)
    if total_cost <= 0:
        return 0.0, ""
    max_total_cost = total_cost * (1.0 + margin)
    rule_note = "(derivado de alternativa de salida)" if margin == 0 else (
        f"(derivado de alternativa de salida +{margin:.0%})"
    )
    return max_total_cost, rule_note


def _make_key(user_id: str, session_id: str) -> SessionKey:
    return (user_id, session_id)


def get_session_state(user_id: str, session_id: str) -> SessionState:
    """
    Recupera el estado de sesión para (user_id, session_id).
    Si no existe, lo crea.
    """
    key = _make_key(user_id, session_id)
    if key not in SESSIONS:
        SESSIONS[key] = SessionState(user_id=user_id, session_id=session_id)
    state = SESSIONS[key]
    state.belief_state = migrate_belief_state_to_v3(state.belief_state)
    state.world_state = migrate_world_state_to_v3(state.world_state)
    return state


def save_session_state(state: SessionState) -> None:
    """
    Guarda/actualiza el estado en el diccionario global.
    """
    key = _make_key(state.user_id, state.session_id)
    state.last_updated = datetime.now(timezone.utc)
    SESSIONS[key] = state


def add_message(state: SessionState, role: Role, content: str) -> None:
    """
    Añade un mensaje al historial corto (history).
    No hace trimming ni resumen: eso lo controla agent.py.
    """
    msg: Message = {"role": role, "content": content.strip()}
    state.history.append(msg)
    state.turn_count += 1
    state.last_updated = datetime.now(timezone.utc)


def reset_session_state(user_id: str, session_id: str) -> None:
    """
    Elimina (reset) el estado de una sesión.
    """
    key = _make_key(user_id, session_id)
    SESSIONS.pop(key, None)
