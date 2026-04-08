# 06 · Contextos, assets y prompting para `conversacion_simple`

## 1) Modelado de flujo

Se propone una raíz paralela a `negociacion`:

```text
backend/conversacion_simple/
  contexts/
    baseline/
    negociacion_sala_reuniones/
```

> Esta fase documenta diseño; no implementa estructura física.

## 2) Contextos iniciales solicitados

1. `baseline`
2. `negociacion_sala_reuniones`

**Regla de fase actual:** ambos idénticos en comportamiento/contratos.

## 3) Estructura de contexto oficial propuesta

Cada contexto:

- `manifest.json`
- `prompts/brain_prompt.txt`
- `assets/persona.json`
- `assets/conversation_brief.json`
- `assets/phase_cards.json` (opcional semántico, recomendado por compatibilidad)
- `assets/phase_classifier_card.json` (opcional en v1; si se mantiene fase explícita)
- `presentation/presentation_config.json`
- `prompt_io_mapping.json` (opcional)

## 4) Qué heredamos de `negociacion`

Se puede heredar inicialmente:

- `persona.json`
- `negotiation_brief.json` (renombrable a `conversation_brief` en diseño futuro)
- `phase_cards.json`
- presentation defaults/override strategy

Racional: minimizar riesgo y acelerar paridad funcional.

## 5) ¿Siguen aplicando phase_cards / brief / persona / mapping / presentation?

- **Persona:** sí, esencial.
- **Brief:** sí (aunque cambie nombre semántico).
- **Phase cards:** sí, útil para continuidad táctica.
- **Prompt IO mapping:** sí, especialmente para desacoplar input/output visible.
- **Presentation:** sí, debe seguir contextual y desacoplada del runtime.

## 6) Prompting recomendado

## 6.1 Developer prompt (`brain_prompt.txt`)

Debe incluir:

1. rol y límites,
2. contrato JSON estricto `BrainOutput`,
3. política anti invención,
4. instrucciones de seguridad y estilo,
5. regla explícita de no emitir texto fuera de JSON.

## 6.2 User payload

Encapsular en bloque `<brain_input_json>` similar al patrón actual de nodos.

## 7) Prompt IO mapping en `conversacion_simple`

Reusar `load_prompt_io_adapter` y soportar v1/v2 para:
- alias de campos,
- ocultación de campos internos,
- outputs amigables sin romper parser interno.

## 8) Compatibilidad con presentation assets públicos

Repetir estrategia existente:
- resolver defaults + overrides,
- normalizar URLs relativas para servir assets por contexto,
- exponer config en bootstrap.

## 9) Respuesta a pregunta clave #7

### ¿Qué pruebas demostrarían que `baseline` y `negociacion_sala_reuniones` son idénticos en contrato?

1. test de manifests: mismos campos obligatorios y schema válido.
2. test de assets shape: mismas estructuras pydantic y equivalencia semántica.
3. test de prompts contract: ambos contienen el mismo `schema_version` de salida.
4. test de mapping equivalence: adapters producen mismos keys visibles/canónicos.
5. test e2e comparativo con fixtures idénticos: mismas clases de salida y mismos reason codes contractuales.
