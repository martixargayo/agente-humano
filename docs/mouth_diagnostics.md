# Mouth diagnostics (theme=realistic)

## Base URL

- `http://localhost:8000/avatar/?theme=realistic&mouthTest=1&debugMouth=1&debugMouthHud=1`

> También sirve con el static server (`python -m http.server`) apuntando a `backend/avatar_app`.

## Parámetros del Mouth Test Harness

- `mouthTest=1`: activa driver determinista (sin micro/audio).
- `mouthPattern=step|sine|ramp|pulses|random|phonemeLike`
- `mouthSeed=123`
- `mouthPeriodMs=1400`
- `mouthHoldMs=180`
- `mouthMax=1`
- `mouthMin=0`
- `mouthNoise=0.08`
- `mouthStateScale=1` (controla `mouthOpenForState` para sealed/split)
- `mouthTalkScale=1` (controla `uTalk` del shader)
- `mouthSpikeMs=6` umbral de spike en rebuild

## Debug/HUD y vistas

- `debugMouth=1`: logs detallados de estado/rebuild/uniforms.
- `debugMouthHud=1`: HUD con frame time/fps/p95/rebuild stats.
- `debugMouthView=weights`: colorea `aMouthWeight`.
- `debugMouthView=side`: colorea `aMouthSide` (arriba/abajo).
- `debugMouthView=bandMask`: colorea `mouthFactor = aMouthWeight * lipOpenMask`.
- `debugMouthView=carveCorridor`: overlay 2D con corredor + mouthLine + split band.

## Casos reproducibles

### Caso 1: step (abre/cierra)

URL:

- `?theme=realistic&mouthTest=1&mouthPattern=step&mouthPeriodMs=1400&mouthHoldMs=260&debugMouth=1&debugMouthHud=1`

Validar:

- En reposo: `actualMode=sealed` y sin costura visible.
- Apertura: transición a `desiredMode=split` + rebuild reason `mouthMode:split`.
- Cierre: `forceSealedNow=true` + rebuild reason `mouthMode:sealed:force`.

### Caso 2: pulses (rápido)

URL:

- `?theme=realistic&mouthTest=1&mouthPattern=pulses&mouthPeriodMs=900&debugMouth=1&debugMouthHud=1`

Validar:

- HUD `rebuild/min` y logs `schedule rebuild`.
- Spikes si `rebuildMs > mouthSpikeMs` (warning en consola).

### Caso 3: jitter controlado

URL:

- `?theme=realistic&mouthTest=1&mouthPattern=sine&mouthNoise=0.08&mouthPeriodMs=1200&debugMouth=1&debugMouthHud=1`

Validar:

- No alternancia caótica sealed/split (mirar `modeChanged`, `canRebuild`, `forceSealedNow`).
- Comparar `mouthOpenForState` (logs) vs `uTalk`/`approxTotalOpen`.

### Caso 4: stress 20s

URL:

- `?theme=realistic&mouthTest=1&mouthPattern=pulses&mouthNoise=0.04&mouthPeriodMs=700&debugMouth=1&debugMouthHud=1&mouthSpikeMs=6`

Pasos:

1. Dejar correr 20s.
2. Recoger en HUD/logs:
   - `rebuild/min`
   - `lastRebuild`/`max`
   - p95 frame time
3. En consola, estimar p95 rebuild con los eventos `[mouth-topocut] realistic geometry rebuilt`.

## Qué mirar para causa raíz

1. **Lag por rebuild**
   - Logs con `rebuild spike` + `rebuildMs`, `trianglesRemoved`, `vertexCount`.
   - `generateAnimatedSurfaceGeometry` y `carve result` muestran tiempos de `clone`/`toNonIndexed`.

2. **Incoherencia split vs deformación shader**
   - `mouthOpenRaw/mouthOpenClamped` + `desiredMode/actualMode`.
   - `uTalk` y cálculos JS: `approxTotalOpen`, `approxLipOpenMask`.
   - Si `actualMode=sealed` y `approxLipOpenMask` alto, hay deformación con boca sellada.

3. **Rectángulo ancho arriba**
   - `debugMouthView=weights`/`bandMask` para ver si `aMouthWeight` invade zona superior.
   - `debugMouthView=carveCorridor` para verificar `corridorHalfWidth`/`lineHalfThickness`/`edgeFeather`.

## Conclusiones esperadas con este sistema

Con esta instrumentación ya se puede confirmar con datos:

- frecuencia real de rebuild y su impacto en frame time,
- si state machine y shader quedan desalineados,
- si el artefacto viene de pesos (`aMouthWeight`/`mouthFactor`) o del carve corridor.
