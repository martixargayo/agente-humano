# API boot fix: prompts shims para `agent.py`

## Símbolos importados desde `prompts` en `backend/agent.py`

Se revisó el bloque `from prompts import (...)` y estos son todos los símbolos requeridos por el entrypoint API:

- `BASE_PERSONALITY_PROMPT`
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT`
- `CONVERSATION_USER_TEMPLATE`

## Shims añadidos en `backend/prompts.py`

Se añadió la sección al final:

`# --- App/Agent entrypoint shims (API) ---`

Con definiciones mínimas (strings simples con `.strip()`) para:

- `BASE_PERSONALITY_PROMPT` (obligatorio)
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT`
- `CONVERSATION_USER_TEMPLATE`

Criterios de estilo aplicados en los textos:

- Español
- Sin acciones físicas
- Sin revelar BATNA

## Comandos ejecutados y resultado (fix de import de app/agent)

1. `python -c "import app; print('app_import_ok')"`
   - Resultado: `app_import_ok`
   - Estado: OK (sin `ImportError`)

2. `python -c "import agent; print('agent_import_ok')"`
   - Resultado: `agent_import_ok`
   - Estado: OK (sin `ImportError`)

3. `uvicorn app:app --host 0.0.0.0 --port 8000`
   - Ejecutado con `timeout 12s` para validación no interactiva.
   - Evidencia de arranque:
     - `Application startup complete.`
     - `Uvicorn running on http://0.0.0.0:8000`
   - Estado: OK (sin `ImportError` durante startup)

---

## Ajuste adicional: 500 por `default_turn`

### 1) Callsite exacto y definición real (rg)

- Callsite: `backend/negotiation/state_migration_v3.py:84`
  - `normalize_world_buckets(buckets, default_turn=turn_idx, max_items=8)`
- Definición importada real: `backend/negotiation/validation.py:10`
  - `def normalize_world_buckets(raw: object, default_turn: int | None = None, **kwargs: Any) -> dict:`

### 2) Fix mínimo aplicado

Se hizo compatible `normalize_world_buckets` aceptando `default_turn` y `**kwargs` sin cambiar comportamiento funcional (se ignoran de forma explícita).

### 3) Test smoke añadido

- `backend/tests/test_semantic_runtime_v1.py::test_normalize_world_buckets_accepts_default_turn_kwarg`
- Llama `normalize_world_buckets(..., default_turn=123)` y verifica que no falla.

### 4) Verificaciones ejecutadas

1. `python -m py_compile backend/negotiation/validation.py backend/tests/test_semantic_runtime_v1.py`
   - Estado: OK

2. `pytest -q backend/tests/test_semantic_runtime_v1.py`
   - Resultado: `7 passed`
   - Estado: OK

### 5) Búsqueda extra de incompatibilidades similares

- `rg -n "got an unexpected keyword argument" -S`
  - Resultado: sin matches.
- `rg -n "default_turn=" backend -S`
  - Matches:
    - `backend/negotiation/state_migration_v3.py:84` (callsite real)
    - `backend/tests/test_semantic_runtime_v1.py:250` (smoke test nuevo)

No se detectaron más incompatibilidades en esa búsqueda.
