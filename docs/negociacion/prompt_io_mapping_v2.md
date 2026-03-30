# prompt_io_mapping.v2

`prompt_io_mapping.v2` amplía el mapping top-level de v1 con transformación profunda para paths anidados y listas.

## Compatibilidad

- `prompt_io_mapping.v1` se mantiene sin cambios.
- Si no hay mapping, el adapter sigue en modo identidad.
- `v2` usa la misma integración runtime (adapt input, output schema visible, normalize output).

## Sintaxis de path soportada

- Campo anidado: `user_turn.raw_text`
- Lista (campo): `negotiation_state.active_axes[]`
- Lista de objetos: `selected_memory[].memory_summary`

No se soporta `[*]` ni otras variantes de wildcard en esta fase.

## Operaciones soportadas en v2 (fase 1)

- `rename`
- `hide`
- `expose`
- `output_alias`

### value_aliases

- Está contemplado en el contrato v2 para reservar estructura.
- En esta fase 1 no se ejecuta; si aparece en configuración, falla explícitamente con `not_supported_in_v2_phase1`.

## Validaciones fail-fast

Al cargar el mapping v2 se valida:

- path inexistente (`field_not_found`)
- uso inválido de `[]` (`array_not_expected`)
- conflicto padre oculto + regla hija (`parent_hidden`)
- colisiones de nombres visibles en mismo padre (`duplicate_visible_name`)
- ocultar output required (`cannot_hide_required_field`)

Los errores incluyen nodo/path/regla/motivo para depuración.

## Ejemplo mínimo

```json
{
  "schema_version": "prompt_io_mapping.v2",
  "nodes": {
    "planner": {
      "inputs": {
        "user_turn.raw_text": { "rename": "mensaje_crudo" },
        "selected_memory[].memory_summary": { "rename": "resumen" }
      },
      "outputs": {
        "turn_goal": { "output_alias": "objetivo_turno" }
      }
    }
  }
}
```
