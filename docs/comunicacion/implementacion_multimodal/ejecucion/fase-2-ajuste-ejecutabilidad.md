# Fase 2 — ajuste de ejecutabilidad en entorno real

## 1) Problema real detectado
La implementación inicial de Fase 2 introdujo `numpy` en:
- `backend/evaluacion/engine/communication_audio_metrics.py`
- `backend/tests/test_communication_phase2_audio_metrics_and_delivery.py`

En este repositorio/entorno, `numpy` no estaba instalado ni declarado en dependencias del proyecto, provocando fallos de colección/import en pytest:
- `ModuleNotFoundError: No module named 'numpy'`

## 2) Decisión tomada
**Opción B**: eliminar dependencia de `numpy`.

## 3) Por qué se eligió B
- El archivo de dependencias del repo (`backend/requirements.txt`) no declara `numpy`.
- No hay uso previo de `numpy` en el resto del código de backend fuera de los archivos recién añadidos de Fase 2.
- Para mantener la fase ejecutable en este entorno sin introducir dependencias científicas nuevas, se priorizó implementación con librería estándar.

## 4) Archivos tocados
- `backend/evaluacion/engine/communication_audio_metrics.py`
- `backend/tests/test_communication_phase2_audio_metrics_and_delivery.py`
- `docs/comunicacion/implementacion_multimodal/ejecucion/fase-2-ajuste-ejecutabilidad.md`

## 5) Cambios exactos
- Reescritura de extracción acústica para operar con Python estándar:
  - lectura PCM WAV con `wave` + `struct.iter_unpack`
  - RMS por frame con listas y `math.sqrt`
  - detección de pausas por umbral dinámico sobre secuencias
  - estimación de pitch por autocorrelación con bucles (sin `numpy.correlate`)
  - estadísticos con `statistics` (`fmean`, `median`, `pstdev`)
  - voiced ratio y clipping ratio calculados con contadores/list comprehensions
- Reescritura del test de Fase 2 para generar señal sintética sin `numpy`:
  - síntesis de tonos con `math.sin`
  - PCM con `array('h')`
  - fixtures de RMS como lista de `float`.

## 6) Estado de `numpy`
`numpy` fue **eliminado de la implementación de Fase 2** (código y test). No se añadió como dependencia del proyecto.

## 7) Métricas que quedan operativas
Se mantienen operativas en Fase 2:
- `pause_events`
- `speech_rate_wpm`
- `speaking_time_ms`
- `pause_time_ms`
- `pause_ratio`
- `pause_mean_ms`
- `pause_max_ms`
- `long_pauses_count`
- `pitch_stats` (estimación por autocorrelación)
- `energy_stats` (RMS stats)
- `voiced_ratio`
- `quality_flags` (incluye clipping, low voiced ratio, speech rate unavailable, etc.)

## 8) Tests en verde
Ejecuciones verificadas en este ajuste:
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q`
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
