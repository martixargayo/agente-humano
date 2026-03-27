# Extracción exacta — selector flotante de dispositivos (negociación / inner.box)

Este documento contiene la extracción **literal** (HTML + CSS + JS) del selector flotante de dispositivos usado en negociación (`interfaz_usuario_app`), para usarlo como base fiel.

## 1) HTML exacto (negociación)
Fuente: `backend/interfaz_usuario_app/index.html`.

```html
<div id="audioDeviceSelector" class="audio-device-selector">
  <button
    id="audioDeviceTrigger"
    class="audio-device-trigger"
    type="button"
    aria-haspopup="dialog"
    aria-expanded="false"
    aria-controls="audioDevicePopover"
    aria-label="Seleccionar micrófono"
  >
    <span class="audio-device-trigger-main">
      <span class="audio-device-trigger-icon" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3.5 8.5V7.5C3.5 5.01472 5.51472 3 8 3C10.4853 3 12.5 5.01472 12.5 7.5V8.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          <path d="M4.5 8.5H3.5C2.94772 8.5 2.5 8.94772 2.5 9.5V10.5C2.5 11.0523 2.94772 11.5 3.5 11.5H5V8.5H4.5Z" fill="currentColor"/>
          <path d="M11.5 8.5H12.5C13.0523 8.5 13.5 8.94772 13.5 9.5V10.5C13.5 11.0523 13.0523 11.5 12.5 11.5H11V8.5H11.5Z" fill="currentColor"/>
          <path d="M5 11.5V12C5 12.8284 5.67157 13.5 6.5 13.5H9.5C10.3284 13.5 11 12.8284 11 12V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        </svg>
      </span>
      <span id="audioDeviceTriggerLabel" class="audio-device-trigger-label">Micrófono</span>
    </span>
    <span class="audio-device-trigger-chevron" aria-hidden="true">▾</span>
  </button>
  <div id="audioDevicePopover" class="audio-device-popover" role="dialog" aria-label="Dispositivos de audio">
    <div id="audioDeviceSelectedList" class="audio-device-popover-list"></div>
    <div id="audioDevicePopoverDivider" class="audio-device-popover-divider" hidden></div>
    <div id="audioDeviceOtherList" class="audio-device-popover-list"></div>
    <div class="audio-device-footer" aria-live="polite">
      <span>Buscando dispositivos…</span>
      <span class="audio-device-footer-spinner" aria-hidden="true"></span>
    </div>
  </div>
</div>
```

## 2) CSS exacto (negociación)
Fuente: `backend/interfaz_usuario_app/index.html` (bloque `<style>`).

```css
.audio-device-selector {
  position: relative;
  min-width: 0;
}

.audio-device-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: #111827;
  padding: 4px 0 4px 8px;
  cursor: pointer;
}

.audio-device-trigger:focus-visible {
  outline: 2px solid rgba(59, 130, 246, 0.38);
  outline-offset: 2px;
}

.audio-device-trigger-main {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.audio-device-trigger-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #111827;
  flex: 0 0 auto;
}

.audio-device-trigger-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
}

.audio-device-trigger-label.muted {
  color: rgba(15, 23, 42, 0.56);
  font-weight: 400;
}

.audio-device-trigger-chevron {
  flex: 0 0 auto;
  color: #111827;
  font-size: 12px;
  transition: transform 0.18s ease;
}

.audio-device-selector.open .audio-device-trigger-chevron {
  transform: rotate(180deg);
}

.audio-device-popover {
  position: absolute;
  right: 0;
  bottom: calc(100% + 10px);
  width: min(340px, 78vw);
  display: none;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 18px 40px rgba(15, 23, 42, 0.16),
    0 4px 12px rgba(15, 23, 42, 0.08);
  z-index: 8;
}

.audio-device-selector.open .audio-device-popover {
  display: flex;
}

.audio-device-popover-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audio-device-popover-divider {
  height: 1px;
  background: rgba(148, 163, 184, 0.28);
}

.audio-device-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: #ffffff;
  color: #111827;
  cursor: pointer;
  text-align: left;
}

.audio-device-option:hover {
  background: #f8fafc;
}

.audio-device-option.active {
  border-color: rgba(96, 165, 250, 0.72);
  background: #eff6ff;
  box-shadow: 0 0 0 1px rgba(147, 197, 253, 0.3);
}

.audio-device-option-main {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.audio-device-option-icon {
  color: #111827;
  opacity: 0.92;
}

.audio-device-option-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.audio-device-option-check {
  color: #2563eb;
  opacity: 0;
}

.audio-device-option.active .audio-device-option-check {
  opacity: 1;
}

.audio-device-empty {
  padding: 12px;
  border-radius: 14px;
  border: 1px dashed rgba(15, 23, 42, 0.16);
  color: rgba(15, 23, 42, 0.62);
  font-size: 13px;
  line-height: 1.4;
}

.audio-device-empty-actions {
  margin-top: 10px;
}

.audio-device-inline-action {
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: #ffffff;
  color: #111827;
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.audio-device-inline-action:hover {
  background: #f8fafc;
}

.audio-device-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  color: rgba(15, 23, 42, 0.62);
  font-size: 12px;
}

.audio-device-footer-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid rgba(148, 163, 184, 0.45);
  border-top-color: rgba(100, 116, 139, 0.9);
  animation: entrySpin 1s linear infinite;
  flex: 0 0 auto;
}
```

## 3) JS exacto (negociación)
Fuente: `backend/interfaz_usuario_app/app.js`.

```js
function getAudioDeviceTriggerText() {
  if (entryPermissionStatus === 'denied') {
    return { text: 'Permiso de micrófono bloqueado', muted: true };
  }
  if (entryPermissionStatus === 'prompt' || entryPermissionStatus === 'unknown') {
    return { text: 'Activar micrófono', muted: true };
  }
  const selected = availableInputDevices.find((device) => device.deviceId === selectedEntryDeviceId);
  if (selected) return { text: selected.cleanLabel, muted: false };
  if (availableInputDevices.length) return { text: availableInputDevices[0].cleanLabel, muted: false };
  return { text: 'Sin micrófonos disponibles', muted: true };
}

function createAudioDeviceOption(device, { active = false } = {}) {
  const option = document.createElement('button');
  option.type = 'button';
  option.className = 'audio-device-option';
  option.dataset.deviceId = device.deviceId;
  option.setAttribute('role', 'option');
  option.setAttribute('aria-selected', String(active));
  option.title = device.cleanLabel;

  if (active) option.classList.add('active');
  option.addEventListener('click', () => {
    void handleAudioDeviceChangeRequest(device.deviceId);
  });

  const main = document.createElement('span');
  main.className = 'audio-device-option-main';

  const icon = document.createElement('span');
  icon.className = 'audio-device-option-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '🎧';

  const name = document.createElement('span');
  name.className = 'audio-device-option-name';
  name.textContent = device.cleanLabel;

  const check = document.createElement('span');
  check.className = 'audio-device-option-check';
  check.setAttribute('aria-hidden', 'true');
  check.textContent = '✓';

  main.append(icon, name);
  option.append(main, check);
  return option;
}

function renderAudioDeviceSelector() {
  if (!ui.audioDeviceSelector || !ui.audioDeviceTriggerLabel || !ui.audioDeviceSelectedList || !ui.audioDeviceOtherList) return;

  const triggerState = getAudioDeviceTriggerText();
  ui.audioDeviceTriggerLabel.textContent = triggerState.text;
  ui.audioDeviceTriggerLabel.classList.toggle('muted', triggerState.muted);
  if (ui.audioDeviceTrigger) {
    ui.audioDeviceTrigger.setAttribute('aria-expanded', String(audioDevicePopoverOpen));
    ui.audioDeviceTrigger.disabled = audioDeviceSwitchInFlight;
    ui.audioDeviceTriggerLabel.title = triggerState.text;
  }
  ui.audioDeviceSelector.classList.toggle('open', audioDevicePopoverOpen);

  ui.audioDeviceSelectedList.innerHTML = '';
  ui.audioDeviceOtherList.innerHTML = '';

  if (entryPermissionStatus !== 'granted') {
    const empty = document.createElement('div');
    empty.className = 'audio-device-empty';
    const text = document.createElement('div');
    text.textContent = entryPermissionStatus === 'denied'
      ? 'Necesitamos permiso para listar los micrófonos disponibles.'
      : 'Necesitamos permiso para listar los micrófonos disponibles.';
    empty.appendChild(text);

    const actions = document.createElement('div');
    actions.className = 'audio-device-empty-actions';
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'audio-device-inline-action';
    action.textContent = 'Activar permisos';
    action.addEventListener('click', () => {
      void handleAudioDevicePermissionRequest();
    });
    actions.appendChild(action);
    empty.appendChild(actions);
    ui.audioDeviceSelectedList.appendChild(empty);
    if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = true;
    return;
  }

  if (!availableInputDevices.length) {
    const empty = document.createElement('div');
    empty.className = 'audio-device-empty';
    empty.textContent = 'No hay micrófonos disponibles en este momento.';
    ui.audioDeviceSelectedList.appendChild(empty);
    if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = true;
    return;
  }

  const selected = availableInputDevices.find((device) => device.deviceId === selectedEntryDeviceId) || availableInputDevices[0];
  const others = availableInputDevices.filter((device) => device.deviceId !== selected.deviceId);

  ui.audioDeviceSelectedList.appendChild(createAudioDeviceOption(selected, { active: true }));
  if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = others.length === 0;
  others.forEach((device) => {
    ui.audioDeviceOtherList.appendChild(createAudioDeviceOption(device));
  });
}

function stopAudioDevicePopoverPolling() {
  if (audioDevicePopoverPollTimer) {
    window.clearInterval(audioDevicePopoverPollTimer);
    audioDevicePopoverPollTimer = null;
  }
}

function closeAudioDevicePopover() {
  if (!audioDevicePopoverOpen) return;
  audioDevicePopoverOpen = false;
  stopAudioDevicePopoverPolling();
  renderAudioDeviceSelector();
}

function openAudioDevicePopover() {
  if (audioDevicePopoverOpen) return;
  audioDevicePopoverOpen = true;
  renderAudioDeviceSelector();
  scheduleEntryDeviceRefresh('audio-selector-open', 0);
  stopAudioDevicePopoverPolling();
  audioDevicePopoverPollTimer = window.setInterval(() => {
    scheduleEntryDeviceRefresh('audio-selector-poll', 120);
  }, 3000);
}

function toggleAudioDevicePopover() {
  if (audioDevicePopoverOpen) {
    closeAudioDevicePopover();
    return;
  }
  openAudioDevicePopover();
}

ui.audioDeviceTrigger?.addEventListener('click', () => {
  toggleAudioDevicePopover();
});

document.addEventListener('click', (e) => {
  if (!audioDevicePopoverOpen || !ui.audioDeviceSelector) return;
  if (e.target instanceof Node && !ui.audioDeviceSelector.contains(e.target)) closeAudioDevicePopover();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeAudioDevicePopover();
    return;
  }
});
```
