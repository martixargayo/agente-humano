# Aplicación idéntica en Comunicación — selector de mic/cámara como negociación (sin aplicar aún)

Este documento define **cómo replicar de forma 1:1** el patrón de negociación en Comunicación para cumplir el punto 3 solicitado, pero **sin aplicarlo aún en código**.

## Objetivo exacto
- Dos filas separadas en self-view:
  - Fila 1: icono micrófono (negro minimalista) + nombre dispositivo (font-weight 500) + flecha.
  - Fila 2: icono cámara (negro minimalista) + nombre dispositivo (font-weight 500) + flecha.
- Cada fila abre **su popover propio** (uno de mic, otro de cámara).
- Popover blanco flotante, redondeado, sombra suave, tamaño fijo.
- Lista simple de nombres, selección limpia, sin cajas internas extra.

---

## 1) Estructura objetivo en Comunicación (HTML)

Crear dos selectores hermanos, calcados al patrón de negociación:

```html
<div class="recording-device-selectors">
  <div id="recordingMicSelector" class="audio-device-selector">
    <!-- trigger y popover de micrófono (misma estructura que negociación) -->
  </div>

  <div id="recordingCamSelector" class="audio-device-selector">
    <!-- trigger y popover de cámara (misma estructura que negociación) -->
  </div>
</div>
```

### Reglas
1. Mantener `button` trigger + `div` popover por cada selector.
2. Cada trigger con `aria-controls` propio.
3. Cada popover con su lista de seleccionado + resto.
4. Texto del nombre del dispositivo con truncado (`ellipsis`) y `font-weight: 500`.

---

## 2) Estilo exacto a portar (CSS)

Portar literalmente estas piezas de negociación a Comunicación (con prefijo de namespace si se desea):
- `.audio-device-selector`
- `.audio-device-trigger`
- `.audio-device-trigger-main`
- `.audio-device-trigger-icon`
- `.audio-device-trigger-label`
- `.audio-device-trigger-chevron`
- `.audio-device-popover`
- `.audio-device-popover-list`
- `.audio-device-option`
- `.audio-device-option.active`
- `.audio-device-option-name`
- `.audio-device-empty`

### Ajustes mínimos permitidos
- Solo cambiar ancho fijo del popover para encajar en el dock de Comunicación.
- Mantener mismas curvas, sombras y ritmo espacial.
- Mantener paleta blanca limpia y hover suave.

---

## 3) Lógica exacta a portar (JS)

Duplicar el patrón de negociación en dos instancias:

1. **Mic selector state**:
   - `micPopoverOpen`
   - `micPopoverPollTimer`
   - `renderMicSelector()`
   - `openMicPopover()/closeMicPopover()/toggleMicPopover()`

2. **Cam selector state**:
   - `camPopoverOpen`
   - `camPopoverPollTimer`
   - `renderCamSelector()`
   - `openCamPopover()/closeCamPopover()/toggleCamPopover()`

3. **Eventos globales**:
   - click outside para cerrar cada popover.
   - `Escape` cierra ambos.

4. **Fuente de datos**:
   - mic usa `available_audio_devices` / `selected_audio_device_id`.
   - cam usa `available_video_devices` / `selected_video_device_id`.

5. **Selección**:
   - click opción => `handleDeviceChange('audio'|'video', deviceId)`.

6. **Permisos/estado vacío**:
   - si no hay permisos: botón “Activar permisos”.
   - si no hay dispositivos: mensaje vacío.

---

## 4) Checklist de “igual que negociación”

- [ ] Trigger visual idéntico (icono + label + chevron).
- [ ] Chevron rota al abrir.
- [ ] Popover flota sobre el trigger (no bloque incrustado).
- [ ] Fondo blanco + borde sutil + sombra doble suave.
- [ ] Opción activa con tintado azul y check.
- [ ] Cierre por click fuera y por Escape.
- [ ] Poll de refresco mientras popover abierto.
- [ ] Estados de permisos y vacío idénticos.

---

## 5) Estado de este documento

- Este diseño está **documentado** para implementación exacta posterior.
- No se aplica aquí por instrucción explícita del usuario (solo documentar el punto 3 en esta iteración).
