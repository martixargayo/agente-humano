import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

// =========================
// URL params
// =========================
const URL_PARAMS = new URLSearchParams(window.location.search);
const DEBUG_EDIT_ENABLED = URL_PARAMS.get('debugEdit') === '1';

// ============================================================================
// ✅ Debug Editor state (DEBE existir antes de animate() y keydown)
// ============================================================================
const DebugEditor = {
  enabled: DEBUG_EDIT_ENABLED,
  visible: DEBUG_EDIT_ENABLED,
  overlay: null,
  ctx: null,
  dpr: 1,
  dragging: null,
  hoverKey: null,
  activeTouchId: null,
  raycaster: new THREE.Raycaster(),
  plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), // z=0
  handlesRadius: 10,
  infoEl: null,
};

// =========================
// Estado global del avatar / audio
// =========================
const AvatarState = {
  mode: 'BOOT', // BOOT | IDLE | LISTENING | THINKING | SPEAKING
  emotion: 'neutral',
  talkLevel: 0,
  micRmsNorm: 0,
  speechIntensity: 1.0,
  idleMotionEnabled: true,
};

const InputMode = {
  TALK: 'talk',
  WRITE: 'write',
};

const AgentMode = {
  CHAT: 'chat',
  NEGOCIAR: 'negociar',
};

let currentInputMode = InputMode.TALK;
let currentAgentMode = AgentMode.CHAT;
let hasMicPermission = false;

const AudioDebug = {
  enabled: false,
  // Más sensible para ver movimiento de labios
  minRms: 0.004,  // umbral de silencio medido con TTS
  scale: 28,      // factor para llevar RMS útil al rango 0..1
  logIntervalMs: 1000,
};

// =========================
// Debug visual: regiones (strict/blend)
//   - Activa con ?debugRegions=strict | ?debugRegions=blend | ?debugRegions=1
//   - Toggle con tecla M
// =========================
const DebugView = { mode: 0 }; // 0=off, 1=strict, 2=blend

(() => {
  if (URL_PARAMS.get('audioDebug') === '1') AudioDebug.enabled = true;
  const minRms = parseFloat(URL_PARAMS.get('minRms'));
  if (!Number.isNaN(minRms)) AudioDebug.minRms = minRms;
  const scale = parseFloat(URL_PARAMS.get('levelScale'));
  if (!Number.isNaN(scale)) AudioDebug.scale = scale;
  const logIntervalMs = parseFloat(URL_PARAMS.get('logIntervalMs'));
  if (!Number.isNaN(logIntervalMs)) AudioDebug.logIntervalMs = logIntervalMs;

  const debugRegionsParam = URL_PARAMS.get('debugRegions');
  if (debugRegionsParam === '1' || debugRegionsParam === 'strict') {
    DebugView.mode = 1;
    console.info('[debug] Debug regiones strict. Pulsa M para alternar.');
  } else if (debugRegionsParam === 'blend') {
    DebugView.mode = 2;
    console.info('[debug] Debug regiones blend. Pulsa M para alternar.');
  }

  if (DEBUG_EDIT_ENABLED) {
    console.info('[debug-editor] Modo editor ACTIVADO (?debugEdit=1). Tecla E para ocultar/mostrar.');
  }

  if (AudioDebug.enabled) {
    console.info('[audio-debug] Activado', {
      minRms: AudioDebug.minRms,
      scale: AudioDebug.scale,
      logIntervalMs: AudioDebug.logIntervalMs,
    });
  } else {
    console.info('Para depurar el movimiento de labios añade ?audioDebug=1&minRms=0.01&levelScale=15 a la URL.');
  }
})();

window.addEventListener('keydown', (e) => {
  if (e.key === 'm' || e.key === 'M') {
    DebugView.mode = (DebugView.mode + 1) % 3;
    const label = DebugView.mode === 1 ? 'strict' : DebugView.mode === 2 ? 'blend' : 'off';
    console.info('[debug] Debug regiones:', label);
  }
  if (DEBUG_EDIT_ENABLED && (e.key === 'e' || e.key === 'E')) {
    DebugEditor.visible = !DebugEditor.visible;
    setDebugEditorVisible(DebugEditor.visible);
    console.info('[debug-editor] Visible:', DebugEditor.visible ? 'ON' : 'OFF');
  }
  if (DEBUG_EDIT_ENABLED) {
    const key = e.key;
    const groupMap = {
      '1': 'eye',
      '2': 'iris',
      '3': 'lid',
      '4': 'brow',
      '5': 'mouth',
      '6': 'jaw',
      '7': 'pivot',
      '8': 'seam',
      '0': 'all',
    };
    if (groupMap[key]) {
      DebugEditor.regionGroup = groupMap[key];
      console.info('[debug-editor] Grupo activo:', DebugEditor.regionGroup);
    }
    if (key === 'c' || key === 'C') {
      copyTuningJson();
    }
    if (key === 'r' || key === 'R') {
      resetTuningGroup(DebugEditor.regionGroup);
    }
  }
});

let audioCtx = null;
let analyser = null;
let analyserData = null;
let audioAnalyserConnected = false;
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

const LipsyncConfig = {
  attack: 32,          // rapidez al subir (abrir boca)
  release: 12,         // rapidez al bajar (cerrar)
  floorSpeaking: 0.12, // mínima apertura cuando hay voz clara
};

const RendererTuning = {
  maxDevicePixelRatio: Math.min(3, Math.max(1, Number.parseFloat(URL_PARAMS.get('maxDpr')) || 2)),
};

async function ensureAudioContextReady(context = getOrCreateAudioContext()) {
  if (!context || context.state === 'closed') {
    context = getOrCreateAudioContext();
  }
  if (context.state === 'suspended') {
    try {
      await context.resume();
    } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] No se pudo reanudar AudioContext', err);
    }
  }
  return context;
}

// === NUEVO: helper para un AudioContext global y reutilizable ===
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
  if (analyser && audioAnalyserConnected) {
    try { analyser.disconnect(); } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] Error al desconectar analyser', err);
    }
  }
  audioAnalyserConnected = false;
  analyser = null;
  analyserData = null;
  silentFrameCount = 0;
}

// =========================
// 1. Escena básica
// =========================
const canvas = document.getElementById('c');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.01, 100);
camera.position.set(0, 0.25, 1.9);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
function applyRendererSizing() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, RendererTuning.maxDevicePixelRatio);
  renderer.setPixelRatio(dpr);
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

applyRendererSizing();
console.info('[three] maxAttributes:', renderer.capabilities.maxAttributes);

canvas.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  console.error('[three] WebGL context perdido.');
  setStatusText('Render pausado (GPU). Intentando recuperar…');
});

canvas.addEventListener('webglcontextrestored', () => {
  console.info('[three] WebGL context restaurado.');
  setStatusText('Render recuperado.');
});

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 0.2, 0);

const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
rimLight.position.set(-2, 3, -2);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.2);
scene.add(ambient);

const clock = new THREE.Clock();
let shaderTime = 0;

// =========================
// Tuning HBL (AJUSTABLE por editor)
// =========================
window.MaskTuning = window.MaskTuning || {
  edge: 0.18,
  gamma: 1.6,
};

window.EyeTuning = window.EyeTuning || {
  leftCenterX: -0.105,
  leftCenterY: 0.225,
  leftCenterZ: 0.07,
  rightCenterX: 0.02,
  rightCenterY: 0.225,
  rightCenterZ: 0.07,
  rx: 0.055,
  ry: 0.035,
  rz: 0.025,
};

window.IrisTuning = window.IrisTuning || {
  leftCenterX: -0.102,
  leftCenterY: 0.222,
  leftCenterZ: 0.075,
  rightCenterX: 0.02,
  rightCenterY: 0.222,
  rightCenterZ: 0.075,
  rx: 0.022,
  ry: 0.016,
  rz: 0.018,
  pupilRx: 0.010,
  pupilRy: 0.008,
  pupilRz: 0.012,
  intensityBase: 0.55,
};

window.LidTuning = window.LidTuning || {
  leftCenterX: -0.105,
  leftCenterY: 0.235,
  leftCenterZ: 0.07,
  rightCenterX: 0.02,
  rightCenterY: 0.235,
  rightCenterZ: 0.07,
  rx: 0.06,
  ry: 0.03,
  rz: 0.028,
  blinkCloseScale: 0.018,
  blinkOpenScale: 0.010,
};

window.BrowTuning = window.BrowTuning || {
  leftCenterX: -0.105,
  leftCenterY: 0.27,
  leftCenterZ: 0.06,
  rightCenterX: 0.02,
  rightCenterY: 0.27,
  rightCenterZ: 0.06,
  rx: 0.07,
  ry: 0.028,
  rz: 0.02,
  raiseScale: 0.018,
  furrowScale: 0.012,
};

window.MouthTuning = window.MouthTuning || {
  centerX: -0.045,
  centerY: 0.16,
  centerZ: 0.08,
  rx: 0.10,
  ry: 0.05,
  rz: 0.06,
  forwardOffsetZ: 0.02,
  mouthTensionBase: 0.06,
  asymmetryScale: 0.08,
};

window.JawTuning = window.JawTuning || {
  centerX: -0.045,
  centerY: 0.135,
  centerZ: 0.04,
  rx: 0.14,
  ry: 0.10,
  rz: 0.10,
  jawOpenScale: 0.08,
  jawDirX: 0.0,
  jawDirY: -1.0,
  jawDirZ: 0.15,
};

window.PivotTuning = window.PivotTuning || {
  headPivotX: 0.0,
  headPivotY: -0.52,
  headPivotZ: 0.0,
  jawPivotX: 0.0,
  jawPivotY: 0.08,
  jawPivotZ: 0.02,
  neckPivotX: 0.0,
  neckPivotY: -0.52,
  neckPivotZ: 0.0,
  seamY: -0.30,
  seamSoftness: 0.08,
  neckBand: 0.12,
};

window.BehaviorTuning = window.BehaviorTuning || {
  blinkRateIdle: 14,
  blinkRateListening: 18,
  blinkRateThinking: 12,
  blinkRateSpeaking: 11,
  blinkDurationMin: 0.18,
  blinkDurationMax: 0.30,
  gazeSmoothingHL: 0.12,
  microSaccadeRate: 1.2,
  microHoldMs: 90,
  microSettleMs: 180,
  microAmpDeg: 0.4,
  breathPeriod: 4.5,
  breathAmp: 0.12,
  maxHeadDegPerSec: 40,
  maxGazeDegPerSec: 120,
  maxJawSpeed: 1.5,
  rmsFloor: 0.01,
  rmsGain: 18,
  rmsSpeakThresh: 0.22,
  rmsHoldMs: 220,
  backchannelCooldownMin: 3.5,
  backchannelCooldownMax: 5.5,
  debugMix: 0.65,
  irisPreserve: 0.45,
  irisPreservePupil: 0.70,
};

// =========================
// Refs para recalcular pesos en caliente
// =========================
let particlesGeometryRef = null;
let basePosAttrRef = null;
let w0AttrRef = null;
let w1AttrRef = null;
let w2AttrRef = null;
let w3AttrRef = null;

// =========================
// JS smoothstep (una sola vez)
// =========================
function smoothstepJS(edge0, edge1, x) {
  const d = edge1 - edge0;
  if (Math.abs(d) < 1e-8) return x < edge0 ? 0 : 1;
  const t = Math.max(0, Math.min(1, (x - edge0) / d));
  return t * t * (3 - 2 * t);
}

function clamp01(x) {
  return Math.max(0, Math.min(1, x));
}

function degToRad(d) {
  return (d * Math.PI) / 180;
}

function mulberry32(seed) {
  return function rand() {
    let t = (seed += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randRange(rand, a, b) {
  return a + (b - a) * rand();
}

function hashStringToSeed(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function emaHalfLife(dt, current, target, halfLife) {
  const hl = Math.max(halfLife, 1e-4);
  const a = 1 - Math.exp(-Math.log(2) * dt / hl);
  return current + (target - current) * a;
}

function clampRate(current, target, maxRate, dt) {
  const maxStep = maxRate * dt;
  const delta = target - current;
  const step = Math.max(-maxStep, Math.min(maxStep, delta));
  return current + step;
}

function smoothCapped(dt, current, target, halfLife, maxRate, minVal, maxVal) {
  const rateTarget = clampRate(current, target, maxRate, dt);
  const smoothed = emaHalfLife(dt, current, rateTarget, halfLife);
  return Math.max(minVal, Math.min(maxVal, smoothed));
}

function ellipsoidWeightXYZ(x, y, z, cx, cy, cz, invRx, invRy, invRz, edge, gamma) {
  const dx = (x - cx) * invRx;
  const dy = (y - cy) * invRy;
  const dz = (z - cz) * invRz;
  const d = dx * dx + dy * dy + dz * dz;
  const dc = d < 0 ? 0 : d > 1 ? 1 : d;
  const s = 1.0 - dc;
  const e = edge > 1e-6 ? edge : 1e-6;
  let t = s / e;
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  const sm = t * t * (3.0 - 2.0 * t);
  return Math.pow(sm, gamma);
}

function buildTuningSnapshot() {
  const mask = window.MaskTuning;
  const pivot = window.PivotTuning;
  const eye = window.EyeTuning;
  const iris = window.IrisTuning;
  const lid = window.LidTuning;
  const brow = window.BrowTuning;
  const mouth = window.MouthTuning;
  const jaw = window.JawTuning;

  return {
    edge: mask.edge,
    gamma: mask.gamma,
    seamY: pivot.seamY,
    seamSoft: pivot.seamSoftness,
    neckBand: pivot.neckBand,
    mouthCenterX: mouth.centerX,
    eyeLCx: eye.leftCenterX,
    eyeLCy: eye.leftCenterY,
    eyeLCz: eye.leftCenterZ,
    eyeRCx: eye.rightCenterX,
    eyeRCy: eye.rightCenterY,
    eyeRCz: eye.rightCenterZ,
    eyeInvRx: 1 / Math.max(eye.rx, 1e-6),
    eyeInvRy: 1 / Math.max(eye.ry, 1e-6),
    eyeInvRz: 1 / Math.max(eye.rz, 1e-6),
    irisLCx: iris.leftCenterX,
    irisLCy: iris.leftCenterY,
    irisLCz: iris.leftCenterZ,
    irisRCx: iris.rightCenterX,
    irisRCy: iris.rightCenterY,
    irisRCz: iris.rightCenterZ,
    irisInvRx: 1 / Math.max(iris.rx, 1e-6),
    irisInvRy: 1 / Math.max(iris.ry, 1e-6),
    irisInvRz: 1 / Math.max(iris.rz, 1e-6),
    pupilInvRx: 1 / Math.max(iris.pupilRx, 1e-6),
    pupilInvRy: 1 / Math.max(iris.pupilRy, 1e-6),
    pupilInvRz: 1 / Math.max(iris.pupilRz, 1e-6),
    lidLCx: lid.leftCenterX,
    lidLCy: lid.leftCenterY,
    lidLCz: lid.leftCenterZ,
    lidRCx: lid.rightCenterX,
    lidRCy: lid.rightCenterY,
    lidRCz: lid.rightCenterZ,
    lidInvRx: 1 / Math.max(lid.rx, 1e-6),
    lidInvRy: 1 / Math.max(lid.ry, 1e-6),
    lidInvRz: 1 / Math.max(lid.rz, 1e-6),
    browLCx: brow.leftCenterX,
    browLCy: brow.leftCenterY,
    browLCz: brow.leftCenterZ,
    browRCx: brow.rightCenterX,
    browRCy: brow.rightCenterY,
    browRCz: brow.rightCenterZ,
    browInvRx: 1 / Math.max(brow.rx, 1e-6),
    browInvRy: 1 / Math.max(brow.ry, 1e-6),
    browInvRz: 1 / Math.max(brow.rz, 1e-6),
    jawCx: jaw.centerX,
    jawCy: jaw.centerY,
    jawCz: jaw.centerZ,
    jawInvRx: 1 / Math.max(jaw.rx, 1e-6),
    jawInvRy: 1 / Math.max(jaw.ry, 1e-6),
    jawInvRz: 1 / Math.max(jaw.rz, 1e-6),
    mouthCx: mouth.centerX,
    mouthCy: mouth.centerY,
    mouthCz: mouth.centerZ,
    mouthInvRx: 1 / Math.max(mouth.rx, 1e-6),
    mouthInvRy: 1 / Math.max(mouth.ry, 1e-6),
    mouthInvRz: 1 / Math.max(mouth.rz, 1e-6),
  };
}

function seamWeightsY(y, seamY, softness, neckBand) {
  const half = Math.max(1e-6, softness) * 0.5;

  let torsoW = 1.0 - smoothstepJS(seamY - half, seamY, y);
  let headW = smoothstepJS(seamY, seamY + half, y);
  let neckW0 = clamp01(1.0 - headW - torsoW);

  const nb = Math.max(1e-6, neckBand);
  const band = smoothstepJS(seamY - nb, seamY, y) * (1.0 - smoothstepJS(seamY, seamY + nb, y));

  const neckW = neckW0 * band;
  const removed = neckW0 - neckW;

  const denom = Math.max(1e-6, headW + torsoW);
  headW += removed * (headW / denom);
  torsoW += removed * (torsoW / denom);

  return { headW, torsoW, neckW };
}

function fillWeightsFromPositions(pos, count, out, snap) {
  const {
    edge,
    gamma,
    seamY,
    seamSoft,
    neckBand,
    mouthCenterX,
    eyeLCx, eyeLCy, eyeLCz,
    eyeRCx, eyeRCy, eyeRCz,
    eyeInvRx, eyeInvRy, eyeInvRz,
    irisLCx, irisLCy, irisLCz,
    irisRCx, irisRCy, irisRCz,
    irisInvRx, irisInvRy, irisInvRz,
    pupilInvRx, pupilInvRy, pupilInvRz,
    lidLCx, lidLCy, lidLCz,
    lidRCx, lidRCy, lidRCz,
    lidInvRx, lidInvRy, lidInvRz,
    browLCx, browLCy, browLCz,
    browRCx, browRCy, browRCz,
    browInvRx, browInvRy, browInvRz,
    jawCx, jawCy, jawCz,
    jawInvRx, jawInvRy, jawInvRz,
    mouthCx, mouthCy, mouthCz,
    mouthInvRx, mouthInvRy, mouthInvRz,
  } = snap;

  const mouthSideK = 25.0;

  for (let i = 0; i < count; i++) {
    const x = pos[i * 3 + 0];
    const y = pos[i * 3 + 1];
    const z = pos[i * 3 + 2];

    const { headW, torsoW, neckW } = seamWeightsY(y, seamY, seamSoft, neckBand);

    const idx = i * 4;

    const eyeLW = ellipsoidWeightXYZ(x, y, z, eyeLCx, eyeLCy, eyeLCz, eyeInvRx, eyeInvRy, eyeInvRz, edge, gamma) * headW;
    const eyeRW = ellipsoidWeightXYZ(x, y, z, eyeRCx, eyeRCy, eyeRCz, eyeInvRx, eyeInvRy, eyeInvRz, edge, gamma) * headW;
    const irisLW = ellipsoidWeightXYZ(x, y, z, irisLCx, irisLCy, irisLCz, irisInvRx, irisInvRy, irisInvRz, edge, gamma) * eyeLW;
    const irisRW = ellipsoidWeightXYZ(x, y, z, irisRCx, irisRCy, irisRCz, irisInvRx, irisInvRy, irisInvRz, edge, gamma) * eyeRW;
    const pupilLW = ellipsoidWeightXYZ(x, y, z, irisLCx, irisLCy, irisLCz, pupilInvRx, pupilInvRy, pupilInvRz, edge, gamma) * irisLW;
    const pupilRW = ellipsoidWeightXYZ(x, y, z, irisRCx, irisRCy, irisRCz, pupilInvRx, pupilInvRy, pupilInvRz, edge, gamma) * irisRW;
    const lidLW = ellipsoidWeightXYZ(x, y, z, lidLCx, lidLCy, lidLCz, lidInvRx, lidInvRy, lidInvRz, edge, gamma) * eyeLW * (1 - irisLW);
    const lidRW = ellipsoidWeightXYZ(x, y, z, lidRCx, lidRCy, lidRCz, lidInvRx, lidInvRy, lidInvRz, edge, gamma) * eyeRW * (1 - irisRW);
    const browLW = ellipsoidWeightXYZ(x, y, z, browLCx, browLCy, browLCz, browInvRx, browInvRy, browInvRz, edge, gamma) * headW * (1 - lidLW) * (1 - irisLW);
    const browRW = ellipsoidWeightXYZ(x, y, z, browRCx, browRCy, browRCz, browInvRx, browInvRy, browInvRz, edge, gamma) * headW * (1 - lidRW) * (1 - irisRW);
    const jawW = ellipsoidWeightXYZ(x, y, z, jawCx, jawCy, jawCz, jawInvRx, jawInvRy, jawInvRz, edge, gamma) * headW;
    const mouthW = ellipsoidWeightXYZ(x, y, z, mouthCx, mouthCy, mouthCz, mouthInvRx, mouthInvRy, mouthInvRz, edge, gamma) * jawW;

    const mouthSideW = Math.tanh((x - mouthCenterX) * mouthSideK);

    out.w0Arr[idx + 0] = headW;
    out.w0Arr[idx + 1] = torsoW;
    out.w0Arr[idx + 2] = neckW;
    out.w0Arr[idx + 3] = eyeLW;

    out.w1Arr[idx + 0] = eyeRW;
    out.w1Arr[idx + 1] = irisLW;
    out.w1Arr[idx + 2] = irisRW;
    out.w1Arr[idx + 3] = pupilLW;

    out.w2Arr[idx + 0] = pupilRW;
    out.w2Arr[idx + 1] = lidLW;
    out.w2Arr[idx + 2] = lidRW;
    out.w2Arr[idx + 3] = browLW;

    out.w3Arr[idx + 0] = browRW;
    out.w3Arr[idx + 1] = jawW;
    out.w3Arr[idx + 2] = mouthW;
    out.w3Arr[idx + 3] = mouthSideW;
  }
}

// =========================
// Recalcular máscaras (API pública)
// =========================
let _maskRecomputePending = false;
let _lastRecomputeMs = 0;
let _pendingReason = null;

function logTuningSnapshot(reason = 'update') {
  console.info(`[hbl] ${reason}`);
  console.log('[hbl] Pega esto en app.js:');
  console.log('window.MaskTuning = ' + JSON.stringify(window.MaskTuning, null, 2) + ';');
  console.log('window.EyeTuning = ' + JSON.stringify(window.EyeTuning, null, 2) + ';');
  console.log('window.IrisTuning = ' + JSON.stringify(window.IrisTuning, null, 2) + ';');
  console.log('window.LidTuning = ' + JSON.stringify(window.LidTuning, null, 2) + ';');
  console.log('window.BrowTuning = ' + JSON.stringify(window.BrowTuning, null, 2) + ';');
  console.log('window.MouthTuning = ' + JSON.stringify(window.MouthTuning, null, 2) + ';');
  console.log('window.JawTuning = ' + JSON.stringify(window.JawTuning, null, 2) + ';');
  console.log('window.PivotTuning = ' + JSON.stringify(window.PivotTuning, null, 2) + ';');
}

function recomputeMasksNow() {
  if (!basePosAttrRef || !w0AttrRef) {
    console.warn('[hbl] Atributos no listos (espera a que cargue el GLB).');
    return;
  }

  const t0 = performance.now();
  const pos = basePosAttrRef.array;
  const count = basePosAttrRef.count;
  const snap = buildTuningSnapshot();

  fillWeightsFromPositions(pos, count, {
    w0Arr: w0AttrRef.array,
    w1Arr: w1AttrRef.array,
    w2Arr: w2AttrRef.array,
    w3Arr: w3AttrRef.array,
  }, snap);

  w0AttrRef.needsUpdate = true;
  w1AttrRef.needsUpdate = true;
  w2AttrRef.needsUpdate = true;
  w3AttrRef.needsUpdate = true;

  const dt = performance.now() - t0;
  if (!DebugEditor?.dragging && AudioDebug.enabled) {
    console.info('[hbl] Máscaras recalculadas', { ms: dt.toFixed(2) });
  }
}

function scheduleRecomputeMasks(reason = 'change', { immediate = false } = {}) {
  _pendingReason = reason;
  const shouldLog =
    immediate ||
    reason === 'manual' ||
    reason === 'drag:final' ||
    reason.startsWith('reset:');
  if (immediate) {
    _maskRecomputePending = false;
    _lastRecomputeMs = performance.now();
    recomputeMasksNow();
    if (shouldLog) logTuningSnapshot(reason);
    return;
  }

  if (_maskRecomputePending) return;
  _maskRecomputePending = true;
  requestAnimationFrame(() => {
    _maskRecomputePending = false;
    const now = performance.now();
    const minInterval = DebugEditor?.dragging ? 70 : 0;
    if (now - _lastRecomputeMs < minInterval) {
      scheduleRecomputeMasks(_pendingReason);
      return;
    }
    _lastRecomputeMs = now;
    recomputeMasksNow();
    if (shouldLog) logTuningSnapshot(_pendingReason);
  });
}

window.recomputeMasks = () => scheduleRecomputeMasks('manual');

// =========================
// 2. Shaders de partículas
// =========================

// Vertex: micro offsets + HBL (jaw/eyes/head) + tamaño fijo
const vertexShader = /* glsl */ `
precision highp float;

uniform float uPointSize;
uniform float uTime;
uniform float uGlobalAmp;
uniform float uClusterAmp;
uniform float uNoiseAmp;

uniform float uBreath;
uniform vec2 uTorsoSway;

uniform float uHeadYaw;
uniform float uHeadPitch;
uniform float uHeadRoll;
uniform vec3 uHeadPivot;
uniform float uNeckBlendW;

uniform float uJawOpen;
uniform vec3 uJawDir;
uniform vec3 uMouthDir;
uniform vec3 uMouthSideDir;
uniform float uMouthTension;
uniform float uMouthAsym;

uniform float uBlinkL;
uniform float uBlinkR;
uniform vec2 uGazeYawPitch;
uniform vec2 uMicroSaccade;
uniform vec2 uIrisOffset;
uniform float uBrowRaiseL;
uniform float uBrowRaiseR;
uniform float uBrowFurrow;
uniform float uSquintL;
uniform float uSquintR;

attribute vec2 aUv;
attribute vec4 aRand;
attribute vec4 aW0;
attribute vec4 aW1;
attribute vec4 aW2;
attribute vec4 aW3;

varying vec2 vUv;
varying float vIrisW;
varying float vPupilW;
varying vec3 vDebugColor;
varying float vDebugWeight;

float hash11(float p) {
  return fract(sin(p * 127.1) * 43758.5453123);
}

float hash21(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float simpleNoise(vec3 p, float t) {
  float n1 = hash21(p.xy + t);
  float n2 = hash21(p.yz - t * 0.5);
  return (n1 + n2) * 0.5;
}

mat3 rotX(float a) {
  float s = sin(a), c = cos(a);
  return mat3(
    1.0, 0.0, 0.0,
    0.0, c,   -s,
    0.0, s,   c
  );
}

mat3 rotY(float a) {
  float s = sin(a), c = cos(a);
  return mat3(
    c,   0.0, s,
    0.0, 1.0, 0.0,
    -s,  0.0, c
  );
}

mat3 rotZ(float a) {
  float s = sin(a), c = cos(a);
  return mat3(
    c,   -s,  0.0,
    s,   c,   0.0,
    0.0, 0.0, 1.0
  );
}

void main() {
  vUv = aUv;
  // Packing:
  // aW0 = (headW, torsoW, neckBlendW, eyeLW)
  // aW1 = (eyeRW, irisLW, irisRW, pupilLW)
  // aW2 = (pupilRW, lidLW, lidRW, browLW)
  // aW3 = (browRW, jawW, mouthW, mouthSide)
  // aRand = (random.xyz, clusterId)
  float aHeadW = aW0.x;
  float aTorsoW = aW0.y;
  float aNeckBlendW = aW0.z;
  float aEyeLW = aW0.w;
  float aEyeRW = aW1.x;
  float aIrisLW = aW1.y;
  float aIrisRW = aW1.z;
  float aPupilLW = aW1.w;
  float aPupilRW = aW2.x;
  float aLidLW = aW2.y;
  float aLidRW = aW2.z;
  float aBrowLW = aW2.w;
  float aBrowRW = aW3.x;
  float aJawW = aW3.y;
  float aMouthW = aW3.z;
  float aMouthSide = aW3.w;

  vIrisW = aIrisLW + aIrisRW;
  vPupilW = aPupilLW + aPupilRW;

  vec3 pos = position;
  float t = uTime;

  float globalPhase = t * 0.5;
  float swayX = sin(globalPhase + aRand.x * 6.2831);
  float swayY = cos(globalPhase * 0.8 + aRand.y * 6.2831);
  vec3 globalOffset = vec3(swayX * 0.002, swayY * 0.0016, 0.0);

  float clusterPhase = hash11(aRand.w + 10.0) * 6.2831;
  float clusterAnim = sin(t * 0.8 + clusterPhase);
  vec3 clusterDir = normalize(vec3(
    hash11(aRand.w + 1.0) - 0.5,
    hash11(aRand.w + 2.0) - 0.5,
    hash11(aRand.w + 3.0) - 0.5
  ));
  vec3 clusterOffset = clusterDir * clusterAnim * 0.0035;

  float n = simpleNoise(position * 1.5, t * 0.6);
  float micro = (n - 0.5);
  vec3 microDir = normalize(aRand.xyz * 2.0 - 1.0);
  vec3 microOffset = microDir * micro * 0.0016;

  vec3 torsoOffset = vec3(uTorsoSway.x, uTorsoSway.y, 0.0) * aTorsoW;
  vec3 breathOffset = vec3(0.0, uBreath * 0.01, uBreath * 0.005) * aTorsoW;

  vec3 gazeOffset = vec3(uIrisOffset + uMicroSaccade, 0.0);
  vec3 irisOffset = gazeOffset * (aIrisLW + aIrisRW);

  float blinkL = uBlinkL * aLidLW;
  float blinkR = uBlinkR * aLidRW;
  float squintL = uSquintL * aLidLW;
  float squintR = uSquintR * aLidRW;
  vec3 lidOffset = vec3(0.0, -(blinkL + blinkR + squintL + squintR), 0.0);

  float browL = (uBrowRaiseL - uBrowFurrow) * aBrowLW;
  float browR = (uBrowRaiseR - uBrowFurrow) * aBrowRW;
  vec3 browOffset = vec3(0.0, browL + browR, 0.0);

  vec3 jawOffset = uJawDir * uJawOpen * aJawW;
  vec3 mouthOffset = uMouthDir * uMouthTension * aMouthW;
  vec3 mouthSideOffset = uMouthSideDir * (uMouthAsym * aMouthSide) * aMouthW;

  vec3 displaced = pos
    + globalOffset * uGlobalAmp
    + clusterOffset * uClusterAmp
    + microOffset * uNoiseAmp
    + torsoOffset
    + breathOffset
    + jawOffset
    + mouthOffset
    + mouthSideOffset
    + lidOffset
    + browOffset
    + irisOffset;

  mat3 headR = rotY(uHeadYaw) * rotX(uHeadPitch) * rotZ(uHeadRoll);
  vec3 headPos = uHeadPivot + headR * (displaced - uHeadPivot);
  float headMix = clamp(aHeadW + aNeckBlendW * uNeckBlendW, 0.0, 1.0);
  vec3 finalPos = mix(displaced, headPos, headMix);

  float dbgMax = aHeadW;
  vec3 dbgColor = vec3(0.25, 0.25, 0.25);
  if (aTorsoW > dbgMax) { dbgMax = aTorsoW; dbgColor = vec3(0.25, 0.1, 0.1); }
  if (aEyeLW > dbgMax || aEyeRW > dbgMax) { dbgMax = max(aEyeLW, aEyeRW); dbgColor = vec3(0.1, 0.4, 0.9); }
  if (aIrisLW > dbgMax || aIrisRW > dbgMax) { dbgMax = max(aIrisLW, aIrisRW); dbgColor = vec3(0.1, 0.9, 0.6); }
  if (aPupilLW > dbgMax || aPupilRW > dbgMax) { dbgMax = max(aPupilLW, aPupilRW); dbgColor = vec3(0.05, 0.05, 0.05); }
  if (aLidLW > dbgMax || aLidRW > dbgMax) { dbgMax = max(aLidLW, aLidRW); dbgColor = vec3(0.8, 0.4, 0.1); }
  if (aBrowLW > dbgMax || aBrowRW > dbgMax) { dbgMax = max(aBrowLW, aBrowRW); dbgColor = vec3(0.9, 0.7, 0.1); }
  if (aJawW > dbgMax) { dbgMax = aJawW; dbgColor = vec3(0.6, 0.25, 0.7); }
  if (aMouthW > dbgMax) { dbgMax = aMouthW; dbgColor = vec3(0.3, 0.9, 0.9); }
  vDebugColor = dbgColor;
  vDebugWeight = dbgMax;

  vec4 mvPosition = modelViewMatrix * vec4(finalPos, 1.0);
  gl_PointSize = uPointSize;
  gl_Position = projectionMatrix * mvPosition;
}
`;

// Fragment: disco suave + shading iris/pupil + debug regiones
const fragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform sampler2D uColorMap;
uniform float uUseMap;
uniform int uDebugMode; // 0=off,1=strict,2=blend
uniform float uDebugMix;
uniform float uIrisPreserve;
uniform float uIrisPreservePupil;
uniform float uIrisIntensity;
uniform float uAlphaCut;

varying vec2 vUv;
varying float vIrisW;
varying float vPupilW;
varying vec3 vDebugColor;
varying float vDebugWeight;

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(p, p);
  if (r2 > 1.0) discard;

  float r = sqrt(r2);
  float circle = 1.0 - smoothstep(0.7, 1.0, r);
  if (circle < uAlphaCut) discard;

  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  float densityRaw = (texColor.r + texColor.g + texColor.b) / 3.0;
  float density = mix(1.0, densityRaw, uUseMap);

  float alpha = circle * density;
  if (alpha < uAlphaCut) discard;

  vec3 baseColor = uColor;
  vec3 finalColor = mix(baseColor * 0.6, baseColor, density);

  float irisW = clamp(vIrisW, 0.0, 1.0);
  float pupilW = clamp(vPupilW, 0.0, 1.0);
  vec3 irisColor = mix(finalColor, finalColor * 0.25, irisW * uIrisIntensity);
  irisColor = mix(irisColor, vec3(0.04), pupilW);

  if (uDebugMode == 1) {
    vec3 dbg = mix(vec3(0.0), vDebugColor, clamp(vDebugWeight, 0.0, 1.0));
    gl_FragColor = vec4(dbg, alpha);
    return;
  }

  if (uDebugMode == 2) {
    vec3 dbgMix = mix(finalColor, vDebugColor, uDebugMix);
    float preserve = mix(uIrisPreserve, uIrisPreservePupil, pupilW);
    finalColor = mix(dbgMix, irisColor, preserve);
  } else {
    finalColor = irisColor;
  }

  gl_FragColor = vec4(finalColor, alpha);
}
`;

// =========================
// 3. Generar puntos desde vértices (cara frontal) + UV
// =========================
function generateFaceParticlesFromVertices(srcGeometry) {
  const srcPos = srcGeometry.getAttribute('position');
  const srcUv = srcGeometry.getAttribute('uv');

  const vertexCount = srcPos.count;

  const v = new THREE.Vector3();
  const uv = new THREE.Vector2();

  const posArray = [];
  const uvArray = [];

  for (let i = 0; i < vertexCount; i++) {
    v.fromBufferAttribute(srcPos, i);
    if (v.z < 0.0) continue;

    posArray.push(v.x, v.y, v.z);

    if (srcUv) {
      uv.fromBufferAttribute(srcUv, i);
      uvArray.push(uv.x, uv.y);
    } else {
      uvArray.push(0.0, 0.0);
    }
  }

  const positions = new Float32Array(posArray);
  const uvs = new Float32Array(uvArray);
  const count = positions.length / 3;

  // Packing:
  // aW0 = (headW, torsoW, neckBlendW, eyeLW)
  // aW1 = (eyeRW, irisLW, irisRW, pupilLW)
  // aW2 = (pupilRW, lidLW, lidRW, browLW)
  // aW3 = (browRW, jawW, mouthW, mouthSide)
  // aRand = (random.xyz, clusterId)
  const randPack = new Float32Array(count * 4);
  const w0Pack = new Float32Array(count * 4);
  const w1Pack = new Float32Array(count * 4);
  const w2Pack = new Float32Array(count * 4);
  const w3Pack = new Float32Array(count * 4);

  for (let i = 0; i < count; i++) {
    const r = i * 4;
    randPack[r + 0] = Math.random();
    randPack[r + 1] = Math.random();
    randPack[r + 2] = Math.random();

    const x = positions[i * 3 + 0];
    const y = positions[i * 3 + 1];

    const cx = Math.floor((x + 0.4) * 10.0);
    const cy = Math.floor((y + 0.4) * 10.0);
    randPack[r + 3] = cx + cy * 10.0;
  }

  const snap = buildTuningSnapshot();
  fillWeightsFromPositions(positions, count, {
    w0Arr: w0Pack,
    w1Arr: w1Pack,
    w2Arr: w2Pack,
    w3Arr: w3Pack,
  }, snap);

  const particlesGeo = new THREE.BufferGeometry();
  particlesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  particlesGeo.setAttribute('aUv', new THREE.BufferAttribute(uvs, 2));
  particlesGeo.setAttribute('aRand', new THREE.BufferAttribute(randPack, 4));
  particlesGeo.setAttribute('aW0', new THREE.BufferAttribute(w0Pack, 4));
  particlesGeo.setAttribute('aW1', new THREE.BufferAttribute(w1Pack, 4));
  particlesGeo.setAttribute('aW2', new THREE.BufferAttribute(w2Pack, 4));
  particlesGeo.setAttribute('aW3', new THREE.BufferAttribute(w3Pack, 4));

  return particlesGeo;
}

// Tamaño de punto fijo
const POINT_SIZE = 3.5 * window.devicePixelRatio;

// =========================
// 4. Cargar GLB, fusionar capas, crear partículas
// =========================
const loader = new GLTFLoader();

let particleMaterial = null;
let particlePoints = null;

loader.load(
  './FaceVolumen.glb',
  (gltf) => {
    const meshes = [];
    gltf.scene.traverse((obj) => {
      if (obj.isMesh) meshes.push(obj);
    });

    if (!meshes.length) {
      console.error('No se encontraron mallas en el GLB');
      return;
    }

    let colorMap = null;
    for (const m of meshes) {
      if (m.material && m.material.map) {
        colorMap = m.material.map;
        break;
      }
    }
    if (!colorMap) {
      console.warn('No se ha encontrado material.map (textura de color). Se usará densidad = 1 en todo.');
    }

    const geoms = [];
    meshes.forEach((m) => {
      const g = m.geometry.clone();
      m.updateWorldMatrix(true, false);
      g.applyMatrix4(m.matrixWorld);
      geoms.push(g);
    });

    const mergeFn = BufferGeometryUtils.mergeGeometries || BufferGeometryUtils.mergeBufferGeometries;
    const mergedGeom = mergeFn(geoms, true);
    if (!mergedGeom) {
      console.error('Fallo al fusionar geometrías');
      return;
    }
    mergedGeom.computeVertexNormals();

    mergedGeom.computeBoundingBox();
    const box = mergedGeom.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    mergedGeom.translate(-center.x, -center.y, -center.z);

    const particlesGeo = generateFaceParticlesFromVertices(mergedGeom);

    // refs para edición / recompute
    particlesGeometryRef = particlesGeo;
    w0AttrRef = particlesGeo.getAttribute('aW0');
    w1AttrRef = particlesGeo.getAttribute('aW1');
    w2AttrRef = particlesGeo.getAttribute('aW2');
    w3AttrRef = particlesGeo.getAttribute('aW3');
    basePosAttrRef = particlesGeo.getAttribute('position');

    const dynamicAttrs = [w0AttrRef, w1AttrRef, w2AttrRef, w3AttrRef];
    for (const attr of dynamicAttrs) {
      attr.setUsage(THREE.DynamicDrawUsage);
    }

    const depthWriteParam = URL_PARAMS.get('depthWrite');
    const alphaTestParam = parseFloat(URL_PARAMS.get('alphaTest'));

    particleMaterial = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      depthTest: true,
      depthWrite: depthWriteParam === null ? false : depthWriteParam === '1',
      alphaTest: Number.isFinite(alphaTestParam) ? alphaTestParam : 0.0,
      blending: THREE.NormalBlending,
      uniforms: {
        uPointSize: { value: POINT_SIZE },
        uColor: { value: new THREE.Color(0xdddddd) },
        uColorMap: { value: colorMap },
        uUseMap: { value: colorMap ? 1.0 : 0.0 },

        uTime: { value: 0.0 },
        uGlobalAmp: { value: 1.5 },
        uClusterAmp: { value: 1.5 },
        uNoiseAmp: { value: 1.6 },

        // HBL
        uBreath: { value: 0.0 },
        uTorsoSway: { value: new THREE.Vector2(0, 0) },
        uHeadYaw: { value: 0.0 },
        uHeadPitch: { value: 0.0 },
        uHeadRoll: { value: 0.0 },
        uHeadPivot: { value: new THREE.Vector3(0, 0, 0) },
        uNeckBlendW: { value: 1.0 },
        uJawOpen: { value: 0.0 },
        uJawDir: { value: new THREE.Vector3(0, -1, 0.1) },
        uMouthDir: { value: new THREE.Vector3(0, -1, 0.0) },
        uMouthSideDir: { value: new THREE.Vector3(1, 0, 0) },
        uMouthTension: { value: 0.0 },
        uMouthAsym: { value: 0.0 },
        uBlinkL: { value: 0.0 },
        uBlinkR: { value: 0.0 },
        uGazeYawPitch: { value: new THREE.Vector2(0, 0) },
        uMicroSaccade: { value: new THREE.Vector2(0, 0) },
        uIrisOffset: { value: new THREE.Vector2(0, 0) },
        uIrisIntensity: { value: 0.5 },
        uBrowRaiseL: { value: 0.0 },
        uBrowRaiseR: { value: 0.0 },
        uBrowFurrow: { value: 0.0 },
        uSquintL: { value: 0.0 },
        uSquintR: { value: 0.0 },

        // DEBUG
        uDebugMode: { value: DebugView.mode },
        uDebugMix: { value: window.BehaviorTuning.debugMix },
        uIrisPreserve: { value: window.BehaviorTuning.irisPreserve },
        uIrisPreservePupil: { value: window.BehaviorTuning.irisPreservePupil },
        uAlphaCut: { value: Number.isFinite(alphaTestParam) ? alphaTestParam : 0.0 },
      },
    });

    particlePoints = new THREE.Points(particlesGeo, particleMaterial);
    particlePoints.frustumCulled = false;
    scene.add(particlePoints);

    const seedSource = URL_PARAMS.get('seed') || 'default';
    const seed = hashStringToSeed(seedSource);
    hbl = new HumanBehaviorLayer({ seed, uniformsRef: particleMaterial.uniforms });

    controls.target.set(0, 0.15, 0);
    controls.update();

    // por si se tocó NeckTuning/MouthTuning antes de cargar
    scheduleRecomputeMasks('after_load');
  },
  undefined,
  (err) => {
    console.error('Error cargando FaceVolumen.glb', err);
  },
);

// =========================
// 5. Resize
// =========================
window.addEventListener('resize', () => {
  applyRendererSizing();
  resizeDebugEditorOverlay();
  if (DebugEditor.dragging) onDebugEditorUp();
});

document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState !== 'visible') return;
  if (AvatarState.mode === 'SPEAKING' || AvatarState.mode === 'LISTENING') {
    await ensureAudioContextReady();
  }
});

// =========================
// 6. Utilidades de red y audio
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
  const arrayBuffer = byteArray.buffer.slice(
    byteArray.byteOffset,
    byteArray.byteOffset + byteArray.byteLength,
  );

  return { blob, mimeType: mimeType || 'audio/wav', arrayBuffer };
}

const BACKEND_URL = window.location.origin;

// =========================
// WARMUP TTS DEL FRONTEND
// =========================
let frontendTtsWarmedUp = false;

async function warmupFrontendTts() {
  if (frontendTtsWarmedUp) return;
  try {
    console.log("[warmup] Iniciando warmup del TTS...");

    const audioData = await requestTTS("Calibración de audio.");
    const ctx = getOrCreateAudioContext();

    const bufferForDecode = audioData.arrayBuffer.slice(0);
    const audioBuffer = await ctx.decodeAudioData(bufferForDecode);

    const gain = ctx.createGain();
    gain.gain.value = 0.0;

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;

    source.connect(gain);
    gain.connect(ctx.destination);

    await ensureAudioContextReady(ctx);

    const startTime = ctx.currentTime + 0.05;
    source.start(startTime);

    frontendTtsWarmedUp = true;
    console.log("[warmup] Frontend TTS OK");
  } catch (e) {
    console.warn("[warmup] Falló warmup frontend TTS:", e);
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

async function fetchAgentReply(message, { mode = AgentMode.CHAT } = {}) {
  const endpoint = mode === AgentMode.CHAT ? '/chat' : '/negociar';
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
  return {
    replyText: data.reply || '',
    emotion: data.emotion || 'neutral',
    intensity: data.tone === 'excited' ? 1.25 : data.tone === 'calm' ? 0.8 : 1.0,
  };
}

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
    setMode('IDLE');
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
  audioAnalyserConnected = true;

  await ensureAudioContextReady(ctx);

  setMode('SPEAKING');
  AvatarState.emotion = emotion;
  AvatarState.speechIntensity = speechIntensity;

  audioSource.onended = () => {
    if (AudioDebug.enabled) console.log('[avatar] TTS terminado');
    handleTtsEnded();
  };

  const startTime = ctx.currentTime + 0.05;
  audioSource.start(startTime);
}

const TURN_TIMINGS = {
  listenDelayMs: 180,
};

function setMode(nextMode) {
  if (AvatarState.mode === nextMode) return;
  AvatarState.mode = nextMode;
  updateUiForMode();
}

function setListeningGlowEnabled(enabled) {
  if (!ui.listeningGlow) return;
  ui.listeningGlow.classList.toggle('active', Boolean(enabled));
}

function setStatusText(message) {
  if (!ui.statusText) return;
  ui.statusText.textContent = message;
}

function handleTtsEnded() {
  AvatarState.speechIntensity = 1.0;
  AvatarState.talkLevel = 0;
  cleanupAudio();

  if (currentInputMode === InputMode.TALK) {
    setMode('IDLE');
    window.setTimeout(() => {
      enterListening();
    }, TURN_TIMINGS.listenDelayMs);
  } else {
    setMode('IDLE');
  }
}

function enterIdle() {
  setMode('IDLE');
}

async function enterSpeaking(replyText, { emotion = 'neutral', intensity = 1.0 } = {}) {
  if (!replyText) {
    setStatusText('Respuesta vacía.');
    if (currentInputMode === InputMode.TALK) {
      return enterListening();
    }
    return enterIdle();
  }

  try {
    const audioData = await requestTTS(replyText);
    await playAudioFromAudioData(audioData, { emotion, speechIntensity: intensity });
  } catch (err) {
    console.error('Error TTS:', err);
    setStatusText('No se pudo reproducir el audio.');
    if (currentInputMode === InputMode.TALK) {
      enterListening();
    } else {
      enterIdle();
    }
  }
}

async function enterListening() {
  if (currentInputMode !== InputMode.TALK) {
    return enterIdle();
  }
  if (!hasMicPermission) {
    flashStatus('Necesitamos permiso de micrófono.');
    return enterIdle();
  }
  if (AvatarState.mode === 'LISTENING' || isRecording) return;
  setMode('LISTENING');
  setStatusText('Activando mic…');
  setListeningGlowEnabled(false);
  ensureOrbLoop();
  try {
    await startRecording();
    updateUiForMode();
    if (isMicActuallyRecording()) {
      triggerFinishHighlight();
    }
  } catch (err) {
    console.error('Error al iniciar grabación:', err);
    setStatusText('No se pudo iniciar el micrófono.');
    enterIdle();
  }
}

async function enterThinking() {
  setMode('THINKING');
}

function getTalkLevelFromAudio(dt) {
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

  try {
    analyser.getByteTimeDomainData(analyserData);
  } catch (err) {
    if (AudioDebug.enabled) console.warn('[audio-debug] Falló lectura del analyser', err);
    lipsyncLevel = 0;
    return 0;
  }
  let sum = 0;
  for (let i = 0; i < analyserData.length; i++) {
    const v = analyserData[i] / 128 - 1;
    sum += v * v;
  }
  const rms = Math.sqrt(sum / analyserData.length);
  if (!Number.isFinite(rms)) {
    lipsyncLevel = 0;
    return 0;
  }
  const intensity = AvatarState.speechIntensity || 1.0;

  const minRms = AudioDebug.minRms;
  const scale = AudioDebug.scale;

  if (rms < minRms) silentFrameCount++;
  else silentFrameCount = 0;

  let target = 0.0;

  if (AvatarState.mode === 'SPEAKING') {
    if (silentFrameCount >= 2) {
      target = 0.0;
    } else {
      let t = (rms - minRms) * scale;
      t = clamp01(t);
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

  const speed = target > lipsyncLevel ? LipsyncConfig.attack : LipsyncConfig.release;
  const smoothing = 1 - Math.exp(-Math.max(dt, 1e-4) * speed);
  lipsyncLevel += (target - lipsyncLevel) * smoothing;
  if (!Number.isFinite(lipsyncLevel)) lipsyncLevel = 0;
  lipsyncLevel = clamp01(lipsyncLevel);

  if (AudioDebug.enabled) {
    debugStats.frames += 1;
    debugStats.rmsSum += rms;
    debugStats.rmsMin = Math.min(debugStats.rmsMin, rms);
    debugStats.rmsMax = Math.max(debugStats.rmsMax, rms);
    debugStats.targetMin = Math.min(debugStats.targetMin, target);
    debugStats.targetMax = Math.max(debugStats.targetMax, target);

    if (rms >= minRms) debugStats.speakingFrames += 1;
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
// Human Behavior Layer (HBL)
// =========================
class HumanBehaviorLayer {
  constructor({ seed, uniformsRef }) {
    this.uniforms = uniformsRef;
    this.rand = mulberry32(seed);
    this.time = 0;
    this.mode = 'BOOT';
    this.outputs = {
      blinkL: 0,
      blinkR: 0,
      gaze: new THREE.Vector2(),
      micro: new THREE.Vector2(),
      irisOffset: new THREE.Vector2(),
      irisIntensity: 0.5,
      jawOpen: 0,
      mouthTension: 0,
      mouthAsym: 0,
      browRaiseL: 0,
      browRaiseR: 0,
      browFurrow: 0,
      squintL: 0,
      squintR: 0,
      breath: 0,
      headYaw: 0,
      headPitch: 0,
      headRoll: 0,
      torsoSway: new THREE.Vector2(),
    };
    this.state = {
      blink: { next: 0, active: false, phase: 0, dur: 0.2, asym: 0 },
      gaze: {
        current: new THREE.Vector2(),
        target: new THREE.Vector2(),
        thinkTimer: 0,
        microState: 'idle',
        microTimer: 0,
        microHold: 0,
        microSettle: 0,
        microTarget: new THREE.Vector2(),
        microCurrent: new THREE.Vector2(),
      },
      breath: { phase: 0 },
      backchannel: { pending: false, triggerTime: 0, cooldownUntil: 0, holdMs: 0, nodPhase: 0, nodDur: 0.28, nodAmp: 0.012 },
      speech: { env: 0, prevEnv: 0, lastBoundary: -10, lastBeat: -10, energyStart: 0, energy: 0, beatAmp: 0 },
    };
    this.zeroVec2 = new THREE.Vector2();
    this.jawDirCache = new THREE.Vector3(0, -1, 0.1);
    this.mouthDirCache = new THREE.Vector3(0, -1, 0.0);
    this.jawDirLast = { x: null, y: null, z: null };
    this.mouthDirLast = { z: null };
  }

  update(dt, signals) {
    this.time += dt;
    const mode = signals.mode;
    const tuning = window.BehaviorTuning;
    const lidTuning = window.LidTuning;
    const browTuning = window.BrowTuning;
    const jawTuning = window.JawTuning;
    const mouthTuning = window.MouthTuning;
    const irisTuning = window.IrisTuning;

    if (this.mode !== mode) {
      if (this.mode === 'THINKING' && mode === 'SPEAKING') {
        if (this.rand() < 0.45) {
          this.state.blink.next = Math.min(this.state.blink.next, this.time + randRange(this.rand, 0.08, 0.2));
        }
      }
      this.mode = mode;
    }

    const blinkRate = mode === 'LISTENING'
      ? tuning.blinkRateListening
      : mode === 'THINKING'
        ? tuning.blinkRateThinking
        : mode === 'SPEAKING'
          ? tuning.blinkRateSpeaking
          : tuning.blinkRateIdle;

    const lambda = Math.max(0.01, blinkRate / 60);
    if (!this.state.blink.active && this.time >= this.state.blink.next) {
      this.state.blink.active = true;
      this.state.blink.phase = 0;
      this.state.blink.dur = randRange(this.rand, tuning.blinkDurationMin, tuning.blinkDurationMax);
      const u = Math.max(1e-6, 1 - this.rand());
      const interval = -Math.log(u) / lambda;
      this.state.blink.next = this.time + interval;
      this.state.blink.asym = randRange(this.rand, -0.03, 0.03);
    }

    const envPrev = this.state.speech.env;
    const env = emaHalfLife(dt, envPrev, signals.talkLevel, 0.05);
    const dEnv = (env - envPrev) / Math.max(dt, 1e-4);
    this.state.speech.prevEnv = envPrev;
    this.state.speech.env = env;
    if (mode === 'SPEAKING' && dEnv < -2.5 && env < 0.25 && (this.time - this.state.speech.lastBoundary) > 0.6) {
      this.state.blink.next = Math.min(this.state.blink.next, this.time + randRange(this.rand, 0.08, 0.2));
      this.state.speech.lastBoundary = this.time;
    }

    let blinkAmount = 0;
    if (this.state.blink.active) {
      this.state.blink.phase += dt;
      const t01 = clamp01(this.state.blink.phase / this.state.blink.dur);
      if (t01 < 0.35) {
        const u = t01 / 0.35;
        blinkAmount = 1 - Math.pow(1 - u, 3);
      } else {
        const u = (t01 - 0.35) / 0.65;
        blinkAmount = 1 - (u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2);
      }
      if (t01 >= 1.0) {
        this.state.blink.active = false;
        blinkAmount = 0;
      }
    }

    this.outputs.blinkL = clamp01(blinkAmount + this.state.blink.asym) * lidTuning.blinkCloseScale;
    this.outputs.blinkR = clamp01(blinkAmount - this.state.blink.asym) * lidTuning.blinkCloseScale;

    const gazeMaxYaw = degToRad(12);
    const gazeMaxPitch = degToRad(8);
    const gazeTarget = this.state.gaze.target;

    if (mode === 'THINKING') {
      if (this.state.gaze.thinkTimer <= 0) {
        this.state.gaze.thinkTimer = randRange(this.rand, 0.5, 1.2);
        gazeTarget.set(randRange(this.rand, -0.08, 0.08), randRange(this.rand, -0.12, -0.04));
      }
      this.state.gaze.thinkTimer -= dt;
      if (this.state.gaze.thinkTimer <= 0) {
        gazeTarget.set(0, 0);
      }
    } else if (mode === 'LISTENING') {
      gazeTarget.set(0, 0);
    } else if (mode === 'SPEAKING') {
      gazeTarget.set(0, 0);
    } else {
      gazeTarget.set(randRange(this.rand, -0.03, 0.03), randRange(this.rand, -0.02, 0.02));
    }

    const maxGazeRate = degToRad(tuning.maxGazeDegPerSec);
    this.state.gaze.current.x = smoothCapped(dt, this.state.gaze.current.x, gazeTarget.x, tuning.gazeSmoothingHL, maxGazeRate, -gazeMaxYaw, gazeMaxYaw);
    this.state.gaze.current.y = smoothCapped(dt, this.state.gaze.current.y, gazeTarget.y, tuning.gazeSmoothingHL, maxGazeRate, -gazeMaxPitch, gazeMaxPitch);

    if (this.state.gaze.microTimer <= 0 && this.state.gaze.microState === 'idle') {
      this.state.gaze.microState = 'step';
      this.state.gaze.microTimer = 0.06;
      const ampRad = degToRad(tuning.microAmpDeg);
      const a = randRange(this.rand, 0, Math.PI * 2);
      const r = randRange(this.rand, 0.4, 1.0) * ampRad;
      this.state.gaze.microTarget.set(Math.cos(a) * r, Math.sin(a) * r);
    }

    if (this.state.gaze.microState === 'step') {
      this.state.gaze.microTimer -= dt;
      const t01 = clamp01(1 - this.state.gaze.microTimer / 0.06);
      this.state.gaze.microCurrent.lerp(this.state.gaze.microTarget, t01);
      if (this.state.gaze.microTimer <= 0) {
        this.state.gaze.microState = 'hold';
        this.state.gaze.microTimer = tuning.microHoldMs / 1000;
      }
    } else if (this.state.gaze.microState === 'hold') {
      this.state.gaze.microTimer -= dt;
      if (this.state.gaze.microTimer <= 0) {
        this.state.gaze.microState = 'settle';
        this.state.gaze.microTimer = tuning.microSettleMs / 1000;
      }
    } else if (this.state.gaze.microState === 'settle') {
      this.state.gaze.microTimer -= dt;
      const t01 = clamp01(1 - this.state.gaze.microTimer / (tuning.microSettleMs / 1000));
      this.state.gaze.microCurrent.lerp(this.zeroVec2, t01);
      if (this.state.gaze.microTimer <= 0) {
        this.state.gaze.microState = 'idle';
        this.state.gaze.microTimer = 1 / tuning.microSaccadeRate;
        this.state.gaze.microTarget.set(0, 0);
      }
    } else {
      this.state.gaze.microTimer -= dt;
    }

    this.outputs.gaze.copy(this.state.gaze.current);
    this.outputs.micro.copy(this.state.gaze.microCurrent);

    const irisScale = Math.max(irisTuning.rx, irisTuning.ry) * 0.6;
    this.outputs.irisOffset.set(
      (this.outputs.gaze.x + this.outputs.micro.x) * irisScale,
      (this.outputs.gaze.y + this.outputs.micro.y) * irisScale,
    );
    this.outputs.irisIntensity = irisTuning.intensityBase;

    const talkMapped = clamp01(signals.talkLevel);
    const mouthIdle = mode === 'LISTENING' ? 0.06 : 0.02;
    const jawTarget = Math.max(talkMapped, mouthIdle);
    this.outputs.jawOpen = smoothCapped(dt, this.outputs.jawOpen, jawTarget, 0.08, tuning.maxJawSpeed, 0, 1) * jawTuning.jawOpenScale;

    const micBoost = mode === 'LISTENING' ? signals.micRmsNorm * 0.05 : 0;
    const tensionTarget = mouthTuning.mouthTensionBase + micBoost;
    this.outputs.mouthTension = smoothCapped(dt, this.outputs.mouthTension, tensionTarget, 0.2, 1.0, 0, 1);
    this.outputs.mouthAsym = Math.sin(this.time * 1.7 + 1.3) * mouthTuning.asymmetryScale * 0.25;

    const breathSpeed = (Math.PI * 2) / Math.max(0.01, tuning.breathPeriod);
    this.state.breath.phase += dt * breathSpeed;
    this.outputs.breath = Math.sin(this.state.breath.phase) * tuning.breathAmp;
    this.outputs.torsoSway.set(0, this.outputs.breath * 0.25);

    let nod = 0;
    if (mode === 'LISTENING') {
      if (signals.micRmsNorm > tuning.rmsSpeakThresh) {
        this.state.backchannel.holdMs += dt * 1000;
      } else {
        this.state.backchannel.holdMs = 0;
      }
      if (!this.state.backchannel.pending && this.time > this.state.backchannel.cooldownUntil) {
        if (this.state.backchannel.holdMs >= tuning.rmsHoldMs) {
          this.state.backchannel.pending = true;
          this.state.backchannel.triggerTime = this.time + randRange(this.rand, 0.3, 0.6);
          this.state.backchannel.holdMs = 0;
        }
      }
      if (this.state.backchannel.pending && this.time >= this.state.backchannel.triggerTime) {
        this.state.backchannel.pending = false;
        this.state.backchannel.nodPhase = 0;
        this.state.backchannel.nodDur = randRange(this.rand, 0.28, 0.4);
        this.state.backchannel.nodAmp = randRange(this.rand, 0.010, 0.014);
        this.state.backchannel.cooldownUntil = this.time + randRange(this.rand, tuning.backchannelCooldownMin, tuning.backchannelCooldownMax);
      }
      if (this.state.backchannel.nodPhase < this.state.backchannel.nodDur) {
        this.state.backchannel.nodPhase += dt;
        const u = clamp01(this.state.backchannel.nodPhase / this.state.backchannel.nodDur);
        nod = -this.state.backchannel.nodAmp * Math.sin(u * 3.14159);
      }
    }

    let beatPitch = 0;
    if (mode === 'SPEAKING') {
      if (this.time - this.state.speech.energyStart > 1.5) {
        this.state.speech.energyStart = this.time;
        this.state.speech.energy = 0;
      }
      if (env > 0.6 && dEnv > 1.6 && (this.time - this.state.speech.lastBeat) > 0.5) {
        const energyScale = this.state.speech.energy >= 2 ? 0.35 : 1.0;
        beatPitch = -0.008 * energyScale;
        this.state.speech.energy += 1;
        this.state.speech.lastBeat = this.time;
      }
    }

    const headYawTarget = this.outputs.gaze.x * 0.25;
    const headPitchTarget = -this.outputs.gaze.y * 0.15 + nod + beatPitch;
    this.outputs.headYaw = smoothCapped(dt, this.outputs.headYaw, headYawTarget, 0.3, degToRad(tuning.maxHeadDegPerSec), -0.35, 0.35);
    this.outputs.headPitch = smoothCapped(dt, this.outputs.headPitch, headPitchTarget, 0.3, degToRad(tuning.maxHeadDegPerSec), -0.35, 0.35);
    this.outputs.headRoll = smoothCapped(dt, this.outputs.headRoll, this.outputs.gaze.x * 0.08, 0.4, degToRad(tuning.maxHeadDegPerSec), -0.25, 0.25);

    const browBase = mode === 'THINKING' ? 0.06 : mode === 'SPEAKING' ? 0.04 : 0.02;
    const browRaise = browBase + (signals.emotion === 'excited' ? 0.05 : 0);
    const browFurrow = mode === 'THINKING' ? 0.08 : 0.02;
    const asym = Math.sin(this.time * 0.7) * 0.03;

    this.outputs.browRaiseL = smoothCapped(dt, this.outputs.browRaiseL, (browRaise + asym) * browTuning.raiseScale, 0.3, 1.0, 0, 1);
    this.outputs.browRaiseR = smoothCapped(dt, this.outputs.browRaiseR, (browRaise - asym) * browTuning.raiseScale, 0.3, 1.0, 0, 1);
    this.outputs.browFurrow = smoothCapped(dt, this.outputs.browFurrow, browFurrow * browTuning.furrowScale, 0.3, 1.0, 0, 1);

    const squintTarget = mode === 'LISTENING' ? signals.micRmsNorm * 0.04 : 0.02;
    this.outputs.squintL = smoothCapped(dt, this.outputs.squintL, squintTarget * lidTuning.blinkOpenScale, 0.3, 1.0, 0, 1);
    this.outputs.squintR = smoothCapped(dt, this.outputs.squintR, squintTarget * lidTuning.blinkOpenScale, 0.3, 1.0, 0, 1);

    return this.outputs;
  }

  apply(outputs) {
    const u = this.uniforms;
    if (!u) return;
    const pivot = window.PivotTuning;
    const jawT = window.JawTuning;
    const mouthT = window.MouthTuning;

    if (jawT.jawDirX !== this.jawDirLast.x || jawT.jawDirY !== this.jawDirLast.y || jawT.jawDirZ !== this.jawDirLast.z) {
      this.jawDirLast = { x: jawT.jawDirX, y: jawT.jawDirY, z: jawT.jawDirZ };
      this.jawDirCache.set(jawT.jawDirX, jawT.jawDirY, jawT.jawDirZ);
      if (this.jawDirCache.lengthSq() < 1e-6) this.jawDirCache.set(0, -1, 0.1);
      this.jawDirCache.normalize();
    }
    if (mouthT.forwardOffsetZ !== this.mouthDirLast.z) {
      this.mouthDirLast = { z: mouthT.forwardOffsetZ };
      this.mouthDirCache.set(0, -1, mouthT.forwardOffsetZ);
      if (this.mouthDirCache.lengthSq() < 1e-6) this.mouthDirCache.set(0, -1, 0.0);
      this.mouthDirCache.normalize();
    }

    u.uBlinkL.value = outputs.blinkL;
    u.uBlinkR.value = outputs.blinkR;
    u.uGazeYawPitch.value.copy(outputs.gaze);
    u.uMicroSaccade.value.copy(outputs.micro);
    u.uIrisOffset.value.copy(outputs.irisOffset);
    u.uIrisIntensity.value = outputs.irisIntensity;
    u.uJawOpen.value = outputs.jawOpen;
    u.uMouthTension.value = outputs.mouthTension;
    u.uMouthAsym.value = outputs.mouthAsym;
    u.uBrowRaiseL.value = outputs.browRaiseL;
    u.uBrowRaiseR.value = outputs.browRaiseR;
    u.uBrowFurrow.value = outputs.browFurrow;
    u.uSquintL.value = outputs.squintL;
    u.uSquintR.value = outputs.squintR;
    u.uBreath.value = outputs.breath;
    u.uTorsoSway.value.copy(outputs.torsoSway);
    u.uHeadYaw.value = outputs.headYaw;
    u.uHeadPitch.value = outputs.headPitch;
    u.uHeadRoll.value = outputs.headRoll;
    u.uHeadPivot.value.set(pivot.headPivotX, pivot.headPivotY, pivot.headPivotZ);
    u.uNeckBlendW.value = 1.0;
    u.uJawDir.value.copy(this.jawDirCache);
    u.uMouthDir.value.copy(this.mouthDirCache);
    u.uMouthSideDir.value.set(1, 0, 0);
    u.uDebugMode.value = DebugView.mode;
    u.uDebugMix.value = window.BehaviorTuning.debugMix;
    u.uIrisPreserve.value = window.BehaviorTuning.irisPreserve;
    u.uIrisPreservePupil.value = window.BehaviorTuning.irisPreservePupil;
  }
}

let hbl = null;

// =========================
// 7. Loop + modo test labios
// =========================
let lipTestActive = false;
let lipTestStartTime = 0;
let testLipsBtn = null;

function animate() {
  requestAnimationFrame(animate);

  let delta = clock.getDelta();
  delta = Math.min(delta, 1 / 20);
  shaderTime += delta;

  if (particleMaterial) {
    particleMaterial.uniforms.uTime.value = shaderTime;

    let targetTalk = 0.0;
    if (lipHoldActive) targetTalk = 1.0;
    else targetTalk = getTalkLevelFromAudio(delta);

    AvatarState.talkLevel = targetTalk;
    if (hbl) {
      const outputs = hbl.update(delta, {
        mode: AvatarState.mode,
        talkLevel: AvatarState.talkLevel,
        micRmsNorm: AvatarState.micRmsNorm,
        emotion: AvatarState.emotion,
        intensity: AvatarState.speechIntensity,
      });
      hbl.apply(outputs);
    }
  }

  if (particlePoints) {
    particlePoints.rotation.set(0, 0, 0);
    particlePoints.position.set(0, 0, 0);
  }

  controls.update();
  renderer.render(scene, camera);

  if (DebugEditor && DebugEditor.visible) drawDebugEditorOverlay();
}

animate();

// =========================
// 8. UI (turnos automáticos)
// =========================
const ui = {
  listeningGlow: document.getElementById('listeningGlow'),
  permissionOverlay: document.getElementById('permissionOverlay'),
  permissionError: document.getElementById('permissionError'),
  startBtn: document.getElementById('startBtn'),
  replyContainer: document.getElementById('replyContainer'),
  lastReply: document.getElementById('lastReply'),
  statusText: document.getElementById('statusText'),
  inputOrb: document.getElementById('inputOrb'),
  finishTurnBtn: document.getElementById('finishTurnBtn'),
  modeTalk: document.getElementById('modeTalk'),
  modeWrite: document.getElementById('modeWrite'),
  talkMode: document.getElementById('talkMode'),
  writeMode: document.getElementById('writeMode'),
  agentChat: document.getElementById('agentChat'),
  agentNegotiation: document.getElementById('agentNegotiation'),
  textInput: document.getElementById('textInput'),
  sendTextBtn: document.getElementById('sendTextBtn'),
};

let statusResetId = null;

function updateReplyText(text) {
  if (!ui.lastReply || !ui.replyContainer) return;
  ui.lastReply.textContent = text;
  ui.replyContainer.classList.toggle('hidden', !text);
}

function isMicActuallyRecording() {
  return Boolean(
    currentInputMode === InputMode.TALK &&
    AvatarState.mode === 'LISTENING' &&
    isRecording &&
    mediaRecorder &&
    mediaRecorder.state === 'recording' &&
    audioStream &&
    audioStream.getTracks().some((track) => track.readyState === 'live')
  );
}

function flashStatus(message, ms = 2200) {
  setStatusText(message);
  if (statusResetId) window.clearTimeout(statusResetId);
  statusResetId = window.setTimeout(() => {
    updateUiForMode();
  }, ms);
}

function updateUiForMode() {
  const micOn = isMicActuallyRecording();
  setListeningGlowEnabled(micOn);

  if (ui.inputOrb) {
    ui.inputOrb.classList.toggle('inactive', !micOn);
  }

  if (ui.finishTurnBtn) {
    ui.finishTurnBtn.disabled = !micOn;
  }

  if (AvatarState.mode === 'LISTENING') {
    setStatusText(micOn ? 'Escuchando…' : 'Activando mic…');
  }
  else if (AvatarState.mode === 'SPEAKING') setStatusText('Hablando…');
  else if (AvatarState.mode === 'THINKING') setStatusText('Procesando…');
  else if (AvatarState.mode === 'IDLE') setStatusText('Listo');
  else setStatusText('Listo');

  const canSendText = AvatarState.mode === 'IDLE' && currentInputMode === InputMode.WRITE;
  if (ui.textInput) ui.textInput.disabled = currentInputMode !== InputMode.WRITE;
  if (ui.sendTextBtn) ui.sendTextBtn.disabled = !canSendText;

  if (AvatarState.mode !== 'LISTENING') {
    stopInputOrb();
  }
}

function triggerFinishHighlight() {
  if (!ui.finishTurnBtn) return;
  ui.finishTurnBtn.classList.remove('highlight');
  void ui.finishTurnBtn.offsetWidth;
  ui.finishTurnBtn.classList.add('highlight');
  window.setTimeout(() => {
    ui.finishTurnBtn?.classList.remove('highlight');
  }, 900);
}

function setInputMode(mode) {
  currentInputMode = mode;
  if (ui.modeTalk) ui.modeTalk.classList.toggle('active', mode === InputMode.TALK);
  if (ui.modeWrite) ui.modeWrite.classList.toggle('active', mode === InputMode.WRITE);
  if (ui.modeTalk) ui.modeTalk.setAttribute('aria-selected', String(mode === InputMode.TALK));
  if (ui.modeWrite) ui.modeWrite.setAttribute('aria-selected', String(mode === InputMode.WRITE));
  if (ui.talkMode) ui.talkMode.classList.toggle('hidden', mode !== InputMode.TALK);
  if (ui.writeMode) ui.writeMode.classList.toggle('hidden', mode !== InputMode.WRITE);

  if (mode === InputMode.WRITE && AvatarState.mode === 'LISTENING') {
    cancelRecording();
  }

  updateUiForMode();
}

function setAgentMode(mode) {
  currentAgentMode = mode;
  if (ui.agentChat) ui.agentChat.classList.toggle('active', mode === AgentMode.CHAT);
  if (ui.agentChat) ui.agentChat.setAttribute('aria-pressed', String(mode === AgentMode.CHAT));
  if (ui.agentNegotiation) ui.agentNegotiation.classList.toggle('active', mode === AgentMode.NEGOCIAR);
  if (ui.agentNegotiation) {
    ui.agentNegotiation.setAttribute('aria-pressed', String(mode === AgentMode.NEGOCIAR));
  }
}

async function handleTextSend() {
  const text = (ui.textInput?.value || '').trim();
  if (!text) return;
  if (AvatarState.mode !== 'IDLE') {
    flashStatus('Espera a que termine el turno actual.');
    return;
  }

  ui.textInput.value = '';
  await sendTextTurn(text);
}

// =========================
// 9. Mic automático + visualizador RMS
// =========================
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioStream = null;
let waveAudioCtx = null;
let waveAnalyser = null;
let waveDataArray = null;
let waveAnimationId = null;
let waveMicSource = null;
let recorderMimeType = '';
let stopRecorderFallbackId = null;
let discardRecording = false;
let orbLevel = 0;

function pickSupportedRecorderMimeType() {
  if (typeof window.MediaRecorder === 'undefined') return '';
  const preferred = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4;codecs=mp4a.40.2',
    'audio/mp4',
  ];
  for (const mime of preferred) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return '';
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
    for (let i = 0; i < waveDataArray.length; i++) {
      const v = waveDataArray[i] / 128 - 1;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / waveDataArray.length);
    const tuning = window.BehaviorTuning;
    const rmsNorm = clamp01((rms - tuning.rmsFloor) * tuning.rmsGain);
    AvatarState.micRmsNorm = rmsNorm;
    level = Math.max(rmsNorm, idle);
  } else {
    AvatarState.micRmsNorm = 0;
  }

  orbLevel += (level - orbLevel) * 0.18;
  const scale = 0.85 + orbLevel * 0.55;
  ui.inputOrb.style.setProperty('--orb-scale', scale.toFixed(2));
  waveAnimationId = requestAnimationFrame(updateInputOrb);
}

function ensureOrbLoop() {
  if (!waveAnimationId) {
    waveAnimationId = requestAnimationFrame(updateInputOrb);
  }
}

function stopInputOrb() {
  if (waveAnimationId) cancelAnimationFrame(waveAnimationId);
  waveAnimationId = null;
  orbLevel = 0;
  if (ui.inputOrb) ui.inputOrb.style.setProperty('--orb-scale', '0.85');
}

function teardownMic() {
  stopInputOrb();

  if (stopRecorderFallbackId) {
    clearTimeout(stopRecorderFallbackId);
    stopRecorderFallbackId = null;
  }

  if (waveMicSource) {
    try { waveMicSource.disconnect(); } catch (_) {}
    waveMicSource = null;
  }

  waveAudioCtx = null;

  try { if (audioStream) audioStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  audioStream = null;

  waveAnalyser = null;
  waveDataArray = null;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('getUserMedia no soportado');
  }
  if (typeof window.MediaRecorder === 'undefined') {
    throw new Error('MediaRecorder no soportado en este navegador. Usa modo Escribir.');
  }

  recorderMimeType = pickSupportedRecorderMimeType();
  if (!recorderMimeType) {
    throw new Error('No hay formato de grabación compatible. Usa modo Escribir.');
  }

  teardownMic();
  discardRecording = false;
  audioStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  mediaRecorder = new MediaRecorder(audioStream, { mimeType: recorderMimeType });
  audioChunks = [];

  mediaRecorder.ondataavailable = (e) => {
    if (e?.data && e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    if (stopRecorderFallbackId) {
      clearTimeout(stopRecorderFallbackId);
      stopRecorderFallbackId = null;
    }

    const blob = new Blob(audioChunks, { type: recorderMimeType });
    audioChunks = [];

    if (discardRecording) {
      discardRecording = false;
      teardownMic();
      enterIdle();
      return;
    }

    try {
      if (!blob.size) throw new Error('No se capturó audio. Intenta grabar de nuevo.');
      const text = await transcribeAudio(blob);
      if (!text) throw new Error('Transcripción vacía');
      await sendTextTurn(text);
    } catch (err) {
      console.error('Error al transcribir/enviar audio:', err);
      updateReplyText(err?.message || 'Error de transcripción');
      flashStatus('No se pudo transcribir.');
      if (currentInputMode === InputMode.TALK) {
        enterListening();
      } else {
        enterIdle();
      }
    } finally {
      teardownMic();
    }
  };

  mediaRecorder.start(250);
  await new Promise((resolve) => setTimeout(resolve, 0));
  isRecording = mediaRecorder.state === 'recording';

  if (!audioStream.getTracks().some((track) => track.readyState === 'live')) {
    throw new Error('El micrófono no está activo.');
  }

  if (!isRecording) {
    throw new Error('No se pudo iniciar la grabación.');
  }

  waveAudioCtx = getOrCreateAudioContext();
  await ensureAudioContextReady(waveAudioCtx);
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;
  waveMicSource = waveAudioCtx.createMediaStreamSource(audioStream);
  waveMicSource.connect(waveAnalyser);
  waveDataArray = new Uint8Array(waveAnalyser.frequencyBinCount);
  ensureOrbLoop();
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

    if (!stopRecorderFallbackId) {
      stopRecorderFallbackId = window.setTimeout(() => {
        if (!isRecording) return;
        console.warn('[mic] Timeout esperando onstop. Limpiando recursos.');
        isRecording = false;
        teardownMic();
        if (AvatarState.mode !== 'SPEAKING' && AvatarState.mode !== 'THINKING') enterIdle();
      }, 3500);
    }
  }

  isRecording = false;
}

function cancelRecording() {
  if (!isRecording) return;
  discardRecording = true;
  stopRecording();
}

function finishUserTurn() {
  if (AvatarState.mode !== 'LISTENING' || !isRecording) return;
  enterThinking();
  stopRecording();
}

async function transcribeAudio(blob) {
  const audioFile = new File([blob], 'grabacion.webm', { type: recorderMimeType });
  const formData = new FormData();
  formData.append('file', audioFile);
  const res = await fetch(`${BACKEND_URL}/stt_google`, { method: 'POST', body: formData });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Error STT: ${res.status} ${errText}`);
  }

  const data = await res.json();
  return (data?.text || '').trim();
}

async function sendTextTurn(message) {
  enterThinking();
  updateReplyText('…');

  try {
    const { replyText, emotion, intensity } = await fetchAgentReply(message, { mode: currentAgentMode });
    updateReplyText(replyText);
    await enterSpeaking(replyText, { emotion, intensity });
  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    updateReplyText(err?.message || 'Error de red');
    if (currentInputMode === InputMode.TALK) {
      enterListening();
    } else {
      enterIdle();
    }
  }
}

async function requestMicPermissions() {
  if (!navigator.mediaDevices?.getUserMedia) {
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    hasMicPermission = true;
    return true;
  } catch (err) {
    console.error('[mic] Permiso denegado', err);
    hasMicPermission = false;
    return false;
  }
}

async function startConversation() {
  if (ui.permissionError) ui.permissionError.textContent = '';

  if (typeof window.MediaRecorder === 'undefined' || !pickSupportedRecorderMimeType()) {
    setInputMode(InputMode.WRITE);
    hasMicPermission = false;
    if (ui.permissionOverlay) ui.permissionOverlay.style.display = 'none';
    flashStatus('Modo voz no disponible en este navegador. Usa Escribir.');
    enterIdle();
    return;
  }

  const ok = await requestMicPermissions();
  if (!ok) {
    if (ui.permissionError) {
      ui.permissionError.textContent = 'No pudimos acceder al micrófono. Reintenta.';
    }
    return;
  }

  try {
    await ensureAudioContextReady();
    warmupFrontendTts();
  } catch (_) {}

  if (ui.permissionOverlay) ui.permissionOverlay.style.display = 'none';
  enterIdle();

  const greeting = 'Hola, ¿en qué puedo ayudarte?';
  updateReplyText(greeting);
  await enterSpeaking(greeting, { emotion: 'neutral', intensity: 1.0 });
}

if (ui.startBtn) {
  ui.startBtn.addEventListener('click', () => {
    startConversation();
  });
}

if (ui.finishTurnBtn) {
  ui.finishTurnBtn.addEventListener('click', () => {
    finishUserTurn();
  });
}

if (ui.modeTalk) {
  ui.modeTalk.addEventListener('click', () => setInputMode(InputMode.TALK));
}
if (ui.modeWrite) {
  ui.modeWrite.addEventListener('click', () => setInputMode(InputMode.WRITE));
}
if (ui.agentChat) {
  ui.agentChat.addEventListener('click', () => setAgentMode(AgentMode.CHAT));
}
if (ui.agentNegotiation) {
  ui.agentNegotiation.addEventListener('click', () => setAgentMode(AgentMode.NEGOCIAR));
}
if (ui.sendTextBtn) {
  ui.sendTextBtn.addEventListener('click', handleTextSend);
}
if (ui.textInput) {
  ui.textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleTextSend();
    }
  });
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.repeat && AvatarState.mode === 'LISTENING') {
    e.preventDefault();
    finishUserTurn();
  }
});

setInputMode(currentInputMode);
setAgentMode(currentAgentMode);
updateUiForMode();

// =========================
// 10. Botón "Hablar (test)" – solo frontend, sin backend (debug)
// =========================
if (URL_PARAMS.get('debugTalk') === '1') {
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
    setMode('SPEAKING');
    console.log('[test-lips] Mantener pulsado: ACTIVADO');
  };

  const stopLipTest = () => {
    lipHoldActive = false;
    setMode('IDLE');
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


function setDebugEditorVisible(v) {
  if (!DebugEditor.enabled) return;
  if (!DebugEditor.overlay) initDebugEditorOverlay();
  DebugEditor.visible = !!v;
  DebugEditor.overlay.style.display = DebugEditor.visible ? 'block' : 'none';
  if (DebugEditor.infoEl) DebugEditor.infoEl.style.display = DebugEditor.visible ? 'block' : 'none';
  DebugEditor.overlay.style.pointerEvents = DebugEditor.visible ? 'auto' : 'none';
}

function initDebugEditorOverlay() {
  if (!DebugEditor.enabled || DebugEditor.overlay) return;

  DebugEditor.regionGroup = 'all';
  DebugEditor.defaults = {
    MaskTuning: JSON.parse(JSON.stringify(window.MaskTuning)),
    EyeTuning: JSON.parse(JSON.stringify(window.EyeTuning)),
    IrisTuning: JSON.parse(JSON.stringify(window.IrisTuning)),
    LidTuning: JSON.parse(JSON.stringify(window.LidTuning)),
    BrowTuning: JSON.parse(JSON.stringify(window.BrowTuning)),
    MouthTuning: JSON.parse(JSON.stringify(window.MouthTuning)),
    JawTuning: JSON.parse(JSON.stringify(window.JawTuning)),
    PivotTuning: JSON.parse(JSON.stringify(window.PivotTuning)),
  };

  const overlay = document.createElement('canvas');
  overlay.id = 'debug-editor-overlay';
  Object.assign(overlay.style, {
    position: 'fixed',
    top: '0px',
    left: '0px',
    width: '100vw',
    height: '100vh',
    zIndex: '9999',
    pointerEvents: 'auto',
  });

  document.body.appendChild(overlay);
  DebugEditor.overlay = overlay;
  DebugEditor.ctx = overlay.getContext('2d');

  const info = document.createElement('div');
  Object.assign(info.style, {
    position: 'fixed',
    top: '12px',
    left: '12px',
    zIndex: '10000',
    padding: '10px 12px',
    borderRadius: '12px',
    background: 'rgba(0,0,0,0.55)',
    color: '#fff',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    fontSize: '12px',
    lineHeight: '1.35',
    maxWidth: '520px',
    userSelect: 'none',
  });
  info.innerHTML = `
    <div style="font-weight:700; margin-bottom:6px;">HBL Debug Editor</div>
    <div>Arrastra handles. Tecla <b>E</b> ocultar/mostrar.</div>
    <div style="margin-top:6px; opacity:.9">
      <div><b>1</b> Eye <b>2</b> Iris <b>3</b> Lid <b>4</b> Brow <b>5</b> Mouth <b>6</b> Jaw <b>7</b> Pivot <b>8</b> Seam <b>0</b> All</div>
      <div><b>C</b> copy JSON · <b>R</b> reset group · <b>M</b> debugRegions strict/blend/off</div>
    </div>
    <div style="margin-top:6px; opacity:.85">Handles: center, rx/ry, rz (drag vertical), cz (centerZ).</div>
  `;
  document.body.appendChild(info);
  DebugEditor.infoEl = info;

  overlay.addEventListener('mousemove', onDebugEditorMove);
  overlay.addEventListener('mousedown', onDebugEditorDown);
  window.addEventListener('mouseup', onDebugEditorUp);

  overlay.addEventListener('touchstart', onDebugEditorTouchStart, { passive: false });
  overlay.addEventListener('touchmove', onDebugEditorTouchMove, { passive: false });
  overlay.addEventListener('touchend', onDebugEditorTouchEnd, { passive: false });
  overlay.addEventListener('touchcancel', onDebugEditorTouchCancel, { passive: false });

  resizeDebugEditorOverlay();
  setDebugEditorVisible(true);
}

function resizeDebugEditorOverlay() {
  if (!DebugEditor.overlay) return;
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  DebugEditor.dpr = dpr;
  DebugEditor.overlay.width = Math.floor(window.innerWidth * dpr);
  DebugEditor.overlay.height = Math.floor(window.innerHeight * dpr);
  DebugEditor.overlay.style.width = '100vw';
  DebugEditor.overlay.style.height = '100vh';
  const ctx = DebugEditor.ctx;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function getMouseNDC(clientX, clientY) {
  return {
    x: (clientX / window.innerWidth) * 2 - 1,
    y: -(clientY / window.innerHeight) * 2 + 1,
  };
}

function screenProject(x, y, z = 0) {
  const v = new THREE.Vector3(x, y, z).project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * window.innerWidth,
    y: (-v.y * 0.5 + 0.5) * window.innerHeight,
  };
}

function rayToPlane(clientX, clientY) {
  const ndc = getMouseNDC(clientX, clientY);
  DebugEditor.raycaster.setFromCamera(ndc, camera);
  const out = new THREE.Vector3();
  const hit = DebugEditor.raycaster.ray.intersectPlane(DebugEditor.plane, out);
  return hit ? out.clone() : null;
}

function copyTuningJson() {
  const payload = {
    MaskTuning: window.MaskTuning,
    EyeTuning: window.EyeTuning,
    IrisTuning: window.IrisTuning,
    LidTuning: window.LidTuning,
    BrowTuning: window.BrowTuning,
    MouthTuning: window.MouthTuning,
    JawTuning: window.JawTuning,
    PivotTuning: window.PivotTuning,
    BehaviorTuning: window.BehaviorTuning,
  };
  const text = JSON.stringify(payload, null, 2);
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      console.info('[debug-editor] JSON copiado al portapapeles.');
    }).catch(() => {
      fallbackCopyToClipboard(text);
    });
  } else {
    fallbackCopyToClipboard(text);
  }
}

function fallbackCopyToClipboard(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch (_) {}
  document.body.removeChild(ta);
  if (copied) {
    console.info('[debug-editor] JSON copiado (fallback).');
  } else {
    console.info('[debug-editor] Copia manual:', text);
  }
}
function resetTuningGroup(group) {
  const d = DebugEditor.defaults;
  if (!d) return;
  const restore = (key) => { window[key] = JSON.parse(JSON.stringify(d[key])); };
  if (group === 'eye') restore('EyeTuning');
  if (group === 'iris') restore('IrisTuning');
  if (group === 'lid') restore('LidTuning');
  if (group === 'brow') restore('BrowTuning');
  if (group === 'mouth') restore('MouthTuning');
  if (group === 'jaw') restore('JawTuning');
  if (group === 'pivot' || group === 'seam') restore('PivotTuning');
  if (group === 'all') {
    restore('MaskTuning');
    restore('EyeTuning');
    restore('IrisTuning');
    restore('LidTuning');
    restore('BrowTuning');
    restore('MouthTuning');
    restore('JawTuning');
    restore('PivotTuning');
  }
  scheduleRecomputeMasks(`reset:${group}`);
}

function buildRegionDefs() {
  return [
    { key: 'eyeL', group: 'eye', color: 'rgba(80,180,255,0.95)', tuning: window.EyeTuning, prefix: 'left' },
    { key: 'eyeR', group: 'eye', color: 'rgba(80,180,255,0.95)', tuning: window.EyeTuning, prefix: 'right' },
    { key: 'irisL', group: 'iris', color: 'rgba(80,255,170,0.95)', tuning: window.IrisTuning, prefix: 'left' },
    { key: 'irisR', group: 'iris', color: 'rgba(80,255,170,0.95)', tuning: window.IrisTuning, prefix: 'right' },
    { key: 'lidL', group: 'lid', color: 'rgba(255,170,80,0.95)', tuning: window.LidTuning, prefix: 'left' },
    { key: 'lidR', group: 'lid', color: 'rgba(255,170,80,0.95)', tuning: window.LidTuning, prefix: 'right' },
    { key: 'browL', group: 'brow', color: 'rgba(255,220,80,0.95)', tuning: window.BrowTuning, prefix: 'left' },
    { key: 'browR', group: 'brow', color: 'rgba(255,220,80,0.95)', tuning: window.BrowTuning, prefix: 'right' },
    { key: 'mouth', group: 'mouth', color: 'rgba(90,230,230,0.95)', tuning: window.MouthTuning, prefix: null },
    { key: 'jaw', group: 'jaw', color: 'rgba(180,120,240,0.95)', tuning: window.JawTuning, prefix: null },
  ];
}

function getCenter(tuning, prefix) {
  const pre = prefix ? `${prefix}Center` : 'center';
  return {
    x: tuning[`${pre}X`],
    y: tuning[`${pre}Y`],
    z: tuning[`${pre}Z`],
  };
}

function setCenter(tuning, prefix, val) {
  const pre = prefix ? `${prefix}Center` : 'center';
  tuning[`${pre}X`] = val.x;
  tuning[`${pre}Y`] = val.y;
  tuning[`${pre}Z`] = val.z;
}

function getRadius(tuning) {
  return { rx: tuning.rx, ry: tuning.ry, rz: tuning.rz };
}

function setRadius(tuning, r) {
  tuning.rx = Math.max(1e-6, r.rx);
  tuning.ry = Math.max(1e-6, r.ry);
  tuning.rz = Math.max(1e-6, r.rz);
}

function getHandlesModel() {
  const handles = [];
  const group = DebugEditor.regionGroup;

  for (const def of buildRegionDefs()) {
    if (group !== 'all' && group !== def.group) continue;
    const c = getCenter(def.tuning, def.prefix);
    const r = getRadius(def.tuning);
    handles.push({ key: `${def.key}_center`, color: def.color, type: 'center', def, pos: { x: c.x, y: c.y, z: c.z } });
    handles.push({ key: `${def.key}_rx`, color: def.color, type: 'rx', def, pos: { x: c.x + r.rx, y: c.y, z: c.z } });
    handles.push({ key: `${def.key}_ry`, color: def.color, type: 'ry', def, pos: { x: c.x, y: c.y + r.ry, z: c.z } });
    handles.push({ key: `${def.key}_rz`, color: def.color, type: 'rz', def, pos: { x: c.x, y: c.y - r.ry, z: c.z } });
    handles.push({ key: `${def.key}_cz`, color: def.color, type: 'cz', def, pos: { x: c.x - r.rx, y: c.y, z: c.z } });
  }

  if (group === 'pivot' || group === 'all') {
    const p = window.PivotTuning;
    handles.push({ key: 'headPivot', color: 'rgba(255,80,80,0.95)', type: 'pivot', pos: { x: p.headPivotX, y: p.headPivotY, z: p.headPivotZ } });
    handles.push({ key: 'jawPivot', color: 'rgba(255,120,120,0.95)', type: 'pivot', pos: { x: p.jawPivotX, y: p.jawPivotY, z: p.jawPivotZ } });
    handles.push({ key: 'neckPivot', color: 'rgba(255,160,160,0.95)', type: 'pivot', pos: { x: p.neckPivotX, y: p.neckPivotY, z: p.neckPivotZ } });
  }

  if (group === 'seam' || group === 'all') {
    const p = window.PivotTuning;
    handles.push({ key: 'seamY', color: 'rgba(255,200,200,0.95)', type: 'seam', pos: { x: 0, y: p.seamY, z: 0 } });
    handles.push({ key: 'seamSoft', color: 'rgba(255,200,200,0.95)', type: 'seamSoft', pos: { x: 0.05, y: p.seamY + p.seamSoftness, z: 0 } });
    handles.push({ key: 'neckBand', color: 'rgba(255,200,200,0.95)', type: 'neckBand', pos: { x: -0.05, y: p.seamY - p.neckBand, z: 0 } });
  }

  return handles;
}

function pickHandle(clientX, clientY) {
  const handles = getHandlesModel();
  let best = null;
  let bestD = Infinity;
  for (const handle of handles) {
    const s = screenProject(handle.pos.x, handle.pos.y, handle.pos.z || 0);
    const dx = s.x - clientX;
    const dy = s.y - clientY;
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < DebugEditor.handlesRadius && d < bestD) {
      bestD = d;
      best = handle.key;
    }
  }
  return best;
}

function applyDrag(key, worldPoint, startPoint, startSnapshot) {
  const handles = getHandlesModel();
  const handle = handles.find((h) => h.key === key);
  if (!handle) return;

  if (handle.type === 'pivot') {
    const p = window.PivotTuning;
    if (key === 'headPivot') {
      p.headPivotX = startSnapshot.PivotTuning.headPivotX + (worldPoint.x - startPoint.x);
      p.headPivotY = startSnapshot.PivotTuning.headPivotY + (worldPoint.y - startPoint.y);
    } else if (key === 'jawPivot') {
      p.jawPivotX = startSnapshot.PivotTuning.jawPivotX + (worldPoint.x - startPoint.x);
      p.jawPivotY = startSnapshot.PivotTuning.jawPivotY + (worldPoint.y - startPoint.y);
    } else if (key === 'neckPivot') {
      p.neckPivotX = startSnapshot.PivotTuning.neckPivotX + (worldPoint.x - startPoint.x);
      p.neckPivotY = startSnapshot.PivotTuning.neckPivotY + (worldPoint.y - startPoint.y);
    }
    scheduleRecomputeMasks(`drag:${key}`);
    return;
  }

  if (handle.type === 'seam') {
    const p = window.PivotTuning;
    p.seamY = startSnapshot.PivotTuning.seamY + (worldPoint.y - startPoint.y);
    scheduleRecomputeMasks(`drag:${key}`);
    return;
  }

  if (handle.type === 'seamSoft') {
    const p = window.PivotTuning;
    p.seamSoftness = Math.max(1e-4, startSnapshot.PivotTuning.seamSoftness + (worldPoint.y - startPoint.y));
    scheduleRecomputeMasks(`drag:${key}`);
    return;
  }

  if (handle.type === 'neckBand') {
    const p = window.PivotTuning;
    p.neckBand = Math.max(1e-4, startSnapshot.PivotTuning.neckBand + (worldPoint.y - startPoint.y));
    scheduleRecomputeMasks(`drag:${key}`);
    return;
  }

  const def = handle.def;
  const tuning = def.tuning;
  const prefix = def.prefix;
  const center = getCenter(tuning, prefix);
  const radius = getRadius(tuning);
  const dx = worldPoint.x - startPoint.x;
  const dy = worldPoint.y - startPoint.y;

  if (handle.type === 'center') {
    setCenter(tuning, prefix, { x: center.x + dx, y: center.y + dy, z: center.z });
  } else if (handle.type === 'cz') {
    setCenter(tuning, prefix, { x: center.x, y: center.y, z: center.z + dy });
  } else if (handle.type === 'rx') {
    setRadius(tuning, { rx: radius.rx + dx, ry: radius.ry, rz: radius.rz });
  } else if (handle.type === 'ry') {
    setRadius(tuning, { rx: radius.rx, ry: radius.ry + dy, rz: radius.rz });
  } else if (handle.type === 'rz') {
    setRadius(tuning, { rx: radius.rx, ry: radius.ry, rz: radius.rz + dy });
  }

  scheduleRecomputeMasks(`drag:${key}`);
}

function onDebugEditorDown(e) {
  if (!DebugEditor.visible) return;
  const key = pickHandle(e.clientX, e.clientY);
  if (!key) return;

  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  DebugEditor.dragging = {
    key,
    startPoint: p,
    startSnapshot: {
      MaskTuning: { ...window.MaskTuning },
      EyeTuning: { ...window.EyeTuning },
      IrisTuning: { ...window.IrisTuning },
      LidTuning: { ...window.LidTuning },
      BrowTuning: { ...window.BrowTuning },
      MouthTuning: { ...window.MouthTuning },
      JawTuning: { ...window.JawTuning },
      PivotTuning: { ...window.PivotTuning },
    },
  };

  controls.enabled = false;
  e.preventDefault();
}

function onDebugEditorMove(e) {
  if (!DebugEditor.visible) return;

  if (!DebugEditor.dragging) {
    DebugEditor.hoverKey = pickHandle(e.clientX, e.clientY);
    return;
  }

  const { key, startPoint, startSnapshot } = DebugEditor.dragging;
  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  applyDrag(key, p, startPoint, startSnapshot);
  e.preventDefault();
}

function onDebugEditorUp() {
  if (!DebugEditor.dragging) return;
  DebugEditor.dragging = null;
  controls.enabled = true;
  scheduleRecomputeMasks('drag:final', { immediate: true });
}

function onDebugEditorTouchStart(e) {
  if (!DebugEditor.visible) return;
  if (!e.touches?.length) return;
  if (e.touches.length > 1) {
    onDebugEditorUp();
    e.preventDefault();
    return;
  }
  const t = e.touches[0];
  DebugEditor.activeTouchId = t.identifier;
  onDebugEditorDown({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onDebugEditorTouchMove(e) {
  if (!DebugEditor.visible) return;
  if (!e.touches?.length) return;
  if (e.touches.length > 1) {
    onDebugEditorUp();
    e.preventDefault();
    return;
  }
  const t = Array.from(e.touches).find((touch) => touch.identifier === DebugEditor.activeTouchId) || e.touches[0];
  onDebugEditorMove({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onDebugEditorTouchEnd(e) {
  if (e.changedTouches?.length) {
    const released = Array.from(e.changedTouches).some((t) => t.identifier === DebugEditor.activeTouchId);
    if (!released) return;
  }
  DebugEditor.activeTouchId = null;
  onDebugEditorUp(e);
  e.preventDefault();
}

function onDebugEditorTouchCancel(e) {
  DebugEditor.activeTouchId = null;
  onDebugEditorUp(e);
  e.preventDefault();
}

function drawHandle(ctx, key, color, filled, clientX, clientY) {
  const r = DebugEditor.handlesRadius;
  const isHover = DebugEditor.hoverKey === key;
  const isDrag = DebugEditor.dragging?.key === key;

  ctx.save();
  ctx.beginPath();
  ctx.arc(clientX, clientY, r, 0, Math.PI * 2);

  ctx.lineWidth = isDrag ? 3 : (isHover ? 2 : 1.5);
  ctx.strokeStyle = color;

  if (filled) {
    ctx.fillStyle = color.includes('67e8f9') ? 'rgba(103,232,249,0.12)' : 'rgba(255,0,0,0.15)';
    ctx.fill();
  }

  ctx.stroke();
  ctx.restore();
}

function drawDebugEditorOverlay() {
  if (!DebugEditor.enabled || !DebugEditor.visible) return;
  if (!DebugEditor.overlay) initDebugEditorOverlay();

  const ctx = DebugEditor.ctx;
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  const handles = getHandlesModel();
  for (const handle of handles) {
    const s = screenProject(handle.pos.x, handle.pos.y, handle.pos.z || 0);
    drawHandle(ctx, handle.key, handle.color, true, s.x, s.y);
    ctx.save();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';
    ctx.fillText(handle.key, s.x + 12, s.y - 10);
    ctx.restore();
  }
}

// init overlay si aplica
if (DEBUG_EDIT_ENABLED) {
  initDebugEditorOverlay();
}