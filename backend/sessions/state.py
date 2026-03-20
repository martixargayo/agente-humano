# backend/state.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
import os
from threading import RLock
from typing import Any, Dict, Iterable, List, Literal, Mapping, Protocol, Tuple, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from sessions.state_migration_v3 import migrate_belief_state_to_v3, migrate_world_state_to_v3

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
SESSION_ENVELOPE_SCHEMA_VERSION = "session_envelope.v1"


def default_exit_option() -> ExitOption:
    return {
        "label": "Coche hermana",
        "total_cost": 0.0,
        "notes": "",
    }


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


class SessionIdentityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    session_id: str


class SessionBindingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface: str | None = None
    context: dict[str, Any] | None = None


class SessionContinuityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_mode: str | None = None
    conversation_id: str | None = None
    previous_response_id: str | None = None


class SessionOperationalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    summary_meta: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
    world_state: dict[str, Any] = Field(default_factory=dict)
    belief_state: dict[str, Any] = Field(default_factory=dict)
    policy_state: dict[str, Any] = Field(default_factory=dict)
    last_policy_executed: dict[str, Any] | None = None
    progress_state: dict[str, Any] = Field(default_factory=dict)
    debug_trace: list[dict[str, Any]] = Field(default_factory=list)
    negotiation_objective: str = ""
    negotiation_plan: list[str] = Field(default_factory=list)
    current_step_index: int = 0
    step_results: list[list[str]] = Field(default_factory=list)
    sister_option_price: float = 8000.0
    sister_option_repairs: float = 2000.0
    max_total_cost: float = 10000.0
    exit_option: dict[str, Any] = Field(default_factory=default_exit_option)
    turn_count: int = 0
    last_updated: str


class SessionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SESSION_ENVELOPE_SCHEMA_VERSION
    identity: SessionIdentityPayload
    bindings: SessionBindingPayload
    continuity: SessionContinuityPayload
    operational: SessionOperationalSnapshot


class SessionStore(Protocol):
    def get(self, *, user_id: str, session_id: str) -> SessionState | None: ...

    def get_or_create(self, *, user_id: str, session_id: str) -> SessionState: ...

    def save(self, state: SessionState) -> None: ...

    def delete(self, *, user_id: str, session_id: str) -> None: ...

    def clear(self) -> None: ...

    def iter_entries(self) -> Iterable[tuple[str, str, SessionState]]: ...

    def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[SessionKey, SessionState] = {}
        self._lock = RLock()

    def get(self, *, user_id: str, session_id: str) -> SessionState | None:
        key = _make_key(user_id, session_id)
        with self._lock:
            state = self._sessions.get(key)
            if state is None:
                return None
            return _normalize_loaded_state(state)

    def get_or_create(self, *, user_id: str, session_id: str) -> SessionState:
        key = _make_key(user_id, session_id)
        with self._lock:
            state = self._sessions.get(key)
            if state is None:
                state = SessionState(user_id=user_id, session_id=session_id)
                self._sessions[key] = state
            return _normalize_loaded_state(state)

    def save(self, state: SessionState) -> None:
        key = _make_key(state.user_id, state.session_id)
        with self._lock:
            state.last_updated = datetime.now(timezone.utc)
            self._sessions[key] = state

    def delete(self, *, user_id: str, session_id: str) -> None:
        key = _make_key(user_id, session_id)
        with self._lock:
            self._sessions.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def iter_entries(self) -> Iterable[tuple[str, str, SessionState]]:
        with self._lock:
            items = list(self._sessions.items())
        for (user_id, session_id), state in items:
            yield user_id, session_id, _normalize_loaded_state(state)

    def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None:
        _ = (user_id, session_id, ttl_seconds)
        return None


# Almacén global en RAM (MVP, sin DB) encapsulado detrás de SessionStore.
_DEFAULT_IN_MEMORY_STORE = InMemorySessionStore()
SESSIONS = _DEFAULT_IN_MEMORY_STORE._sessions
_ACTIVE_SESSION_STORE: SessionStore = _DEFAULT_IN_MEMORY_STORE
logger = logging.getLogger(__name__)

# Si algún día quieres leer estos valores desde env, puedes moverlos a agent.py.
# Aquí solo documentamos que son "parámetros de diseño".
DEFAULT_CONTEXT_LIMIT_TURNS: int = 12        # a partir de cuántos turnos totales empezamos a resumir
DEFAULT_KEEP_LAST_TURNS: int = 4            # cuántos turnos recientes guardamos "enteros"


def _normalize_loaded_state(state: SessionState) -> SessionState:
    state.belief_state = migrate_belief_state_to_v3(state.belief_state)
    state.world_state = migrate_world_state_to_v3(state.world_state)
    return state


def _make_key(user_id: str, session_id: str) -> SessionKey:
    return (user_id, session_id)


def get_session_store() -> SessionStore:
    return _ACTIVE_SESSION_STORE


def set_session_store(store: SessionStore) -> SessionStore:
    global _ACTIVE_SESSION_STORE, SESSIONS
    _ACTIVE_SESSION_STORE = store
    if isinstance(store, InMemorySessionStore):
        SESSIONS = store._sessions
    return _ACTIVE_SESSION_STORE


def reset_session_store() -> SessionStore:
    return set_session_store(_DEFAULT_IN_MEMORY_STORE)




def configure_session_store_from_env(*, force: bool = False) -> SessionStore:
    backend = os.getenv("SESSION_STORE_BACKEND", "auto").strip().lower() or "auto"
    redis_url = os.getenv("REDIS_URL", "").strip()

    if backend not in {"auto", "memory", "redis"}:
        raise RuntimeError(f"unsupported_session_store_backend:{backend}")

    if backend == "memory" or (backend == "auto" and not redis_url):
        if force or not isinstance(get_session_store(), InMemorySessionStore):
            logger.info("Using in-memory session store (backend=%s, redis_configured=%s)", backend, bool(redis_url))
            reset_session_store()
        return get_session_store()

    if not redis_url:
        raise RuntimeError("redis_session_store_requires_redis_url")

    from sessions.redis_store import RedisSessionStore, build_redis_client_from_url

    current = get_session_store()
    if not force and current.__class__.__name__ == "RedisSessionStore":
        return current

    redis_host = redis_url.split("@", 1)[-1] if "@" in redis_url else redis_url
    logger.info("Configuring Redis session store for host=%s", redis_host)
    redis_client = build_redis_client_from_url(redis_url)
    redis_client.ping()
    logger.info("Redis session store connectivity check succeeded for host=%s", redis_host)
    set_session_store(RedisSessionStore(redis_client))
    return get_session_store()

def export_session_envelope(state: SessionState) -> SessionEnvelope:
    state = _normalize_loaded_state(state)
    world_state = state.world_state if isinstance(state.world_state, dict) else {}
    context_payload = world_state.get("negotiation_context") if isinstance(world_state.get("negotiation_context"), dict) else None
    surface = world_state.get("_session_surface") if isinstance(world_state.get("_session_surface"), str) else None
    canonical = world_state.get("negotiation_canonical") if isinstance(world_state.get("negotiation_canonical"), dict) else {}
    thread = canonical.get("openai_thread") if isinstance(canonical, dict) else {}

    payload = asdict(state)
    payload["last_updated"] = state.last_updated.isoformat()
    payload["step_results"] = [list(item) for item in state.step_results]
    payload.pop("user_id", None)
    payload.pop("session_id", None)

    operational = SessionOperationalSnapshot.model_validate(payload)
    continuity = SessionContinuityPayload(
        thread_mode=thread.get("thread_mode") if isinstance(thread, dict) else None,
        conversation_id=thread.get("conversation_id") if isinstance(thread, dict) else None,
        previous_response_id=thread.get("previous_response_id") if isinstance(thread, dict) else None,
    )
    return SessionEnvelope(
        identity=SessionIdentityPayload(user_id=state.user_id, session_id=state.session_id),
        bindings=SessionBindingPayload(surface=surface, context=context_payload),
        continuity=continuity,
        operational=operational,
    )


def hydrate_session_state(envelope: SessionEnvelope | Mapping[str, Any]) -> SessionState:
    parsed = envelope if isinstance(envelope, SessionEnvelope) else SessionEnvelope.model_validate(envelope)
    operational = parsed.operational.model_dump(mode="json")
    last_updated_raw = operational.pop("last_updated", None)
    step_results_raw = operational.pop("step_results", [])
    state = SessionState(
        user_id=parsed.identity.user_id,
        session_id=parsed.identity.session_id,
        **operational,
    )
    state.step_results = [
        (str(item[0]), str(item[1]))
        for item in step_results_raw
        if isinstance(item, (list, tuple)) and len(item) == 2
    ]
    if isinstance(last_updated_raw, str) and last_updated_raw:
        try:
            state.last_updated = datetime.fromisoformat(last_updated_raw)
        except ValueError:
            state.last_updated = datetime.now(timezone.utc)
    else:
        state.last_updated = datetime.now(timezone.utc)

    if parsed.bindings.surface:
        state.world_state["_session_surface"] = parsed.bindings.surface
    if parsed.bindings.context is not None:
        state.world_state["negotiation_context"] = parsed.bindings.context

    canonical = state.world_state.get("negotiation_canonical")
    if isinstance(canonical, dict):
        thread = canonical.get("openai_thread")
        if isinstance(thread, dict):
            if parsed.continuity.thread_mode:
                thread["thread_mode"] = parsed.continuity.thread_mode
            thread["conversation_id"] = parsed.continuity.conversation_id
            thread["previous_response_id"] = parsed.continuity.previous_response_id

    return _normalize_loaded_state(state)


def normalize_exit_option(
    raw: Mapping[str, Any] | None,
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


def get_session_state(user_id: str, session_id: str) -> SessionState:
    """
    Recupera el estado de sesión para (user_id, session_id).
    Si no existe, lo crea.
    """
    return get_session_store().get_or_create(user_id=user_id, session_id=session_id)


def save_session_state(state: SessionState) -> None:
    """
    Guarda/actualiza el estado en el store activo.
    """
    get_session_store().save(state)


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
    get_session_store().delete(user_id=user_id, session_id=session_id)
