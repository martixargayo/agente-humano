# 02 · Pantalla intermedia nueva: información + AIDA

## 1) Objetivo del doc
Definir con precisión la pantalla nueva (hoy inexistente) que aparece tras permisos y antes de grabar, con:
- título,
- texto descriptivo configurable,
- cuatro recuadros AIDA editables,
- persistencia/reutilización del contenido para la pantalla de grabación.

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/feedback_report_view.js`

## 3) Evidencia exacta encontrada en repo
- En `comunicacion` no existe pantalla entre permisos y grabación; hoy la transición pasa por `SCREEN_PREVIEW` y luego `SCREEN_RECORDING`.
- `comunicacion` ya trae `state.context.activity_brief` y lo pinta en UI (`activityTitle`, `introContextSummary`), por lo que hay fuente de texto para título/descripción.
- `renderApp()` ya centraliza rehidratación de UI por estado, por lo que es el punto natural para hidratar AIDA.
- En negociación/report se usan cards blancas con bordes suaves (`fb-card`) que sirven como referencia de jerarquía y respiración visual.

## 4) Diagnóstico del estado actual
- Falta fase de preparación cognitiva; el usuario entra a grabar sin guía.
- No hay estructura para convertir instrucciones del caso en guion operativo.
- El flujo actual prioriza mecánica técnica sobre calidad de mensaje.

## 5) Referencia visual/técnica exacta
- Referencia de estilo de cajas limpias: `fb-card` (`feedback_report_view.js`).
- Referencia de shell/espaciado comunicación: `communication-card` + `communication-panel`.
- Referencia de navegación simple: patrón de CTA principal/secondary ya existente (`btn-primary`, `btn-secondary`).

## 6) Propuesta detallada de cómo debería quedar

### 6.1 Nueva pantalla `screenAidaPrep`
- Bloque superior:
  - `h2`: título del paso,
  - `p`: descripción configurable (desde backend/contexto).
- Bloque principal:
  - grid 2x2 de cards AIDA:
    - Atención,
    - Interés,
    - Desarrollo,
    - Acción.
  - cada card incluye `textarea` libre.
- Navegación:
  - `Atrás` (vuelve a setup de permisos),
  - `Continuar` (avanza a grabación).

### 6.2 Persistencia propuesta en `app.js`
Agregar en `state`:
```text
brainmap: {
  attention: '',
  interest: '',
  development: '',
  action: '',
  updated_at: null,
}
```
- escritura por `input`/`change` listeners por textarea.
- rehidratación en `renderApp()` al entrar al paso y al paso de grabación.

## 7) Layout detallado
- Fondo global blanco.
- Card principal blanca.
- Encabezado textual arriba, AIDA debajo en 2 columnas x 2 filas.
- En mobile, colapsar a 1 columna.
- Botonera inferior fija del paso (`Atrás`, `Continuar`).

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `communication-card` | `backend/comunicacion_app/styles.css` | Reutilizar | Ya estructura shell | contenedor del paso AIDA |
| `btn-primary` / `btn-secondary` | `backend/comunicacion_app/styles.css` | Reutilizar | patrón CTA existente | navegación del wizard |
| `fb-card` estética | `backend/interfaz_usuario_app/feedback_report_view.js` | Adaptar | referencia visual blanca de negociación | cards AIDA |
| `SCREEN_PREVIEW` | `backend/comunicacion_app/app.js` | Descartar (UX) | paso técnico prescindible | sustituido por AIDA prep |
| `activity_brief` | `backend/comunicacion_app/app.js` | Reutilizar | ya trae título/descripcion | contenido superior del paso |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | insertar nueva sección entre setup y recording | estructura general de panels | preview como paso visible | `screenAidaPrep` + textareas AIDA | Bajo |
| `backend/comunicacion_app/app.js` | `state`, `SCREEN_ORDER`, `renderApp`, listeners | render centralizado | salto directo setup→recording | estado `brainmap` y handlers de persistencia | Medio |
| `backend/comunicacion_app/styles.css` | estilos de grid/cards/textareas | variables color útiles | contrastes grises fuertes | sistema blanco limpio AIDA | Bajo |

## 10) Riesgos o puntos delicados
- No convertir esta pantalla en formulario pesado.
- Mantener persistencia al navegar atrás/adelante sin perder texto.
- Asegurar accesibilidad en textareas (labels y foco).

## 11) Criterio de aceptación visual/UX
- El usuario entiende en segundos qué preparar antes de grabar.
- Los 4 bloques AIDA son visibles, editables y fáciles de escanear.
- El contenido se conserva y reaparece en grabación como guía.
