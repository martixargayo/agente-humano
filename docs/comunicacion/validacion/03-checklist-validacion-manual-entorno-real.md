# Checklist manual final · Entorno real (navegador + hardware)

Fecha: 2026-03-26 (UTC)

> Este checklist cubre lo que no se puede cerrar al 100% con `testclient` (cámara/mic/permisos, UX visual percibida, flicker real).

## A. Setup AV / permisos
- [ ] Entrar a `/comunicacion/<slug>` y verificar pantalla setup visible.
- [ ] Caso sin permisos: mostrar mensaje de activación AV.
- [ ] Conceder permisos y verificar transición a estado listo.
- [ ] Denegar permisos y verificar mensaje claro de bloqueo.
- [ ] Verificar listado de cámaras/micrófonos y refresco.

## B. AIDA
- [ ] Completar 4 campos AIDA.
- [ ] Navegar a recording y comprobar persistencia de contenido.
- [ ] Volver atrás y confirmar que no se pierde contenido.

## C. Recording (Fase 2)
- [ ] Ver self-view lateral (no layout antiguo full-video principal).
- [ ] Ver badges de mic/cámara vivos.
- [ ] Ver waveform/medidor reaccionando al audio real.
- [ ] Abrir panel “Gestionar micrófono y cámara”.
- [ ] Cambiar micrófono/cámara con stream activo.
- [ ] Intentar cambiar durante grabación y validar comportamiento seguro (mensaje explícito).
- [ ] Grabar clip corto y clip largo (>2 min).
- [ ] Confirmar mitigación de flicker percibida durante grabación continua.

## D. Review y submit
- [ ] Ver review con duración y tamaño correctos.
- [ ] Confirmar ausencia de MIME/ref técnica visible al usuario.
- [ ] Probar “Volver a grabar”.
- [ ] Probar “Enviar y evaluar”.

## E. Loading parity (Fase 3)
- [ ] Confirmar nueva loading visual (shimmer + floating + stage pill).
- [ ] Confirmar que no se muestran `evaluation_id/status/stage` técnicos.
- [ ] Validar transición automática a report al completar evaluación.

## F. Feedback final (Fase 3)
- [ ] Ver hero con score y estrellas.
- [ ] Ver resumen inmediato.
- [ ] Ver bloque AIDA 2x2.
- [ ] Ver bloque entonación (barras/valoración).
- [ ] Ver bloque gestos/presencia.
- [ ] Ver recomendaciones.
- [ ] Probar export JSON/HTML/PNG.
- [ ] Probar “Entregar resultado final” (embed/final_result).

## G. Concurrencia básica
- [ ] Abrir dos navegadores/sesiones distintas en paralelo y ejecutar flujo completo.
- [ ] Confirmar aislamiento de resultados.
- [ ] Simular doble submit rápido del mismo attempt (doble click/script) y verificar que no crea evaluaciones duplicadas.

## Evidencias recomendadas a adjuntar
- Capturas por fase (setup, recording, loading, report).
- Video corto de la grabación mostrando waveform y panel AV.
- Logs del backend para submit/polling/report.
- IDs de attempt/evaluation por sesión en escenario de concurrencia.
