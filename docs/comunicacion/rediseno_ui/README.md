# Rediseño UI Comunicación · Base documental ampliada (fase de precisión)

## 1) Alcance de esta fase
Este paquete deja preparada la implementación futura pantalla por pantalla, sin tocar runtime UI ni lógica core en este paso.

Incluye:
- diseño UX detallado de permisos, AIDA, grabación, post-grabación, loading y feedback,
- trazabilidad a ids/clases/handlers/estados reales,
- análisis técnico de parpadeos,
- análisis de aislamiento/concurrencia multiusuario.

## 2) Documentos disponibles
1. `01-referencia-negociacion-permisos-y-entrada.md`
2. `02-pantalla-instrucciones-y-brain-map.md`
3. `03-pantalla-de-grabacion-redisenada.md`
4. `04-flujo-ux-y-pasos-antiintuitivos.md`
5. `05-pantalla-de-carga-identica-a-negociacion.md`
6. `06-rediseno-plantilla-feedback.md`
7. `07-analisis-parpadeos-preview-y-captura.md`
8. `08-aislamiento-de-sesiones-y-concurrencia.md`

## 3) Dependencias entre cambios (UX + técnico)

### 3.1 Dependencias de pantallas
- Setup AV (doc 01) debe existir antes de AIDA (doc 02).
- AIDA (doc 02) alimenta grabación (doc 03).
- Flujo global y CTA único (doc 04) condiciona review y submit.
- Loading parity (doc 05) depende de submit/evaluation ya activos.
- Feedback final (doc 06) depende de contrato de datos disponible en report.

### 3.2 Dependencias técnicas invisibles para usuario
- Flicker (doc 07) debe resolverse antes o junto a rediseño de grabación para evitar degradación UX.
- Concurrencia/aislamiento (doc 08) debe revisarse antes de rollout multiusuario en producción.

## 4) Orden recomendado de implementación futura

### Fase A · Estructura UX base
1. Pantalla única de permisos AV (eliminar portada/preview explícita).
2. Paso intermedio AIDA editable.
3. Reordenar wizard y navegación (`Atrás` / `Continuar`).

### Fase B · Grabación robusta
4. Rediseño de recording (AIDA visible + self-view + indicadores AV + gestión dispositivos moderna).
5. Corrección de flicker/rerender agresivo.

### Fase C · Cierre y resultados
6. Review simplificada con CTA único `Enviar y evaluar`.
7. Port literal de loading de negociación.
8. Rediseño de feedback final alineado con negociación.

### Fase D · Hardening backend
9. Revisión de concurrencia/aislamiento (locks/idempotencia/storage compartido si aplica).

## 5) Qué está listo para pasar a implementación
- Definición detallada de las 6 pantallas objetivo (incluido flujo completo).
- Inventario de piezas reutilizables de negociación/interfaz_usuario.
- Inventario de piezas a eliminar/adaptar en comunicación.
- Análisis de riesgos UX/técnicos por archivo.

## 6) Gaps que dependen de contrato de datos
- Feedback de entonación/gestos y semáforo AIDA fino puede requerir ampliar/normalizar payloads del report.
- Visualización avanzada (barras/ondas “narrativas”) puede necesitar campos derivados adicionales.

## 7) Nota de trazabilidad
Durante la inspección se usó como base el código real de:
- `backend/comunicacion_app/*`
- `backend/interfaz_usuario_app/*`
- `backend/comunicacion/services/*`, `storage/*`
- `backend/evaluacion/engine/communication_*`
- `backend/sessions/*`
