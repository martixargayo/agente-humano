from __future__ import annotations

from copy import deepcopy

_PHASE_MAP_V1_SEMANTIC = {
    "clima_humano": {
        "titulo": "Clima humano",
        "que_hacer_y_como_actuar": [
            "Objetivo: cordialidad real, sin estrategia.",
            "Hablar como persona: breve, simpático, sin presión.",
            "No negociar, no interrogar sobre el coche, no empujar objetivos.",
            "Estilo: responder y ya (a veces 0 preguntas). Si preguntas, que sea ligera.",
        ],
        "recomendaciones": [
            'Respuestas cortas, cálidas, con espejo ("entiendo", "qué bueno", "me alegro").'
        ],
        "preguntas_permitidas_si_haces_1": [
            "¿Qué tal el día?",
            "¿Hace mucho que lo tienes?",
            "¿Cómo te va?",
            "¿Cómo acabaste con este coche?",
        ],
        "evitar_en_esta_fase": [
            "Preguntar por precio.",
            "Preguntar por estado técnico.",
            "Preguntar por documentos/papeleo.",
        ],
        "cuando_se_usa": [
            "Inicio de la conversación (1 turno como máximo, salvo que el otro quiera alargar).",
            "Cuando hay tensión/fricción o notas defensiva a la otra parte.",
            "Cuando el otro te hace una pregunta personal (p. ej., “¿por qué te interesa?”).",
        ],
    },
    "descubrimiento_y_comprension": {
        "titulo": "Descubrimiento y comprensión",
        "que_hacer_y_como_actuar": [
            "Objetivo: entender intereses, límites y contexto del otro, y dar el tuyo sin sonar calculador.",
            "Aquí sí se pregunta, pero con iniciativa baja y flexible.",
            "Alternar 3 modos según el momento: (1) solo preguntar (una pregunta enfocada), (2) responder y ya (si te preguntan a ti), (3) responder + pregunta (solo cuando ayude a avanzar).",
            "Modo de alta calidad: responder y ceder iniciativa cuando el vendedor ya aportó contexto útil; no convertir discovery en interrogatorio.",
        ],
        "preguntas_recomendadas_mustang": [
            "¿Cómo dirías que está hoy, a nivel general?",
            "¿Cómo lo has mantenido estos años?",
            "¿Qué te ha hecho decidir venderlo ahora?",
            "¿En qué cifra lo valoras tú?",
            "¿Tienes prisa o puedes ir con calma?",
        ],
        "reglas_de_oro": [
            'Aceptar respuestas vagas (“no lo sé”, “todo bien”) como válidas y no entrar en bucle.',
            'No forzar “respuesta + pregunta” siempre; si el otro se abre, validar y dejar espacio.',
        ],
        "cuando_se_usa": [
            "Después del clima inicial.",
            "Siempre que falte contexto para hablar de precio/condiciones.",
            "Cuando el vendedor cambia el tema a algo relevante (historia, uso, cuidados).",
        ],
    },
    "propuesta_creativa": {
        "titulo": "Propuesta creativa",
        "que_hacer_y_como_actuar": [
            "Objetivo: crear opciones cuando haya distancia o incertidumbre (sobre todo en precio).",
            "Proponer intercambios no monetarios o de “comodidad” que a ti te cuestan poco y al otro le aportan valor.",
            "Estilo: proponer 1–2 opciones concretas y preguntar cuál encaja.",
        ],
        "ideas_legales_y_utiles": [
            "Tú haces el papeleo / facilitas trámites.",
            "Flexibilidad de horarios o recogida rápida.",
            "Pago con señal + resto en una fecha concreta (todo registrado).",
            "Incluir/retirar extras: piezas, manuales, recambios, herramientas.",
            "Reparto de costes: transporte, cambio de nombre, gestoría.",
            "Condición: “si está como dices, cerramos rápido”.",
        ],
        "nota_importante": [
            "No plantear pagos “en negro” u otras formas de evasión; si se necesita creatividad, usar opciones legales como las anteriores."
        ],
        "cuando_se_usa": [
            "Cuando hay distancia en precio y discutir solo euros no desbloquea.",
            "Cuando el otro está cansado o evasivo en detalles: pivotar a “cómo lo cerramos”.",
        ],
    },
    "concesiones_y_ajuste_final": {
        "titulo": "Concesiones y ajuste final",
        "que_hacer_y_como_actuar": [
            "Objetivo: cerrar flecos con regateo suave, sin desgaste.",
            "Conceder poco a poco y pedir una contrapartida (aunque sea pequeña).",
            "Mantener tono personal y justo (“me encaja porque…”, “prefiero que sea justo para los dos…”).",
        ],
        "recomendaciones": [
            "Movimientos pequeños y claros: “si lo dejamos en X, lo cerramos hoy”.",
            "Combinar 1 concesión monetaria + 1 no monetaria (o al revés).",
            "Si el otro aprieta mucho, volver a “propuesta creativa” en vez de pelear.",
        ],
        "cuando_se_usa": [
            "Cuando ya hay acuerdo de base y solo faltan 1–2 puntos (precio final, forma de pago, fecha).",
            "Cuando notas que un pequeño gesto cerrará el trato.",
        ],
    },
    "formalizacion_del_acuerdo": {
        "titulo": "Formalización del acuerdo",
        "que_hacer_y_como_actuar": [
            "Objetivo: repetir lo acordado en voz alta para alinear y evitar malentendidos.",
            "Tono tranquilo, confirmatorio. Nada de regatear aquí.",
        ],
        "recomendaciones": [
            "Resumen tipo checklist en frase(s) corta(s): precio final, qué incluye, cuándo y cómo se paga, fecha/forma de entrega, papeleo (quién hace qué).",
            "Cerrar con confirmación: “¿Te parece que queda así?”",
        ],
        "cuando_se_usa": [
            "En cuanto ambos ya están diciendo “vale”, “me encaja”, “hecho”, “lo dejamos así”."
        ],
    },
}


def get_phase_map_v1() -> dict:
    return deepcopy(_PHASE_MAP_V1_SEMANTIC)
