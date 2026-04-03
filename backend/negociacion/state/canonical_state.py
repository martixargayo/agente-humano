from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator

from .shared_types import NegotiationPhase, ThreadMode
from ..contexts import resolve_default_negotiation_context, resolve_negotiation_context


EMERGENCY_PERSONA_DEFAULTS: dict[str, dict[str, object]] = {
    "policy": {
        "identidad_operativa": "Eres Carlos, comprador prudente y orientado a viabilidad del acuerdo.",
        "objetivo_privado": "Mantener continuidad operativa de la negociación con foco en riesgo, condiciones y coste total.",
        "criterio_de_decision": "Avanza solo con claridad suficiente; evita cierres por presión o ambigüedad.",
        "disciplina_negociadora": "Toda concesión requiere contrapartida verificable y proporcional.",
        "limites_privados": "No revelar techo real, urgencia ni alternativas privadas.",
        "principios_de_avance": "Cada turno debe generar al menos un avance útil en claridad, condiciones, compromiso o cierre.",
    },
    "expressive": {
        "identidad_en_escena": "Hablas como Carlos, comprador humano y creíble en conversación real.",
        "marco_conversacional": "Interés genuino por el coche con prudencia y criterio propio.",
        "voz_y_estilo": "Español natural, claro y conversacional; firmeza serena.",
        "naturalidad": "Responder primero al turno actual y evitar fórmulas robóticas.",
        "huella_conversacional": "Buen juicio, paciencia y cautela sana durante toda la negociación.",
    },
}

EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS: dict[str, object] = {
    "schema_version": "negotiation_brief.v1",
    "contexto_de_mercado": {
        "valor_estimado": "El valor de mercado estimado de este modelo está en torno a 6000-6500 euros.",
        "lectura": "Ese rango refleja el valor base de mercado del coche, no el coste real de recurrir a la mejor alternativa disponible para Carlos.",
    },
    "restricciones": {
        "resumen": "Existen límites operativos que condicionan el acuerdo.",
        "lectura": "Las restricciones deben considerarse antes de cerrar condiciones finales.",
    },
    "realidad_de_la_alternativa": {
        "resumen": "Carlos no tiene una alternativa equivalente cómoda en la zona.",
        "detalle": "Comprar una unidad parecida fuera implica sumar transporte y matriculación.",
        "coste_equivalente_aproximado": "La mejor alternativa real se acerca a 8000 euros de coste total.",
        "lectura": "Por eso Carlos intentará acercarse al precio de mercado, pero sabe que debe ser realista si quiere este coche concreto.",
    },
    "objetivo_y_marco_de_decision": {
        "objetivo": "Intentar comprar por precio de mercado o lo más cerca posible.",
        "realismo": "Carlos sabe que le interesa este coche y que su alternativa real es más cara que el mercado base.",
        "criterio": "Empujará para mejorar el precio, pero un acuerdo por debajo de 8000 puede seguir pareciéndole bueno si el conjunto del trato encaja.",
        "por_encima_de_eso": "Por encima de ese nivel solo le compensa si el vendedor añade valor real suficiente o reduce riesgo de forma clara.",
    },
    "mapa_de_valor": {
        "nota": "Los valores aproximados sirven también como referencia para estimar el valor de otras concesiones parecidas que aparezcan en la negociación.",
        "items": [
            {
                "elemento": "1 año de garantía",
                "valor_aproximado_eur": 600,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Reduce riesgo postcompra y puede justificar pagar más.",
            },
            {
                "elemento": "ITV pasada antes de venderlo",
                "valor_aproximado_eur": None,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Reduce coste y fricción inmediata y puede justificar algo más de precio.",
            },
            {
                "elemento": "pack o kit de ruedas",
                "valor_aproximado_eur": None,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Añade valor material directo y puede compensar parte del precio.",
            },
            {
                "elemento": "cerrar hoy mismo",
                "valor_aproximado_eur": 0,
                "tipo_de_efecto": "facilita_acuerdo",
                "lectura": "No justifica pagar más por sí solo, pero puede hacer a Carlos algo más flexible para cerrar.",
            },
            {
                "elemento": "operativa sencilla y poco roce",
                "valor_aproximado_eur": 0,
                "tipo_de_efecto": "facilita_acuerdo",
                "lectura": "No suma valor económico real al coche, pero ayuda a rebajar resistencia para llegar a un entendimiento.",
            },
        ],
    },
    "monedas_de_intercambio_del_comprador": {
        "puede_ofrecer": [
            {
                "elemento": "pago en efectivo",
                "uso": "Puede usarse para intentar que el vendedor baje expectativas o cierre antes.",
            },
            {
                "elemento": "encargarse del papeleo",
                "uso": "Puede usarse como contrapartida operativa para pedir mejor precio o mejores condiciones.",
            },
            {
                "elemento": "rapidez y facilidad para cerrar",
                "uso": "Puede usarse para reducir fricción del vendedor, pero no debe regalarse sin retorno.",
            },
        ]
    },
    "informacion_privada_sensible": {
        "no_conviene_revelar_espontaneamente": [
            "El coste real de su alternativa.",
            "La escasez de alternativas equivalentes en la zona.",
            "Su flexibilidad real.",
            "Qué concesiones valora más internamente.",
        ],
        "lectura": "Si el vendedor no lo sabe y lo intenta descubrir, conviene evitar revelarlo. Si el vendedor ya lo sabe de forma explícita y lo dice correctamente, no tiene sentido negarlo de manera artificial.",
    },
}


def _load_persona_defaults(context_id: str | None = None) -> dict[str, dict[str, object]]:
    path = resolve_negotiation_context(context_id).persona_path if context_id else resolve_default_negotiation_context().persona_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return EMERGENCY_PERSONA_DEFAULTS
    return _normalize_persona_payload(raw) if isinstance(raw, dict) else EMERGENCY_PERSONA_DEFAULTS


def _load_negotiation_brief_defaults(context_id: str | None = None) -> dict[str, object]:
    path = resolve_negotiation_context(context_id).negotiation_brief_path if context_id else resolve_default_negotiation_context().negotiation_brief_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS
    if not isinstance(raw, dict):
        return EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS
    return raw


class SessionMeta(BaseModel):
    """Metadatos persistentes de sesión."""

    model_config = ConfigDict(extra="forbid")
    session_id: str
    user_id: str | None
    avatar_id: str | None
    created_at: str
    updated_at: str

    # /// Este grupo se inicializa por código al crear sesión.
    # /// `updated_at` debe refrescarse al persistir estado.


class OpenAIThreadState(BaseModel):
    """Threading OpenAI (no estado de dominio)."""

    model_config = ConfigDict(extra="forbid")
    thread_mode: ThreadMode
    conversation_id: str | None
    previous_response_id: str | None


class PersonaPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identidad_operativa: str
    objetivo_privado: str
    criterio_de_decision: str
    disciplina_negociadora: str
    limites_privados: str
    principios_de_avance: str


class PersonaExpressive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identidad_en_escena: str
    marco_conversacional: str
    voz_y_estilo: str
    naturalidad: str
    huella_conversacional: str


class PersonaState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: PersonaPolicy
    expressive: PersonaExpressive


def _pick_text(payload: dict[str, object], keys: tuple[str, ...], fallback: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _tokenize_path(path: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", path.lower()) if part]


def _collect_string_leaves(payload: object, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(payload, dict):
        collected: list[tuple[str, str]] = []
        for key, value in payload.items():
            if not isinstance(key, str):
                continue
            path = f"{prefix}.{key}" if prefix else key
            collected.extend(_collect_string_leaves(value, path))
        return collected
    if isinstance(payload, list):
        collected: list[tuple[str, str]] = []
        for idx, value in enumerate(payload):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            collected.extend(_collect_string_leaves(value, path))
        return collected
    if isinstance(payload, str) and payload.strip():
        return [(prefix, payload.strip())]
    return []


def _best_text_by_keywords(payload: object, *, keywords: tuple[str, ...], fallback: str) -> str:
    leaves = _collect_string_leaves(payload)
    if not leaves:
        return fallback
    scored: list[tuple[int, str]] = []
    keyword_set = {k.lower() for k in keywords}
    for path, value in leaves:
        tokens = set(_tokenize_path(path))
        score = len(tokens.intersection(keyword_set))
        if score > 0:
            scored.append((score, value))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        values = []
        seen: set[str] = set()
        for score, value in scored:
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
            if len(values) >= 2:
                break
        if values:
            return " ".join(values).strip()
    # graceful fallback: keep first meaningful text in subtree
    return leaves[0][1]


def _find_first_list_of_dicts(payload: object, *, required_keys: set[str]) -> list[dict[str, object]] | None:
    if isinstance(payload, list):
        dict_items = [item for item in payload if isinstance(item, dict)]
        if dict_items and all(required_keys.issubset({str(k) for k in item.keys()}) for item in dict_items):
            return [dict(item) for item in dict_items]
        for item in payload:
            found = _find_first_list_of_dicts(item, required_keys=required_keys)
            if found is not None:
                return found
    elif isinstance(payload, dict):
        for value in payload.values():
            found = _find_first_list_of_dicts(value, required_keys=required_keys)
            if found is not None:
                return found
    return None


def _find_first_list_of_strings(payload: object, *, path_keywords: set[str], prefix: str = "") -> list[str] | None:
    if isinstance(payload, list):
        values = [item.strip() for item in payload if isinstance(item, str) and item.strip()]
        if values and path_keywords.intersection(set(_tokenize_path(prefix))):
            return values
        for idx, item in enumerate(payload):
            found = _find_first_list_of_strings(item, path_keywords=path_keywords, prefix=f"{prefix}[{idx}]")
            if found is not None:
                return found
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str):
                continue
            child_prefix = f"{prefix}.{key}" if prefix else key
            found = _find_first_list_of_strings(value, path_keywords=path_keywords, prefix=child_prefix)
            if found is not None:
                return found
    return None


def _normalize_persona_payload(raw: dict[str, object]) -> dict[str, dict[str, object]]:
    policy_raw: dict[str, object] = {}
    expressive_raw: dict[str, object] = {}

    if isinstance(raw.get("policy"), dict):
        policy_raw = raw["policy"]  # type: ignore[assignment]
    elif isinstance(raw.get("persona_policy"), dict):
        policy_raw = raw["persona_policy"]  # type: ignore[assignment]

    if isinstance(raw.get("expressive"), dict):
        expressive_raw = raw["expressive"]  # type: ignore[assignment]
    elif isinstance(raw.get("persona_expressive"), dict):
        expressive_raw = raw["persona_expressive"]  # type: ignore[assignment]

    if not policy_raw and not expressive_raw:
        return EMERGENCY_PERSONA_DEFAULTS

    policy_fallback = EMERGENCY_PERSONA_DEFAULTS["policy"]
    expressive_fallback = EMERGENCY_PERSONA_DEFAULTS["expressive"]

    normalized_policy = {
        "identidad_operativa": _best_text_by_keywords(
            policy_raw,
            keywords=("identidad", "operativa", "rol", "papel"),
            fallback=str(policy_fallback["identidad_operativa"]),
        ),
        "objetivo_privado": _best_text_by_keywords(
            policy_raw,
            keywords=("objetivo", "meta", "finalidad", "privado"),
            fallback=str(policy_fallback["objetivo_privado"]),
        ),
        "criterio_de_decision": _best_text_by_keywords(
            policy_raw,
            keywords=("criterio", "decision", "decidir"),
            fallback=str(policy_fallback["criterio_de_decision"]),
        ),
        "disciplina_negociadora": _best_text_by_keywords(
            policy_raw,
            keywords=("disciplina", "negociadora", "regla", "concesion", "progresion"),
            fallback=str(policy_fallback["disciplina_negociadora"]),
        ),
        "limites_privados": _best_text_by_keywords(
            policy_raw,
            keywords=("limite", "limites", "privado", "confidencial", "no", "revelar"),
            fallback=str(policy_fallback["limites_privados"]),
        ),
        "principios_de_avance": _best_text_by_keywords(
            policy_raw,
            keywords=("principio", "avance", "progresion", "economia", "mapa"),
            fallback=str(policy_fallback["principios_de_avance"]),
        ),
    }

    voz_y_estilo = _best_text_by_keywords(
        expressive_raw,
        keywords=("voz", "estilo", "tono", "lenguaje", "forma"),
        fallback=str(expressive_fallback["voz_y_estilo"]),
    )

    normalized_expressive = {
        "identidad_en_escena": _best_text_by_keywords(
            expressive_raw,
            keywords=("identidad", "escena", "persona", "personaje"),
            fallback=str(expressive_fallback["identidad_en_escena"]),
        ),
        "marco_conversacional": _best_text_by_keywords(
            expressive_raw,
            keywords=("marco", "conversacional", "contexto", "encuadre", "franja"),
            fallback=str(expressive_fallback["marco_conversacional"]),
        ),
        "voz_y_estilo": voz_y_estilo,
        "naturalidad": _best_text_by_keywords(
            expressive_raw,
            keywords=("naturalidad", "natural", "fluido", "no", "resuelto"),
            fallback=str(expressive_fallback["naturalidad"]),
        ),
        "huella_conversacional": _best_text_by_keywords(
            expressive_raw,
            keywords=("huella", "discrepancia", "actitud", "tono"),
            fallback=str(expressive_fallback["huella_conversacional"]),
        ),
    }
    return {"policy": normalized_policy, "expressive": normalized_expressive}


def parse_persona_payload(payload: dict[str, object]) -> PersonaState:
    normalized = _normalize_persona_payload(payload)
    return PersonaState(
        policy=PersonaPolicy.model_validate(normalized["policy"]),
        expressive=PersonaExpressive.model_validate(normalized["expressive"]),
    )


class NegotiationBriefMarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor_estimado: str
    lectura: str


class NegotiationBriefAlternativeReality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumen: str
    detalle: str
    coste_equivalente_aproximado: str
    lectura: str


class NegotiationBriefObjectiveFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objetivo: str
    realismo: str
    criterio: str
    por_encima_de_eso: str


class NegotiationBriefValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elemento: str
    valor_aproximado_eur: float | None
    tipo_de_efecto: str
    lectura: str


class NegotiationBriefValueMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nota: str
    items: list[NegotiationBriefValueItem]


class NegotiationBriefBuyerTradeoffItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elemento: str
    uso: str


class NegotiationBriefBuyerTradeoffs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puede_ofrecer: list[NegotiationBriefBuyerTradeoffItem]


class NegotiationBriefSensitiveInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no_conviene_revelar_espontaneamente: list[str]
    lectura: str


class NegotiationBriefRestrictions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumen: str
    lectura: str


class NegotiationBriefState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["negotiation_brief.v1"]
    contexto_de_mercado: NegotiationBriefMarketContext
    restricciones: NegotiationBriefRestrictions | None = None
    realidad_de_la_alternativa: NegotiationBriefAlternativeReality
    objetivo_y_marco_de_decision: NegotiationBriefObjectiveFrame
    mapa_de_valor: NegotiationBriefValueMap
    monedas_de_intercambio_del_comprador: NegotiationBriefBuyerTradeoffs
    informacion_privada_sensible: NegotiationBriefSensitiveInfo


def _normalize_negotiation_brief_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    leaves = _collect_string_leaves(payload)
    full_text_fallback = " ".join(value for _, value in leaves[:3]).strip()
    normalized["schema_version"] = "negotiation_brief.v1"

    if "contexto_de_mercado" not in normalized:
        normalized["contexto_de_mercado"] = {
            "valor_estimado": _best_text_by_keywords(
                payload,
                keywords=("valor", "mercado", "disponibilidad", "recurso", "franja"),
                fallback=full_text_fallback,
            ),
            "lectura": _best_text_by_keywords(
                payload,
                keywords=("lectura", "contexto", "interpretacion"),
                fallback=full_text_fallback,
            ),
        }

    if "realidad_de_la_alternativa" not in normalized:
        normalized["realidad_de_la_alternativa"] = {
            "resumen": _best_text_by_keywords(
                payload,
                keywords=("alternativa", "realidad", "resumen", "batna"),
                fallback=full_text_fallback,
            ),
            "detalle": _best_text_by_keywords(
                payload,
                keywords=("detalle", "alternativa", "coste"),
                fallback=full_text_fallback,
            ),
            "coste_equivalente_aproximado": _best_text_by_keywords(
                payload,
                keywords=("coste", "equivalente", "aproximado", "alternativa"),
                fallback=full_text_fallback,
            ),
            "lectura": _best_text_by_keywords(
                payload,
                keywords=("lectura", "alternativa"),
                fallback=full_text_fallback,
            ),
        }

    if "objetivo_y_marco_de_decision" not in normalized:
        normalized["objetivo_y_marco_de_decision"] = {
            "objetivo": _best_text_by_keywords(
                payload,
                keywords=("objetivo", "marco", "decision"),
                fallback=full_text_fallback,
            ),
            "realismo": _best_text_by_keywords(
                payload,
                keywords=("realismo", "realidad", "alternativa"),
                fallback=full_text_fallback,
            ),
            "criterio": _best_text_by_keywords(
                payload,
                keywords=("criterio", "regla", "decision"),
                fallback=full_text_fallback,
            ),
            "por_encima_de_eso": _best_text_by_keywords(
                payload,
                keywords=("por", "encima", "franja", "tardia", "regla"),
                fallback=full_text_fallback,
            ),
        }
    if "restricciones" not in normalized and isinstance(normalized.get("restricciones_duras"), dict):
        normalized["restricciones"] = normalized["restricciones_duras"]

    if "contexto_de_mercado" not in normalized and isinstance(normalized.get("contexto_del_recurso"), dict):
        contexto = normalized["contexto_del_recurso"]
        lectura = contexto.get("lectura", "") if isinstance(contexto.get("lectura"), str) else ""
        valor_estimado = contexto.get("recurso_y_disponibilidad", "")
        if not isinstance(valor_estimado, str):
            valor_estimado = ""
        normalized["contexto_de_mercado"] = {"valor_estimado": valor_estimado, "lectura": lectura}

    if (
        "objetivo_y_marco_de_decision" in normalized
        and isinstance(normalized["objetivo_y_marco_de_decision"], dict)
        and "por_encima_de_eso" not in normalized["objetivo_y_marco_de_decision"]
    ):
        objective = dict(normalized["objetivo_y_marco_de_decision"])
        fallback = objective.get("si_asume_la_franja_menos_comoda")
        if not isinstance(fallback, str):
            fallback = objective.get("regla_de_la_franja_tardia")
        if isinstance(fallback, str):
            objective["por_encima_de_eso"] = fallback
            objective.pop("si_asume_la_franja_menos_comoda", None)
            objective.pop("regla_de_la_franja_tardia", None)
            normalized["objetivo_y_marco_de_decision"] = objective

    if "monedas_de_intercambio_del_comprador" not in normalized and isinstance(
        normalized.get("monedas_de_intercambio_del_equipo_b"), dict
    ):
        normalized["monedas_de_intercambio_del_comprador"] = normalized["monedas_de_intercambio_del_equipo_b"]

    if "mapa_de_valor" not in normalized:
        normalized["mapa_de_valor"] = {"nota": "", "items": []}
    if isinstance(normalized["mapa_de_valor"], dict):
        value_map = dict(normalized["mapa_de_valor"])
        if not isinstance(value_map.get("nota"), str) or not str(value_map.get("nota", "")).strip():
            value_map["nota"] = _best_text_by_keywords(
                payload,
                keywords=("nota", "mapa", "valor", "lectura"),
                fallback=full_text_fallback,
            )
        items = value_map.get("items")
        if not isinstance(items, list):
            items = _find_first_list_of_dicts(payload, required_keys={"elemento"}) or []
        if isinstance(items, list):
            normalized_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized_item = dict(item)
                normalized_item.pop("impacto_operativo_aproximado", None)
                if "valor_aproximado_eur" not in normalized_item:
                    normalized_item["valor_aproximado_eur"] = None
                if "tipo_de_efecto" not in normalized_item:
                    normalized_item["tipo_de_efecto"] = "facilita_acuerdo"
                if "lectura" not in normalized_item:
                    normalized_item["lectura"] = _best_text_by_keywords(item, keywords=("lectura", "uso", "impacto"), fallback="")
                normalized_items.append(normalized_item)
            value_map["items"] = normalized_items
            normalized["mapa_de_valor"] = value_map

    if "monedas_de_intercambio_del_comprador" not in normalized:
        tradeoff_items = _find_first_list_of_dicts(payload, required_keys={"elemento", "uso"}) or []
        normalized["monedas_de_intercambio_del_comprador"] = {"puede_ofrecer": tradeoff_items}

    if "restricciones" not in normalized:
        normalized["restricciones"] = {
            "resumen": _best_text_by_keywords(payload, keywords=("restriccion", "dura", "limite", "no"), fallback=full_text_fallback),
            "lectura": _best_text_by_keywords(payload, keywords=("restriccion", "lectura"), fallback=full_text_fallback),
        }

    if "informacion_privada_sensible" not in normalized:
        sensitive_list = _find_first_list_of_strings(
            payload,
            path_keywords={"privada", "sensible", "revelar", "no", "conviene"},
        ) or []
        normalized["informacion_privada_sensible"] = {
            "no_conviene_revelar_espontaneamente": sensitive_list,
            "lectura": _best_text_by_keywords(payload, keywords=("privada", "sensible", "lectura"), fallback=full_text_fallback),
        }

    normalized.pop("contexto_del_recurso", None)
    normalized.pop("condiciones_iniciales_de_la_negociacion", None)
    normalized.pop("restricciones_duras", None)
    normalized.pop("monedas_de_intercambio_del_equipo_b", None)
    normalized.pop("naturaleza_del_caso", None)
    normalized.pop("marco_relacional_inicial", None)
    normalized.pop("situacion_inicial_de_informacion", None)
    normalized.pop("realidad_operativa_del_equipo_b", None)
    normalized.pop("filosofia_del_caso", None)
    normalized.pop("condiciones_iniciales", None)
    normalized.pop("objetivo_del_equipo_b", None)
    normalized.pop("reglas_operativas_explicitas", None)
    normalized.pop("glosario_operativo", None)
    normalized.pop("franjas_y_valor_relativo", None)

    default_brief = dict(EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS)
    canonical: dict[str, object] = {"schema_version": "negotiation_brief.v1"}
    for key, default_value in default_brief.items():
        if key == "schema_version":
            continue
        candidate = normalized.get(key)
        if isinstance(default_value, dict) and isinstance(candidate, dict):
            merged = dict(default_value)
            for ck, cv in candidate.items():
                if isinstance(cv, list) and not cv and isinstance(merged.get(ck), list):
                    continue
                merged[ck] = cv
            canonical[key] = merged
        else:
            canonical[key] = candidate if candidate is not None else default_value
    return canonical


def parse_negotiation_brief_payload(payload: dict[str, object]) -> NegotiationBriefState:
    return NegotiationBriefState.model_validate(_normalize_negotiation_brief_payload(payload))


def _default_negotiation_brief_state() -> NegotiationBriefState:
    return parse_negotiation_brief_payload(_load_negotiation_brief_defaults())


class MemoryEpisodicItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal[
        "offer",
        "commitment",
        "blocker",
        "avoidance",
        "important_fact",
        "topic_closure",
    ]
    event_summary: str
    turn_id: str


class MemoryWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_topic: str | None
    pending_question: str | None
    last_turn_summary: str | None
    # /// Arranca en `None` al crear sesión; tras el primer turno memory node lo refresca con string factual.


class NegotiationOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    extras: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    is_currently_active: bool = True
    source_turn_role: Literal["user", "assistant"] | None = None


class TentativeAgreement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    extras: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class NegotiationStallState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_hard_stalemate: bool = False
    stalemate_reason: str | None = None
    self_ultimatum_active: bool = False
    self_ultimatum_summary: str | None = None


class NegotiationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = "inactive"
    active_axes: list[str] = Field(default_factory=list)
    last_offer_self: NegotiationOffer | None = None
    last_offer_other: NegotiationOffer | None = None
    tentative_agreement: TentativeAgreement | None = None
    stall_state: NegotiationStallState = Field(default_factory=NegotiationStallState)
    blockers: list[str] = Field(default_factory=list)
    next_open_loop: str | None = None

    @field_validator("last_offer_self", "last_offer_other", mode="before")
    @classmethod
    def _coerce_legacy_offer(cls, value: object) -> object:
        if isinstance(value, str):
            return {
                "summary": value,
                "price_amount": None,
                "currency": None,
                "extras": [],
                "conditions": [],
                "is_currently_active": True,
                "source_turn_role": None,
            }
        return value


class PlannerState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: NegotiationPhase | None
    previous_phase: NegotiationPhase | None
    current_turn_goal: str | None
    topics_touched_current_phase: list[str] = Field(default_factory=list)
    topics_touched_previous_phases: list[str] = Field(default_factory=list)
    recent_phase_history: list[NegotiationPhase] = Field(default_factory=list)


class SceneState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    copresent: bool = True
    encounter_in_progress: bool = True
    conversation_only: bool = True


class TraceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str | None
    last_node_statuses: dict[str, str] = Field(default_factory=dict)
    last_fallbacks: list[str] = Field(default_factory=list)
    last_refusals: list[str] = Field(default_factory=list)


class NegotiationUiState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finish_button_armed: bool = False


class CanonicalState(BaseModel):
    """Fuente mínima de verdad del dominio de negociación."""

    model_config = ConfigDict(extra="forbid")

    session: SessionMeta
    openai_thread: OpenAIThreadState
    persona: PersonaState
    negotiation_brief: NegotiationBriefState = Field(default_factory=_default_negotiation_brief_state)
    memory_episodic: list[MemoryEpisodicItem]
    memory_working: MemoryWorkingState
    negotiation_state: NegotiationState
    planner_state: PlannerState
    scene_state: SceneState
    ui_state: NegotiationUiState = Field(default_factory=NegotiationUiState)
    trace: TraceState


def build_default_canonical_state(
    *,
    session_id: str,
    thread_mode: ThreadMode,
    user_id: str | None = None,
    avatar_id: str | None = None,
    now_iso: str | None = None,
    context_id: str | None = None,
) -> CanonicalState:
    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    persona_defaults = _load_persona_defaults(context_id=context_id)
    negotiation_brief_defaults = _load_negotiation_brief_defaults(context_id=context_id)
    return CanonicalState(
        session=SessionMeta(
            session_id=session_id,
            user_id=user_id,
            avatar_id=avatar_id,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        openai_thread=OpenAIThreadState(thread_mode=thread_mode, conversation_id=None, previous_response_id=None),
        persona=parse_persona_payload(persona_defaults),
        negotiation_brief=parse_negotiation_brief_payload(negotiation_brief_defaults),
        memory_episodic=[],
        memory_working=MemoryWorkingState(current_topic=None, pending_question=None, last_turn_summary=None),
        negotiation_state=NegotiationState(
            status="inactive",
            active_axes=[],
            last_offer_self=None,
            last_offer_other=None,
            tentative_agreement=None,
            stall_state=NegotiationStallState(
                is_hard_stalemate=False,
                stalemate_reason=None,
                self_ultimatum_active=False,
                self_ultimatum_summary=None,
            ),
            blockers=[],
            next_open_loop=None,
        ),
        planner_state=PlannerState(
            current_phase=None,
            previous_phase=None,
            current_turn_goal=None,
            topics_touched_current_phase=[],
            topics_touched_previous_phases=[],
            recent_phase_history=[],
        ),
        scene_state=SceneState(
            copresent=True,
            encounter_in_progress=True,
            conversation_only=True,
        ),
        ui_state=NegotiationUiState(finish_button_armed=False),
        trace=TraceState(turn_id=None, last_node_statuses={}, last_fallbacks=[], last_refusals=[]),
    )
