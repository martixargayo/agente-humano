from __future__ import annotations

import json
import time
from typing import Any

from ..validation import normalize_belief_buckets

_ALLOWED_HEALTH = {"stable", "tense", "stalled"}
_ALLOWED_MOVES = {"hold", "probe", "tradeoff", "deescalate", "anchor", "close", "boundary"}
_MAX_ITEMS = 8
_MAX_TEXT = 180

BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT = """
Eres un extractor estricto de JSON para belief_state v3.
Devuelve SOLO JSON válido con las claves exactas solicitadas.
Sin markdown. Sin comentarios. Sin claves extra al nivel superior.
Todos los campos belief_buckets.*.text deben estar en español.
Perspectiva: comprador Carlos. Si la evidencia proviene del vendedor (speaker_of_user_message='seller' o items que atribuyen al vendedor), formula hipótesis sobre el vendedor (ej. 'El vendedor podría...' / 'El vendedor parece...'), NO 'User is...' ni frases genéricas en inglés.
BACKGROUND_CONTEXT/PERSONA_PUBLIC/SCENE_PUBLIC/STYLE_PUBLIC/CONSTRAINTS_PUBLIC NO son evidencia. No crees hipótesis/factores basados solo en esos objetos si no aparecen en world_buckets o en el mensaje actual.
CONSTRAINTS_PUBLIC es guardrail (qué evitar), no evidencia. No generes hipótesis basadas solo en eso.
planner_signals son sugerencias. Si no hay evidencia clara, recommended_move='hold' y conflict_risk bajo. No fuerces 'probe' por defecto.
Usa previous_belief_state_compact para marcar status:
  - new si no existía antes
  - active si sigue aplicando
  - weakening si la evidencia nueva lo debilita
""".strip()

BELIEF_EXTRACTOR_V1_USER_PROMPT = """
Construye BELIEF STATE v3 a partir de evidencia de negociación en este turno.

turn_idx: {turn_idx}
{background_block}
MENSAJE_ACTUAL:
{user_message}

world_state.world_buckets (top N por bucket):
{world_buckets_json}

previous_belief_state_compact:
{prev_belief_json}

Devuelve SOLO este esquema:
{{
  "schema_version": "v3",
  "belief_buckets": {{
    "hypotheses": [{{"text": "...", "confidence": 0.0, "status": "active|weakening|new"}}],
    "strategy_notes": [{{"text": "...", "confidence": 0.0, "status": "active|weakening|new"}}],
    "risk_flags": [{{"text": "...", "confidence": 0.0, "status": "active|weakening|new"}}],
    "watch_items": [{{"text": "...", "confidence": 0.0, "status": "active|weakening|new"}}]
  }},
  "planner_signals": {{
    "interaction_health": "stable|tense|stalled",
    "conflict_risk": 0.0,
    "recommended_move": "hold|probe|tradeoff|deescalate|anchor|close|boundary",
    "recovery_mode": true
  }}
}}

Reglas:
- Usa world buckets como evidencia principal.
- strategy_notes son pistas tácticas, nunca la respuesta final del asistente.
- Mantén cada text conciso.
- conflict_risk debe ser numérico en [0,1].
""".strip()


def _safe_json_load(text: str) -> dict[str, Any]:
    txt = (text or "").strip()
    i = txt.find("{")
    j = txt.rfind("}")
    if i >= 0 and j > i:
        txt = txt[i : j + 1]
    return json.loads(txt)


def _compact_world_buckets(world_state: dict[str, Any], *, max_items: int = _MAX_ITEMS) -> dict[str, list[dict[str, Any]]]:
    buckets = (world_state or {}).get("world_buckets") if isinstance(world_state, dict) else {}
    buckets = buckets if isinstance(buckets, dict) else {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, values in buckets.items():
        if not isinstance(values, list):
            continue
        compact_vals: list[dict[str, Any]] = []
        for item in values[:max_items]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()[:_MAX_TEXT]
            if not text:
                continue
            confidence = item.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0.0
            compact_vals.append({"text": text, "confidence": max(0.0, min(1.0, confidence))})
        out[str(key)] = compact_vals
    return out


def _compact_prev_belief(prev_belief_state: dict[str, Any], *, max_items: int = 4) -> dict[str, Any]:
    src = prev_belief_state if isinstance(prev_belief_state, dict) else {}
    buckets = normalize_belief_buckets(src.get("belief_buckets", {}))
    compact = {bucket: items[:max_items] for bucket, items in buckets.items()}
    signals = src.get("planner_signals") if isinstance(src.get("planner_signals"), dict) else {}
    return {
        "belief_buckets": compact,
        "planner_signals": {
            "interaction_health": str(signals.get("interaction_health", "stable")),
            "conflict_risk": float(signals.get("conflict_risk", 0.0) or 0.0),
            "recommended_move": str(signals.get("recommended_move", "hold")),
            "recovery_mode": bool(signals.get("recovery_mode", False)),
        },
    }


def _normalize_belief_output(raw: dict[str, Any]) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    buckets = normalize_belief_buckets(src.get("belief_buckets", {}))
    for key in list(buckets.keys()):
        buckets[key] = buckets[key][:_MAX_ITEMS]

    planner = src.get("planner_signals") if isinstance(src.get("planner_signals"), dict) else {}
    interaction_health = str(planner.get("interaction_health", "stable"))
    if interaction_health not in _ALLOWED_HEALTH:
        interaction_health = "stable"
    recommended_move = str(planner.get("recommended_move", "hold"))
    if recommended_move not in _ALLOWED_MOVES:
        recommended_move = "hold"
    try:
        conflict_risk = float(planner.get("conflict_risk", 0.0) or 0.0)
    except Exception:
        conflict_risk = 0.0
    conflict_risk = max(0.0, min(1.0, conflict_risk))

    return {
        "schema_version": "v3",
        "belief_buckets": buckets,
        "planner_signals": {
            "interaction_health": interaction_health,
            "conflict_risk": conflict_risk,
            "recommended_move": recommended_move,
            "recovery_mode": bool(planner.get("recovery_mode", False)),
        },
    }


def extract_belief_state_llm_v1(
    deps,
    user_message: str,
    world_state: dict,
    prev_belief_state: dict,
    turn_idx: int,
    speaker_of_user_message: str = "unknown",
    persona_profile: dict | None = None,
    scene_profile: dict | None = None,
    style_contract: dict | None = None,
    constraints_struct: dict | None = None,
    background_block_public: str = "",
) -> tuple[dict, dict]:
    del speaker_of_user_message, persona_profile, scene_profile, style_contract, constraints_struct
    world_buckets_json = json.dumps(_compact_world_buckets(world_state), ensure_ascii=False)
    prev_belief_json = json.dumps(_compact_prev_belief(prev_belief_state), ensure_ascii=False)
    user_prompt = BELIEF_EXTRACTOR_V1_USER_PROMPT.format(
        turn_idx=int(turn_idx),
        background_block=str(background_block_public or "").strip(),
        user_message=str(user_message or "")[:1500],
        world_buckets_json=world_buckets_json,
        prev_belief_json=prev_belief_json,
    )
    messages = [
        {"role": "system", "content": BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    started = time.perf_counter()
    raw = deps.execute(messages)
    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = _safe_json_load(text)
    belief_state = _normalize_belief_output(data)
    input_payload_raw = [
        {"role": item.get("role", "user"), "content": str(item.get("content", ""))}
        for item in messages
    ]
    meta = {
        "belief_engine": "llm_belief_extractor_v1",
        "belief_latency_ms": latency_ms,
        "belief_llm_used": True,
        "belief_input_payload_raw": input_payload_raw,
        "belief_input_prompt_rendered": "\n\n".join(
            f"[{item['role']}]\n{item['content']}" for item in input_payload_raw
        ),
        "belief_output_text_rendered": str(text),
        "belief_output_payload_raw": data,
    }
    return belief_state, meta
