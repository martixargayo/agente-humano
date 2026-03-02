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
        "Pequeño rapport: cómo estás tú hoy",
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
        "Paquetes (2 opciones): precio vs concesiones (MESO)",
        "Cierre rápido condicionado (si encaja, cerramos ya)",
        "Papeleo y trámites (quién se encarga)",
        "Garantía razonable / asunción de riesgos",
        "Incluye extras/recambios/herramientas"
    ],
    "concesiones_y_ajuste_final": [
        "Contraoferta pequeña y condicionada",
        "Subo X si tú haces Y (contrapartida)",
        "Precio vs comodidad (fecha/recogida/papeleo)",
        "Último ajuste para cerrar (sin regalar)",
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
        "do_text": """- Objetivo: convertir “me interesa” en “cómo lo cerramos” con opciones claras.
- Propón 1 idea concreta (o 2 como máximo) con tradeoff explícito, siempre dentro del coche.
- Usa paquetes (MESO) cuando haya fricción: 2 opciones equivalentes para ti (precio vs concesiones).
- Ofrece comodidad que te cuesta poco (rapidez/flexibilidad) solo a cambio de algo (precio/papeles/garantía/extras).""",
        "tecnicas_text": """- “Paquetes A/B (MESO)”: dos rutas: una mejor para ti, otra aceptable, ambas defendibles.
- “Cierre condicional”: “Si X queda claro / si tú haces Y, yo cierro esta semana”.
- “Reciprocidad”: das facilidad (pago rápido/horarios) para pedir ajuste en € o papeles.
- “Persuasión social suave”: buenas manos + criterio (“comparables/riesgo/papeles”) sin sonar técnico.""",
        "evitar_text": """- Más de 2 opciones (abruma) o explicar contabilidad interna.
- Meter bienes externos (lavadora/furgoneta) o inventar extras no relacionados.
- Creatividad ilegal/opaca (pagos en negro, evasión).
- Ceder precio sin contrapartida (“vale, lo pago”) solo por avanzar.""",
        "question_policy": "- 0 preguntas por defecto. Máx 1 para elegir A/B o confirmar condición.",
        "topics": TOPICS_BY_PHASE["propuesta_creativa"],
    },
    "concesiones_y_ajuste_final": {
        "phase": "concesiones_y_ajuste_final",
        "do_text": """- Objetivo: apretar sin romper el trato: mejoras pequeñas, siempre condicionadas.
- Nunca aceptes “de primeras” una cifra solo porque esté dentro del techo: intenta mejorar 1–2 rondas.
- Si el precio está alto: baja con contraoferta o exige concesiones (papeles/garantía/extras/entrega).
- Si subes, hazlo en escalera (grande→pequeño) y siempre con contrapartida fuerte.""",
        "tecnicas_text": """- “Tradeoff obligatorio”: “Yo subo a X si tú haces Y (papeles/garantía/extras/entrega)”.
- “Paso pequeño”: movimientos cortos (+300, +200, +100) para no regalar margen.
- “Último empujón elegante”: una concesión final + condición operativa (fecha/pago/papeles) + cierre.
- “Partir diferencia” solo si te conviene y añades algo de valor (no por inercia).""",
        "evitar_text": """- Concesiones gratis (subir sin pedir nada).
- Volver a discovery (preguntas largas) cuando ya hay base para decidir.
- Regateo infinito: más de 2 rondas si no hay nueva palanca.
- Sonar agresivo/chantajista o justificar de más (“porque mi máximo es…”).""",
        "question_policy": "- 0–1 pregunta, idealmente de confirmación operativa (“¿lo dejamos así?”).",
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
