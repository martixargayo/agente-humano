# Documento 1 — Plan de reemplazo de prompts (reemplazar, no versionar)

## Regla general obligatoria
1. Reemplazar contenido de prompts existentes con el texto definitivo de `docs/prompts_literal_v2/`.
2. No introducir nuevos nombres de constantes en código (prohibido crear `*_V2_*` adicionales).
3. Mantener los mismos identificadores ya cableados por runtime.

## Fuente de verdad de prompts definitivos
- `docs/prompts_literal_v2/SUMMARY_SYSTEM_PROMPT_v2.txt`
- `docs/prompts_literal_v2/SUMMARY_USER_PROMPT_v2.txt`
- `docs/prompts_literal_v2/PLANNER_SEMANTIC_V2_SYSTEM_PROMPT.txt`
- `docs/prompts_literal_v2/PLANNER_SEMANTIC_V2_USER_PROMPT.txt`
- `docs/prompts_literal_v2/EXECUTOR_V2_SYSTEM_PROMPT.txt`
- `docs/prompts_literal_v2/EXECUTOR_V2_USER_PROMPT.txt`
- `docs/prompts_literal_v2/EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT.txt`
- `docs/prompts_literal_v2/EXECUTOR_FINALIZER_V1_USER_PROMPT.txt`

## Ubicación de prompts actuales y reemplazos

### A) Summarizer
1. Archivo objetivo: `backend/prompts.py`
2. Constantes a reemplazar (mismo nombre):
   - `SUMMARY_SYSTEM_PROMPT`
   - `SUMMARY_USER_PROMPT`
3. Fuente para pegar:
   - `docs/prompts_literal_v2/SUMMARY_SYSTEM_PROMPT_v2.txt`
   - `docs/prompts_literal_v2/SUMMARY_USER_PROMPT_v2.txt`
4. Dependencia de consumo (sin renombre):
   - `backend/negotiation/state/deps.py` (usa `SUMMARY_SYSTEM_PROMPT`, `SUMMARY_USER_PROMPT` vía `repo_prompts`)

### B) Planner
1. Archivo objetivo: `backend/prompts.py`
2. Constantes a reemplazar (mismo nombre, nuevo contenido contractual):
   - `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT`
   - `PLANNER_SEMANTIC_V1_USER_PROMPT`
3. Fuente para pegar:
   - contenido de `docs/prompts_literal_v2/PLANNER_SEMANTIC_V2_SYSTEM_PROMPT.txt` dentro de `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT`
   - contenido de `docs/prompts_literal_v2/PLANNER_SEMANTIC_V2_USER_PROMPT.txt` dentro de `PLANNER_SEMANTIC_V1_USER_PROMPT`
4. Dependencias de consumo (sin renombre):
   - `backend/negotiation/phase_policy_planner.py`
   - `backend/negotiation/repo_prompts.py`

### C) Executor
1. Archivo objetivo: `backend/negotiation/elementos/render/executor_prompts.py`
2. Constantes a reemplazar (mismo nombre):
   - `EXECUTOR_V2_SYSTEM_PROMPT`
   - `EXECUTOR_V2_USER_PROMPT`
3. Fuente para pegar:
   - `docs/prompts_literal_v2/EXECUTOR_V2_SYSTEM_PROMPT.txt`
   - `docs/prompts_literal_v2/EXECUTOR_V2_USER_PROMPT.txt`
4. Regla de formato:
   - El prompt real debe ser texto final de instrucciones.
   - No incluir wrappers/documentación auxiliar dentro del prompt en runtime.
5. Dependencias de consumo:
   - `backend/negotiation/executor/render_executor.py`

## Archivos de puente a revisar (sin introducir versionado paralelo)
1. `backend/negotiation/repo_prompts.py` (debe seguir apuntando a las mismas constantes).
2. `backend/negotiation/state/deps.py` (mantener el wiring existente de summarizer).
3. `backend/negotiation/phase_policy_planner.py` (consume planner vigente por nombre actual).

## Orden de ejecución recomendado
1. Reemplazo Summarizer.
2. Reemplazo Planner.
3. Reemplazo Executor.
4. Verificación de referencias cruzadas (sin crear nuevas constantes).
5. Revisión de documentación para eliminar ambigüedad v1/v2 en implementación activa.

## Criterio de cierre
- El sistema conserva nombres actuales de constantes.
- El contenido activo coincide con `docs/prompts_literal_v2/`.
- No existen nuevas rutas de prompt paralelas para producción.
