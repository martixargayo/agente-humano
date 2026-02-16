# Fase actual: switch a `Points` SOLO en un anillo pequeño de labios (rim-only) durante habla

## Veredicto de viabilidad (esta fase)

**Sí, viable** y con riesgo moderado-bajo si:

1. el switch se limita a una franja estrecha (rim),  
2. el movimiento de points copia 1:1 la boca de dark,  
3. la malla se atenúa de forma suave solo en interior mínimo (sin `discard`),  
4. se usa histéresis para evitar parpadeo en micro-pausas.

Sin plate/cavidad (por constraint), el hueco se leerá como “vacío hacia fondo blanco” y puede funcionar si el centro queda realmente con poca contribución de malla durante apertura.

---

## 1) Definición exacta de la región rim (anillo)

## 1.1 Principio

La región de points debe ser **anillo estrecho alrededor del contorno labial**, no toda la boca.  
Base principal: `aMouthWeight` (ya representa la máscara funcional de boca).

## 1.2 Definición recomendada (v1)

Sea `w = aMouthWeight`.

- **Rim principal**: banda media de la máscara.
- **Inner mínimo opcional**: soporte muy ligero para evitar gaps en aperturas medias.

Propuesta numérica inicial:

- `rimMask = smoothstep(0.26, 0.46, w) * (1.0 - smoothstep(0.68, 0.84, w))`
- `innerTiny = smoothstep(0.70, 0.82, w) * 0.22`
- `mouthPointsMask = clamp(rimMask + innerTiny, 0.0, 1.0)`

Selección para construir `mouthPointsGeo`:
- incluir vértices si `mouthPointsMask > 0.08`.

## 1.3 Filtros adicionales recomendados

- Mantener separación sup/inf con `aMouthSide` (se usa en movimiento, no para excluir).  
- Opcional anti-outliers: excluir vértices con `abs(aMouthSide) < 0.02` **si** aparecen puntos “en centro” no deseados.

## 1.4 ¿Rim-only puro o rim + mini-inner?

**Recomendado: rim + mini-inner (muy pequeño)**.  
Rim-only puro reduce seams, pero puede dejar discontinuidades en close-up según densidad de malla. El mini-inner al 20–25% de peso mejora continuidad sin convertir toda la boca en points.

---

## 2) Comportamiento exacto durante habla

## 2.1 Activación con `mouthOpenVisual`

No usar `uTalk` crudo para visibilidad.  
Crear `mouthOpenVisual` suavizado con attack/release + histéresis:

- attack: `24–30`
- release: `10–14`
- ON points: `mouthOpenVisual > 0.050`
- OFF points: `mouthOpenVisual < 0.032`

Esto evita toggling rápido en pausas 80–120 ms.

## 2.2 Movimiento de points (copiar dark EXACTO)

Usar la misma ecuación de dark para los points rim:

- `talkOpen = max(sin(uTime * uTalkFreq), 0.0) * uTalk`
- `totalOpen = clamp(uRestOpen + talkOpen, 0.0, 1.0)`
- `mouthFactor = aMouthWeight * totalOpen`
- `verticalOffset = aMouthSide * lipAmp * mouthFactor`
- `depthOffset = -uLipDepthAmp * mouthFactor`

Sin jitter temporal adicional.

## 2.3 Cómo se forma el “hueco” sin plate

En esta fase, el hueco debe aparecer por combinación de:

1. separación sup/inf de points rim (contorno orgánico),  
2. atenuación suave de malla en interior mínimo durante apertura,  
3. centro relativamente libre de points (rim-only + mini-inner controlado).

Resultado esperado: el centro revela fondo blanco/DOM cuando hay apertura suficiente.

---

## 3) Qué hacer con la malla debajo

## 3.1 Opción recomendada

**No dejar la malla tal cual**.  
Solo con points rim, la “membrana” puede seguir asomando en interior. Recomendado atenuar interior mínimo con fade suave.

## 3.2 Fade interior mínimo (sin borde facetado)

En `realisticSurfaceFragmentShader`, sin `discard`:

- pasar `vMouthWeight` desde vertex.
- máscara interior pequeña:
  - `innerFadeMask = smoothstep(0.62 - f, 0.88 + f, vMouthWeight)`
  - `f = uMouthFeather` (inicial `0.10–0.16`)
- fade final:
  - `fade = uMouthOpenVisual * uMouthMeshFade * innerFadeMask`

Valores iniciales:
- `uMouthMeshFade = 0.42` (moderado, no agresivo)
- `uMouthFeather = 0.12`

Sin alpha a cero brusca, sin recorte binario. Así evitas triángulos/rombos en borde.

## 3.3 ¿Confiar en points para tapar malla?

No como estrategia única.  
Rim points + **fade interior mínimo** es la combinación más segura para eliminar membrana sin artefacto de corte.

---

## 4) Densidad y tamaño de points (solo rim)

## 4.1 Orden de magnitud esperado

En rim-only pequeño, según densidad base del mesh:
- esperado inicial: **120–380 points** (normalmente insuficiente en close-up).

Objetivo operativo:
- **300–650 points efectivos** en rim para continuidad aceptable.

## 4.2 Si densidad es baja

Orden recomendado:

1. Construir con vértices reales.  
2. Si `< 260` points, activar **duplicación estable 1x** en CPU al construir `mouthPointsGeo`:
   - duplicar cada punto con offset deterministic hash (`aBasePosition`),
   - amplitud pequeña: `0.0007–0.0015`.

Esto aumenta cobertura sin ruido temporal ni muestreo complejo.

## 4.3 Tamaño/alpha para no parecer “bolitas”

Inicial recomendado:

- size: `2.3 * dpr` (far) a `3.0 * dpr` (near)
- alpha global points: `0.44–0.56`
- alpha clip points: `0.010–0.016`
- soft edge: `circle = 1.0 - smoothstep(0.68, 1.0, r)`

Si se ven bolitas:
- subir size +0.2 dpr,
- bajar alpha ~0.04,
- subir clip +0.002.

---

## 5) Render/depth y seams (sin plate)

## 5.1 Render order recomendado

- `particleSurfaceMesh` (base realistic): `renderOrder = 2`
- `mouthPoints` (rim overlay): `renderOrder = 3`

## 5.2 Flags

- base mesh: `depthTest=true`, `depthWrite=true`
- mouthPoints: `depthTest=true`, `depthWrite=false`, `transparent=true`, `NormalBlending`

## 5.3 Evitar seams/halos

- evitar additive blending en points.
- usar alpha clip bajo para quitar borde lechoso.
- mantener transición de fade interior en malla (no abrupta).
- si seam brillante persiste: reducir `innerTiny` y subir `uMouthMeshFade` levemente (`+0.05`).

## 5.4 Z-fighting

Sin plate, el riesgo baja mucho.  
Si hay conflicto puntual por coplanaridad perceptual, aplicar un sesgo mínimo (ej. points size/alpha tuning antes de tocar polygonOffset).

---

## 6) Plan paso a paso (prototipo mínimo)

Archivo: `backend/avatar_app/app.js`

## 6.1 Estado y toggles

Añadir:
- `mouthPoints`, `mouthPointsMaterial`, `mouthOpenVisual`, `mouthPointsVisibleLatched`.
- URL params:
  - `debugMouthPoints=1`
  - `debugMouthFade=1`
  - `mouthPointsOnly=1`

## 6.2 Construcción de `mouthPointsGeo`

En rama `isRealisticTheme`, tras crear `realisticSurfaceGeo`:
1. leer `aMouthWeight/aMouthSide/aBasePosition`.
2. computar `rimMask/innerTiny` y filtrar por `mouthPointsMask > 0.08`.
3. opcional duplicación estable si conteo bajo.
4. crear `THREE.Points` con shader tipo dark simplificado.

## 6.3 Shaders

- Crear `mouthPointsVertexShader` y `mouthPointsFragmentShader` (base dark, sin ruido global innecesario).  
- Extender realistic shaders con `vMouthWeight` + fade interior (`uMouthOpenVisual`, `uMouthMeshFade`, `uMouthFeather`).

## 6.4 Runtime (`animate()`)

1. calcular `mouthOpenVisual` suavizado desde `AvatarState.talkLevel`.  
2. aplicar histéresis y toggle `mouthPoints.visible`.  
3. actualizar uniforms compartidos (`uTime`, `uTalk`, `uRestOpen`, etc.).  
4. actualizar fade interior en malla con `uMouthOpenVisual`.

Todo preconstruido: sin crear/destruir geometrías por frame.

---

## 7) Plan de pruebas y criterios de aceptación/fallo

## 7.1 Pruebas

1. **Micro-pausas**: 200–300ms open / 80–120ms close (20 ciclos).  
2. **Frontal + yaw/pitch**: yaw ±45°, pitch ±20°.  
3. **Primer plano**: comprobar continuidad rim y ausencia de bolitas.  
4. **Reposo**: points ocultos, malla normal restaurada sin popping.

## 7.2 Criterios de aceptación

- En habla, desaparece lectura de “membrana estirada” en centro.
- Borde de abertura se percibe orgánico (sprites), no facetado.
- Sin flicker de switch en micro-pausas.
- En reposo, vuelta limpia a realistic.

## 7.3 Criterios de descarte (esta dirección)

Descartar o pasar a variante con plate si ocurre persistentemente:
- centro demasiado “blanco plano”/poco profundo en la mayoría de ángulos,
- seam visible irresoluble entre rim points y malla,
- granulado inevitable en close-up aun con tuning razonable.

---

## Recomendación final de esta fase

Para decidir rápido si seguir o no:

1. Implementar rim switch mínimo + fade interior suave (sin plate, como pediste).  
2. Tunear 3 parámetros primero: `rimMask`, `uMouthMeshFade`, `uMouthPointsAlphaClip`.  
3. Evaluar con checklist.

Si pasa criterios de aceptación, seguir iterando aquí. Si no, el siguiente paso natural sería introducir cavidad oscura mínima (plate), pero eso queda fuera de esta fase por constraint.
