# Addendum de cierre de decisiones — implementación LLM visual por frames

Fecha: 2026-03-27  
Estado: **Cierre técnico previo a implementación** (sin cambios funcionales)

---

# 1. Propósito del addendum

Este addendum cierra decisiones operativas que en el plan principal quedaron abiertas o implícitas. Objetivo:

- eliminar ambigüedad antes de tocar código,
- alinear documentación, tests y runtime,
- reducir riesgo de regresión y de review confusa,
- dejar una base verificable para ejecutar Fase 1 sin reinterpretaciones.

**Alcance:** solo decisiones de diseño y reglas operativas para V1.  
**No incluye implementación ni cambios de comportamiento.**

---

# 2. Decisiones cerradas de naming

## 2.1 Principio de naming adoptado
Se congela convención:

- `communication_visual_*` para todo lo nuevo específico de rama visual LLM.
- usar sustantivo funcional singular por módulo (ej. `sampling`, `openai_client`, `batch_runner`, `synthesizer`).
- evitar variantes casi sinónimas (`selector` vs `selection`) para no fragmentar imports/tests.

## 2.2 Naming definitivo de módulos nuevos

### A) Módulo de sampling/batching
**Nombre final:** `backend/evaluacion/engine/communication_visual_sampling.py`

**Por qué este nombre:**
- explicita que cubre *sampling* + *batching* para visual LLM,
- evita conflicto semántico `selector`/`selection`,
- permite que futuros métodos de selección (uniform/adaptativo) convivan en un único módulo.

**Responsabilidad exacta:**
- construir candidatos temporales 1fps,
- selección uniforme cap 90,
- partición en lotes con regla `<6`,
- utilidades puras y deterministas.

**Qué NO debe vivir ahí:**
- llamadas OpenAI,
- lectura/escritura de artefactos,
- lógica de report/síntesis textual,
- parsing de respuestas LLM.

---

### B) Cliente OpenAI visual
**Nombre final:** `backend/evaluacion/engine/communication_visual_openai_client.py`

**Por qué este nombre:**
- declara dependencia explícita de proveedor,
- centraliza puntos de red/timeouts/retries,
- facilita swap futuro de proveedor sin contaminar el dominio.

**Responsabilidad exacta:**
- construir payload Responses API multimodal,
- enviar request por lote,
- validar parse estructurado,
- mapear errores a excepciones de dominio.

**Qué NO debe vivir ahí:**
- decisión de qué frames elegir,
- orquestación completa del job,
- persistencia de artefactos,
- síntesis final cross-batch.

---

### C) Runner por lotes
**Nombre final:** `backend/evaluacion/engine/communication_visual_batch_runner.py`

**Por qué este nombre:**
- separa claramente orquestación de lotes del cliente HTTP/API,
- permite testear estrategia batch sin tocar OpenAI real.

**Responsabilidad exacta:**
- transformar manifest + estrategia en `BatchEvalInput[]`,
- ejecutar lotes (V1 secuencial),
- consolidar parciales y metadatos de ejecución por lote.

**Qué NO debe vivir ahí:**
- lógica de sampling (importa de `communication_visual_sampling.py`),
- síntesis final global,
- render/ensamble de reporte final.

---

### D) Síntesis final
**Nombre final:** `backend/evaluacion/engine/communication_visual_synthesizer.py`

**Por qué este nombre:**
- más estable y neutral que `*_synthesis_llm.py` (permite combinar reglas deterministas + LLM),
- comunica claramente propósito de agregación final.

**Responsabilidad exacta:**
- tomar `BatchEvalOutput[]` + metadatos de cobertura,
- producir `CommunicationVisualFinalEvalV1`,
- aplicar reglas de consistencia/confidence global.

**Qué NO debe vivir ahí:**
- transporte de imágenes,
- scheduling de batches,
- lectura directa del frame extractor.

---

## 2.3 Resultado de cierre de naming
Se considera **cerrada** la inconsistencia previa `selector/selection` y se congela set final:

1. `communication_visual_sampling.py`
2. `communication_visual_openai_client.py`
3. `communication_visual_batch_runner.py`
4. `communication_visual_synthesizer.py`

---

# 3. Decisión final sobre sampling temporal

## 3.1 Definición inequívoca de “1 frame por segundo”
Para esta V1, “1 fps” significa:

- trabajar sobre **segundos completos** del timeline,
- usar timestamps discretos en milisegundos: `t_i = i * 1000`,
- no agregar frame extra por fracción final de segundo.

## 3.2 Fórmula definitiva de candidatos
Dado `duration_ms`:

- `N_raw = floor(duration_ms / 1000)`
- `N = max(1, N_raw)`
- candidatos en índices `i = 0..N-1`
- `timestamp_ms_i = i * 1000`

Consecuencias:
- siempre hay al menos 1 candidato (incluye primer segundo en `t=0`),
- el último tramo fraccional (`duration_ms % 1000`) **no añade** candidato propio.

## 3.3 Regla definitiva de uso/selección
- si `N <= 90`: usar todos los candidatos,
- si `N > 90`: seleccionar exactamente `K=90` índices uniformes sobre `[0..N-1]`.

### Fórmula uniforme cerrada (center-bin)
Para `j in [0..K-1]`:

- `idx_j = floor((j + 0.5) * N / K)`
- `idx_j = min(max(idx_j, 0), N-1)`

## 3.4 Deduplicación defensiva (normativa)
Aunque con `N>K` no debería duplicar en condiciones normales, se define comportamiento obligatorio:

1. construir lista `idx` por fórmula,
2. eliminar duplicados preservando orden,
3. si faltan índices para llegar a `K`, rellenar con vecinos no usados más cercanos al hueco esperado,
4. ordenar final ascendente y truncar a `K`.

Esto evita ambigüedad en tests por edge numéricos/plataforma.

## 3.5 Inclusión del inicio y cobertura de cola
- **Inicio:** siempre incluido (`t=0`) porque `idx_0` cae en primer bin.
- **Cola:** razonablemente cubierta por center-bin; en la práctica incluirá muestras del tramo final sin forzar “último frame exacto”.

No se fuerza inclusión de `N-1` por norma, porque rompería uniformidad en algunos casos.

## 3.6 Ejemplos normativos (deben convertirse en tests)

### Caso A — `duration_ms = 500`
- `N_raw=0`, `N=1`
- candidatos: `[0]`
- seleccionados: `[0]`

### Caso B — `duration_ms = 999`
- `N_raw=0`, `N=1`
- candidatos: `[0]`
- seleccionados: `[0]`

### Caso C — `duration_ms = 1000`
- `N_raw=1`, `N=1`
- candidatos: `[0]`
- seleccionados: `[0]`

### Caso D — `duration_ms = 65_000`
- `N=65`
- `N<=90` => 65 seleccionados
- timestamps: `0..64_000` cada 1000ms

### Caso E — `duration_ms = 90_000`
- `N=90`
- `N<=90` => 90 seleccionados
- timestamps: `0..89_000`

### Caso F — `duration_ms = 90_500`
- `N=floor(90.5)=90`
- 90 seleccionados (sin frame extra por 500ms finales)
- timestamps: `0..89_000`

### Caso G — `duration_ms = 180_000`
- `N=180`
- `N>90` => selección uniforme de 90 sobre 180
- patrón esperado aproximado: un frame cada 2 segundos, distribuido full-duration

---

# 4. Decisión final sobre confidence

## 4.1 Política operativa mínima (V1)
Se adopta `confidence` como valor continuo `[0,1]`, derivado de dos capas:

1. **Suficiencia de evidencia por lote** (`evidence_sufficiency`): `low|medium|high`.
2. **Penalizaciones de observabilidad/calidad** por flags y cobertura.

## 4.2 Relación obligatoria con `evidence_sufficiency`
Mapeo base por lote:
- `high` -> base `0.80`
- `medium` -> base `0.62`
- `low` -> base `0.42`

`confidence` final de lote parte de ese base y aplica caps/penalizaciones.

## 4.3 Señales que afectan confidence
Inputs mínimos obligatorios:
- `frames_total`, `frames_usable`,
- `frames_with_face_visible`,
- `frames_with_hands_visible`,
- flags de observabilidad (`hands_not_visible`, `face_partially_visible`, `upper_body_not_visible`, `blur_detected`, `low_light_detected`).

## 4.4 Reglas de cap y penalización (V1 cerrada)
Reglas por lote:

1. **Cap por usabilidad baja**
   - si `frames_usable / frames_total < 0.50` -> `confidence <= 0.55`

2. **Cap por manos no observables**
   - si `frames_with_hands_visible == 0` -> `confidence <= 0.50`

3. **Cap por rostro no observable**
   - si `frames_with_face_visible == 0` -> `confidence <= 0.45`

4. **Cap por torso superior fuera de encuadre**
   - si `upper_body_not_visible=true` -> `confidence <= 0.55`

5. **Penalizaciones acumulables**
   - `blur_detected=true` -> `-0.08`
   - `low_light_detected=true` -> `-0.08`
   - `face_partially_visible=true` -> `-0.06`

6. **Clamp final**
   - `confidence = min(max(confidence, 0.05), 0.95)`

## 4.5 Ejemplos operativos

### Ejemplo 1 (buena observabilidad)
- sufficiency=`high` (0.80)
- usable 26/30, face 24, hands 18, sin flags
- confidence final ~0.80

### Ejemplo 2 (manos no visibles)
- sufficiency=`medium` (0.62)
- hands=0 -> cap 0.50
- final: 0.50 (aunque resto sea bueno)

### Ejemplo 3 (video degradado)
- sufficiency=`high` (0.80)
- usable ratio 0.43 -> cap 0.55
- blur + low_light -> -0.16
- final min(0.55, 0.64) => 0.55, luego penalizado y clamp -> 0.48 aprox

## 4.6 Justificación y trade-offs
- Esta política evita “sobreconfianza por texto bonito sin observabilidad real”.
- Riesgo si es demasiado agresiva: infraestima casos aceptables con mal encuadre puntual.
- Riesgo si es demasiado laxa: resultados difíciles de auditar y confianza inflada.

**Decisión V1:** sesgo levemente conservador (preferimos subestimar antes que sobreafirmar).

---

# 5. Decisión final sobre transporte base64 y límites V1

## 5.1 Decisión V1 cerrada
**Sí, V1 usa base64 data URL como mecanismo único de transporte.**  
No se abre en V1 la vía `file_id`/URL pública para evitar complejidad de storage y permisos.

## 5.2 Política de preprocesado por frame (antes de serializar)
Pipeline obligatorio por frame:
1. decodificar JPG extraído,
2. reescalar para que lado mayor <= **960 px**,
3. convertir/forzar a **JPEG**,
4. comprimir calidad objetivo **75**,
5. validar tamaño binario final.

## 5.3 Límites concretos
- **Tamaño máximo por frame (post-compress):** `<= 220 KB`
- **Tamaño máximo por lote (suma binaria pre-base64):** `<= 5.5 MB`
- **Tamaño máximo por lote serializado (aprox base64):** `<= 7.5 MB`

Racional: margen cómodo para lotes de 30 y estabilidad de latencia.

## 5.4 Política al superar umbrales

### Frame supera 220KB
- intento 1: bajar lado mayor a 800px y calidad 70
- intento 2: bajar a 640px y calidad 65
- si sigue >220KB -> marcar frame `oversize_unusable` y excluir de lote usable

### Lote supera umbral
- recodificar frames más pesados primero (estrategia greedy)
- si no alcanza -> reducir tamaño del lote en runtime (sub-lote excepcional)
- si ni así cumple o usable cae demasiado -> fallback metadata para ese batch

## 5.5 Umbral de fallback a metadata
Fallback automático de batch si:
- `frames_usable < 6` después de normalización, o
- payload sigue superando umbral tras 2 rondas de compresión, o
- error de serialización/decodificación no recuperable.

Registrar motivo en artefacto y `limitations`.

## 5.6 Resolución objetivo y `detail="low"`
Con `detail="low"` (model-side downsampling), lado mayor 960px es suficiente para:
- manos visibles/no visibles,
- postura/apertura,
- expresividad facial gruesa.

No perseguimos microdetalle en V1.

---

# 6. Decisión final sobre secuencialidad en Fase 2

## 6.1 Decisión cerrada
**Fase 2 ejecuta lotes de forma secuencial obligatoria.**

## 6.2 Excepciones
No hay excepciones funcionales en F2.  
Única excepción operativa: retry del mismo lote (sigue siendo secuencial).

## 6.3 Justificación V1
- simplifica trazabilidad de errores por lote,
- reduce presión sobre rate limits y picos de latencia,
- evita abrir frente de concurrencia antes de estabilizar schema/prompt,
- facilita debugging y comparación humana lote-a-lote.

## 6.4 Qué se gana / qué se pierde
- **Gana:** estabilidad operacional, auditabilidad, menor complejidad.
- **Pierde:** latencia total potencialmente mayor en videos largos.

## 6.5 Condición para habilitar paralelización futura
Solo en fase posterior si se cumple simultáneamente:
1. p95 latencia secuencial supera SLO por 2 releases seguidas,
2. tasa de fallos schema/retry < 2%,
3. no-regresión de consistencia entre runs en dataset de calibración,
4. límites de proveedor verificados para concurrencia segura.

---

# 7. Schema parcial endurecido propuesto

## 7.1 Decisión de endurecimiento
Se aprueba endurecer salida parcial con dos bloques obligatorios nuevos:

1. `observability_flags`
2. `frame_coverage_summary`

## 7.2 Modelo propuesto (`CommunicationVisualBatchEvalV2`)

```json
{
  "schema_version": "communication_visual_batch_eval.v2",
  "batch_index": 1,
  "total_batches": 3,
  "batch_score_1_5": 4,
  "evidence_sufficiency": "medium",
  "confidence": 0.58,
  "hand_use_assessment": "...",
  "facial_expression_assessment": "...",
  "posture_assessment": "...",
  "visual_support_assessment": "...",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "limitations": ["..."],
  "cited_frame_ids": ["frame_012", "frame_020"],
  "observability_flags": {
    "hands_not_visible": false,
    "face_partially_visible": true,
    "upper_body_not_visible": false,
    "blur_detected": true,
    "low_light_detected": false,
    "camera_far_distance": false
  },
  "frame_coverage_summary": {
    "frames_total": 30,
    "frames_usable": 24,
    "frames_with_face_visible": 22,
    "frames_with_hands_visible": 11,
    "frames_with_upper_body_visible": 20,
    "frames_blurry": 6,
    "frames_low_light": 2
  },
  "confidence_reasoning": [
    "evidence_sufficiency=medium base=0.62",
    "hands_visibility_ratio=0.37",
    "blur_detected=true penalty=0.08"
  ]
}
```

## 7.3 Campos obligatorios/opcionales

### Obligatorios
- `schema_version`, `batch_index`, `total_batches`
- `batch_score_1_5`, `evidence_sufficiency`, `confidence`
- `strengths`, `weaknesses`, `limitations`, `cited_frame_ids`
- `observability_flags`
- `frame_coverage_summary`

### Opcionales (pero recomendados)
- `hand_use_assessment`, `facial_expression_assessment`, `posture_assessment`, `visual_support_assessment`
- `confidence_reasoning`

## 7.4 Tipos y restricciones
- `batch_score_1_5`: `int` [1..5]
- `confidence`: `float` [0.0..1.0]
- `frames_*`: `int >= 0`, y `frames_usable <= frames_total`
- flags: `bool`

## 7.5 Justificación por campo nuevo

### `observability_flags`
- diagnóstico rápido de por qué un lote no permite inferencias fuertes,
- mejora auditoría humana y debugging en incidentes.

### `frame_coverage_summary`
- cuantifica cobertura real, no solo impresión textual,
- habilita reglas de confidence reproducibles,
- útil para calibración futura y dashboards.

### `confidence_reasoning`
- trazabilidad auditiva del cálculo aplicado,
- facilita detectar si política es demasiado agresiva/laxa.

## 7.6 Impacto en confidence y síntesis
- síntesis global debe ponderar lotes por `frames_usable/frames_total` y `evidence_sufficiency`,
- lotes con flags críticos no se descartan, pero reducen peso/confianza final,
- `cited_frame_ids` + coverage ayudan a defender recomendaciones finales.

---

# 8. Impacto de estas decisiones sobre el plan de fases existente

## Cambios respecto al plan base
1. Se congela naming definitivo (evita churn de imports/tests).
2. Se formaliza sampling V1 con ejemplos normativos exactos.
3. Se fija política concreta de confidence (caps + penalties).
4. Se cierran límites operativos de base64 con umbrales numéricos.
5. Se zanja secuencialidad obligatoria en Fase 2.
6. Se endurece schema parcial a versión `v2` auditable.

## Efecto práctico en Fase 1/Fase 2/Fase 3
- **Fase 1:** ya puede diseñar tests exactos de sampling/batching sin huecos.
- **Fase 2:** integra OpenAI con política de payload cerrada y secuencialidad definida.
- **Fase 3:** síntesis final recibe parciales más robustos para agregación confiable.

---

# 9. Qué queda ya suficientemente cerrado para aprobar Fase 1

Se considera cerrado para arrancar Fase 1:

1. naming final de módulos nuevos,
2. definición matemática y ejemplos de sampling temporal,
3. criterio de batching ya definido,
4. shape mínimo de contratos parciales/finales,
5. política base de confidence para futura implementación,
6. principio de compatibilidad (`metadata` default).

Con esto, Fase 1 puede ejecutarse sin reinterpretaciones.

---

# 10. Qué seguiría pendiente antes de implementar Fase 2 (si algo quedara)

Pendientes menores (no bloqueantes para Fase 1, sí para Fase 2):

1. confirmar SLO operativo objetivo (latencia p95 por evaluación),
2. confirmar límites de logging/redacción de payload base64 en artefactos,
3. confirmar modelo exacto default en entorno (`gpt-4.1-mini` propuesto),
4. confirmar si `CommunicationVisualBatchEvalV2` reemplaza `V1` o convive versionado.

**Recomendación:** dejarlos resueltos al cierre de Fase 1 antes de activar la primera llamada real a OpenAI.

---

## Cierre
Este addendum deja decisiones críticas en estado operativo, testeable y auditable.  
Tras su aprobación, el inicio de Fase 1 es técnicamente seguro desde el punto de vista de especificación.
