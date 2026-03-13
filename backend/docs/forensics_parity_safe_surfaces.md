# Investigación forense: superficies parity-safe

## Ámbito parity-safe (referencia del sistema nuevo)
- `POST /api/interfaz_usuario/negociacion/turn`
- `POST /api/optimizador/sandbox/turn`

Ambas superficies comparten `execute_turn_with_contract(...)` y registran `_entry_contract`.

## Fuera del contrato parity-safe (legacy/compatibilidad)
- `avatar_app`
- `POST /chat`
- `POST /negociar`

Se mantienen por compatibilidad histórica, pero no son referencia metodológica para comparar paridad estructural del sistema nuevo.

## Evidencia ejecutable
- Script canónico: `backend/scripts/diagnose_parity_safe_surfaces.py`
- JSON versionado en repo: `backend/docs/forensics_optimizer_vs_avatar_run.json`
