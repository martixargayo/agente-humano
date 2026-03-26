# 06 - Checklist de validación manual final (navegador/hardware real)

Fecha: 2026-03-26

> Objetivo: cerrar los puntos que no son totalmente confiables en entorno headless/CI (AV real, UX perceptual y embed real con parent host).

## A. Preparación de entorno
- [ ] Abrir `/comunicacion` en Chrome y Firefox actualizados.
- [ ] Repetir en modo incógnito (sin permisos previos).
- [ ] Probar en al menos 2 equipos (si es posible: webcam/micrófono distintos).

## B. Setup AV
- [ ] Botón principal de setup solicita permisos reales de cámara/micrófono.
- [ ] Si se niega permiso, se muestra error recuperable.
- [ ] Si se acepta permiso, preview en `setupPreviewVideo` se activa.
- [ ] Selectores de cámara/micrófono listan dispositivos reales.
- [ ] Cambiar dispositivo actualiza preview sin congelamiento.

## C. AIDA
- [ ] La pantalla AIDA aparece después de setup.
- [ ] Campos Atención/Interés/Desarrollo/Acción aceptan texto.
- [ ] Navegación Atrás/Continuar conserva estado esperado.

## D. Recording
- [ ] Al entrar en recording, self-view activo.
- [ ] Botón `Grabar` inicia captura y oculta/inhabilita estados incompatibles.
- [ ] Botón `Detener` aparece solo durante grabación.
- [ ] Indicador de tiempo y waveform reaccionan al audio real.
- [ ] Panel Gestionar AV permite cambiar dispositivos y refleja estado.

## E. Review
- [ ] Vídeo grabado se reproduce en `reviewVideo`.
- [ ] Duración/tamaño muestran datos coherentes.
- [ ] `Volver a grabar` reinicia correctamente el intento local.
- [ ] `Enviar y evaluar` dispara flujo sin bloqueo.

## F. Loading / Report / Error
- [ ] Al enviar, aparece loading full-screen (`communicationLoadingScreen`).
- [ ] No aparece pantalla intermedia visible de `screenUploading`.
- [ ] Al completar evaluación, se ve report full-screen (`communicationReportScreen`).
- [ ] Si falla backend, pantalla de error full-screen (`communicationErrorScreen`) permite volver.

## G. final_result / embed (si aplica)
- [ ] En modo embebido con `parent_origin`, se emiten `final_result_available` y `final_result`.
- [ ] Parent responde `final_result_saved` y UI muestra toast de confirmación.
- [ ] ACK de origen no autorizado se ignora.

## H. Export interno
- [ ] Desde consola o harness interno, `exportReportJson/Html/Png` funcionan con report cargado.
- [ ] Verificar que no hay botones manuales legacy visibles en UI final.

## I. UX perceptual / flicker
- [ ] Sin parpadeos notorios al pasar setup->AIDA->recording->review.
- [ ] Sin “flash” de vistas intermedias al transicionar review->loading->report.
- [ ] El toast final no tapa controles críticos ni se queda pegado.

## J. Evidencia a capturar manualmente
- [ ] Video corto de flujo completo (setup a report).
- [ ] Capturas de: setup, recording, loading, report, toast final.
- [ ] Logs de consola de eventos embed si aplica.

## Artefactos automáticos relacionados
- `docs/comunicacion/validacion/artifacts/pytest_regresion_comunicacion_2026-03-26.txt`
- `docs/comunicacion/validacion/artifacts/pytest_repositorio_comunicacion_2026-03-26.txt`
- `docs/comunicacion/validacion/artifacts/ui_regression_contract_checks_2026-03-26.json`
