import { AvatarState, AudioDebug, LipsyncConfig } from './state.js';

let audioCtx = null;
let analyser = null;
let analyserData = null;
let lastAudioDebugLog = 0;
let lastMissingAnalyserLog = 0;
let silentFrameCount = 0;
let audioSource = null;
let lipHoldActive = false;
let lipsyncLevel = 0; // nivel suavizado 0..1

const debugStats = {
  frames: 0,
  rmsSum: 0,
  rmsMin: Number.POSITIVE_INFINITY,
  rmsMax: 0,
  normalizedMin: Number.POSITIVE_INFINITY,
  normalizedMax: 0,
  rawTalkMin: Number.POSITIVE_INFINITY,
  rawTalkMax: 0,
  targetMin: Number.POSITIVE_INFINITY,
  targetMax: 0,
  speakingFrames: 0,
  silentFrames: 0,
};

// === helper para un AudioContext global y reutilizable ===
function getOrCreateAudioContext() {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function cleanupAudio() {
  if (audioSource) {
    try { audioSource.stop(); } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] Error al parar source', err);
    }
    try { audioSource.disconnect(); } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] Error al desconectar source', err);
    }
    audioSource = null;
  }
  analyser = null;
  analyserData = null;
  silentFrameCount = 0;
}

function primeAudioOutput(ctx) {
  // 20ms de silencio para "enganchar" el pipeline de salida
  const frames = Math.floor(ctx.sampleRate * 0.02);
  const buf = ctx.createBuffer(1, frames, ctx.sampleRate);

  const src = ctx.createBufferSource();
  src.buffer = buf;

  const g = ctx.createGain();
  g.gain.value = 0.0;

  src.connect(g);
  g.connect(ctx.destination);

  const t0 = ctx.currentTime + 0.01;
  src.start(t0);
  src.stop(t0 + 0.02);

  src.onended = () => {
    try { src.disconnect(); } catch (_) {}
    try { g.disconnect(); } catch (_) {}
  };
}

function measureLeadingSilence(audioBuffer, thr = 0.002) {
  const ch = audioBuffer.getChannelData(0);
  const sr = audioBuffer.sampleRate;

  let first = -1;
  for (let i = 0; i < ch.length; i++) {
    if (Math.abs(ch[i]) > thr) { first = i; break; }
  }

  const lead = first < 0 ? audioBuffer.duration : first / sr;
  console.log('[audio-check]', {
    duration: Number(audioBuffer.duration.toFixed(3)),
    leadingSilenceSec: Number(lead.toFixed(3)),
    sampleRate: sr,
  });

  return lead;
}


// =========================
// Utilidades de red y audio
// =========================
function base64ToAudioData(b64, mimeType = 'audio/wav') {
  if (typeof b64 !== 'string' || !b64.trim()) {
    throw new Error('Respuesta TTS sin audio_base64 válido');
  }

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
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  const byteArray = new Uint8Array(byteNumbers);

  if (byteArray.length === 0) {
    throw new Error('Audio vacío tras decodificar base64');
  }

  const blob = new Blob([byteArray], { type: mimeType || 'audio/wav' });
  const objectUrl = URL.createObjectURL(blob);
  const arrayBuffer = byteArray.buffer.slice(
    byteArray.byteOffset,
    byteArray.byteOffset + byteArray.byteLength,
  );

  return { blob, objectUrl, mimeType: mimeType || 'audio/wav', arrayBuffer };
}

const BACKEND_URL = window.location.origin;

// =========================
// WARMUP TTS DEL FRONTEND
// =========================
let frontendTtsWarmedUp = false;

async function warmupFrontendTts() {
  if (frontendTtsWarmedUp) return;
  try {
    console.log('[warmup] Iniciando warmup del TTS...');

    const audioData = await requestTTS('Calibración de audio.');
    const ctx = getOrCreateAudioContext();

    const bufferForDecode = audioData.arrayBuffer.slice(0);
    const audioBuffer = await ctx.decodeAudioData(bufferForDecode);

    const gain = ctx.createGain();
    gain.gain.value = 0.0;

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;

    source.connect(gain);
    gain.connect(ctx.destination);

    await ctx.resume();

    const startTime = ctx.currentTime + 0.05;
    source.start(startTime);

    frontendTtsWarmedUp = true;
    console.log('[warmup] Frontend TTS OK');
  } catch (e) {
    console.warn('[warmup] Falló warmup frontend TTS:', e);
  }
}

async function requestTTS(text) {
  const res = await fetch(`${BACKEND_URL}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`Error TTS: ${res.status} ${msg}`);
  }
  const data = await res.json();
  const { audio_base64: audioBase64, audio_mime_type: audioMimeType } = data;
  if (!audioBase64) {
    throw new Error('Respuesta TTS sin audio');
  }

  return base64ToAudioData(audioBase64, audioMimeType || 'audio/wav');
}

async function sendTextToAgent(message, { mode = 'negociar', withAudio = true } = {}) {
  const lastReplyEl = document.getElementById('lastReply');
  if (lastReplyEl) lastReplyEl.textContent = '…';
  AvatarState.mode = 'THINKING';

  try {
    const endpoint = mode === 'chat' ? '/chat' : '/negociar';
    const res = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'web_user', session_id: 'sesion_demo', message }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Error agente: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const replyText = data.reply || '';
    const emotion = data.emotion || 'neutral';
    const intensity = data.tone === 'excited' ? 1.25 : data.tone === 'calm' ? 0.8 : 1.0;
    AvatarState.emotion = emotion;
    if (lastReplyEl) lastReplyEl.textContent = replyText;

    if (!withAudio || !replyText) {
      AvatarState.mode = 'IDLE';
      return;
    }

    const audioData = await requestTTS(replyText);
    await playAudioFromAudioData(audioData, { emotion, speechIntensity: intensity });
  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    if (lastReplyEl) lastReplyEl.textContent = err.message || 'Error de red';
    AvatarState.mode = 'IDLE';
  }
}

// =========================
// Loop + modo test labios (se mantiene igual)
// =========================
let lipTestActive = false;
let lipTestStartTime = 0;
let testLipsBtn = null;

async function playAudioFromAudioData(
  audioData,
  { emotion = 'neutral', speechIntensity = 1.0 } = {},
) {
  lipTestActive = false;
  if (testLipsBtn) testLipsBtn.textContent = 'Test labios';

  cleanupAudio();

  if (!audioData?.arrayBuffer) {
    throw new Error('Audio inválido (sin buffer)');
  }

  const ctx = getOrCreateAudioContext();

  let audioBuffer;
  try {
    const bufferForDecode = audioData.arrayBuffer.slice(0);
    audioBuffer = await ctx.decodeAudioData(bufferForDecode);
  } catch (err) {
    console.error('[audio] No se pudo decodificar audio_base64', err);
    AvatarState.mode = 'IDLE';
    AvatarState.talkLevel = 0;
    cleanupAudio();
    throw err;
  }

  const paddingSeconds = 0.06;
  const paddingSamples = Math.floor(audioBuffer.sampleRate * paddingSeconds);

  const paddedBuffer = ctx.createBuffer(
    audioBuffer.numberOfChannels,
    audioBuffer.length + paddingSamples,
    audioBuffer.sampleRate,
  );

  for (let ch = 0; ch < audioBuffer.numberOfChannels; ch++) {
    const src = audioBuffer.getChannelData(ch);
    const dst = paddedBuffer.getChannelData(ch);
    dst.set(src, paddingSamples);
  }

  audioBuffer = paddedBuffer;
  measureLeadingSilence(audioBuffer);

  if (AudioDebug.enabled) {
    console.log('[avatar] TTS decodificado', {
      mimeType: audioData?.mimeType,
      blobSize: audioData?.blob?.size,
      duration: audioBuffer?.duration,
    });
  }

  analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  analyserData = new Uint8Array(analyser.frequencyBinCount);

  audioSource = ctx.createBufferSource();
  audioSource.buffer = audioBuffer;

  audioSource.connect(analyser);
  analyser.connect(ctx.destination);

  await ctx.resume();
  primeAudioOutput(ctx);

  AvatarState.mode = 'SPEAKING';
  AvatarState.emotion = emotion;
  AvatarState.speechIntensity = speechIntensity;

  audioSource.onended = () => {
    if (AudioDebug.enabled) console.log('[avatar] TTS terminado');
    AvatarState.mode = 'IDLE';
    AvatarState.speechIntensity = 1.0;
    AvatarState.talkLevel = 0;
    cleanupAudio();
  };

  audioSource.start(); // empieza ya (el prime ya estabiliza)
}

export function getTalkLevelFromAudio() {
  if (!(analyser && analyserData)) {
    if (AudioDebug.enabled) {
      const now = performance.now();
      if (now - lastMissingAnalyserLog > AudioDebug.logIntervalMs) {
        lastMissingAnalyserLog = now;
        console.warn('[audio-debug] Sin señal de analyser', {
          mode: AvatarState.mode,
          hasAnalyser: !!analyser,
          hasData: !!analyserData,
        });
      }
    }
    lipsyncLevel = 0;
    return 0;
  }

  analyser.getByteTimeDomainData(analyserData);
  let sum = 0;
  for (let i = 0; i < analyserData.length; i++) {
    const v = analyserData[i] / 128 - 1;
    sum += v * v;
  }
  const rms = Math.sqrt(sum / analyserData.length);
  const intensity = AvatarState.speechIntensity || 1.0;

  const SILENCE_RMS = 0.01;
  const VOICE_RMS = 0.12;

  if (rms < SILENCE_RMS) silentFrameCount++;
  else silentFrameCount = 0;

  let target = 0.0;

  if (AvatarState.mode === 'SPEAKING') {
    if (silentFrameCount >= 2) {
      target = 0.0;
    } else {
      let t = (rms - SILENCE_RMS) / (VOICE_RMS - SILENCE_RMS);
      t = Math.max(0, Math.min(1, t));
      t *= intensity;

      if (t > 0) {
        const floor = LipsyncConfig.floorSpeaking;
        t = floor + (1.0 - floor) * t;
      }
      target = t;
    }
  } else {
    target = 0.0;
  }

  const dt = 1 / 60;
  const speed = target > lipsyncLevel ? LipsyncConfig.attack : LipsyncConfig.release;
  const smoothing = 1 - Math.exp(-dt * speed);
  lipsyncLevel += (target - lipsyncLevel) * smoothing;

  if (AudioDebug.enabled) {
    debugStats.frames += 1;
    debugStats.rmsSum += rms;
    debugStats.rmsMin = Math.min(debugStats.rmsMin, rms);
    debugStats.rmsMax = Math.max(debugStats.rmsMax, rms);
    debugStats.targetMin = Math.min(debugStats.targetMin, target);
    debugStats.targetMax = Math.max(debugStats.targetMax, target);

    if (rms >= SILENCE_RMS) debugStats.speakingFrames += 1;
    else debugStats.silentFrames += 1;

    const now = performance.now();
    if (now - lastAudioDebugLog > AudioDebug.logIntervalMs) {
      lastAudioDebugLog = now;
      const avgRms = debugStats.frames ? debugStats.rmsSum / debugStats.frames : 0;
      console.info('[audio-debug] RMS', {
        rms: Number(rms.toFixed(4)),
        lipsyncLevel: Number(lipsyncLevel.toFixed(3)),
        target: Number(target.toFixed(3)),
        stats: {
          frames: debugStats.frames,
          rmsMin: Number(debugStats.rmsMin.toFixed(4)),
          rmsMax: Number(debugStats.rmsMax.toFixed(4)),
          rmsAvg: Number(avgRms.toFixed(4)),
          targetMin: Number(debugStats.targetMin.toFixed(3)),
          targetMax: Number(debugStats.targetMax.toFixed(3)),
          speakingFrames: debugStats.speakingFrames,
          silentFrames: debugStats.silentFrames,
        },
      });

      debugStats.frames = 0;
      debugStats.rmsSum = 0;
      debugStats.rmsMin = Number.POSITIVE_INFINITY;
      debugStats.rmsMax = 0;
      debugStats.targetMin = Number.POSITIVE_INFINITY;
      debugStats.targetMax = 0;
      debugStats.speakingFrames = 0;
      debugStats.silentFrames = 0;
    }
  }

  return lipsyncLevel;
}

// =========================
// UI básica (texto → agente → TTS)
// =========================
const sendToAgentBtn = document.getElementById('sendToAgentBtn');
const userTextEl = document.getElementById('userText');
const textOnlyCheckbox = document.getElementById('textOnly');
const idleMotionToggle = document.getElementById('idleMotionToggle');
let agentSendInFlight = 0;

function setAgentSendBusy(isBusy, buttonLabel) {
  if (!sendToAgentBtn) return;
  if (isBusy) agentSendInFlight += 1;
  else agentSendInFlight = Math.max(0, agentSendInFlight - 1);

  sendToAgentBtn.disabled = agentSendInFlight > 0;
  if (agentSendInFlight === 0) sendToAgentBtn.textContent = 'Enviar al agente';
  else if (buttonLabel) sendToAgentBtn.textContent = buttonLabel;
}

function setupTextUI() {
  if (sendToAgentBtn) {
    sendToAgentBtn.addEventListener('click', async () => {
      const text = (userTextEl?.value || '').trim();
      if (!text) return;

      const modeRadio = document.querySelector('input[name="agentMode"]:checked');
      const mode = modeRadio ? modeRadio.value : 'negociar';
      const withAudio = !textOnlyCheckbox?.checked;

      // ✅ Warmup también aquí (si vas a reproducir audio)
      if (withAudio) {
        try {
          getOrCreateAudioContext().resume().catch(() => {});
          warmupFrontendTts(); // no bloquea si ya está warmed
        } catch (_) {}
      }

      setAgentSendBusy(true, 'Hablando...');
      try {
        await sendTextToAgent(text, { mode, withAudio });
      } finally {
        setAgentSendBusy(false);
      }
    });
  }

  if (userTextEl) {
    userTextEl.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        sendToAgentBtn?.click();
      }
    });
  }

  if (idleMotionToggle) {
    idleMotionToggle.addEventListener('change', (e) => {
      AvatarState.idleMotionEnabled = e.target.checked;
    });
  }
}

// =========================
// Mic simple (visual) – lo de siempre
// =========================
const micBtn = document.getElementById('micBtn');
const waveCanvas = document.getElementById('waveCanvas');
const micLabel = document.getElementById('micLabel');
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioStream = null;
let waveAudioCtx = null;
let waveAnalyser = null;
let waveDataArray = null;
let waveAnimationId = null;

let recorderMimeType = 'audio/webm;codecs=opus';

function drawWaveform() {
  if (!waveCanvas || !waveAnalyser) return;
  const ctx = waveCanvas.getContext('2d');
  const width = waveCanvas.width;
  const height = waveCanvas.height;
  waveAnimationId = requestAnimationFrame(drawWaveform);
  waveAnalyser.getByteTimeDomainData(waveDataArray);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = 'rgba(15,23,42,1)';
  ctx.fillRect(0, 0, width, height);
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#22c55e';
  ctx.beginPath();
  const sliceWidth = width / waveDataArray.length;
  let x = 0;
  for (let i = 0; i < waveDataArray.length; i++) {
    const v = waveDataArray[i] / 128.0;
    const y = (v * height) / 2;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    x += sliceWidth;
  }
  ctx.lineTo(width, height / 2);
  ctx.stroke();
}

function teardownMic() {
  try { if (waveAnimationId) cancelAnimationFrame(waveAnimationId); } catch (_) {}
  waveAnimationId = null;

  try { if (waveAudioCtx) waveAudioCtx.close(); } catch (_) {}
  waveAudioCtx = null;

  try { if (audioStream) audioStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  audioStream = null;

  waveAnalyser = null;
  waveDataArray = null;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) return alert('getUserMedia no soportado');

  // gesto de usuario → desbloqueo + warmup (igual que tu baseline)
  try {
    getOrCreateAudioContext().resume().catch(() => {});
    warmupFrontendTts();
  } catch (_) {}

  audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  recorderMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';

  mediaRecorder = new MediaRecorder(audioStream, { mimeType: recorderMimeType });

  audioChunks = [];

  mediaRecorder.ondataavailable = (e) => {
    if (e?.data && e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: recorderMimeType });
    const lastReplyEl = document.getElementById('lastReply');
    let hadError = false;

    if (micLabel) micLabel.textContent = 'Transcribiendo…';
    setAgentSendBusy(true);

    try {
      if (!blob.size) throw new Error('No se capturó audio. Intenta grabar de nuevo.');

      const audioFile = new File([blob], 'grabacion.webm', { type: recorderMimeType });
      const formData = new FormData();
      formData.append('file', audioFile);

      const res = await fetch(`${BACKEND_URL}/stt_google`, { method: 'POST', body: formData });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Error STT: ${res.status} ${errText}`);
      }

      const data = await res.json();
      const text = (data?.text || '').trim();
      if (!text) throw new Error('Transcripción vacía');

      if (micLabel) micLabel.textContent = 'Enviando…';
      const modeRadio = document.querySelector('input[name="agentMode"]:checked');
      const mode = modeRadio ? modeRadio.value : 'negociar';
      const withAudio = !textOnlyCheckbox?.checked;

      teardownMic();
      await sendTextToAgent(text, { mode, withAudio });

    } catch (err) {
      hadError = true;
      teardownMic();

      console.error('Error al transcribir/enviar audio:', err);
      const message = err?.message || 'Error de transcripción';
      if (lastReplyEl) lastReplyEl.textContent = message;
      if (micLabel) micLabel.textContent = message;
      AvatarState.mode = 'IDLE';

    } finally {
      setAgentSendBusy(false);
      if (!hadError && micLabel) micLabel.textContent = 'Pulsa el micro y habla';
    }
  };

  mediaRecorder.start(250);
  isRecording = true;
  if (micLabel) micLabel.textContent = 'Grabando…';
  AvatarState.mode = 'LISTENING';

  waveAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;
  const source = waveAudioCtx.createMediaStreamSource(audioStream);
  source.connect(waveAnalyser);
  waveDataArray = new Uint8Array(waveAnalyser.frequencyBinCount);
  drawWaveform();
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    try {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.requestData();
        setTimeout(() => {
          try { mediaRecorder.stop(); } catch (_) {}
        }, 150);
      } else {
        mediaRecorder.stop();
      }
    } catch (err) {
      console.warn('[mic] Error al detener MediaRecorder', err);
      try { mediaRecorder.stop(); } catch (_) {}
    }
  }

  isRecording = false;
  if (micLabel) micLabel.textContent = 'Procesando…';
  if (AvatarState.mode === 'LISTENING') AvatarState.mode = 'IDLE';
}

function setupMicUI() {
  if (micBtn) {
    micBtn.addEventListener('click', async () => {
      if (isRecording) {
        stopRecording();
        micBtn.textContent = '🎤 Hablar';
      } else {
        await startRecording();
        micBtn.textContent = '⏹️ Detener';
      }
    });
  }
}

// =========================
// Botón "Hablar (test)" – igual
// =========================
function setupTestTalkButton() {
  const testTalkBtn = document.createElement('button');
  testTalkBtn.textContent = 'Hablar (test)';
  Object.assign(testTalkBtn.style, {
    position: 'fixed',
    bottom: '16px',
    right: '16px',
    padding: '8px 14px',
    borderRadius: '999px',
    border: 'none',
    background: 'rgba(255,255,255,0.14)',
    color: '#ffffff',
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontSize: '12px',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    backdropFilter: 'blur(10px)',
    zIndex: '20',
  });
  document.body.appendChild(testTalkBtn);

  const startLipTest = () => {
    lipHoldActive = true;
    AvatarState.mode = 'SPEAKING';
    console.log('[test-lips] Mantener pulsado: ACTIVADO');
  };

  const stopLipTest = () => {
    lipHoldActive = false;
    AvatarState.mode = 'IDLE';
    AvatarState.talkLevel = 0;
    console.log('[test-lips] Mantener pulsado: DESACTIVADO');
  };

  testTalkBtn.addEventListener('mousedown', startLipTest);
  testTalkBtn.addEventListener('mouseup', stopLipTest);
  testTalkBtn.addEventListener('mouseleave', stopLipTest);

  testTalkBtn.addEventListener(
    'touchstart',
    (e) => { e.preventDefault(); startLipTest(); },
    { passive: false },
  );

  testTalkBtn.addEventListener(
    'touchend',
    (e) => { e.preventDefault(); stopLipTest(); },
    { passive: false },
  );
}

export function isLipHoldActive() {
  return !!lipHoldActive;
}

export function initAgentUI() {
  setupTextUI();
  setupMicUI();
  setupTestTalkButton();
}
