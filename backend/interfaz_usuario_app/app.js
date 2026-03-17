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

let currentInputMode = InputMode.TALK;
let currentAgentMode = AgentMode.CHAT;
let finishButtonArmed = false;
let lastSessionKey = '';
let orbRaf = null;
let orbLevel = 0;
let finalizePopoverOpen = false;
let feedbackPollingTimer = null;
let feedbackEvaluationId = null;
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
let turnInFlight = false;
let voiceTurnInFlight = false;
let entryMode = InputMode.TALK;
let scenarioReady = false;
let entryRequested = false;
let entryInProgress = false;
let entryPermissionStatus = 'unknown';
let availableInputDevices = [];
let selectedEntryDeviceId = null;
const LAST_DEVICE_STORAGE_KEY = 'interfaz_usuario:last_audio_input_device';

const ui = {
  listeningGlow: $('listeningGlow'),
  entryOverlay: $('entryOverlay'),
  entryModeTalk: $('entryModeTalk'),
  entryModeWrite: $('entryModeWrite'),
  entryTalkContent: $('entryTalkContent'),
  entryWriteContent: $('entryWriteContent'),
  entrySubtitle: $('entrySubtitle'),
  entryDeviceSelect: $('entryDeviceSelect'),
  entryDeviceStatus: $('entryDeviceStatus'),
  entryError: $('entryError'),
  entryLoadingText: $('entryLoadingText'),
  startBtn: $('startBtn'),
  replyContainer: $('replyContainer'),
  lastReply: $('lastReply'),
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
  conversationMode: $('conversationMode'),
};

// Hard guard: if any stale HTML/version still injects the old Chat/Negociación selector,
// remove it at runtime so the negotiation flow remains fixed and selector-free.
$('conversationMode')?.remove();

function closeConversationModeMenu() {
  if (!ui.conversationMode) return;
  ui.conversationMode.classList.remove('open');
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
  waveAudioCtx = null;
  waveAnalyser = null;
  waveDataArray = null;
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
  discardRecording = false;
  const audioConstraints = selectedEntryDeviceId
    ? { deviceId: { exact: selectedEntryDeviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    : { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: audioConstraints,
  });

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
  const source = waveAudioCtx.createMediaStreamSource(micStream);
  source.connect(waveAnalyser);
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
  ui.finishTurnBtn.disabled = !(currentInputMode === InputMode.TALK && micOn && !isBusy);
  ui.inputOrb.classList.toggle('inactive', !micOn);
  setListeningGlowEnabled(micOn);
  updateFinishNegotiationButton();
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

function getEntryModeStartEnabled() {
  if (entryMode === InputMode.WRITE) return true;
  return entryPermissionStatus === 'granted' && Boolean(selectedEntryDeviceId);
}

function getCanEnterNow() {
  return getEntryModeStartEnabled() && scenarioReady;
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
    ? 'Prepara tu dispositivo para hablar.'
    : 'Entrarás directamente en modo escritura.';

  const startEnabled = getEntryModeStartEnabled();
  ui.startBtn.disabled = !startEnabled || entryInProgress;
  ui.startBtn.textContent = entryRequested && !getCanEnterNow() ? 'Esperando...' : 'Empezar';

  if (!scenarioReady) {
    ui.entryLoadingText.textContent = 'Cargando escenario';
  } else if (entryRequested && !getCanEnterNow()) {
    ui.entryLoadingText.textContent = 'Esperando condiciones de acceso';
  } else {
    ui.entryLoadingText.textContent = 'Escenario listo';
  }
}

function renderEntryDevices() {
  if (!ui.entryDeviceSelect) return;
  ui.entryDeviceSelect.innerHTML = '';
  if (!availableInputDevices.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'Sin dispositivos detectados';
    ui.entryDeviceSelect.appendChild(option);
    ui.entryDeviceSelect.disabled = true;
    selectedEntryDeviceId = null;
  } else {
    ui.entryDeviceSelect.disabled = false;
    availableInputDevices.forEach((device, index) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Micrófono ${index + 1}`;
      ui.entryDeviceSelect.appendChild(option);
    });
    if (!selectedEntryDeviceId || !availableInputDevices.some((d) => d.deviceId === selectedEntryDeviceId)) {
      selectedEntryDeviceId = availableInputDevices[0]?.deviceId || null;
    }
    ui.entryDeviceSelect.value = selectedEntryDeviceId || '';
  }

  if (entryPermissionStatus !== 'granted') {
    ui.entryDeviceStatus.textContent = 'Necesitamos permisos de micrófono para habilitar este modo.';
    ui.entryDeviceStatus.classList.add('error');
  } else if (!selectedEntryDeviceId) {
    ui.entryDeviceStatus.textContent = 'No encontramos un dispositivo apto para hablar.';
    ui.entryDeviceStatus.classList.add('error');
  } else {
    ui.entryDeviceStatus.textContent = 'Dispositivo listo para empezar en modo hablar.';
    ui.entryDeviceStatus.classList.remove('error');
  }
}

async function requestMicPermissions() {
  if (!navigator.mediaDevices?.getUserMedia) {
    hasMicPermission = false;
    entryPermissionStatus = 'denied';
    return false;
  }
  try {
    const constraints = selectedEntryDeviceId
      ? { audio: { deviceId: { exact: selectedEntryDeviceId } } }
      : { audio: true };
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    stream.getTracks().forEach((track) => track.stop());
    hasMicPermission = true;
    entryPermissionStatus = 'granted';
    return true;
  } catch (err) {
    console.error('[mic] Permiso denegado', err);
    hasMicPermission = false;
    entryPermissionStatus = 'denied';
    return false;
  }
}

async function refreshEntryDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    availableInputDevices = [];
    renderEntryDevices();
    renderEntryState();
    return;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    availableInputDevices = devices.filter((device) => device.kind === 'audioinput' && device.deviceId);
    const preferred = getSavedEntryDeviceId();
    if (preferred && availableInputDevices.some((d) => d.deviceId === preferred)) selectedEntryDeviceId = preferred;
  } catch (err) {
    console.warn('[entry] No se pudo enumerar dispositivos', err);
    availableInputDevices = [];
  }
  renderEntryDevices();
  renderEntryState();
}

async function prepareTalkModeForEntry() {
  if (ui.entryError) ui.entryError.textContent = '';
  const ok = await requestMicPermissions();
  await refreshEntryDevices();
  renderEntryState();
  if (!ok) {
    if (ui.entryError) ui.entryError.textContent = 'No pudimos habilitar micrófono. Puedes pasar a Escribir.';
    return false;
  }
  if (!selectedEntryDeviceId) {
    if (ui.entryError) ui.entryError.textContent = 'No se detectó un dispositivo válido para hablar.';
    return false;
  }
  return true;
}

async function finalizeEntry() {
  if (entryInProgress) return;
  if (!getCanEnterNow()) return;
  entryInProgress = true;
  ui.startBtn.disabled = true;

  if (entryMode === InputMode.WRITE) {
    setInputMode(InputMode.WRITE);
    setStatusText('Listo');
  } else {
    setInputMode(InputMode.TALK);
    setStatusText('Activando mic…');
    try {
      await startVoiceCapture();
      updateReplyText('Te escucho. Empieza a hablar cuando quieras.');
      updateUi();
      syncAvatarMode();
    } catch (err) {
      console.error('[entry] Error al iniciar modo hablar', err);
      setInputMode(InputMode.WRITE);
      setStatusText('No se pudo iniciar el micrófono. Modo escritura activado.');
    }
  }

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
    if (ui.entryError) ui.entryError.textContent = '';
    renderEntryState();
    return;
  }
  void prepareTalkModeForEntry();
}

async function handleStartEntry() {
  if (entryMode === InputMode.TALK) {
    const talkReady = await prepareTalkModeForEntry();
    if (!talkReady) {
      renderEntryState();
      return;
    }
  }
  entryRequested = true;
  tryResolveEntryRequest();
}

function stopFeedbackPolling() {
  if (feedbackPollingTimer) {
    window.clearTimeout(feedbackPollingTimer);
    feedbackPollingTimer = null;
  }
}

function closeFinalizePopover() {
  finalizePopoverOpen = false;
  $('finishConfirmPopover')?.classList.remove('visible');
}

function openFinalizePopover() {
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

ui.entryDeviceSelect?.addEventListener('change', () => {
  selectedEntryDeviceId = ui.entryDeviceSelect.value || null;
  saveEntryDeviceId(selectedEntryDeviceId);
  renderEntryDevices();
  renderEntryState();
});

ui.modeTalk.addEventListener('click', async () => {
  if (turnInFlight) return;
  setInputMode(InputMode.TALK);
  if (!hasMicPermission) return;
  try {
    await startVoiceCapture();
    updateUi();
    syncAvatarMode();
  } catch (err) {
    console.error('[mic] No se pudo iniciar grabación', err);
    setInputMode(InputMode.WRITE);
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
  closeFinalizePopover();
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo iniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackBackBtn').onclick = () => showFeedbackView('app');

$('feedbackRetryBtn').onclick = async () => {
  showFeedbackView('app');
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo reiniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

document.addEventListener('click', (e) => {
  if (!ui.conversationMode) return;
  if (!ui.conversationMode.contains(e.target)) closeConversationModeMenu();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeConversationModeMenu();
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

if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', () => {
    void refreshEntryDevices();
  });
}

(async function initInterfazUsuarioSession() {
  _seedDefaultIds();
  syncSessionBoundaryReset();
  try {
    const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(ids()) });
    lastSessionKey = `${out.user_id}::${out.session_id}`;
    resetFinishButtonArmed();
    $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
  } catch (err) {
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }
  try {
    await getOrCreateAudioContext().resume();
    await warmupFrontendTts();
  } catch (_) {}

  setInputMode(InputMode.WRITE);
  bindRuntimeReadiness();
  await refreshEntryDevices();
  setEntryMode(InputMode.TALK);
  renderEntryState();
  stopInputOrb();
  syncAvatarMode();
})();
