# Verificación de hipótesis: paridad optimizador vs interfaz_usuario

Hallazgos validados:

1. Optimizador e `interfaz_usuario` convergen en el mismo runtime de negociación y comparten contrato de entrada estructural (`_entry_contract`).
2. El optimizador conserva su wrapper experimental (`resolve_entries`, `apply_overrides`, `_optimizador`).
3. `interfaz_usuario` no consume overrides del optimizador por accidente.
4. `interfaz_usuario` no fuga al carril `/chat`.
5. `avatar_app` y `/negociar` legacy quedan fuera del contrato parity-safe (compatibilidad histórica, no referencia arquitectónica).

Evidencia ejecutable canónica:
- `backend/tests/test_interfaz_usuario_api.py`
- `backend/scripts/diagnose_parity_safe_surfaces.py`
- `backend/docs/forensics_optimizer_vs_avatar_run.json`
