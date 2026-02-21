# LiveTrace2 v1

## Endpoints
- `GET /negociacion/livetrace2`
- `GET /negociacion/livetrace2/stream`

## Feature flags
- `LIVETRACE2_MODE=public|internal` (default: `public`)
- `LIVETRACE2_REDACT_FIELDS=field1,field2,...`
- `WORLD_PARALLELISM_ENABLED=0|1` (default: `1`)
- `ADVISOR_ENABLED=0|1` (default: `1`)

## Notes
- En `public`, payloads raw se redaccionan por defecto.
- En `internal`, se muestran prompts y outputs completos.
- Con `WORLD_PARALLELISM_ENABLED=1`, extractor/judge/advisor se ejecutan en paralelo dentro de `world_updater`.
