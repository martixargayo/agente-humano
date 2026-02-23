from __future__ import annotations

import json
from copy import deepcopy

from .elementos.render.carlos_buyer_preset import (
    CARLOS_CONSTRAINTS_STRUCT,
    CARLOS_PERSONA_PROFILE,
    CARLOS_SCENE_PROFILE,
    CARLOS_STYLE_CONTRACT,
)
from .llm_background import build_background_context

POLICY_CATALOG_ES = {
  "safe_neutral": {
    "goal": "Mantener seguridad, neutralidad y claridad sin escalar tensión.",
    "when_to_use": "Cuando hay ambigüedad alta, riesgo de malentendido o necesitas una respuesta mínima y segura.",
    "how_to_execute": ["Responder breve y factual", "Pedir una sola aclaración si falta dato clave", "Evitar juicios o presión"],
    "avoid": ["Amenazas", "Sarcasmo", "Afirmar hechos no presentes", "Forzar cierre prematuro"]
  },
  "reflect_and_validate": {"goal": "Reflejar y validar para reducir fricción y aumentar cooperación.", "when_to_use": "Cuando la otra parte muestra emoción, resistencia o necesitas bajar defensas.", "how_to_execute": ["Parafrasear lo dicho", "Validar intención o esfuerzo (sin ceder en contenido)", "Cerrar con una pregunta suave"], "avoid": ["Validar posiciones injustas", "Ceder sin pedir nada a cambio", "Frases vacías repetitivas"]},
  "summarize_and_align": {"goal": "Resumir puntos y alinear entendimiento para avanzar.", "when_to_use": "Después de varias vueltas, antes de proponer opciones, o cuando detectas confusión.", "how_to_execute": ["Enumerar 2-4 puntos acordados/entendidos", "Marcar 1 punto abierto", "Pedir confirmación breve"], "avoid": ["Resúmenes largos", "Introducir puntos nuevos", "Reescribir historia sin evidencia"]},
  "clarify_missing_info": {"goal": "Extraer información faltante crítica para no negociar a ciegas.", "when_to_use": "Cuando no puedes proponer ni evaluar opciones por falta de datos.", "how_to_execute": ["Hacer 1-2 preguntas directas", "Explicar por qué necesitas ese dato", "Confirmar supuestos solo si el otro los valida"], "avoid": ["Interrogatorio", "Preguntas múltiples en cadena", "Suponer números/fechas no dadas"]},
  "set_process_rules": {"goal": "Acordar proceso, reglas de conversación y estructura de intercambio.", "when_to_use": "Al inicio, cuando hay caos, o cuando el diálogo se vuelve improductivo.", "how_to_execute": ["Proponer un orden (objetivos → info → opciones → cierre)", "Acordar límites (tiempo, canales)", "Pedir aceptación explícita"], "avoid": ["Imponer reglas", "Sonar autoritario", "Hacerlo si la otra parte está ya colaborativa"]},
  "meta_negotiation_reset": {"goal": "Reiniciar la negociación cuando está estancada o mal encuadrada.", "when_to_use": "Loop repetitivo, escalada suave, o pérdida de foco.", "how_to_execute": ["Nombrar el atasco sin culpar", "Proponer 2 caminos claros", "Re-centrar en objetivo compartido o BATNA"], "avoid": ["Acusar", "Reabrir agravios", "Cambiar tema sin explicar"]},
  "boundary_and_respect": {"goal": "Poner límites firmes con respeto y mantener la relación funcional.", "when_to_use": "Ante presión, falta de respeto, demandas abusivas o invasión de límites.", "how_to_execute": ["Decir no de forma clara", "Explicar límite en una frase", "Ofrecer alternativa o siguiente paso"], "avoid": ["Amenazar", "Humillar", "Negociar el límite básico"]},
  "repair_loop_structured_choice": {"goal": "Salir de loops ofreciendo elecciones estructuradas.", "when_to_use": "Cuando la conversación da vueltas y faltan decisiones.", "how_to_execute": ["Ofrecer 2-3 opciones concretas", "Pedir que elijan una", "Definir criterio de elección"], "avoid": ["Demasiadas opciones", "Opciones vagas", "Volver al loop sin decisión"]},
  "tone_deescalate": {"goal": "Bajar tensión y evitar ruptura.", "when_to_use": "Señales de enfado, acusaciones, amenazas o tono agresivo.", "how_to_execute": ["Reconocer emoción", "Bajar ritmo y lenguaje", "Proponer pausa o reformulación", "Volver a hechos"], "avoid": ["Contraatacar", "Justificarse largo", "Competir por la razón"]},
  "trust_micro_reciprocity": {"goal": "Construir confianza con micro-concesiones comunicativas y pasos pequeños.", "when_to_use": "Inicio o baja información con tono estable; cuando necesitas que el otro se abra.", "how_to_execute": ["Agradecer flexibilidad", "Mostrar intención cooperativa", "Pedir un detalle concreto", "Proponer un micro-siguiente paso"], "avoid": ["Prometer de más", "Ceder valor sin retorno", "Pedir cifras si disallow_numbers=true"]},
  "rapport_and_legitimacy": {"goal": "Crear rapport y legitimidad (empatía + criterios justos).", "when_to_use": "Al inicio o cuando hay desconfianza; antes de hablar de condiciones.", "how_to_execute": ["Reconocer contexto del otro", "Mencionar criterio objetivo (mercado, práctica)", "Invitar a enfoque colaborativo"], "avoid": ["Halagos excesivos", "Manipulación evidente", "Criterios inventados"]},
  "separate_people_from_problem": {"goal": "Separar relación y problema para negociar sin personalizar.", "when_to_use": "Cuando hay ataques personales o atribuciones.", "how_to_execute": ["Re-encuadrar en términos del problema", "Usar lenguaje 'nosotros vs problema'", "Confirmar respeto mutuo"], "avoid": ["Psicoanalizar", "Culpar", "Invalidar sentimientos"]},
  "diagnose_resistance": {"goal": "Diagnosticar la causa de resistencia (miedo, falta de info, incentivos).", "when_to_use": "Respuestas evasivas, noes repetidos, contradicciones.", "how_to_execute": ["Pregunta diagnóstica abierta", "Ofrecer 2-3 hipótesis como opciones", "Confirmar antes de proponer"], "avoid": ["Asumir mala fe", "Presionar", "Convertirlo en interrogatorio"]},
  "communication_clean_channel": {"goal": "Limpiar el canal de comunicación (precisión, malentendidos, definiciones).", "when_to_use": "Confusión sobre términos, promesas ambiguas, discusiones por interpretación.", "how_to_execute": ["Definir términos", "Separar hechos vs opiniones", "Reformular en una frase comprobable"], "avoid": ["Debates semánticos largos", "Definiciones rígidas sin acuerdo"]},
  "permission_to_probe": {"goal": "Pedir permiso para explorar temas sensibles sin activar defensas.", "when_to_use": "Cuando vas a preguntar por límites, razones, dinero, tiempos u objeciones delicadas.", "how_to_execute": ["Pedir permiso en 1 frase", "Explicar beneficio", "Hacer 1 pregunta concreta"], "avoid": ["Preguntar directo sin contexto si hay tensión", "Encadenar preguntas"]},
  "acknowledge_and_bridge": {"goal": "Reconocer y puentear hacia el siguiente paso sin atascarse.", "when_to_use": "Cuando el otro repite postura o hay un punto de desacuerdo fijo.", "how_to_execute": ["Reconocer postura", "Enunciar objetivo", "Proponer siguiente micro-paso u opción"], "avoid": ["Rebatir largo", "Entrar en bucle argumental"]},
  "recovery_mode_entry": {"goal": "Entrar en modo recuperación para estabilizar una interacción dañada.", "when_to_use": "Tensión alta, amenaza de ruptura o señales de mala fe percibida.", "how_to_execute": ["Bajar exigencia", "Priorizar seguridad/claridad", "Proponer pausa/proceso", "Reducir a 1 pregunta"], "avoid": ["Negociar valor en pico de tensión", "Ironía", "Escalar"]},
  "exit_climate_check": {"goal": "Comprobar si hay clima suficiente para pasar a intereses/opciones.", "when_to_use": "Tras rapport o desescalada; antes de pedir info crítica.", "how_to_execute": ["Pregunta breve de disposición", "Confirmar objetivo común", "Transicionar con permiso"], "avoid": ["Asumir que ya hay permiso", "Cambiar de fase sin señal"]},
  "close_graciously_leave_door_open": {"goal": "Cerrar con elegancia y dejar puerta abierta sin quemar relación.", "when_to_use": "Sin acuerdo viable, tiempo agotado, o necesidad de pausar.", "how_to_execute": ["Resumir 1-2 puntos", "Explicar pausa/cierre", "Proponer recontacto o condición de retorno"], "avoid": ["Ultimátum innecesario", "Culpas", "Cerrar abrupto"]},
  "rapport_build": {"goal": "Generar cercanía y cooperación básica.", "when_to_use": "Inicio frío, interlocutor distante, o necesitas humanizar antes de negociar.", "how_to_execute": ["Pregunta ligera relevante", "Reconocer contexto", "Mostrar intención colaborativa"], "avoid": ["Small talk largo", "Desviarte del objetivo", "Exceso de familiaridad"]},
  "info_extract_critical": {"goal": "Extraer información crítica mínima para avanzar (alta precisión).", "when_to_use": "Cuando falta 1-2 datos que bloquean toda decisión y hay poco tiempo.", "how_to_execute": ["Pregunta cerrada o muy concreta", "Una por turno", "Confirmar respuesta y registrar en world"], "avoid": ["Preguntas abiertas largas", "Explorar temas secundarios", "Asumir sin confirmación"]}
}

PHASE_DEFINITIONS_ES = """PHASE_DEFINITIONS:
- climate:
  objective: "Estabilizar tono, construir confianza mínima y acordar un marco básico para conversar."
  enter_when: ["inicio de la negociación", "tono incierto", "falta de confianza", "hay tensión leve"]
  exit_when: ["tono estable", "la otra parte acepta explorar condiciones", "hay permiso para preguntar por detalles"]
  do: ["validar y reflejar", "preguntar con permiso", "definir proceso ligero"]
  dont: ["presionar por precio/cierre", "hacer demandas duras sin rapport", "escalar tensión"]

- interests:
  objective: "Descubrir motivaciones, restricciones y prioridades (de comprador y vendedor)."
  enter_when: ["climate está estable", "hay disposición a hablar de condiciones", "faltan motivos/limitaciones"]
  exit_when: ["intereses clave identificados", "restricciones principales claras", "criterios de decisión explícitos o inferidos con confirmación"]
  do: ["preguntas diagnósticas", "separar posiciones de intereses", "confirmar supuestos"]
  dont: ["proponer ofertas sin entender restricciones", "inventar razones", "convertirlo en interrogatorio"]

- options:
  objective: "Generar opciones y posibles paquetes (tradeoffs) sin comprometerse aún."
  enter_when: ["intereses y restricciones suficientemente claros", "hay espacio para alternativas", "conflicto bajo/medio"]
  exit_when: ["al menos 2 opciones comparables", "criterios para evaluarlas", "una opción preferida emergente"]
  do: ["proponer 2-3 opciones", "explorar paquetes", "usar criterios objetivos"]
  dont: ["anclar duro sin base", "forzar una sola salida", "usar números si disallow_numbers=true"]

- adjust:
  objective: "Ajustar una propuesta concreta: concesiones, condiciones, plazos, garantías, intercambio."
  enter_when: ["hay opción preferida", "se discuten condiciones específicas", "hay señales de intercambio (X por Y)"]
  exit_when: ["acuerdo casi cerrado", "condiciones principales aceptadas", "solo quedan detalles menores o formalización"]
  do: ["negociar concesiones condicionales", "pedir reciprocidad", "confirmar entendimiento paso a paso"]
  dont: ["ceder sin retorno", "reabrir temas ya cerrados", "romper límites del comprador"]

- formalize:
  objective: "Cerrar y formalizar: resumen final, confirmación, próximos pasos y registro de acuerdos."
  enter_when: ["acuerdo explícito o muy cercano", "solo queda confirmar y documentar", "decisión tomada"]
  exit_when: ["acuerdo confirmado o cierre elegante si no hay acuerdo"]
  do: ["resumir acuerdos", "confirmar compromisos", "definir siguiente paso y condiciones de vuelta"]
  dont: ["introducir cambios grandes", "negociar de nuevo lo acordado", "alargar innecesariamente"]
"""


def build_full_roleplay_profiles(progress_state: dict | None) -> tuple[dict, dict, dict, dict]:
    progress = progress_state if isinstance(progress_state, dict) else {}
    render_state = progress.get("render_state") if isinstance(progress.get("render_state"), dict) else {}
    persona_id = str(render_state.get("persona_id", "") or "").strip()
    scene_id = str(render_state.get("scene_id", "") or "").strip()
    style_id = str(render_state.get("style_id", "") or "").strip()

    should_force_carlos = any(
        [
            persona_id == "buyer_mustang67_v1",
            scene_id == "mustang67_in_person_viewing",
            style_id == "psyplay_compact",
            not persona_id and scene_id == "mustang67_in_person_viewing",
            not persona_id and style_id == "psyplay_compact",
        ]
    )
    if should_force_carlos:
        return (
            deepcopy(CARLOS_PERSONA_PROFILE),
            deepcopy(CARLOS_SCENE_PROFILE),
            deepcopy(CARLOS_STYLE_CONTRACT),
            deepcopy(CARLOS_CONSTRAINTS_STRUCT),
        )
    return build_background_context(progress_state)


def _build_full_context_block(
    progress_state: dict | None,
    *,
    persona_profile: dict | None = None,
    scene_profile: dict | None = None,
    style_contract: dict | None = None,
    constraints_struct: dict | None = None,
    perspectiva: str | None = None,
) -> str:
    if not all(isinstance(x, dict) for x in [persona_profile, scene_profile, style_contract, constraints_struct]):
        persona_profile, scene_profile, style_contract, constraints_struct = build_full_roleplay_profiles(progress_state)
    lines = [
        "BLOQUE_PERFILES_COMPLETOS:",
        f"PERSONA_PROFILE_JSON: {json.dumps(persona_profile, ensure_ascii=False)}",
        f"ESCENA_PROFILE_JSON: {json.dumps(scene_profile, ensure_ascii=False)}",
        f"STYLE_CONTRACT_JSON: {json.dumps(style_contract, ensure_ascii=False)}",
        f"CONSTRAINTS_STRUCT_JSON: {json.dumps(constraints_struct, ensure_ascii=False)}",
        'PARTICIPANTES: {"buyer":"Carlos","seller":"Don Joaquín"}',
    ]
    if str(perspectiva or "").strip():
        lines.append(f"PERSPECTIVA: {str(perspectiva).strip()}")
    lines.append("IDIOMA: es")
    return "\n".join(lines).strip()


def build_planner_context_block_full(progress_state: dict | None) -> str:
    return _build_full_context_block(progress_state)


def build_judge_context_block_full(progress_state: dict | None) -> str:
    persona_profile, scene_profile, style_contract, constraints_struct = build_full_roleplay_profiles(progress_state)
    return _build_full_context_block(
        progress_state,
        persona_profile=persona_profile,
        scene_profile=scene_profile,
        style_contract=style_contract,
        constraints_struct=constraints_struct,
        perspectiva="buyer",
    )


def build_advisor_context_block_full(progress_state: dict | None) -> str:
    return build_judge_context_block_full(progress_state)


def build_executor_context_block_full(
    progress_state: dict | None,
    *,
    persona_profile: dict | None = None,
    scene_profile: dict | None = None,
    style_contract: dict | None = None,
    constraints_struct: dict | None = None,
) -> str:
    return _build_full_context_block(
        progress_state,
        persona_profile=persona_profile,
        scene_profile=scene_profile,
        style_contract=style_contract,
        constraints_struct=constraints_struct,
    )


def build_world_digest(world_state: dict, world_diff: dict | None, *, top_n: int = 3) -> dict:
    buckets = world_state.get("world_buckets", {}) if isinstance(world_state, dict) else {}
    out = {}
    for key in ("offers", "concessions", "requests", "constraints", "interests", "claims", "context"):
        value = buckets.get(key)
        if isinstance(value, list):
            out[key] = value[:top_n]
    return {"top": out, "diff": world_diff if isinstance(world_diff, dict) else {}}


def build_belief_digest(belief_state: dict, *, top_n: int = 3) -> dict:
    buckets = belief_state.get("belief_buckets", {}) if isinstance(belief_state, dict) else {}
    return {
        "planner_signals": belief_state.get("planner_signals", {}) if isinstance(belief_state, dict) else {},
        "top": {
            "hypotheses": list(buckets.get("hypotheses", []))[:top_n],
            "risk_flags": list(buckets.get("risk_flags", []))[:top_n],
            "watch_items": list(buckets.get("watch_items", []))[:top_n],
        },
    }


def build_objective_summary(objective: str, scene_profile: dict, persona_profile: dict) -> str:
    if str(objective or "").strip():
        return str(objective).strip()
    macro_goal = str(scene_profile.get("macro_goal", "") or "").strip()
    goals = ((persona_profile.get("role_card") or {}).get("goals") if isinstance(persona_profile, dict) else []) or []
    goals_compact = "; ".join(str(g).strip() for g in goals[:2] if str(g).strip())
    return f"{macro_goal}. Metas inmediatas: {goals_compact}".strip(" .")


def infer_speaker_of_last_message(*, user_message: str, recent_history_text: str, fallback: str = "unknown") -> str:
    history = str(recent_history_text or "")
    last_line = ""
    if history:
        lines = [line.strip() for line in history.splitlines() if line.strip()]
        if lines:
            last_line = lines[-1]
    probes = [last_line, str(user_message or "").strip()]
    for text in probes:
        lowered = text.lower()
        if lowered.startswith("vendedor:") or lowered.startswith("don joaquín:"):
            return "seller"
        if lowered.startswith("comprador:") or lowered.startswith("carlos:"):
            return "buyer"
    return str(fallback or "unknown") or "unknown"


def build_world_full_compact(world_state: dict, *, top_n: int = 6) -> dict:
    state = world_state if isinstance(world_state, dict) else {}
    buckets = state.get("world_buckets") if isinstance(state.get("world_buckets"), dict) else {}
    compact_buckets: dict[str, list] = {}
    for key, value in buckets.items():
        if isinstance(value, list):
            compact_buckets[str(key)] = value[:top_n]
    return {
        "world_state_meta": state.get("world_state_meta", {}) if isinstance(state.get("world_state_meta"), dict) else {},
        "world_buckets": compact_buckets,
    }


def compact_json_for_prompt(payload: dict, *, max_chars: int = 8000) -> str:
    text = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def map_constraints_to_must_avoid(constraints_struct: dict) -> list[str]:
    forbid = constraints_struct.get("forbid_behaviors", []) if isinstance(constraints_struct, dict) else []
    return [str(x).strip() for x in forbid if str(x).strip()][:8]
