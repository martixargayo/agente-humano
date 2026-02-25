# Fix verification: assistant_last_message propagation + compat judgement schema

## Archivos tocados

1. `backend/negotiation/negotiation_graph.py`
2. `backend/negotiation/nodes/world_node.py`
3. `backend/negotiation/nodes/planner_node.py`
4. `backend/negotiation/executor/render_executor.py`
5. `backend/negotiation/nodes/progress_node.py`
6. `backend/tests/test_semantic_runtime_v1.py`

---

## Cambios clave (antes/después)

## 1) Canonicalización de `assistant_last_message`

### a) Inicialización de estado del turno (graph)

**Antes**: solo se seteaba `last_assistant_message`.

**Después**:
```python
"last_assistant_message": _last_assistant_message(state.history),
"assistant_last_message": _last_assistant_message(state.history),
```

### b) Canonicalización defensiva en nodos críticos

**world_node.py** (inicio de turno):
```python
state["assistant_last_message"] = state.get("assistant_last_message") or state.get("last_assistant_message") or ""
```

**planner_node.py** (inicio de nodo):
```python
state["assistant_last_message"] = state.get("assistant_last_message") or state.get("last_assistant_message") or ""
```

### c) Fallback en lecturas de renderers/prompts

**render_executor.py**:
```python
assistant_last_message_ctx = str(state.get("assistant_last_message") or state.get("last_assistant_message") or "")
...
assistant_last_message=assistant_last_message_ctx,
```

**planner_node.py** al llamar planner:
```python
assistant_last_message=str(state.get("assistant_last_message") or state.get("last_assistant_message") or ""),
```

**progress_node.py** al pasar al updater:
```python
last_assistant_message=str(state.get("assistant_last_message") or state.get("last_assistant_message") or ""),
```

---

## 2) Compat inerte de `policy_plan_judgement`

**Archivo**: `backend/negotiation/nodes/world_node.py`

**Antes**:
```python
"schema_version": "v1_compat_inert",
```

**Después**:
```python
"schema_version": "v1",
```

Manteniendo:
```python
"why": "compat_inert_semantic_judge_active"
```

---

## Por qué ya no hay pérdida de contexto

Con los cambios aplicados:
- Existe una clave canónica `state["assistant_last_message"]` desde el inicio del turno.
- En los puntos de render/ensamblado críticos (planner/executor/progress), las lecturas usan fallback robusto:
  `assistant_last_message or last_assistant_message or ""`.
- Esto evita que prompts semánticos queden sin contexto cuando solo exista la clave legacy.

---

## Confirmación final de compat judgement

La estructura inerte de `policy_plan_judgement` conserva:
- `schema_version: "v1"`
- `plan_status: "continue_same_step"`
- `skip_planner: False`
- `evidence: []`
- `missing_signals: []`
- `why: "compat_inert_semantic_judge_active"`

Con esto se evita romper tooling/tests que esperan exactamente `schema_version="v1"`.
