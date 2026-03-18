# Mouth diagnostics (theme=realistic)

## Causa raíz confirmada (con telemetría)

Con los logs previos se confirmó que el stutter principal venía de **rebuild topológico en caliente** al cambiar `sealed ↔ split`, con picos de cientos de ms y explosión de vértices en split.

## Cambios aplicados para mitigarlo

1. **Cache dual de geometría** (`sealed` + `split`) precomputada y reutilizada en runtime.
2. **Swap de geometría por modo** en lugar de reconstrucción completa por transición.
3. **Carve indexado** (evita `toNonIndexed()` en la ruta principal).
4. **Filtro temporal para `mouthOpenForState`** (ataque rápido / release más lento) para evitar thrash por jitter.
5. **Mouth cavity en realistic** visible en split para evitar hueco blanco.
6. Ajuste de pesos/desplazamientos de labios para reducir banda rectangular superior.

## URLs de reproducción recomendadas

### 1) Step (abre/cierra estable)

`?theme=realistic&mouthTest=1&mouthPattern=step&mouthPeriodMs=1400&mouthHoldMs=260&debugMouth=1&debugMouthHud=1`

Qué validar:
- transición suave de modo,
- sin spikes grandes,
- en split el interior no debe verse blanco.

### 2) Pulses (stress)

`?theme=realistic&mouthTest=1&mouthPattern=pulses&mouthPeriodMs=700&mouthNoise=0.04&debugMouth=1&debugMouthHud=1`

Qué validar:
- fps estable,
- `lastRebuild/max` sin picos masivos,
- ausencia de stutter severo.

### 3) Artefacto rectangular

- `?theme=realistic&mouthTest=1&mouthPattern=sine&mouthNoise=0.08&debugMouthHud=1&debugMouthView=weights`
- `?theme=realistic&mouthTest=1&mouthPattern=sine&mouthNoise=0.08&debugMouthHud=1&debugMouthView=bandMask`
- `?theme=realistic&mouthTest=1&mouthPattern=sine&mouthNoise=0.08&debugMouthHud=1&debugMouthView=side`
- `?theme=realistic&mouthTest=1&mouthPattern=sine&mouthNoise=0.08&debugMouthHud=1&debugMouthView=carveCorridor`

Qué validar:
- área de `aMouthWeight` concentrada en labios,
- `bandMask` sin franja rectangular alta,
- corredor/corte alineado con la línea de boca.

## Parámetros útiles

- `mouthTest=1`
- `mouthPattern=step|sine|ramp|pulses|random|phonemeLike`
- `mouthSeed=123`
- `mouthPeriodMs=1400`
- `mouthHoldMs=180`
- `mouthMax=1`
- `mouthMin=0`
- `mouthNoise=0.08`
- `mouthStateScale=1`
- `mouthTalkScale=1`
- `mouthSpikeMs=6`
- `debugMouth=1`
- `debugMouthHud=1`
- `debugMouthView=weights|side|bandMask|carveCorridor`

## Notas

- El driver principal sigue siendo audio real (`getTalkLevelFromAudio()`) cuando `mouthTest=0`.
- El harness solo se usa para reproducibilidad y diagnóstico.
