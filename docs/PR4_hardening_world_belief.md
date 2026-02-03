# PR4: Hardening world/belief extractor v2

## Por qué _NullLLM era un bug crítico en voz
En modo voice, el gate marca extractor_mode="llm". Si no había deps, el extractor v2 usaba _NullLLM y devolvía parches vacíos sin error. Eso es un fallo silencioso: parece que hubo extracción LLM, pero no se actualizó nada. Este PR obliga a usar un LLM real por defecto y, si falla, devuelve meta explícita de error y fallback.

## Por qué el fingerprint es necesario
El universal_state puede cambiar sin variar tamaños o summaries (dedupe, reemplazos, cambios de evidencia). Un fingerprint determinista sobre el estado normalizado detecta cambios estructurales reales y permite gating fiable sin heurísticas frágiles.

## Por qué el merge debe reemplazar por confidence
Si llega evidencia mejor (más confidence o evidence_text más informativo), mantener el item viejo pierde señal y degrada la calidad. El merge con score evita que la evidencia mejor quede descartada.

## Cómo mejora observabilidad/depuración
El extractor v2 ahora reporta fallos explícitos con extractor_failed/extractor_error y no miente sobre last_update_source. Los fingerprints hacen visibles los cambios en universal_state y facilitan rastrear por qué se abrió el gate.
