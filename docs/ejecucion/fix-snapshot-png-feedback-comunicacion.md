# Fix aplicado: snapshot PNG fiel del feedback de comunicación

## 1) Resumen del problema

El simulador enviaba `snapshot_png_dataurl` como una miniatura sintética (canvas con título/score/recomendaciones), por lo que el PNG persistido en Moodle no coincidía con el feedback real renderizado en `simulador.gestionce.com`.

## 2) Causa raíz ya demostrada

La función `captureCommunicationReportPngDataUrl(...)` de `backend/comunicacion_app/report_view.js` usaba una única ruta de canvas manual 1200x720 y no capturaba el DOM real del reporte (`.comm-report-v3`).

## 3) Flujo antiguo de captura

1. `buildCommunicationFinalResultPayload(...)` pedía snapshot con `captureCommunicationReportPngDataUrl(...)`.
2. Esa función dibujaba una composición sintética en canvas.
3. Se enviaba ese PNG simplificado en `final_result.snapshot_png_dataurl`.

## 4) Flujo nuevo tras el fix

### Happy path (nuevo principal)

`captureCommunicationReportPngDataUrl(...)` ahora:

1. intenta `captureCommunicationReportPngDataUrlFromDom(...)` como estrategia principal,
2. resuelve root real (`options.rootElement` conectado y con `[data-report-root="true"]`),
3. si no hay root visible, monta uno detached fuera de pantalla renderizando el mismo markup real (`renderCommunicationReport`),
4. espera estabilidad mínima (fuentes + RAF + settle delay),
5. clona DOM real y lo rasteriza con SVG/`foreignObject` + canvas,
6. devuelve PNG data URL resultante.

### Fallback (mantenido)

Si falla la captura DOM real, cae a `buildCommunicationReportSyntheticFallbackPngDataUrl(...)` (la miniatura sintética anterior) para no romper entrega de `final_result`.

## 5) Archivo/s modificados

- `backend/comunicacion_app/report_view.js`
  - nueva ruta principal DOM capture
  - fallback sintético explícito separado
  - helpers de estabilidad, dimensiones y estilos para rasterización
- `backend/evaluacion/engine/communication_report_assembler.py`
  - texto de `placeholders.snapshot_png` actualizado para reflejar captura en cliente + fallback
- `backend/tests/test_communication_report_renderer.py`
  - markers ajustados a API/funciones actuales
- `backend/tests/test_communication_snapshot_capture_path.py` (nuevo)
  - prueba que happy path usa captura DOM primaria
  - prueba que fallback entra cuando DOM capture falla

## 6) Fallback mantenido

Se mantiene fallback sintético por resiliencia operacional (entornos donde SVG/foreignObject/canvas pueda fallar), pero ya no es la ruta principal.

## 7) Tests ejecutados

- `python -m pytest backend/tests/test_communication_snapshot_capture_path.py -q`
- `python -m pytest backend/tests/test_communication_report_renderer.py -q`
- `python -m pytest backend/tests/test_comunicacion_embed_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_snapshot_pipeline_validation.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`

## 8) Limitaciones o riesgos residuales

- La captura DOM usa `foreignObject`; en algunos runtimes de navegador restringidos puede fallar y activar fallback.
- El snapshot puede depender de la carga de estilos/fuentes disponibles en runtime; se añadió espera mínima de estabilidad, pero no garantía absoluta ante CSP/extensiones agresivas.

## 9) Veredicto final

El `snapshot_png_dataurl` de comunicación ahora toma como ruta principal una captura del DOM real del feedback renderizado. Esto corrige la causa del PNG simplificado en happy path y conserva fallback para no romper el pipeline de entrega.
