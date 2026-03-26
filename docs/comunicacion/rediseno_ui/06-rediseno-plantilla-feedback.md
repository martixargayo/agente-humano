# 06 · Rediseño de pantalla final/feedback (alineación fuerte con negociación)

## 1) Objetivo del doc
Definir la nueva arquitectura visual del feedback final de comunicación para acercarla a negociación, conservando lógica de datos actual y preparando puntos que aún requieren evolución de contrato.

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion_app/styles.css`
- `backend/comunicacion_app/index.html`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/interfaz_usuario_app/index.html`

## 3) Evidencia exacta encontrada en repo

### 3.1 Comunicación actual
- El report se arma desde `buildCommunicationReportSnapshotMarkup()`.
- Secciones actuales:
  - hero + video panel,
  - `block_cards`,
  - `timeline`,
  - `recommendations`.
- Clases principales: `.comm-report__header`, `.comm-report__hero-copy`, `.comm-report__video-panel`, `.comm-report__card`, `.comm-report__timeline`, `.comm-report__recommendations`.

### 3.2 Negociación actual (referencia)
- Report usa cards tipo dashboard: `.feedback-dashboard`, `.fb-card`, `.fb-header`, `.fb-score-pill`, `.fb-grid-cards`, `.fb-recommendations`.
- Incluye jerarquía clara de score/estrellas/resultado y color semántico por estado.

## 4) Diagnóstico del estado actual
- Comunicación tiene buena base estructural pero menor jerarquía visual.
- Falta una tarjeta hero de alto impacto equivalente a negociación.
- No hay apartados explícitos de entonación y gestos como bloques visuales diferenciados.

## 5) Referencia visual/técnica exacta
- De negociación reutilizar:
  - Hero con score+estrellas (`fb-header`, `fb-score-pill`, stars).
  - Semántica de estado por color (ok/warn/bad).
  - Estructura de cards claras en grid.

## 6) Propuesta detallada de cómo debería quedar

### 6.1 Bloque superior (hero)
- Card superior equivalente a negociación con:
  - nombre del caso,
  - score,
  - estrellas,
  - resumen ultra corto del resultado.

### 6.2 Resumen inmediato (debajo del hero)
- 1-2 frases:
  - por qué obtuvo esa nota,
  - qué hizo bien,
  - qué mejorar primero.

### 6.3 Técnica AIDA (2x2)
- Cuatro cards en grid:
  - Atención,
  - Interés,
  - Desarrollo,
  - Acción.
- Semántica de color:
  - verde / amarillo / rojo.
- Cada card con checklist de criterios (ticks/cruces).

### 6.4 Entonación
- Bloque dedicado con visual estilizada de barras/ondas.
- Escala propuesta: 1–5.
- Texto corto explicando ritmo, pausas, variación de intensidad.

### 6.5 Gestos
- Bloque dedicado con iconografía de expresividad.
- Score + explicación breve.
- Preparado para datos actuales aunque todavía haya gaps de contrato.

## 7) Layout detallado
- Orden vertical recomendado:
  1. Hero score/estrellas.
  2. Resumen inmediato.
  3. AIDA 2x2.
  4. Entonación.
  5. Gestos.
  6. Recomendaciones accionables.
- Mantener fondo blanco y cards blancas con bordes suaves.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `buildCommunicationReportSnapshotMarkup()` | `backend/comunicacion_app/report_view.js` | Adaptar | ya centraliza render | nueva plantilla por secciones |
| `.comm-report__*` namespace | `backend/comunicacion_app/styles.css` | Adaptar | evita colisiones CSS | estilo renovado |
| `fb-header` / `fb-score-pill` patrón | `backend/interfaz_usuario_app/feedback_report_view.js` | Adaptar | referencia visual solicitada | hero comunicación |
| `block_cards` actuales | `backend/comunicacion_app/report_view.js` | Adaptar | base para AIDA evaluada | grid 2x2 semáforo |
| timeline actual | `backend/comunicacion_app/report_view.js` | Reubicar/Adaptar | mantener valor pero menor prioridad | sección secundaria |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/report_view.js` | orden y markup de secciones | rutas export html/png/json | estructura plana actual | hero estilo negociación + AIDA + entonación + gestos | Medio |
| `backend/comunicacion_app/styles.css` | bloque `.comm-report*` | base de tipografía | jerarquía visual actual plana | sistema de cards/estados semáforo | Medio |
| `backend/comunicacion_app/index.html` | contenedor reporte/acciones | root de render `reportPlaceholderRoot` | acciones mal posicionadas (si aplica) | framing visual equivalente a negociación | Bajo |

## 10) Riesgos o puntos delicados
- Entonación/gestos pueden no tener aún métricas perfectas; diseñar fallback visual honesto.
- Mantener compatibilidad de snapshot y serialización HTML.
- Evitar que la nueva presentación “prometa” granularidad que el contrato aún no entrega.

## 11) Criterio de aceptación visual/UX
- Al abrir feedback, la jerarquía visual recuerda claramente a negociación.
- El usuario entiende en menos de 10 segundos: nota, motivo, AIDA, entonación, gestos.
- El diseño soporta evolución de contrato sin rehacer estructura de pantalla.
