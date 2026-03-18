const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(`/api/interfaz_usuario${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function ids() {
  return { user_id: $('userId').value.trim(), session_id: $('sessionId').value.trim() };
}

const InputMode = { TALK: 'talk', WRITE: 'write' };
const AgentMode = { CHAT: 'chat', NEGOTIATION: 'negotiation' };
const AgentModeLabels = { chat: 'Chat', negotiation: 'Negociación' };

const JobStageLabel = {
  created: 'Creando evaluación...',
  queued: 'Evaluación en cola...',
  building_inputs: 'Analizando la conversación...',
  running_core: 'Evaluando desempeño global...',
  running_trajectory: 'Evaluando trayectoria turno a turno...',
  assembling_report: 'Preparando el informe...',
  completed: 'Informe listo.',
  failed: 'No se pudo completar la evaluación.',
};

const FeedbackFloatingPhrases = [
  [['token-keyword', 'Analizando'], ['token-entity', 'tendencias']],
  [['token-keyword', 'Detectando'], ['token-value', 'patrones']],
  [['token-keyword', 'Evaluando'], ['token-metric', 'puntos fuertes']],
  [['token-keyword', 'Identificando'], ['token-entity', 'áreas de mejora']],
  [['token-keyword', 'Procesando'], ['token-value', 'métricas']],
  [['token-keyword', 'Correlacionando'], ['token-entity', 'resultados']],
  [['token-keyword', 'Comparando'], ['token-metric', 'desempeño']],
  [['token-keyword', 'Generando'], ['token-value', 'insights']],
  [['token-keyword', 'Estimando'], ['token-entity', 'evolución']],
  [['token-keyword', 'Revisando'], ['token-metric', 'consistencia']],
  [['token-keyword', 'Mapeando'], ['token-value', 'habilidades']],
  [['token-keyword', 'Sintetizando'], ['token-entity', 'observaciones']],
];

const FloatingPhraseQuadrantsDesktop = {
  topLeft: [
    { top: [10, 18], left: [6, 16] },
    { top: [22, 32], left: [10, 22] },
    { top: [38, 46], left: [4, 14] },
  ],
  topRight: [
    { top: [10, 18], left: [72, 84] },
    { top: [22, 32], left: [76, 88] },
    { top: [38, 46], left: [82, 92] },
  ],
  bottomLeft: [
    { top: [62, 72], left: [8, 18] },
    { top: [74, 84], left: [12, 24] },
    { top: [82, 90], left: [18, 30] },
  ],
  bottomRight: [
    { top: [62, 72], left: [72, 84] },
    { top: [74, 84], left: [66, 78] },
    { top: [82, 90], left: [62, 76] },
  ],
};

const FloatingPhraseQuadrantsMobile = {
  topLeft: [
    { top: [11, 19], left: [4, 16] },
    { top: [24, 32], left: [6, 18] },
  ],
  topRight: [
    { top: [12, 20], left: [64, 78] },
    { top: [26, 34], left: [68, 82] },
  ],
  bottomLeft: [
    { top: [66, 76], left: [8, 20] },
    { top: [80, 88], left: [10, 22] },
  ],
  bottomRight: [
    { top: [66, 76], left: [64, 78] },
    { top: [80, 88], left: [60, 74] },
  ],
};

const FloatingPhraseQuadrantOrder = ['topLeft', 'topRight', 'bottomLeft', 'bottomRight'];

let currentInputMode = InputMode.TALK;
let currentAgentMode = AgentMode.CHAT;
let finishButtonArmed = false;
let latestTraceCount = 0;
let lastSessionKey = '';
const MIN_TURNS_BEFORE_FINALIZE = 5;
let orbRaf = null;
let orbLevel = 0;
let finalizePopoverOpen = false;
let feedbackPollingTimer = null;
let feedbackEvaluationId = null;
let feedbackFloatingTimer = null;
let feedbackQuadrantCursor = 0;
let audioCtx = null;
let ttsWarmedUp = false;
let micStream = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recorderMimeType = 'audio/webm;codecs=opus';
let discardRecording = false;
let hasMicPermission = false;
let waveAudioCtx = null;
let waveAnalyser = null;
let waveDataArray = null;
let waveSourceNode = null;
let turnInFlight = false;
let voiceTurnInFlight = false;
let entryMode = InputMode.TALK;
let scenarioReady = false;
let entryRequested = false;
let entryInProgress = false;
let entryRequestedMode = null;
let entryResolvedInputMode = null;
let entryPermissionStatus = 'unknown';
let lastEntryMicError = '';
let availableInputDevices = [];
let selectedEntryDeviceId = null;
let entryDeviceRefreshTimer = null;
let entryDeviceDebounceTimer = null;
let refreshInFlight = false;
let refreshPendingAfterInFlight = false;
let refreshSequence = 0;
let audioDevicePopoverOpen = false;
let audioDevicePopoverPollTimer = null;
let audioDeviceSwitchInFlight = false;
let audioDeviceToastTimer = null;
const LAST_DEVICE_STORAGE_KEY = 'interfaz_usuario:last_audio_input_device';

const ui = {
  listeningGlow: $('listeningGlow'),
  entryOverlay: $('entryOverlay'),
  entryModeTalk: $('entryModeTalk'),
  entryModeWrite: $('entryModeWrite'),
  entryTalkContent: $('entryTalkContent'),
  entryWriteContent: $('entryWriteContent'),
  entrySubtitle: $('entrySubtitle'),
  entryDeviceLabel: $('entryDeviceLabel'),
  entryDeviceSearch: $('entryDeviceSearch'),
  entryDeviceList: $('entryDeviceList'),
  entryDeviceStatus: $('entryDeviceStatus'),
  entryError: $('entryError'),
  entryScenarioState: $('entryScenarioState'),
  entryScenarioSpinner: $('entryScenarioSpinner'),
  entryLoadingText: $('entryLoadingText'),
  startBtn: $('startBtn'),
  replyContainer: $('replyContainer'),
  lastReply: $('lastReply'),
  audioDeviceToast: $('audioDeviceToast'),
  statusText: $('statusText'),
  inputOrb: $('inputOrb'),
  finishTurnBtn: $('finishTurnBtn'),
  modeTalk: $('modeTalk'),
  modeWrite: $('modeWrite'),
  talkMode: $('talkMode'),
  writeMode: $('writeMode'),
  textInput: $('textInput'),
  sendTextBtn: $('sendTextBtn'),
  finishNegotiationBtn: $('finishNegotiationBtn'),
  finishConfirmMessage: $('finishConfirmMessage'),
  finishConfirmHint: $('finishConfirmHint'),
  finishConfirmBtn: $('finishConfirmBtn'),
  conversationMode: $('conversationMode'),
  audioDeviceSelector: $('audioDeviceSelector'),
  audioDeviceTrigger: $('audioDeviceTrigger'),
  audioDeviceTriggerLabel: $('audioDeviceTriggerLabel'),
  audioDevicePopover: $('audioDevicePopover'),
  audioDeviceSelectedList: $('audioDeviceSelectedList'),
  audioDeviceOtherList: $('audioDeviceOtherList'),
  audioDevicePopoverDivider: $('audioDevicePopoverDivider'),
};

// Hard guard: if any stale HTML/version still injects the old Chat/Negociación selector,
// remove it at runtime so the negotiation flow remains fixed and selector-free.
$('conversationMode')?.remove();

function closeConversationModeMenu() {
  if (!ui.conversationMode) return;
  ui.conversationMode.classList.remove('open');
}

function isEntryOverlayVisible() {
  return Boolean(ui.entryOverlay && ui.entryOverlay.style.display !== 'none');
}

function isAnyAudioDeviceSurfaceVisible() {
  return isEntryOverlayVisible() || audioDevicePopoverOpen;
}

function withAvatarRuntime(fn) {
  const runtime = window.__avatarRuntime;
  if (!runtime) return;
  fn(runtime);
}

function syncAvatarMode() {
  withAvatarRuntime((runtime) => {
    if (isMicActuallyRecording() && currentInputMode === InputMode.TALK) {
      runtime.setMode('LISTENING');
      runtime.setTalkLevel(0);
      return;
    }
    runtime.setMode('IDLE');
    runtime.setTalkLevel(0);
  });
}

function isMicActuallyRecording() {
  return Boolean(isRecording && mediaRecorder && mediaRecorder.state === 'recording');
}

function updateReplyText(text) {
  ui.lastReply.textContent = text;
  ui.replyContainer.classList.toggle('hidden', !text);
}

function showAudioDeviceToast(message, durationMs = 3200) {
  if (!ui.audioDeviceToast) return;
  ui.audioDeviceToast.textContent = message;
  ui.audioDeviceToast.classList.add('visible');
  if (audioDeviceToastTimer) window.clearTimeout(audioDeviceToastTimer);
  audioDeviceToastTimer = window.setTimeout(() => {
    audioDeviceToastTimer = null;
    ui.audioDeviceToast.classList.remove('visible');
  }, durationMs);
}

function getOrCreateAudioContext() {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function base64ToAudioData(b64, mimeType = 'audio/wav') {
  if (typeof b64 !== 'string' || !b64.trim()) throw new Error('Respuesta TTS sin audio_base64 válido');

  const sanitized = b64
    .replace(/^data:[^;]+;base64,/, '')
    .replace(/\s+/g, '')
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  let byteChars;
  try {
    byteChars = atob(sanitized);
  } catch (err) {
    console.error('[audio] No se pudo decodificar base64', err);
    throw new Error('Audio base64 corrupto');
  }

  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i += 1) byteNumbers[i] = byteChars.charCodeAt(i);
  const byteArray = new Uint8Array(byteNumbers);
  if (!byteArray.length) throw new Error('Audio vacío tras decodificar base64');

  return {
    mimeType: mimeType || 'audio/wav',
    arrayBuffer: byteArray.buffer.slice(byteArray.byteOffset, byteArray.byteOffset + byteArray.byteLength),
  };
}

async function requestTTS(text) {
  const response = await fetch('/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  return base64ToAudioData(data.audio_base64, data.audio_mime_type || 'audio/wav');
}

async function warmupFrontendTts() {
  if (ttsWarmedUp) return;
  try {
    const audioData = await requestTTS('Calibración de audio.');
    const ctx = getOrCreateAudioContext();
    const audioBuffer = await ctx.decodeAudioData(audioData.arrayBuffer.slice(0));
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(gain);
    gain.connect(ctx.destination);
    await ctx.resume();
    source.start(ctx.currentTime + 0.05);
    ttsWarmedUp = true;
  } catch (err) {
    console.warn('[warmup] Falló warmup frontend TTS', err);
  }
}

function teardownMic() {
  stopInputOrb();
  if (waveSourceNode) {
    try { waveSourceNode.disconnect(); } catch (_) {}
  }
  waveSourceNode = null;
  waveAudioCtx = null;
  waveAnalyser = null;
  waveDataArray = null;
  isRecording = false;
  mediaRecorder = null;
  audioChunks = [];
  discardRecording = false;
  try { if (micStream) micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  micStream = null;
}

function computeIdlePulse(timeMs) {
  return 0.08 * (0.5 + 0.5 * Math.sin((timeMs * 2 * Math.PI) / 3800));
}

function updateInputOrb() {
  if (!ui.inputOrb) return;
  const now = performance.now();
  const idle = computeIdlePulse(now);
  let level = idle;

  if (waveAnalyser && waveDataArray && isMicActuallyRecording()) {
    waveAnalyser.getByteTimeDomainData(waveDataArray);
    let sum = 0;
    for (let i = 0; i < waveDataArray.length; i += 1) {
      const v = waveDataArray[i] / 128 - 1;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / waveDataArray.length);
    const rmsNorm = Math.min(1, rms * 6);
    level = Math.max(rmsNorm, idle);
  }

  orbLevel += (level - orbLevel) * 0.18;
  const scale = 0.85 + orbLevel * 0.55;
  ui.inputOrb.style.setProperty('--orb-scale', scale.toFixed(2));
  orbRaf = requestAnimationFrame(updateInputOrb);
}

function ensureOrbLoop() {
  if (!orbRaf) orbRaf = requestAnimationFrame(updateInputOrb);
}

function stopInputOrb() {
  if (orbRaf) cancelAnimationFrame(orbRaf);
  orbRaf = null;
  orbLevel = 0;
  if (ui.inputOrb) ui.inputOrb.style.setProperty('--orb-scale', '0.85');
}

async function startVoiceCapture() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('getUserMedia no soportado');
  if (isMicActuallyRecording()) return;

  discardRecording = false;
  teardownMic();

  const buildConstraints = (deviceId = null) => ({
    audio: deviceId
      ? {
          deviceId: { exact: deviceId },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      : {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
  });

  try {
    micStream = await navigator.mediaDevices.getUserMedia(buildConstraints(selectedEntryDeviceId));
  } catch (err) {
    const recoverable = err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError';
    if (!recoverable) throw err;
    micStream = await navigator.mediaDevices.getUserMedia(buildConstraints());
    void refreshEntryDevices('capture-fallback-device');
  }

  recorderMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';

  mediaRecorder = new MediaRecorder(micStream, { mimeType: recorderMimeType });
  audioChunks = [];

  mediaRecorder.ondataavailable = (event) => {
    if (event?.data && event.data.size > 0) audioChunks.push(event.data);
  };

  mediaRecorder.start(250);
  await new Promise((resolve) => setTimeout(resolve, 0));
  isRecording = mediaRecorder.state === 'recording';

  if (!micStream.getTracks().some((track) => track.readyState === 'live')) {
    throw new Error('El micrófono no está activo.');
  }

  if (!isRecording) {
    throw new Error('No se pudo iniciar la grabación.');
  }

  waveAudioCtx = getOrCreateAudioContext();
  await waveAudioCtx.resume();
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;
  waveSourceNode = waveAudioCtx.createMediaStreamSource(micStream);
  waveSourceNode.connect(waveAnalyser);
  waveDataArray = new Uint8Array(waveAnalyser.frequencyBinCount);
  ensureOrbLoop();
}

function stopVoiceCapture() {
  if (!mediaRecorder || !isRecording) return Promise.resolve(null);

  return new Promise((resolve, reject) => {
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: recorderMimeType });
      audioChunks = [];
      isRecording = false;
      mediaRecorder = null;

      if (discardRecording) {
        discardRecording = false;
        resolve(null);
        return;
      }

      resolve(blob);
    };

    try {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.requestData();
        setTimeout(() => {
          try { mediaRecorder.stop(); } catch (err) { reject(err); }
        }, 150);
      } else {
        mediaRecorder.stop();
      }
    } catch (err) {
      reject(err);
    }
  });
}

async function transcribeAudio(blob) {
  const audioFile = new File([blob], 'grabacion.webm', { type: recorderMimeType });
  const formData = new FormData();
  formData.append('file', audioFile);
  const response = await fetch('/stt_google', { method: 'POST', body: formData });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  return (data?.text || '').trim();
}

async function playTtsWithAvatar(replyText) {
  const audioData = await requestTTS(replyText);
  const ctx = getOrCreateAudioContext();
  const decoded = await ctx.decodeAudioData(audioData.arrayBuffer.slice(0));
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  const source = ctx.createBufferSource();
  source.buffer = decoded;
  source.connect(analyser);
  analyser.connect(ctx.destination);

  withAvatarRuntime((runtime) => {
    runtime.connectAnalyser(analyser);
    runtime.setMode('SPEAKING');
    runtime.setTalkLevel(0);
  });

  await ctx.resume();
  await new Promise((resolve) => {
    source.onended = () => {
      withAvatarRuntime((runtime) => {
        runtime.connectAnalyser(null);
      });
      resolve();
    };
    source.start(ctx.currentTime + 0.05);
  });
}

function setStatusText(text) {
  ui.statusText.textContent = text;
}

function setListeningGlowEnabled(enabled) {
  ui.listeningGlow.classList.toggle('active', Boolean(enabled));
}

function getRemainingTurnsBeforeFinalize() {
  return Math.max(0, MIN_TURNS_BEFORE_FINALIZE - latestTraceCount);
}

function canFinalizeConversation() {
  return getRemainingTurnsBeforeFinalize() === 0;
}

function getFinalizePopoverCopy() {
  const remainingTurns = getRemainingTurnsBeforeFinalize();
  if (remainingTurns === 0) {
    return {
      message: '¿Seguro que quieres finalizar la conversación?',
      hint: '',
      confirmDisabled: false,
    };
  }

  const turnWord = remainingTurns === 1 ? 'turno' : 'turnos';
  return {
    message: 'La conversación no es suficientemente relevante para haber llegado a un resultado siguiendo el método adecuado.',
    hint: `Finalizar conversación disponible en ${remainingTurns} ${turnWord}.`,
    confirmDisabled: true,
  };
}

function renderFinalizePopoverState() {
  if (!ui.finishConfirmMessage || !ui.finishConfirmHint || !ui.finishConfirmBtn) return;
  const copy = getFinalizePopoverCopy();
  ui.finishConfirmMessage.textContent = copy.message;
  ui.finishConfirmHint.textContent = copy.hint;
  ui.finishConfirmHint.classList.toggle('hidden', !copy.hint);
  ui.finishConfirmBtn.disabled = copy.confirmDisabled;
}

function setLatestTraceCount(nextCount) {
  const numericCount = Number(nextCount);
  latestTraceCount = Number.isFinite(numericCount) && numericCount > 0 ? Math.floor(numericCount) : 0;
  renderFinalizePopoverState();
}

function updateFinishNegotiationButton() {
  ui.finishNegotiationBtn.classList.toggle('is-armed', finishButtonArmed);
}

function armFinishButton(nextArmed) {
  finishButtonArmed = finishButtonArmed || Boolean(nextArmed);
  updateFinishNegotiationButton();
}

function resetFinishButtonArmed() {
  finishButtonArmed = false;
  updateFinishNegotiationButton();
}

function syncSessionBoundaryReset() {
  const { user_id, session_id } = ids();
  const currentSessionKey = `${user_id}::${session_id}`;
  if (lastSessionKey && lastSessionKey !== currentSessionKey) resetFinishButtonArmed();
  lastSessionKey = currentSessionKey;
}

function updateUi() {
  renderFinalizePopoverState();
  ui.modeTalk.classList.toggle('active', currentInputMode === InputMode.TALK);
  ui.modeWrite.classList.toggle('active', currentInputMode === InputMode.WRITE);
  ui.modeTalk.setAttribute('aria-selected', String(currentInputMode === InputMode.TALK));
  ui.modeWrite.setAttribute('aria-selected', String(currentInputMode === InputMode.WRITE));
  ui.talkMode.classList.toggle('hidden', currentInputMode !== InputMode.TALK);
  ui.writeMode.classList.toggle('hidden', currentInputMode !== InputMode.WRITE);

  const isBusy = turnInFlight || voiceTurnInFlight;
  const canSendText = currentInputMode === InputMode.WRITE && !isBusy;
  ui.textInput.disabled = currentInputMode !== InputMode.WRITE || isBusy;
  ui.sendTextBtn.disabled = !canSendText;
  const micOn = isMicActuallyRecording();
  ui.finishTurnBtn.disabled = !(currentInputMode === InputMode.TALK && micOn && !isBusy && !audioDeviceSwitchInFlight);
  ui.inputOrb.classList.toggle('inactive', !micOn);
  setListeningGlowEnabled(micOn);
  updateFinishNegotiationButton();
  renderAudioDeviceSelector();
}

function setInputMode(mode) {
  currentInputMode = mode;
  if (mode === InputMode.WRITE && isMicActuallyRecording()) {
    discardRecording = true;
    void stopVoiceCapture().finally(() => teardownMic());
  }
  setStatusText(mode === InputMode.TALK ? (isMicActuallyRecording() ? 'Escuchando…' : 'Listo') : 'Listo');
  updateUi();
  syncAvatarMode();
}

function resolveEntryInputMode(mode) {
  entryResolvedInputMode = mode;
  setInputMode(mode);
}

function getSavedEntryDeviceId() {
  try {
    return window.localStorage.getItem(LAST_DEVICE_STORAGE_KEY);
  } catch (_) {
    return null;
  }
}

function saveEntryDeviceId(deviceId) {
  try {
    if (deviceId) window.localStorage.setItem(LAST_DEVICE_STORAGE_KEY, deviceId);
  } catch (_) {}
}

function normalizeDeviceLabel(label, index) {
  const raw = String(label || '').trim();
  if (!raw) return `Micrófono ${index + 1}`;
  return raw
    .replace(/^(default|predeterminado)\s*-\s*/i, '')
    .replace(/^(communications|comunicaciones)\s*-\s*/i, '')
    .replace(/\s*\((default|predeterminado|communications|comunicaciones)\)\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function getDeviceLabelKey(label) {
  return String(label || '')
    .toLowerCase()
    .replace(/[^a-z0-9áéíóúüñ]+/gi, ' ')
    .trim();
}

function toUiAudioInputDevices(devices) {
  const byIdentity = new Map();
  devices.forEach((device, index) => {
    if (device.kind !== 'audioinput' || !device.deviceId) return;
    const cleanLabel = normalizeDeviceLabel(device.label, index);
    const groupPart = device.groupId ? `g:${device.groupId}` : '';
    const labelPart = getDeviceLabelKey(cleanLabel);
    const dedupeKey = `${groupPart}|${labelPart}`;
    if (!byIdentity.has(dedupeKey)) {
      byIdentity.set(dedupeKey, {
        deviceId: device.deviceId,
        groupId: device.groupId || '',
        label: device.label || '',
        cleanLabel,
      });
    }
  });
  return [...byIdentity.values()].sort((a, b) => a.cleanLabel.localeCompare(b.cleanLabel, 'es', { sensitivity: 'base' }));
}

function pickReplacementDevice(previousDeviceId, previousList, nextList) {
  if (!nextList.length) return null;
  if (!previousDeviceId) return nextList[0].deviceId;
  const exact = nextList.find((d) => d.deviceId === previousDeviceId);
  if (exact) return exact.deviceId;
  const previous = previousList.find((d) => d.deviceId === previousDeviceId);
  if (!previous) return nextList[0].deviceId;
  if (previous.groupId) {
    const byGroup = nextList.find((d) => d.groupId && d.groupId === previous.groupId);
    if (byGroup) return byGroup.deviceId;
  }
  const prevLabelKey = getDeviceLabelKey(previous.cleanLabel || previous.label || '');
  if (prevLabelKey) {
    const byLabel = nextList.find((d) => getDeviceLabelKey(d.cleanLabel || d.label || '') === prevLabelKey);
    if (byLabel) return byLabel.deviceId;
  }
  return nextList[0].deviceId;
}

function canStartTalkEntry() {
  if (entryPermissionStatus === 'denied') return false;
  if (entryPermissionStatus === 'granted') return Boolean(selectedEntryDeviceId);
  return true;
}

function getEntryModeStartEnabled() {
  if (entryMode === InputMode.WRITE) return true;
  return canStartTalkEntry();
}

function getCanEnterNow() {
  return getEntryModeStartEnabled() && scenarioReady;
}

function setSelectedEntryDevice(deviceId, reason = 'manual') {
  if (!deviceId || !availableInputDevices.some((d) => d.deviceId === deviceId)) return;
  if (selectedEntryDeviceId === deviceId) return;
  selectedEntryDeviceId = deviceId;
  saveEntryDeviceId(deviceId);
  renderEntryDevices();
  renderEntryState();
  renderAudioDeviceSelector();
}

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

function getAudioDeviceSwitchFailureMessage(err) {
  if (err?.name === 'NotReadableError') {
    return 'No se pudo activar el nuevo micrófono. Cierra otras apps que lo estén usando y vuelve a intentarlo.';
  }
  if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
    return 'No encontramos ese micrófono disponible. Revisa la conexión y vuelve a intentarlo.';
  }
  return 'No se pudo cambiar el micrófono. Reintenta o usa modo Escribir si el problema continúa.';
}

async function restorePreviousMicrophoneAfterFailure(previousDeviceId) {
  if (previousDeviceId && previousDeviceId !== selectedEntryDeviceId && availableInputDevices.some((device) => device.deviceId === previousDeviceId)) {
    setSelectedEntryDevice(previousDeviceId, 'restore-after-switch-failure');
  }

  if (currentInputMode !== InputMode.TALK || !hasMicPermission) {
    setStatusText('Listo');
    updateUi();
    syncAvatarMode();
    return false;
  }

  try {
    await startVoiceCapture();
    setStatusText('Escuchando…');
    updateUi();
    syncAvatarMode();
    return true;
  } catch (restoreErr) {
    console.error('[audio-selector] No se pudo restaurar el micrófono previo', restoreErr);
    setInputMode(InputMode.WRITE);
    setStatusText('Listo');
    updateUi();
    syncAvatarMode();
    return false;
  }
}

async function restartVoiceCaptureAfterDeviceSwitch(previousDeviceId) {
  audioDeviceSwitchInFlight = true;
  updateUi();
  setStatusText('Cambiando mic…');

  discardRecording = true;
  try {
    await stopVoiceCapture();
  } catch (stopErr) {
    console.warn('[audio-selector] Error deteniendo captura previa para cambiar micrófono', stopErr);
  }
  teardownMic();

  try {
    await startVoiceCapture();
    setStatusText('Escuchando…');
    showAudioDeviceToast('Se ha cambiado el micrófono. Vuelve a decir lo que estabas diciendo porque tu respuesta puede haberse perdido.');
    updateUi();
    syncAvatarMode();
    closeAudioDevicePopover();
    return true;
  } catch (err) {
    console.error('[audio-selector] No se pudo activar el nuevo micrófono', err);
    const restored = await restorePreviousMicrophoneAfterFailure(previousDeviceId);
    showAudioDeviceToast(restored
      ? 'No se pudo activar el nuevo micrófono. Seguimos usando el anterior.'
      : getAudioDeviceSwitchFailureMessage(err));
    return false;
  } finally {
    audioDeviceSwitchInFlight = false;
    updateUi();
    void refreshEntryDevices('audio-selector-post-switch');
  }
}

async function handleAudioDeviceChangeRequest(deviceId) {
  if (!deviceId || !availableInputDevices.some((device) => device.deviceId === deviceId)) return;
  if (audioDeviceSwitchInFlight) return;

  if (turnInFlight || voiceTurnInFlight) {
    showAudioDeviceToast('Espera a que termine este turno para cambiar de micrófono.');
    setStatusText('Procesando…');
    return;
  }

  const previousDeviceId = selectedEntryDeviceId;
  if (previousDeviceId === deviceId) {
    closeAudioDevicePopover();
    return;
  }

  setSelectedEntryDevice(deviceId, 'audio-selector');

  if (!isMicActuallyRecording() || currentInputMode !== InputMode.TALK) {
    closeAudioDevicePopover();
    return;
  }

  await restartVoiceCaptureAfterDeviceSwitch(previousDeviceId);
}

async function handleAudioDevicePermissionRequest() {
  if (audioDeviceSwitchInFlight) return;
  setStatusText('Activando mic…');
  const permissionOk = await requestMicPermissionsForEntry();
  await refreshEntryDevices(permissionOk ? 'audio-selector-permission-ok' : 'audio-selector-permission-error');
  renderAudioDeviceSelector();

  if (permissionOk) {
    setStatusText(isMicActuallyRecording() ? 'Escuchando…' : 'Listo');
    return;
  }

  setStatusText('Listo');
  showAudioDeviceToast(lastEntryMicError || 'No pudimos activar el micrófono. Revisa los permisos e inténtalo de nuevo.');
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

function renderEntryState() {
  if (!ui.entryOverlay) return;
  ui.entryModeTalk.classList.toggle('active', entryMode === InputMode.TALK);
  ui.entryModeWrite.classList.toggle('active', entryMode === InputMode.WRITE);
  ui.entryModeTalk.setAttribute('aria-selected', String(entryMode === InputMode.TALK));
  ui.entryModeWrite.setAttribute('aria-selected', String(entryMode === InputMode.WRITE));
  ui.entryTalkContent.classList.toggle('entry-hidden', entryMode !== InputMode.TALK);
  ui.entryWriteContent.classList.toggle('entry-hidden', entryMode !== InputMode.WRITE);
  ui.entrySubtitle.textContent = entryMode === InputMode.TALK
    ? (entryPermissionStatus === 'granted'
        ? ''
        : 'Necesitamos permiso de micrófono para detectar tus dispositivos.')
    : '';
  ui.entrySubtitle.classList.toggle('entry-hidden', entryMode !== InputMode.TALK);

  const startEnabled = getEntryModeStartEnabled();
  ui.startBtn.disabled = !startEnabled || entryInProgress;
  if (entryRequested && !scenarioReady) {
    ui.startBtn.textContent = 'Cargando escenario…';
  } else if (entryMode === InputMode.TALK && entryPermissionStatus !== 'granted') {
    ui.startBtn.textContent = 'Activar micrófono';
  } else {
    ui.startBtn.textContent = 'Empezar';
  }

  if (!scenarioReady) {
    ui.entryLoadingText.textContent = 'Cargando escenario';
    ui.entryScenarioSpinner.style.display = 'inline-flex';
    ui.entryScenarioState.classList.remove('ready');
  } else {
    ui.entryLoadingText.textContent = 'Escenario cargado';
    ui.entryScenarioSpinner.style.display = 'none';
    ui.entryScenarioState.classList.add('ready');
  }

  const showSearchHeader = entryMode === InputMode.TALK;
  const waitingForPermission = entryMode === InputMode.TALK && entryPermissionStatus !== 'granted';
  ui.entryDeviceSearch?.classList.toggle('hidden', !showSearchHeader);
  ui.entryDeviceLabel?.classList.toggle('entry-hidden', waitingForPermission || entryMode !== InputMode.TALK);
  if (ui.entryDeviceSearch) {
    ui.entryDeviceSearch.innerHTML = waitingForPermission
      ? '<span>Necesitamos permiso para listar los micrófonos disponibles</span>'
      : '<span>Micrófonos detectados</span><span class="entry-device-search-spinner" aria-hidden="true"></span>';
  }

  if (entryPermissionStatus === 'prompt' || entryPermissionStatus === 'unknown') {
    ui.entryDeviceStatus.textContent = 'Pulsa “Activar micrófono” para conceder acceso y cargar tus dispositivos de audio.';
    ui.entryDeviceStatus.classList.remove('error');
  } else if (entryPermissionStatus === 'denied') {
    ui.entryDeviceStatus.textContent = 'Permiso de micrófono denegado. Habilítalo en el navegador o usa modo Escribir.';
    ui.entryDeviceStatus.classList.add('error');
  } else if (!selectedEntryDeviceId) {
    ui.entryDeviceStatus.textContent = 'No encontramos un micrófono válido después de conceder permiso.';
    ui.entryDeviceStatus.classList.add('error');
  } else {
    ui.entryDeviceStatus.textContent = 'Micrófono seleccionado. Puedes empezar en modo hablar.';
    ui.entryDeviceStatus.classList.remove('error');
  }
  renderAudioDeviceSelector();
}

function renderEntryDevices() {
  if (!ui.entryDeviceList) return;
  const currentChildren = [...ui.entryDeviceList.querySelectorAll('[data-device-id]')];
  const currentById = new Map(currentChildren.map((node) => [node.dataset.deviceId, node]));

  if (entryPermissionStatus !== 'granted') {
    ui.entryDeviceList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'entry-device-empty';
    empty.textContent = 'Activa el micrófono para mostrar tus dispositivos disponibles';
    ui.entryDeviceList.appendChild(empty);
    selectedEntryDeviceId = null;
    return;
  }

  if (!availableInputDevices.length) {
    ui.entryDeviceList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'entry-device-empty';
    empty.textContent = 'Ningún dispositivo conectado';
    ui.entryDeviceList.appendChild(empty);
    selectedEntryDeviceId = null;
    return;
  }

  const fragment = document.createDocumentFragment();
  availableInputDevices.forEach((device) => {
    let option = currentById.get(device.deviceId);
    if (!option) {
      option = document.createElement('button');
      option.type = 'button';
      option.className = 'entry-device-option';
      option.setAttribute('role', 'option');
      option.dataset.deviceId = device.deviceId;
      option.addEventListener('click', () => setSelectedEntryDevice(device.deviceId, 'click'));

      const main = document.createElement('span');
      main.className = 'entry-device-main';
      const icon = document.createElement('span');
      icon.className = 'entry-device-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '🎧';
      const name = document.createElement('span');
      name.className = 'entry-device-name';
      main.append(icon, name);
      const check = document.createElement('span');
      check.className = 'entry-device-check';
      check.setAttribute('aria-hidden', 'true');
      check.textContent = '✓';
      option.append(main, check);
    }

    option.querySelector('.entry-device-name').textContent = device.cleanLabel;
    const isActive = selectedEntryDeviceId === device.deviceId;
    option.classList.toggle('active', isActive);
    option.setAttribute('aria-selected', String(isActive));
    fragment.appendChild(option);
  });

  ui.entryDeviceList.innerHTML = '';
  ui.entryDeviceList.appendChild(fragment);
}

async function syncMicPermissionState() {
  if (!navigator.permissions?.query) return;
  try {
    const status = await navigator.permissions.query({ name: 'microphone' });
    if (status.state === 'granted' || status.state === 'denied' || status.state === 'prompt') {
      entryPermissionStatus = status.state;
      hasMicPermission = status.state === 'granted';
    }
    status.onchange = () => {
      entryPermissionStatus = status.state;
      hasMicPermission = status.state === 'granted';
      scheduleEntryDeviceRefresh('permission-change', 0);
      renderEntryState();
    };
  } catch (_) {}
}

async function requestMicPermissionsForEntry() {
  if (!navigator.mediaDevices?.getUserMedia) {
    entryPermissionStatus = 'denied';
    hasMicPermission = false;
    lastEntryMicError = 'Este navegador no soporta acceso al micrófono.';
    return false;
  }

  lastEntryMicError = '';

  try {
    await getOrCreateAudioContext().resume();
  } catch (_) {}

  const baseAudioConstraints = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  const preferredConstraints = selectedEntryDeviceId
    ? { audio: { ...baseAudioConstraints, deviceId: { exact: selectedEntryDeviceId } } }
    : { audio: baseAudioConstraints };

  try {
    const stream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
    stream.getTracks().forEach((track) => track.stop());
    entryPermissionStatus = 'granted';
    hasMicPermission = true;
    return true;
  } catch (err) {
    const recoverable = err?.name === 'NotReadableError'
      || err?.name === 'NotFoundError'
      || err?.name === 'OverconstrainedError';

    if (recoverable && selectedEntryDeviceId) {
      try {
        const fallbackStream = await navigator.mediaDevices.getUserMedia({ audio: baseAudioConstraints });
        fallbackStream.getTracks().forEach((track) => track.stop());
        entryPermissionStatus = 'granted';
        hasMicPermission = true;
        lastEntryMicError = '';
        return true;
      } catch (fallbackErr) {
        err = fallbackErr;
      }
    }

    if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
      entryPermissionStatus = 'denied';
      lastEntryMicError = 'Has bloqueado el permiso del micrófono.';
    } else if (err?.name === 'NotReadableError') {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No se pudo iniciar el micrófono. Cierra otras apps que lo estén usando y reintenta.';
    } else if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No encontramos un micrófono disponible con esa selección.';
    } else {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No pudimos activar el micrófono. Reintenta.';
    }
    hasMicPermission = false;
    console.error('[entry] Error al pedir permiso de micrófono', err);
    return false;
  }
}

async function refreshEntryDevices(reason = 'manual') {
  if (!navigator.mediaDevices?.enumerateDevices) {
    availableInputDevices = [];
    selectedEntryDeviceId = null;
    renderEntryDevices();
    renderEntryState();
    return;
  }

  if (refreshInFlight) {
    refreshPendingAfterInFlight = true;
    return;
  }

  refreshInFlight = true;
  refreshPendingAfterInFlight = false;
  const sequence = ++refreshSequence;
  const previousList = availableInputDevices;
  const previousSelected = selectedEntryDeviceId;

  try {
    const rawDevices = await navigator.mediaDevices.enumerateDevices();
    if (sequence !== refreshSequence) return;

    const nextDevices = entryPermissionStatus === 'granted'
      ? toUiAudioInputDevices(rawDevices)
      : [];
    availableInputDevices = nextDevices;

    const stored = getSavedEntryDeviceId();
    const storedExists = stored && nextDevices.some((d) => d.deviceId === stored);

    if (storedExists && !previousSelected) {
      selectedEntryDeviceId = stored;
    } else {
      selectedEntryDeviceId = pickReplacementDevice(previousSelected, previousList, nextDevices);
    }

    if (selectedEntryDeviceId) saveEntryDeviceId(selectedEntryDeviceId);

  } catch (err) {
    console.warn('[entry] enumerateDevices falló', err);
    availableInputDevices = [];
    selectedEntryDeviceId = null;
  } finally {
    refreshInFlight = false;
  }

  renderEntryDevices();
  renderEntryState();
  renderAudioDeviceSelector();

  if (refreshPendingAfterInFlight) {
    refreshPendingAfterInFlight = false;
    scheduleEntryDeviceRefresh(`follow-up:${reason}`, 80);
  }
}

function scheduleEntryDeviceRefresh(reason = 'manual', delayMs = 120) {
  if (entryDeviceDebounceTimer) window.clearTimeout(entryDeviceDebounceTimer);
  entryDeviceDebounceTimer = window.setTimeout(() => {
    entryDeviceDebounceTimer = null;
    if (!isAnyAudioDeviceSurfaceVisible()) return;
    void refreshEntryDevices(reason);
  }, delayMs);
}

async function validateTalkModeForEntry() {
  if (ui.entryError) ui.entryError.textContent = '';

  if (entryPermissionStatus !== 'granted') {
    const permissionOk = await requestMicPermissionsForEntry();
    await refreshEntryDevices(permissionOk ? 'validate-post-permission' : 'validate-permission-error');

    if (!permissionOk) {
      if (ui.entryError) {
        ui.entryError.textContent = lastEntryMicError || (entryPermissionStatus === 'denied'
          ? 'No pudimos habilitar el micrófono. Activa permisos o usa Escribir.'
          : 'No pudimos validar el micrófono. Reintenta.');
      }
      renderEntryState();
      return false;
    }

    if (!selectedEntryDeviceId) {
      if (ui.entryError) ui.entryError.textContent = 'Concediste permiso, pero no detectamos un micrófono disponible.';
      renderEntryState();
      return false;
    }

    renderEntryState();
    return 'ready-after-permission';
  }

  await refreshEntryDevices('validate-existing-permission');

  if (!selectedEntryDeviceId) {
    if (ui.entryError) ui.entryError.textContent = 'No se detectó un micrófono disponible.';
    renderEntryState();
    return false;
  }

  renderEntryState();
  return 'ready';
}

async function finalizeEntry() {
  if (entryInProgress) return;
  if (!getCanEnterNow()) return;
  entryInProgress = true;
  ui.startBtn.disabled = true;
  const targetMode = entryRequestedMode || entryMode;

  if (targetMode === InputMode.WRITE) {
    resolveEntryInputMode(InputMode.WRITE);
    setStatusText('Listo');
  } else {
    resolveEntryInputMode(InputMode.TALK);
    updateReplyText('Te escucho. Empieza a hablar cuando quieras.');
    try {
      if (!isMicActuallyRecording()) {
        setStatusText('Activando mic…');
        await startVoiceCapture();
      }
      setStatusText('Escuchando…');
    } catch (err) {
      console.error('[entry] No se pudo iniciar captura en modo hablar', err);
      resolveEntryInputMode(InputMode.WRITE);
      setStatusText('Listo');
      updateReplyText('No se pudo iniciar el micrófono. Puedes continuar en modo escritura.');
    }
    updateUi();
    syncAvatarMode();
  }

  entryRequestedMode = null;
  ui.entryOverlay.classList.add('hidden');
  window.setTimeout(() => {
    ui.entryOverlay.style.display = 'none';
  }, 240);
}

function tryResolveEntryRequest() {
  renderEntryState();
  if (entryRequested && getCanEnterNow()) {
    void finalizeEntry();
  }
}

function setEntryMode(mode) {
  entryMode = mode;
  if (mode === InputMode.WRITE) {
    if (isMicActuallyRecording()) {
      discardRecording = true;
      void stopVoiceCapture().finally(() => teardownMic());
    }
    if (ui.entryError) ui.entryError.textContent = '';
    renderEntryState();
    return;
  }
  renderEntryState();
  scheduleEntryDeviceRefresh('mode-talk', 0);
}

async function handleStartEntry() {
  if (entryMode === InputMode.TALK) {
    const talkReady = await validateTalkModeForEntry();
    if (!talkReady) {
      renderEntryState();
      return;
    }

    if (talkReady === 'ready-after-permission') {
      if (ui.entryError) ui.entryError.textContent = '';
      renderEntryState();
      return;
    }

    try {
      setStatusText('Activando mic…');
      await startVoiceCapture();
      setStatusText('Escuchando…');
      updateUi();
      syncAvatarMode();
    } catch (err) {
      console.error('[entry] No se pudo precalentar captura desde Empezar', err);
      if (ui.entryError) {
        ui.entryError.textContent = err?.name === 'NotReadableError'
          ? 'No se pudo iniciar el micrófono. Puede estar ocupado por otra app; reintenta o usa Escribir.'
          : 'No pudimos iniciar el micrófono. Reintenta o usa Escribir.';
      }
      renderEntryState();
      return;
    }
  }
  entryRequestedMode = entryMode;
  entryRequested = true;
  tryResolveEntryRequest();
}

function stopFeedbackPolling() {
  if (feedbackPollingTimer) {
    window.clearTimeout(feedbackPollingTimer);
    feedbackPollingTimer = null;
  }
}

function stopFeedbackFloatingPhrases() {
  if (feedbackFloatingTimer) {
    window.clearTimeout(feedbackFloatingTimer);
    feedbackFloatingTimer = null;
  }
  if (ui.feedbackFloatingLayer) ui.feedbackFloatingLayer.innerHTML = '';
}

function renderFeedbackPhraseMarkup(parts) {
  return `<code>${parts.map(([klass, text]) => `<span class="token ${klass}">${text}</span>`).join('<span class="token token-muted">&nbsp;</span>')}</code>`;
}

function randomInRange([min, max]) {
  return min + Math.random() * (max - min);
}

function nextFeedbackQuadrant(isMobile) {
  if (!ui.feedbackFloatingLayer) return { quadrant: 'topLeft', anchor: { top: [12, 18], left: [8, 16] } };

  const quadrants = isMobile ? FloatingPhraseQuadrantsMobile : FloatingPhraseQuadrantsDesktop;
  const activeCounts = Object.fromEntries(FloatingPhraseQuadrantOrder.map((name) => [name, 0]));

  Array.from(ui.feedbackFloatingLayer.children).forEach((child) => {
    const quadrant = child?.dataset?.quadrant;
    if (quadrant in activeCounts) activeCounts[quadrant] += 1;
  });

  const minCount = Math.min(...Object.values(activeCounts));
  const candidates = FloatingPhraseQuadrantOrder.filter((name) => activeCounts[name] === minCount);
  const orderedCandidates = candidates.sort((a, b) => {
    const aIdx = FloatingPhraseQuadrantOrder.indexOf(a);
    const bIdx = FloatingPhraseQuadrantOrder.indexOf(b);
    const aDistance = (aIdx - feedbackQuadrantCursor + FloatingPhraseQuadrantOrder.length) % FloatingPhraseQuadrantOrder.length;
    const bDistance = (bIdx - feedbackQuadrantCursor + FloatingPhraseQuadrantOrder.length) % FloatingPhraseQuadrantOrder.length;
    return aDistance - bDistance;
  });

  const quadrant = orderedCandidates[0] || FloatingPhraseQuadrantOrder[feedbackQuadrantCursor % FloatingPhraseQuadrantOrder.length];
  const anchors = quadrants[quadrant] || quadrants.topLeft;
  const anchor = anchors[Math.floor(Math.random() * anchors.length)];
  feedbackQuadrantCursor = (FloatingPhraseQuadrantOrder.indexOf(quadrant) + 1) % FloatingPhraseQuadrantOrder.length;
  return { quadrant, anchor };
}

function spawnFeedbackFloatingPhrase() {
  if (!$('feedbackLoadingScreen') || $('feedbackLoadingScreen').classList.contains('hidden')) return;
  if (!ui.feedbackFloatingLayer) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia('(max-width: 640px)').matches;
  const maxActive = reducedMotion ? (isMobile ? 4 : 4) : (isMobile ? 4 : 6);
  const activeCount = ui.feedbackFloatingLayer.childElementCount;
  if (activeCount >= maxActive) return;

  const phrase = FeedbackFloatingPhrases[Math.floor(Math.random() * FeedbackFloatingPhrases.length)];
  const { quadrant, anchor } = nextFeedbackQuadrant(isMobile);
  const el = document.createElement('span');
  const durationMs = reducedMotion ? 0 : 7600 + Math.random() * 2400;
  const opacity = reducedMotion ? 0.18 : 0.19 + Math.random() * 0.12;
  const scale = 0.92 + Math.random() * 0.12;
  const blur = reducedMotion ? 0 : Math.random() > 0.72 ? 0.35 : 0;

  el.className = 'feedback-floating-line';
  el.dataset.quadrant = quadrant;
  el.style.top = `${randomInRange(anchor.top).toFixed(2)}%`;
  el.style.left = `${randomInRange(anchor.left).toFixed(2)}%`;
  el.style.setProperty('--line-opacity', opacity.toFixed(2));
  el.style.setProperty('--line-scale', scale.toFixed(2));
  el.style.setProperty('--line-blur', `${blur.toFixed(2)}px`);
  el.style.setProperty('--line-duration', `${durationMs}ms`);
  el.innerHTML = renderFeedbackPhraseMarkup(phrase);
  ui.feedbackFloatingLayer.appendChild(el);

  if (reducedMotion) {
    el.style.opacity = String(opacity);
    el.style.transform = 'none';
    return;
  }

  window.setTimeout(() => el.remove(), durationMs);
}

function scheduleFeedbackFloatingPhrase() {
  if (!$('feedbackLoadingScreen') || $('feedbackLoadingScreen').classList.contains('hidden')) return;

  spawnFeedbackFloatingPhrase();

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia('(max-width: 640px)').matches;
  const nextDelay = reducedMotion ? 2400 : (isMobile ? 1150 : 900) + Math.random() * 1200;
  feedbackFloatingTimer = window.setTimeout(scheduleFeedbackFloatingPhrase, nextDelay);
}

function startFeedbackFloatingPhrases() {
  stopFeedbackFloatingPhrases();
  if (!ui.feedbackFloatingLayer) return;

  feedbackQuadrantCursor = 0;
  const initialBursts = 4;
  for (let idx = 0; idx < initialBursts; idx += 1) spawnFeedbackFloatingPhrase();
  scheduleFeedbackFloatingPhrase();
}

function closeFinalizePopover() {
  finalizePopoverOpen = false;
  $('finishConfirmPopover')?.classList.remove('visible');
}

function openFinalizePopover() {
  renderFinalizePopoverState();
  finalizePopoverOpen = true;
  $('finishConfirmPopover')?.classList.add('visible');
}

function setFeedbackStageText(status) {
  $('feedbackLoadingText').textContent = JobStageLabel[status] || 'Procesando evaluación...';
}

function showFeedbackView(mode) {
  const app = $('mainApp');
  const loading = $('feedbackLoadingScreen');
  const report = $('feedbackReportScreen');
  const error = $('feedbackErrorScreen');
  if (!app || !loading || !report || !error) return;

  app.classList.toggle('hidden', mode !== 'app');
  loading.classList.toggle('hidden', mode !== 'loading');
  report.classList.toggle('hidden', mode !== 'report');
  error.classList.toggle('hidden', mode !== 'error');

  if (mode === 'loading') startFeedbackFloatingPhrases();
  else stopFeedbackFloatingPhrases();
}

function renderFinalReport(report) {
  const root = $('feedbackReportRoot');
  if (!root || !window.FeedbackReportView) return;
  window.FeedbackReportView.renderReport(root, report);
}

async function fetchEvaluationReport(evaluationId) {
  const out = await api(`/feedback/evaluations/${evaluationId}/report`, { method: 'GET' });
  showFeedbackView('report');
  renderFinalReport(out.report);
}

async function pollEvaluationStatus(evaluationId) {
  try {
    const status = await api(`/feedback/evaluations/${evaluationId}`, { method: 'GET' });
    setFeedbackStageText(status.status);

    if (status.status === 'completed') {
      stopFeedbackPolling();
      await fetchEvaluationReport(evaluationId);
      return;
    }

    if (status.status === 'failed') {
      stopFeedbackPolling();
      $('feedbackErrorMessage').textContent = status.error || 'La evaluación no pudo completarse.';
      showFeedbackView('error');
      return;
    }

    feedbackPollingTimer = window.setTimeout(() => pollEvaluationStatus(evaluationId), 1700);
  } catch (err) {
    stopFeedbackPolling();
    $('feedbackErrorMessage').textContent = `Error de red durante la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
}

async function startFeedbackEvaluation() {
  const out = await api('/feedback/evaluations', { method: 'POST', body: JSON.stringify(ids()) });
  feedbackEvaluationId = out.evaluation_id;
  showFeedbackView('loading');
  setFeedbackStageText(out.status);
  stopFeedbackPolling();
  feedbackPollingTimer = window.setTimeout(() => pollEvaluationStatus(feedbackEvaluationId), 200);
}

function _seedDefaultIds() {
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  $('userId').value = `u_interfaz_${suffix}`;
  $('sessionId').value = `interfaz-main__${suffix}`;
}

async function runNegotiationTurnFromText(message, { allowWhileVoiceTurn = false } = {}) {
  syncSessionBoundaryReset();
  if (!message || turnInFlight || (voiceTurnInFlight && !allowWhileVoiceTurn)) return;

  turnInFlight = true;
  updateUi();
  try {
    const payload = { ...ids(), message, new_conversation: false };
    updateReplyText('...');
    setStatusText('Procesando…');
    withAvatarRuntime((runtime) => { runtime.setMode('THINKING'); runtime.setTalkLevel(0); });

    const out = await api('/negociacion/turn', { method: 'POST', body: JSON.stringify(payload) });
    updateReplyText(out.reply || '');
    armFinishButton(out.finish_button_armed);
    setLatestTraceCount(out.trace_count);

    const contract = out.entry_contract;
    $('meta').textContent =
      `session=${out.session_id} endpoint=${contract.entrypoint} runtime=execute_turn_with_contract ` +
      `overrides=${contract.overrides_applied} turn=${out.latest_turn_id || '-'} ` +
      `conversation=${out.conversation_id_after || '-'} traces=${out.trace_count}`;
    setStatusText('Listo');

    if (out.reply) {
      try {
        await playTtsWithAvatar(out.reply);
      } catch (err) {
        console.warn('[tts] Error reproduciendo TTS; fallback visual', err);
        withAvatarRuntime((runtime) => {
          runtime.setMode('SPEAKING');
          runtime.setTalkLevel(0.38);
          window.setTimeout(() => {
            runtime.setTalkLevel(0.16);
            window.setTimeout(() => {
              runtime.setTalkLevel(0);
              syncAvatarMode();
            }, 240);
          }, 260);
        });
        return;
      }
    }

    syncAvatarMode();
  } finally {
    turnInFlight = false;
    updateUi();
  }
}

async function handleSend() {
  if (turnInFlight || voiceTurnInFlight) return;
  const message = ui.textInput.value.trim();
  if (!message) return;
  await runNegotiationTurnFromText(message);
  ui.textInput.value = '';
}

$('bootstrap').onclick = async () => {
  syncSessionBoundaryReset();
  const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(ids()) });
  $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
};

$('newConv').onclick = async () => {
  const payload = ids();
  const out = await api('/negociacion/new_conversation', { method: 'POST', body: JSON.stringify(payload) });
  $('sessionId').value = out.session_id;
  lastSessionKey = `${payload.user_id}::${out.session_id}`;
  resetFinishButtonArmed();
  setLatestTraceCount(0);
  $('meta').textContent = `nueva session=${out.session_id}`;
  updateReplyText('');
};

ui.startBtn.addEventListener('click', () => {
  void handleStartEntry();
});

ui.entryModeTalk?.addEventListener('click', () => {
  setEntryMode(InputMode.TALK);
});

ui.entryModeWrite?.addEventListener('click', () => {
  setEntryMode(InputMode.WRITE);
});

ui.audioDeviceTrigger?.addEventListener('click', () => {
  toggleAudioDevicePopover();
});

ui.modeTalk.addEventListener('click', async () => {
  if (turnInFlight || voiceTurnInFlight) return;

  setInputMode(InputMode.TALK);
  if (!hasMicPermission) return;

  try {
    setStatusText('Activando mic…');
    await startVoiceCapture();
    setStatusText('Escuchando…');
    updateUi();
    syncAvatarMode();
  } catch (err) {
    console.error('[mic] No se pudo iniciar grabación', err);
    setInputMode(InputMode.WRITE);
    setStatusText('Listo');
    syncAvatarMode();
  }
});
ui.modeWrite.addEventListener('click', () => {
  if (turnInFlight) return;
  if (isRecording) {
    discardRecording = true;
    void stopVoiceCapture().finally(() => teardownMic());
  }
  setInputMode(InputMode.WRITE);
});

ui.sendTextBtn.addEventListener('click', handleSend);
async function handleFinishTurn() {
  if (turnInFlight || voiceTurnInFlight || ui.finishTurnBtn.disabled) return;
  voiceTurnInFlight = true;
  updateUi();
  setStatusText('Procesando…');
  ui.finishTurnBtn.classList.remove('highlight');
  void ui.finishTurnBtn.offsetWidth;
  ui.finishTurnBtn.classList.add('highlight');

  try {
    const blob = await stopVoiceCapture();
    teardownMic();
    if (!blob || !blob.size) throw new Error('No se capturó audio.');
    const text = await transcribeAudio(blob);
    if (!text) throw new Error('Transcripción vacía.');
    await runNegotiationTurnFromText(text, { allowWhileVoiceTurn: true });
    if (currentInputMode === InputMode.TALK) {
      setStatusText('Escuchando…');
      await startVoiceCapture();
      updateUi();
      syncAvatarMode();
    }
  } catch (err) {
    console.error('[voice] Error procesando turno hablado', err);
    setStatusText(err?.message || 'No se pudo procesar el audio.');
    if (currentInputMode === InputMode.TALK) {
      try {
        await startVoiceCapture();
        updateUi();
        syncAvatarMode();
      } catch (_) {
        // fallback a escritura solo si mic falla realmente
        setInputMode(InputMode.WRITE);
        syncAvatarMode();
      }
    }
  } finally {
    voiceTurnInFlight = false;
    updateUi();
  }
}

ui.finishTurnBtn.addEventListener('click', () => {
  void handleFinishTurn();
});


ui.finishNegotiationBtn.onclick = () => {
  if (finalizePopoverOpen) {
    closeFinalizePopover();
    return;
  }
  openFinalizePopover();
};

$('finishCancelBtn').onclick = closeFinalizePopover;

$('finishConfirmBtn').onclick = async () => {
  if (!canFinalizeConversation()) return;
  closeFinalizePopover();
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo iniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackRetryBtn').onclick = async () => {
  showFeedbackView('app');
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo reiniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackBackBtnSecondary').onclick = () => showFeedbackView('app');

document.addEventListener('click', (e) => {
  if (!ui.conversationMode) return;
  if (!ui.conversationMode.contains(e.target)) closeConversationModeMenu();
});

document.addEventListener('click', (e) => {
  if (!audioDevicePopoverOpen || !ui.audioDeviceSelector) return;
  if (e.target instanceof Node && !ui.audioDeviceSelector.contains(e.target)) closeAudioDevicePopover();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeConversationModeMenu();
    closeAudioDevicePopover();
    return;
  }

  if (e.key !== 'Enter' || e.repeat || e.shiftKey || turnInFlight || voiceTurnInFlight) return;
  const target = e.target;
  if (target instanceof HTMLTextAreaElement && currentInputMode !== InputMode.WRITE) return;

  if (currentInputMode === InputMode.WRITE) {
    e.preventDefault();
    void handleSend();
    return;
  }

  if (currentInputMode === InputMode.TALK && !ui.finishTurnBtn.disabled) {
    e.preventDefault();
    void handleFinishTurn();
  }
});

window.addEventListener('click', (ev) => {
  if (!finalizePopoverOpen) return;
  const popover = $('finishConfirmPopover');
  const btn = $('finishNegotiationBtn');
  const target = ev.target;
  if (popover && btn && target instanceof Node && !popover.contains(target) && !btn.contains(target)) closeFinalizePopover();
});

window.addEventListener('avatar-runtime-ready', () => {
  scenarioReady = true;
  tryResolveEntryRequest();
});

window.addEventListener('avatar-runtime-error', () => {
  scenarioReady = false;
  if (ui.entryError) ui.entryError.textContent = 'No se pudo cargar el escenario. Recarga para reintentar.';
  renderEntryState();
});

function bindRuntimeReadiness() {
  const runtime = window.__avatarRuntime;
  if (!runtime) return;
  if (typeof runtime.onReady === 'function') {
    runtime.onReady(() => {
      scenarioReady = true;
      tryResolveEntryRequest();
    });
  }
  if (typeof runtime.onError === 'function') {
    runtime.onError(() => {
      scenarioReady = false;
      if (ui.entryError) ui.entryError.textContent = 'No se pudo cargar el escenario. Recarga para reintentar.';
      renderEntryState();
    });
  }
  if (typeof runtime.isReady === 'function' && runtime.isReady()) {
    scenarioReady = true;
  }
}

async function bootstrapEntryDeviceBackground() {
  await syncMicPermissionState();
  await refreshEntryDevices('bootstrap');
  renderEntryDevices();
  renderEntryState();
}

function startEntryDevicePolling() {
  if (entryDeviceRefreshTimer) window.clearInterval(entryDeviceRefreshTimer);
  entryDeviceRefreshTimer = window.setInterval(() => {
    if (!isEntryOverlayVisible()) return;
    scheduleEntryDeviceRefresh('poll', 220);
  }, 3000);
}

if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', () => {
    scheduleEntryDeviceRefresh('devicechange', 140);
  });
}

window.addEventListener('focus', () => {
  scheduleEntryDeviceRefresh('focus', 120);
});

window.addEventListener('pageshow', () => {
  scheduleEntryDeviceRefresh('pageshow', 120);
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') scheduleEntryDeviceRefresh('visibilitychange', 80);
});

(async function initInterfazUsuarioSession() {
  _seedDefaultIds();
  syncSessionBoundaryReset();
  try {
    const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(ids()) });
    lastSessionKey = `${out.user_id}::${out.session_id}`;
    resetFinishButtonArmed();
    setLatestTraceCount(out.trace_count);
    $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
  } catch (err) {
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }

  if (!entryResolvedInputMode) setInputMode(InputMode.WRITE);
  bindRuntimeReadiness();
  startEntryDevicePolling();
  await bootstrapEntryDeviceBackground();
  setEntryMode(InputMode.TALK);
  renderEntryState();
  scheduleEntryDeviceRefresh('post-init', 0);
  stopInputOrb();
  renderFinalizePopoverState();
  syncAvatarMode();
})();
