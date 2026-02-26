from __future__ import annotations

from copy import deepcopy
import re

OFFICIAL_PHASE_IDS = [
    "clima_humano",
    "descubrimiento_y_comprension",
    "propuesta_creativa",
    "concesiones_y_ajuste_final",
    "formalizacion_del_acuerdo",
]

TOPICS_BY_PHASE = {
    "clima_humano": [
        "Pequeño rapport: día / cómo está",
        "Historia ligera: ¿hace cuánto lo tienes?",
        "Anécdota/valor emocional (sin negociar)",
    ],
    "descubrimiento_y_comprension": [
        "Estado general hoy (en una frase)",
        "Mantenimiento y cuidados (qué se ha hecho)",
        "Motivo de venta (por qué ahora)",
        "Cifra objetivo del vendedor (en qué cifra lo valora)",
        "Urgencia y tiempos (prisa vs calma)",
    ],
    "propuesta_creativa": [
        "Cierre rápido condicionado (si encaja, cerramos ya)",
        "Papeleo y trámites (quién se encarga)",
        "Señal + fecha de pago (todo registrado)",
        "Incluye extras/recambios/herramientas",
        "Reparto de costes (gestoría/transferencia/transporte)",
    ],
    "concesiones_y_ajuste_final": [
        "Contraoferta pequeña y condicionada",
        "Subo X si tú haces Y (contrapartida)",
        "Precio vs comodidad (fecha/recogida/papeleo)",
        "Último ajuste para cerrar hoy",
    ],
    "formalizacion_del_acuerdo": [
        "Checklist: precio + qué incluye",
        "Checklist: forma y fecha de pago",
        "Checklist: entrega y trámites",
        "Confirmación final (¿queda así?)",
    ],
}

_PHASE_CARDS_EXTENDED = {
    "clima_humano": {
        "phase": "clima_humano",
        "do": "Cálido y breve. Persona primero. Cero negociación técnica en este paso.",
        "avoid": "No precio, no estado técnico, no checklist. No encadenar preguntas.",
        "question_policy": "0 preguntas por defecto; máximo 1 ligera si suma rapport.",
    },
    "descubrimiento_y_comprension": {
        "phase": "descubrimiento_y_comprension",
        "do": "Sacar 1 dato útil por turno sin interrogatorio. Validar + una pregunta enfocada si destraba.",
        "avoid": "No listas de preguntas. No pedir mostrar/enviar/adjuntar. No repetir lo ya preguntado.",
        "question_policy": "Máx 1 pregunta y solo si desbloquea decisión.",
    },
    "propuesta_creativa": {
        "phase": "propuesta_creativa",
        "do": "Proponer 1 opción concreta (máximo 2) con intercambio claro y cierre condicional.",
        "avoid": "Sin ilegalidades, sin ultimátums, sin 3-4 opciones simultáneas.",
        "question_policy": "Máx 1 pregunta para elegir opción o confirmar condición.",
    },
    "concesiones_y_ajuste_final": {
        "phase": "concesiones_y_ajuste_final",
        "do": "Concesiones pequeñas y condicionadas, tono práctico, empuje de cierre.",
        "avoid": "No volver a discovery largo ni cambiar de tema si el otro quiere cerrar.",
        "question_policy": "0-1 pregunta, idealmente confirmación de cierre.",
    },
    "formalizacion_del_acuerdo": {
        "phase": "formalizacion_del_acuerdo",
        "do": "Confirmar acuerdo con mini-checklist y siguiente paso logístico.",
        "avoid": "No reabrir precio/condiciones, no meter requisitos nuevos.",
        "question_policy": "Máx 1 pregunta de confirmación logística.",
    },
}

_TOPIC_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$')
_TOPIC_FALLBACK_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*(.+?)\s*$')


def get_phase_card_extended(phase_id: str) -> tuple[dict, str]:
    pid = str(phase_id or "").strip()
    if pid in _PHASE_CARDS_EXTENDED:
        return deepcopy(_PHASE_CARDS_EXTENDED[pid]), "ok"
    fallback = deepcopy(_PHASE_CARDS_EXTENDED["clima_humano"])
    fallback["phase"] = "clima_humano"
    return fallback, "fallback"


def extract_topic_selected(next_move_hint: str) -> tuple[str, str]:
    text = str(next_move_hint or "")
    m = _TOPIC_REGEX.search(text)
    if m:
        return m.group(1).strip(), "hint_regex"
    m2 = _TOPIC_FALLBACK_REGEX.search(text)
    if m2:
        return m2.group(1).strip().strip('"“”'), "hint_fallback"
    return "", "none"


def default_topic_for_phase(phase_id: str) -> str:
    topics = TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])
    if topics:
        return str(topics[0])
    return "sin_tema"


def is_valid_topic_for_phase(phase_id: str, topic: str) -> bool:
    topic_s = str(topic or "").strip()
    if not topic_s:
        return False
    return topic_s in TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])
