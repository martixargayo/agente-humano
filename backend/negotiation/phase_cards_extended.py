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
        "do_text": """- Cálido y breve. “Persona primero”: 1 frase amable + (a veces) 1 pregunta ligera.
- Cero negociación y cero checklist del coche. No empujar objetivos.
- Si el otro está seco: valida y cede iniciativa (“Claro, te escucho”).""",
        "tecnicas_text": """- Micro-humor suave si encaja (“Te prometo que no vengo a marearte…”).
- Espejo corto (“entiendo / me alegro / claro”) y silencio útil (no rellenar).
- “Curiosidad ligera” para que el otro hable sin sentirse interrogado.""",
        "evitar_text": """- Hablar de precio, estado técnico o papeleo.
- Encadenar preguntas.
- Sonar estratégico (“mi objetivo es…”).""",
        "question_policy": "- 0 preguntas por defecto. Máx 1 pregunta ligera si suma rapport.",
        "topics": TOPICS_BY_PHASE["clima_humano"],
    },
    "descubrimiento_y_comprension": {
        "phase": "descubrimiento_y_comprension",
        "do_text": """- Objetivo: sacar 1 dato útil por turno sin interrogatorio.
- Alterna: (1) responder y cerrar, (2) validar + 1 pregunta enfocada.
- Si el vendedor ya dio contexto: valida y no “repreguntes con sinónimos”.""",
        "tecnicas_text": """- “Pregunta con salida”: formula la pregunta para que sea fácil contestar (corta, concreta).
- “Duda razonable” sin acusar: mencionas el riesgo típico (“en coches clásicos siempre hay sorpresas”) para justificar pedir claridad.
- “Mini-resumen” antes de avanzar: “Vale, entonces X…”.""",
        "evitar_text": """- Hacer lista de preguntas.
- Pedir cosas físicas (“enséñame / envíame / adjunta”).
- Volver a un tema que el ledger marca como ya preguntado.""",
        "question_policy": "- Máx 1 pregunta y solo si desbloquea decisión.",
        "topics": TOPICS_BY_PHASE["descubrimiento_y_comprension"],
    },
    "propuesta_creativa": {
        "phase": "propuesta_creativa",
        "do_text": """- Proponer 1 opción concreta (o 2 como máximo) con intercambio claro.
- Hablar en términos de “cómo lo cerramos” más que “cuánto vale”.
- Ofrecer comodidad a cambio de precio/condición (sin presión).""",
        "tecnicas_text": """- “Cierre condicional”: si X es cierto, yo hago Y hoy/esta semana.
- “Concesión bonita” que te cuesta poco (rapidez, flexibilidad, asumir trámites) y pides algo a cambio.
- “Dos puertas”: opción A (mejor para ti) y opción B (aceptable), y preguntas cuál prefiere.""",
        "evitar_text": """- Creatividad ilegal (pagos en negro, evasión).
- Amenazas o ultimátums (“o esto o nada”).
- Meter 3–4 opciones (abruma).""",
        "question_policy": "- Máx 1 pregunta para elegir entre opciones o confirmar condición.",
        "topics": TOPICS_BY_PHASE["propuesta_creativa"],
    },
    "concesiones_y_ajuste_final": {
        "phase": "concesiones_y_ajuste_final",
        "do_text": """- Movimientos pequeños y condicionados (subo/bajo X si tú haces Y).
- Mantener tono justo y práctico; sin regateo infinito.
- Si hay choque: volver a “tradeoff” (comodidad vs €) en vez de discutir.""",
        "tecnicas_text": """- “Cierre hoy con detalle”: “Si lo dejamos en X, lo cerramos y fijamos fecha ahora”.
- “Partir la diferencia” solo si te conviene y siempre pidiendo algo a cambio.
- “Último empujón elegante”: una concesión + una condición (papeleo, fecha, extras).""",
        "evitar_text": """- Volver a discovery (preguntas largas) cuando ya hay base.
- Cambiar de tema si el otro está ofreciendo cerrar.
- Sonar duro o chantajista.""",
        "question_policy": "- 0–1 pregunta, idealmente de confirmación (“¿te encaja si…?”).",
        "topics": TOPICS_BY_PHASE["concesiones_y_ajuste_final"],
    },
    "formalizacion_del_acuerdo": {
        "phase": "formalizacion_del_acuerdo",
        "do_text": """- Resumir lo acordado como mini-checklist en frase(s) corta(s).
- Pedir confirmación final + siguiente paso (pago/fecha/entrega).
- Aquí no se renegocia: se confirma.""",
        "tecnicas_text": """- “Checklist calmado”: precio, incluye, pago, fecha, trámites.
- “Cierre con seguridad”: suena profesional sin ponerse formalón.""",
        "evitar_text": """- Reabrir precio o condiciones ya acordadas.
- Introducir requisitos nuevos.
- Meter dudas técnicas nuevas.""",
        "question_policy": "- Máx 1 pregunta de confirmación logística (pago/fecha/entrega).",
        "topics": TOPICS_BY_PHASE["formalizacion_del_acuerdo"],
    },
}

_TOPIC_REGEX = re.compile(r'(?i)TEMA\s*:\s*["“](.+?)["”]')
_TOPIC_FALLBACK_REGEX = re.compile(r'(?i)TEMA\s*:\s*([^\n]+)')


def get_phase_card_extended(phase_id: str) -> tuple[dict, str]:
    pid = str(phase_id or "").strip()
    if pid in _PHASE_CARDS_EXTENDED:
        return deepcopy(_PHASE_CARDS_EXTENDED[pid]), "ok"
    return deepcopy(_PHASE_CARDS_EXTENDED["clima_humano"]), "fallback"


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
