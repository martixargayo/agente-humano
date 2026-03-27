# Análisis de rediseño — pantalla de grabación (estética minimalista, misma línea visual)

## Objetivo
Definir **cómo rediseñar** la pantalla de grabación de Comunicación manteniendo la misma línea estética minimalista (tipo OpenAI):
- bloque de video + ondas + estado AV en un lateral inferior,
- 4 recuadros AIDA (Atención, Interés, Desarrollo, Acción) como foco principal en el centro,
- reuso del sistema actual de micrófono/cámara/ondas sin reescribir la lógica core.

> Este documento es de análisis y diseño técnico. No aplica cambios de código.

---

## 1) Qué ya tenemos (base reutilizable)

### 1.1 Estructura actual de grabación
La pantalla actual ya separa un bloque central (`recording-main`) y un lateral (`recording-side`) dentro de `recording-layout`. Esto encaja bien con la idea de “AIDA al centro + AV a un lado”.

- Centro: `recording-aida-grid` con 4 tarjetas AIDA.
- Lateral: `recording-preview-stack` + `recording-waveform` + `recording-av-control-row`.

Esto permite rediseñar casi todo con CSS y microajustes de jerarquía visual, sin romper la arquitectura funcional.

### 1.2 Lógica actual que conviene conservar
Hay tres piezas robustas que no hace falta rehacer:
1. **Estado de salud AV** (`refreshCaptureHealthIndicators`) → badges mic/cam con `ok/ko/missing`.
2. **Waveform** (`ensureWaveformBars`, `renderWaveform`, `startAudioMonitoring`) → barras dinámicas por RMS.
3. **Gestión de panel AV** (`manageAvBtn` + `renderApp`) → toggle del panel y `aria-expanded`.

Conclusión: el rediseño puede ser **presentacional** (HTML/CSS y orden visual), reusando la capa JS actual.

---

## 2) Dirección estética exacta (línea minimalista)

Para que quede consistente con una estética minimalista:

- **Menos bloques “encerrados”**: reducir bordes fuertes duplicados.
- **Más aire (spacing)**: aumentar padding vertical/horizontal en contenedor principal.
- **Contraste moderado**: superficies neutras, un solo color de acento (azul) para estado activo/acción.
- **Tipografía limpia y jerarquía clara**: títulos pequeños en mayúscula suave o semibold, cuerpo ligero.
- **Microfeedback discreto**: transiciones cortas y estados de hover suaves, sin sombras pesadas.

---

## 3) Layout propuesto (AIDA centro + AV lateral inferior)

## 3.1 Wireframe lógico

```text
┌──────────────────────────────────────────────────────────────┐
│                    Pantalla de grabación                    │
│                                                              │
│   ┌──────────────────────────────┐   ┌────────────────────┐  │
│   │        AIDA (foco)           │   │   Self-view        │  │
│   │  [Atención]   [Interés]      │   │   (video)          │  │
│   │  [Desarrollo] [Acción]       │   │   Ondas audio      │  │
│   │                              │   │   Mic/Cam badges   │  │
│   └──────────────────────────────┘   │   [Gestionar]       │  │
│                                      └────────────────────┘  │
│   [Indicador tiempo] [Grabar/Detener] [Atrás]                │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Decisión de composición
- Mantener `recording-layout` con 2 columnas.
- Dar **más ancho visual al centro** (AIDA) y comprimir el lateral AV.
- Llevar el lateral AV a una composición “apilada” (video → ondas → badges → botón).
- Mover la barra de acciones (`recording-action-row`) para que quede alineada al borde inferior del bloque lateral o en una fila global inferior (según pruebas UX).

---

## 4) Propuesta de cambios por capa

## 4.1 HTML (mínimos, sin rehacer JS)

### Qué mantener
- IDs críticos para JS: `recordingVideo`, `recordingWaveform`, `recordingMicBadge`, `recordingCamBadge`, `manageAvBtn`, `avDevicePanel`, `recordingVideoDeviceList`, `recordingAudioDeviceList`.

### Qué mover/reordenar (si se decide)
- Reordenar dentro de `recording-side` para priorizar:
  1) Video,
  2) Ondas,
  3) Badges,
  4) Gestión,
  5) Botones de grabación.

Conservando los IDs, la lógica actual seguirá funcionando.

## 4.2 CSS (donde está el grueso del rediseño)

### Bloques principales a retocar
1. `.recording-layout`
   - Ajustar proporción: columna principal más dominante.
   - Ejemplo conceptual: `grid-template-columns: minmax(0, 1.9fr) minmax(260px, 0.7fr);`

2. `.recording-main` + `.recording-aida-grid` + `.recording-aida-card`
   - Reducir ruido visual (bordes más suaves, fondo casi plano).
   - Mejorar legibilidad del texto AIDA (line-height y padding consistente).

3. `.recording-side` + `.video-shell--recording-side` + `.video-frame--selfview`
   - Unificar radios y bordes para look limpio.
   - Video con proporción estable y recorte elegante.

4. `.recording-waveform` + `.recording-waveform__bar`
   - Mantener motor actual, afinar look:
     - barras un poco más delgadas,
     - mayor separación respirable,
     - activo con azul del sistema.

5. `.recording-av-unified` + `.recording-av-item` + `.status-badge--*`
   - Convertir badges en “chips de estado” más livianos.
   - Colores de éxito/error menos saturados.

6. `@media (max-width: 720px)`
   - Asegurar orden mobile: AIDA arriba, AV abajo.
   - Confirmar que no se rompa `manageAvBtn` ni panel de dispositivos.

## 4.3 JS (ajustes opcionales, no estructurales)

No es necesario tocar la lógica base. Solo opcionales:
- Ajustar `WAVEFORM_BAR_COUNT` si visualmente se requiere menos densidad.
- Afinar factor de amplificación (`rms * 3.2`) para que la onda sea más estable visualmente.

Ambos son parámetros, no cambios de arquitectura.

---

## 5) Estrategia de implementación recomendada (en fases)

### Fase 1 — Solo CSS
- Redefinir layout y jerarquía visual sin mover HTML.
- Validar que no se rompe ningún handler ni estado.

### Fase 2 — Reordenado leve de HTML
- Si hace falta, reorganizar nodos dentro de `recording-side` manteniendo IDs.
- Sin cambiar nombres de elementos usados por JS.

### Fase 3 — Afinado de onda/estados
- Ajuste fino de densidad de barras y tonos de badges.
- QA con micrófono real (silencio, voz baja, voz alta).

### Fase 4 — Hardening responsive
- Revisión completa desktop/tablet/mobile.
- Validar accesibilidad (`aria-expanded`, foco de botón, contraste).

---

## 6) Riesgos y cómo mitigarlos

1. **Riesgo**: perder acoplamiento con JS por renombrar IDs.
   - **Mitigación**: no cambiar IDs, solo clases/layout.

2. **Riesgo**: waveform demasiado “nerviosa” visualmente.
   - **Mitigación**: ajustar suavizado visual en CSS o factor RMS.

3. **Riesgo**: panel AV incómodo en móvil.
   - **Mitigación**: media query con stacking simple y botón Gestionar visible.

4. **Riesgo**: sobrecargar la UI con demasiados contenedores.
   - **Mitigación**: eliminar doble borde y dejar solo una capa de superficie por bloque.

---

## 7) Checklist de ejecución (cuando se implemente)

- [ ] AIDA queda centrado y dominante visualmente.
- [ ] Bloque AV queda lateral/inferior, compacto y claro.
- [ ] Ondas siguen animando en tiempo real.
- [ ] Badges de cámara/micrófono siguen reflejando `ok/ko`.
- [ ] Botón Gestionar abre/cierra panel AV correctamente.
- [ ] Diseño responsive mantiene orden lógico.
- [ ] Sin regresión funcional en grabar/detener/reintentar.

---

## 8) Resumen ejecutivo
Sí se puede llevar la pantalla de grabación a esa línea estética con bajo riesgo, porque la lógica actual ya está bien separada:
- **JS ya resuelve estado y comportamiento AV**.
- **El rediseño real está en composición/estilo (CSS + orden visual de HTML)**.
- **La disposición objetivo “AIDA al centro, AV al lado con video+ondas” ya existe como base y solo hay que refinarla**.

---

## 9) Ajuste exacto solicitado: “recuadro flotante abajo + AIDA sin recuadro”

Esta sección concreta exactamente la idea que pediste:
- un **único recuadro con sombra** (estilo `dev.inner.box`) ubicado abajo, que contenga todo el bloque de grabación AV;
- y **AIDA sin cajas**, como texto directamente sobre fondo blanco, visualmente prioritario.

### 9.1 Estructura visual final (composición)

```text
FONDO BLANCO TOTAL
┌──────────────────────────────────────────────────────────────┐
│  AIDA (sin cards, solo texto):                              │
│  Atención: ...                                               │
│  Interés: ...                                                │
│  Desarrollo: ...                                             │
│  Acción: ...                                                 │
│                                                              │
│                    [espacio respirable]                      │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  RECUADRO FLOTANTE CON SOMBRA (dock inferior)         │   │
│  │  [self-view] [ondas] [estado mic/cam] [gestionar]     │   │
│  │  [timer] [grabar/detener]                             │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 9.2 Regla de jerarquía visual
1. **AIDA manda**: texto grande/limpio, sin contenedor, sin borde.
2. **AV acompaña**: dock flotante inferior, compacto, con una sola sombra elegante.
3. **Evitar doble-caja**: no anidar tarjetas fuertes dentro del dock; solo sub-bloques suaves.

### 9.3 Implementación HTML (sin romper JS)

Mantener IDs actuales, pero envolver lateral AV y controles en un único contenedor “dock”:

- Nuevo wrapper conceptual: `recording-floating-dock`.
- Dentro: `recording-preview-stack`, `recording-waveform`, badges AV, `manageAvBtn`, botones grabar/detener.
- AIDA se renderiza en `recording-main` sin cards (`recording-aida-card` se convierte en texto plano con títulos).

**Importante**: no renombrar IDs usados por JS (`recordingVideo`, `recordingWaveform`, `recordingMicBadge`, `recordingCamBadge`, `manageAvBtn`, etc.).

### 9.4 Implementación CSS (núcleo del efecto “medio flotante”)

#### A) Fondo limpio y AIDA sin recuadro
- Quitar borde/fondo de `recording-main`.
- Eliminar estilo de tarjeta en `.recording-aida-card` y pasar a bloques de texto.
- Subir jerarquía tipográfica (`h4` más claro, cuerpo con mejor interlineado).

#### B) Dock inferior flotante
Crear clase dedicada (ejemplo conceptual):

```css
.recording-floating-dock {
  position: sticky;
  bottom: 18px;
  margin-top: 28px;
  border: 1px solid #e8edf3;
  border-radius: 16px;
  background: #ffffff;
  box-shadow:
    0 10px 30px rgba(15, 23, 42, 0.10),
    0 2px 10px rgba(15, 23, 42, 0.06);
  padding: 12px;
}
```

Notas:
- Si `sticky` no convence, usar layout normal con `margin-top: auto` para empujarlo abajo.
- La sombra debe ser suave, no dramática, para mantener estética minimalista.

#### C) Subbloques dentro del dock
- `video-shell--recording-side`: borde más sutil.
- `recording-waveform`: más fino y limpio.
- `recording-av-unified`: chips neutrales, colores de estado contenidos.
- `btn-secondary` de Gestionar: estilo ghost/sutil para no competir con Grabar.

### 9.5 Fases concretas para este ajuste
1. **Fase visual AIDA**: quitar cards y dejar texto plano en `recording-main`.
2. **Fase dock**: crear wrapper único con sombra y mover dentro todo AV.
3. **Fase pulido**: compactar spacing, afinar sombra y tamaño de video.
4. **Fase responsive**: en móvil, dock pasa debajo de AIDA, siempre visible y compacto.

### 9.6 Criterio de éxito (aceptación)
- Se percibe claramente:
  - **contenido importante arriba sin caja** (AIDA sobre fondo blanco),
  - **bloque de acción abajo con sombra flotante** (video+ondas+AV+acciones).
- Funcionalidad intacta:
  - ondas animan igual,
  - badges mic/cam actualizan estado,
  - botón Gestionar abre/cierra panel AV,
  - grabar/detener funciona sin regresión.
