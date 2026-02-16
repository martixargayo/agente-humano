# Análisis exhaustivo: sistema de boca en tema **dark** vs **realistic**

## Resumen ejecutivo

Sí, **hay métodos viables para que la malla del tema realistic se comporte de forma inspirada en dark** (agrupando elementos de labio superior/inferior para abrir una cavidad), sin depender solamente del `discard`/cutout actual.

La clave es cambiar de un modelo **"agujero por recorte de fragmento"** a un modelo **"agujero por separación geométrica + recorte suave de apoyo"**.

---

## 1) Cómo funciona hoy el sistema en dark (y por qué “se siente” mejor)

En dark, la boca no se percibe solo como un agujero recortado, sino como un patrón de **reorganización de partículas**:

1. Cada partícula tiene pesos de boca (`aMouthWeight`) y un signo de lado (`aMouthSide`) precalculados desde `MouthTuning`.
2. En vertex shader, al hablar (`uTalk`) se aplica:
   - desplazamiento vertical opuesto para cada labio (`side * lipAmp * mouthFactor`),
   - desplazamiento en profundidad (`-uLipDepthAmp * mouthFactor`).
3. El resultado visual es una **separación física local** de partículas en la zona de boca.

Esto está en:
- cálculo de pesos de boca en CPU y atributos (`aMouthWeight`, `aMouthSide`),
- desplazamiento de boca en `vertexShader` con `uTalk`, `uTalkAmpTop/Bot`, `uLipDepthAmp`.

---

## 2) Cómo funciona hoy realistic (y por qué falla en algunos casos)

En realistic hoy conviven dos capas:

1. **Cutout por shader**: en fragment shader se calcula una elipse (`mouthHoleSdf`) y se hace `discard` dentro cuando `uMouthOpen` supera umbral.
2. **Mouth interior mesh**: una malla/plano interior oscuro para dar cavidad.

Limitación estructural:
- El cutout funciona como “corte 2D proyectado” en espacio base (`vBaseXY`), no como separación real de la superficie de labios.
- En boca (zona muy curva/dinámica) esto puede generar artefactos: bordes duros, popping, fuga visual con ciertos ángulos y expresiones.

---

## 3) Diagnóstico comparativo (dark vs realistic)

### Dark (fortaleza)
- El hueco emerge de la **dinámica de elementos** (partículas se apartan), no sólo de ocultación.
- Tiene inercia perceptual natural al abrir/cerrar.

### Realistic actual (debilidad)
- El hueco depende demasiado de `discard` elíptico.
- Si la elipse no coincide perfecto con la anatomía instantánea del labio, se nota “corte” más que “apertura”.

---

## 4) Métodos viables para llevar el comportamiento dark a realistic

## Método A (recomendado): **Lip Convergence Field + Soft Cutout** (híbrido)

Objetivo: hacer que la superficie de labios se mueva de forma análoga a dark y usar cutout solo como refinamiento.

### Idea
1. Reusar `aMouthWeight` y `aMouthSide` en la geometría realistic (si no están ya para esa malla, generarlos igual que en dark).
2. En vertex shader de realistic, aplicar:
   - separación vertical de labios,
   - ligera compresión horizontal hacia comisuras,
   - empuje en Z para “abrir cavidad”.
3. Mantener cutout pero más pequeño/suave, sólo para limpiar intersecciones.

### Ventajas
- Apariencia de “vaciar boca” por **movimiento real de elementos de malla**.
- Menos dependencia de recorte agresivo.
- Inspiración directa del patrón dark.

### Riesgos
- Requiere tuning fino para evitar deformación rara en sonrisas o fonemas extremos.

---

## Método B: **Split de labios por máscaras anatómicas (upper/lower bands)**

Separar explícitamente regiones anatómicas de labio superior e inferior (por peso o por grupos de vértices) y animarlas con curvas independientes.

### Ventajas
- Control artístico alto.

### Desventajas
- Más coste de autoría/tuning por personaje.

---

## Método C: **Distance-field cavity en screen space (solo shading)**

Mantener geometría casi fija y construir una cavidad más física con SDF avanzado + depth tricks.

### Ventajas
- Menos modificación geométrica.

### Desventajas
- Sigue siendo "truco de shading"; no resuelve del todo el problema base de recorte.

---

## 5) Propuesta concreta de implementación (iterativa)

## Fase 1 — MVP técnico (bajo riesgo)

1. Añadir uniforms en realistic vertex shader:
   - `uLipGather`, `uLipSpreadYTop`, `uLipSpreadYBot`, `uLipDepth`, `uLipCornerPull`.
2. Aplicar offset por vértice usando `aMouthWeight` + `aMouthSide`:
   - `open = smoothstep(openMin, openFade, uMouthOpen)`
   - `w = aMouthWeight * open`
   - `dy = sign(aMouthSide) * mix(uLipSpreadYBot, uLipSpreadYTop, step(0.0, aMouthSide)) * w`
   - `dz = -uLipDepth * w`
   - `dx = -sign(x-centerX) * uLipCornerPull * w * (1.0 - abs(aMouthSide))`
3. Reducir tamaño del cutout actual (ej. 10–20%) y suavizar feather.
4. Validar con `forceTalk` y secuencias de habla real.

## Fase 2 — Calidad visual

1. Ajustar anisotropía por fonema (AA/EE/OO).
2. Añadir limitadores para evitar colapso en comisuras.
3. Ajustar material interior según apertura (oscurecimiento y escala).

## Fase 3 — Robustez

1. Histeresis/filtrado temporal del `mouthOpen` para evitar jitter.
2. Presets por idioma/voz (si cambia patrón de apertura).
3. Telemetría de clipping/intersección para QA.

---

## 6) Parámetros sugeridos iniciales (para arrancar tuning)

- `uLipSpreadYTop`: 0.010–0.016
- `uLipSpreadYBot`: 0.012–0.020
- `uLipDepth`: 0.006–0.012
- `uLipCornerPull`: 0.002–0.006
- `uLipGather`: 1.0
- cutout width/height: 0.80–0.90 de valor actual

---

## 7) Criterios de aceptación

1. Al hablar, la boca debe abrirse principalmente por **separación de labios** (no por agujero abrupto).
2. En perfil 3/4, el hueco debe mantenerse coherente sin popping.
3. En cierre, los labios deben reunirse sin “mordidas” ni flicker.
4. Degradación visual mínima en 30/60 fps.

---

## 8) Conclusión

Sí, tu intuición es correcta: aunque en realistic no sean “bolas”, se puede lograr un comportamiento muy parecido al dark si haces que los vértices/elementos del labio **se agrupen y separen proceduralmente** para abrir la cavidad, usando el cutout solo como complemento.

La ruta más pragmática es el enfoque híbrido (**Método A**), porque aprovecha el pipeline actual y evita rehacer todo el sistema.
