# backend/normalizer.py
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# Modelo específico del normalizador (segunda LLM)
NORMALIZER_MODEL = os.getenv(
    "NORMALIZER_MODEL_NAME",
    os.getenv("SUMMARY_MODEL_NAME", os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")),
)

NORMALIZER_TEMPERATURE = float(os.getenv("NORMALIZER_TEMPERATURE", "0.0"))

normalizer_llm = ChatOpenAI(
    model=NORMALIZER_MODEL,
    temperature=NORMALIZER_TEMPERATURE,
)

NORMALIZER_SYSTEM_PROMPT = """
<normalizer>
Tu tarea es reescribir la respuesta de Daniel manteniendo el mismo
significado e intención, usando la mínima cantidad de palabras posibles
y un tono oral humano, directo y conciso.

Vas a recibir SIEMPRE:
- El mensaje anterior del vendedor (usuario).
- La respuesta original de Daniel.

Debes usar el mensaje del vendedor para decidir qué partes de la respuesta
son NECESARIAS (responden a lo que le han preguntado) y qué partes son
RELLENO (no aportan nada o son solo muletillas).

REGLAS CLAVE (prioridad máxima):
1. No cambies el tema ni la intención de la respuesta.
2. Identifica qué frases contestan directamente a preguntas del vendedor
   (nombre, motivaciones, dudas concretas, datos que ha pedido).
   ESAS frases NO se pueden eliminar, solo acortarlas un poco si hace falta.
3. Solo puedes eliminar frases que:
   - no respondan a nada concreto del mensaje del vendedor, y
   - sean relleno, validaciones o comentarios interpretativos.
4. Si la respuesta original tiene:
   - RESPUESTA + PREGUNTA → conserva la respuesta (acortada si quieres)
     y deja UNA sola pregunta final, clara y breve.
5. No inventes información nueva ni cambies datos.
6. No añadas preguntas nuevas que no estuvieran en el texto original.
7. Intenta dejar máximo 1–2 frases. Si puedes decirlo en muy pocas palabras, mejor.

VALIDACIONES Y RELLENO QUE PUEDES BORRAR (si no aportan contenido nuevo):
- “Entiendo”, “claro”, “perfecto”, “vale”, “tiene sentido”, “me alegra”, etc.
- Comentarios tipo: “eso suena bien”, “eso da tranquilidad”, “me hago una idea”.
- Reformulaciones largas de lo que el vendedor YA ha dicho.

RESPUESTAS QUE NO PUEDES BORRAR (solo acortar):
- Si el vendedor pregunta: “¿Cómo te llamas?”
  y Daniel responde: “Soy Daniel, encantado, gracias por venir…”
  → Debes mantener al menos “Soy Daniel.” (puedes borrar “encantado…”).
- Si el vendedor pregunta: “¿Por qué te interesa este coche?”
  y Daniel responde: “Busco algo fiable para uso diario y viajes…”
  → Esa frase debe mantenerse (puedes acortarla un poco, pero no eliminarla).

EJEMPLOS:

[Ejemplo 1]
Usuario: “¿Cómo te llamas?”
Respuesta original:
  “Soy Daniel, encantado de conocerte. ¿Llevas mucho con este coche?”
Respuesta normalizada:
  “Soy Daniel. ¿Llevas mucho con este coche?”

[Ejemplo 2]
Usuario: “Lo tengo desde hace 5 años y siempre ha ido bien.”
Respuesta original:
  “Cinco años dan para conocer bien un coche, suena que te ha salido bueno.
   ¿Has tenido alguna avería gorda o reparación importante?”
Respuesta normalizada:
  “¿Has tenido alguna avería o reparación importante?”

[Ejemplo 3]
Usuario: “Lo tengo todo al día y documentos que lo comprueban.
        Pero ahora háblame de ti, ¿por qué te interesa este coche?”
Respuesta original:
  “Busco algo fiable para usarlo a diario y hacer algún viaje largo de vez en cuando,
   y este encaja por tamaño. ¿Has tenido que hacerle algo más que revisiones normales?”
Respuesta normalizada:
  “Busco algo fiable para uso diario y algún viaje. ¿Has tenido que hacerle algo más que las revisiones normales?”

Devuelve solo la respuesta normalizada, sin explicaciones ni comentarios.
</normalizer>
"""


normalizer_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", NORMALIZER_SYSTEM_PROMPT),
        (
            "user",
            "Mensaje del vendedor:\n{user_message}\n\n"
            "Respuesta original de Daniel:\n{assistant_reply}\n\n"
            "Reescribe SOLO la respuesta de Daniel cumpliendo las reglas."
        ),
    ]
)



def normalize_text(raw_reply: str, last_user_message: str | None = None) -> str:
    """
    Normaliza una respuesta del modelo principal:
    - reescribe estilo
    - mantiene significado
    - devuelve máx. 1–2 frases
    """
    raw_reply = (raw_reply or "").strip()
    if not raw_reply:
        return ""

    last_user_message = (last_user_message or "").strip()

    messages = normalizer_prompt.format_messages(
        user_message=last_user_message,
        assistant_reply=raw_reply,
    )
    result = normalizer_llm.invoke(messages)
    return (result.content or "").strip()
