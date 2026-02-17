import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';
import { createDemoFeedbackMode } from './demo_feedback_mode.js';

// =========================
// URL params
// =========================
const URL_PARAMS = new URLSearchParams(window.location.search);
const DEBUG_EDIT_ENABLED = URL_PARAMS.get('debugEdit') === '1';
const DEBUG_BROWS_ENABLED = URL_PARAMS.get('debugBrows') === '1';
const DEBUG_BLINK_COVER_ENABLED = URL_PARAMS.get('debugBlinkCover') === '1';
const DEBUG_MOTION_LEVEL = Number.parseInt(URL_PARAMS.get('debugMotion') || '0', 10);
const DEBUG_MOTION_ENABLED = DEBUG_MOTION_LEVEL >= 1;
const DEBUG_MOTION_VERBOSE = DEBUG_MOTION_LEVEL >= 2;
const DEBUG_MOTION_HUD_ENABLED = URL_PARAMS.get('debugMotionHud') === '1';
const DEBUG_CONTROLS_ENABLED = URL_PARAMS.get('debugControls') === '1';
const DEBUG_MOUTH_POINTS_ENABLED = URL_PARAMS.get('debugMouthPoints') === '1';
const DEBUG_MOUTH_FADE_ENABLED = URL_PARAMS.get('debugMouthFade') === '1';
const MOUTH_POINTS_ONLY_ENABLED = URL_PARAMS.get('mouthPointsOnly') === '1';
const DEBUG_MOUTH_DIAMOND_ENABLED = DEBUG_EDIT_ENABLED || URL_PARAMS.get('debugMouthDiamond') === '1';
const FORCE_BLINK_ENABLED = URL_PARAMS.get('forceBlink') === '1';
const FORCE_BLINK_DURATION_SEC = 2.0;
const FREEZE_IN_EDIT = DEBUG_EDIT_ENABLED; // En ?debugEdit=1 congelamos motion/UI conversacional para ajustar handles con precisión.
const demoFeedbackMode = createDemoFeedbackMode({ urlParams: URL_PARAMS });

function hideConversationUiForDebugEdit() {
  if (!DEBUG_EDIT_ENABLED) return;
  // Bypass UI conversacional incluso antes de inicializar renderer/audio.
  [
    'permissionOverlay',
    'startBtn',
    'finishTurnBtn',
    'replyContainer',
    'listeningGlow',
    'inputOrb',
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.style.display = 'none';
      el.setAttribute('aria-hidden', 'true');
    }
  });
  document.querySelector('.bottom-bar')?.setAttribute('style', 'display:none');
}

hideConversationUiForDebugEdit();


function resolveHexColorParam(paramName, fallbackColor) {
  const rawValue = URL_PARAMS.get(paramName);
  if (!rawValue) return fallbackColor;

  const normalizedValue = rawValue.trim().replace(/^#/, '').replace(/^0x/i, '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalizedValue)) {
    console.warn(`[theme] Valor inválido para ${paramName}:`, rawValue);
    return fallbackColor;
  }

  return Number.parseInt(normalizedValue, 16);
}

function resolveNumberParam(paramName, fallbackValue) {
  const rawValue = URL_PARAMS.get(paramName);
  if (rawValue == null) return fallbackValue;
  const parsedValue = Number.parseFloat(rawValue);
  return Number.isFinite(parsedValue) ? parsedValue : fallbackValue;
}

// =========================
// Tema perceptual del avatar (dark/light)
// - Geometría, rig, lipsync y animación NO cambian con el tema.
// - Solo cambia la capa perceptual: fondo + respuesta tonal/alpha del shader.
// =========================
const DEFAULT_THEME = 'realistic';

const THEME_PRESETS = {
  dark: {
    background: 0x000000,
    particleColor: 0xdddddd,
    densityInMin: 0.0,
    densityInMax: 1.0,
    densityGamma: 1.0,
    densityOutMin: 0.0,
    densityOutMax: 1.0,
    alphaGain: 1.0,
    alphaClip: 0.02,
    shadeMin: 0.6,
    shadeMax: 1.0,
  },
  realistic: {
    // Tema principal: fondo blanco puro, sin arte de fondo ni capa de puntos.
    background: 0xffffff,
    particleColor: 0xffffff,
    densityInMin: 0.0,
    densityInMax: 1.0,
    densityGamma: 1.0,
    densityOutMin: 0.0,
    densityOutMax: 1.0,
    alphaGain: 1.0,
    alphaClip: 0.0,
    shadeMin: 1.0,
    shadeMax: 1.0,
    useTextureColor: true,
    useLumaDensity: false,
    saturation: 1.0,
    removeHeadCutCap: true,
    disableBackgroundArt: true,
  },
  realistic: {
    // Tema realista: fondo blanco puro, sin arte de fondo ni capa de puntos.
    background: 0xffffff,
    particleColor: 0xffffff,
    densityInMin: 0.0,
    densityInMax: 1.0,
    densityGamma: 1.0,
    densityOutMin: 0.0,
    densityOutMax: 1.0,
    alphaGain: 1.0,
    alphaClip: 0.0,
    shadeMin: 1.0,
    shadeMax: 1.0,
    useTextureColor: true,
    useLumaDensity: false,
    saturation: 1.0,
    removeHeadCutCap: true,
    disableBackgroundArt: true,
  },
};

function resolveTheme() {
  const urlTheme = URL_PARAMS.get('theme');
  if (!urlTheme) return DEFAULT_THEME;

  const lowerTheme = urlTheme.trim().toLowerCase();
  if (lowerTheme === 'realista' || lowerTheme === 'realistic') return 'realistic';
  if (lowerTheme === 'dark') return 'dark';
  return DEFAULT_THEME;
}

const activeThemeName = resolveTheme();
const activeTheme = THEME_PRESETS[activeThemeName];
const isRealisticTheme = activeThemeName === 'realistic';
document.documentElement.dataset.avatarTheme = activeThemeName;
console.info('[theme] Avatar perceptual theme:', activeThemeName);

const isWhiteCanvasTheme = isRealisticTheme;
if (isWhiteCanvasTheme) {
  const canvasBg = `#${activeTheme.background.toString(16).padStart(6, '0')}`;
  document.body.style.backgroundColor = canvasBg;
  const stageEl = document.getElementById('stage');
  if (stageEl) stageEl.style.backgroundColor = canvasBg;
  const bgEl = document.getElementById('bg');
  if (bgEl) {
    bgEl.style.backgroundColor = canvasBg;
    bgEl.style.backgroundImage = activeTheme.disableBackgroundArt ? 'none' : '';
  }
}

// ============================================================================
// ✅ Neck Editor state (DEBE existir antes de animate() y keydown)
// ============================================================================
const NeckEditor = {
  enabled: DEBUG_EDIT_ENABLED,
  visible: DEBUG_EDIT_ENABLED,
  overlay: null,
  ctx: null,
  dpr: 1,
  dragging: null,
  hoverKey: null,
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
  speechIntensity: 1.0,
  idleMotionEnabled: true,
};

if (FREEZE_IN_EDIT) {
  AvatarState.mode = 'IDLE';
  AvatarState.idleMotionEnabled = false;
}

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
// Debug visual: pintar por aHeadWeight
//   - Activa con ?debugNeck=1 o ?debugHead=1
//   - Toggle con tecla N
// =========================
const DebugView = { headWeight: false };
const MotionDebugState = {
  deltaMin: Number.POSITIVE_INFINITY,
  deltaMax: 0,
  deltaSum: 0,
  deltaCount: 0,
  spikeCount: 0,
  lastSpikeLogAt: 0,
  lastReportAt: 0,
  lastFrameLogAt: 0,
  lastHudUpdateAt: 0,
  lastTargetSwitchAt: 0,
  snapCount: 0,
  modeTransitions: 0,
  controlsLogAt: 0,
  renderMsSum: 0,
  renderMsMax: 0,
  overlayMsSum: 0,
  overlayMsMax: 0,
  frameBudgetCount: 0,
  lastFrameBudgetReportAt: 0,
  lastFrameBudgetLogMs: 0,
  prevHeadCurrent: new THREE.Vector3(0, 0, 0),
  prevHeadUniform: new THREE.Vector3(0, 0, 0),
  prevBodyUniform: new THREE.Vector3(0, 0, 0),
  hudEl: null,
};

(() => {
  if (URL_PARAMS.get('audioDebug') === '1') AudioDebug.enabled = true;
  const minRms = parseFloat(URL_PARAMS.get('minRms'));
  if (!Number.isNaN(minRms)) AudioDebug.minRms = minRms;
  const scale = parseFloat(URL_PARAMS.get('levelScale'));
  if (!Number.isNaN(scale)) AudioDebug.scale = scale;
  const logIntervalMs = parseFloat(URL_PARAMS.get('logIntervalMs'));
  if (!Number.isNaN(logIntervalMs)) AudioDebug.logIntervalMs = logIntervalMs;

  // Debug cuello
  if (URL_PARAMS.get('debugNeck') === '1' || URL_PARAMS.get('debugHead') === '1') {
    DebugView.headWeight = true;
    console.info('[debug] Debug cuello/cabeza activado (aHeadWeight). Pulsa N para alternar.');
  }

  if (DEBUG_EDIT_ENABLED) {
    console.info('[neck-editor] Modo editor ACTIVADO (?debugEdit=1). Tecla E para ocultar/mostrar.');
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

  if (DEBUG_BROWS_ENABLED) {
    console.info('[debug-brows] Activado (?debugBrows=1). Se habilitan logs geométricos + overlay shader usando vBaseXY.');
  }
  if (DEBUG_BLINK_COVER_ENABLED) {
    console.info('[debug-brows] Contorno de blinkCover ACTIVADO (?debugBlinkCover=1).');
  }
  if (DEBUG_MOTION_ENABLED) {
    console.info('[debug-motion] Activado (?debugMotion=1|2). Se reportan métricas de delta y motion cada ~1s.');
  }
  if (FORCE_BLINK_ENABLED) {
    console.info(`[blink-debug] forceBlink=1 activo: blink fijado en 1.0 durante ${FORCE_BLINK_DURATION_SEC.toFixed(1)}s.`);
  }
})();

window.addEventListener('keydown', (e) => {
  if (e.key === 'n' || e.key === 'N') {
    DebugView.headWeight = !DebugView.headWeight;
    console.info('[debug] Debug cuello/cabeza (aHeadWeight):', DebugView.headWeight ? 'ON' : 'OFF');
  }
  if (DEBUG_EDIT_ENABLED && (e.key === 'p' || e.key === 'P')) {
    logMouthDiamondSnippet('hotkey');
  }
  if (DEBUG_EDIT_ENABLED && (e.key === 'e' || e.key === 'E')) {
    NeckEditor.visible = !NeckEditor.visible;
    setNeckEditorVisible(NeckEditor.visible);
    console.info('[neck-editor] Visible:', NeckEditor.visible ? 'ON' : 'OFF');
  }
});

let audioCtx = null;
let analyser = null;
let analyserData = null;
let lastAudioDebugLog = 0;
let lastMissingAnalyserLog = 0;
let silentFrameCount = 0;
let audioSource = null;
let lipHoldActive = false;
let lipsyncLevel = 0; // nivel suavizado 0..1
let browsDiagnosticsLogged = false;
let lastBrowsUniformLogMs = 0;

const EyelidMotionState = {
  value: 0.0,
  phase: 'idle', // idle | closing | opening
  timer: 0.0,
  duration: 0.12,
  nextBlinkAt: 2.2,
  pendingDouble: false,
  initialized: false,
  forceUntil: FORCE_BLINK_ENABLED ? FORCE_BLINK_DURATION_SEC : 0.0,
};

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
  analyser = null;
  analyserData = null;
  silentFrameCount = 0;
}

// =========================
// 1. Escena básica
// =========================
const canvas = document.getElementById('c');

const scene = new THREE.Scene();
scene.background = null;

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.01, 100);
camera.position.set(0, 0.25, 1.9);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setClearColor(0x000000, 0);
renderer.setSize(window.innerWidth, window.innerHeight);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 0.2, 0);
if (DEBUG_CONTROLS_ENABLED) controls.addEventListener('change', () => {
  const now = performance.now();
  if (now - MotionDebugState.controlsLogAt < 250) return;
  MotionDebugState.controlsLogAt = now;
  console.info('[debug-motion] controls-change', {
    cameraPos: { x: Number(camera.position.x.toFixed(3)), y: Number(camera.position.y.toFixed(3)), z: Number(camera.position.z.toFixed(3)) },
    target: { x: Number(controls.target.x.toFixed(3)), y: Number(controls.target.y.toFixed(3)), z: Number(controls.target.z.toFixed(3)) },
  });
});

const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
rimLight.position.set(-2, 3, -2);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.2);
scene.add(ambient);

const clock = new THREE.Clock();

// =========================
// Config boca (AJUSTABLE por editor)
// =========================
window.MouthTuning = window.MouthTuning || {
  centerY: 0.16,   // posición vertical del centro de la boca
  centerX: -0.045, // posición horizontal del centro de la boca
  width: 0.18,     // ancho de la región de boca
  height: 0.14,    // alto máximo (labios + hueco)
  curve: 0.0,      // curvatura en U (0 = recto)
};

window.EyeBlinkTuning = window.EyeBlinkTuning || {
  "left": {
    "centerX": -0.21262084897756595,
    "centerY": 0.49398826434773013,
    "halfWidth": 0.06927066702311041,
    "rotation": -0.07747718419813834,
    "upper": { "offset": 0.015333409431849491, "curve": -0.01375947353731123 },
    "lower": { "offset": -0.012817365534143615, "curve": 0.004398359546727952 }
  },
  "right": {
    "centerX": 0.09769628198016435,
    "centerY": 0.48632749262174674,
    "halfWidth": 0.07165083081892201,
    "rotation": 0.05966598604243294,
    "upper": { "offset": 0.009755191469550624, "curve": -0.013990511698837487 },
    "lower": { "offset": -0.018494072161187834, "curve": 0.0027252480420008746 }
  }
};

window.BrowsDebugTuning = window.BrowsDebugTuning || {
  eyeMarkerAspectY: 0.7,
  eyeMarkerRadiusScale: 1.0,
  eyeMarkerFeather: 0.18,
  browYOffset: 0.085,
  browThickness: 0.018,
  browXSpan: 10.0,
};

// =========================
// Config cuello / separación cabeza-cuerpo (TUNED)
// =========================
window.NeckTuning = {
  centerX: -0.05540768292619062,
  width: 0.3289615614114691,
  topY: -0.3029435623085454,
  bottomY: -0.5299623850146092,
  curve: -0.18449820086885416,
  neckPivotY: -0.5299623850146092,
  bodyPivotY: -0.6499623850146092
};

// =========================
// Refs para recalcular pesos en caliente
// =========================
let particlesGeometryRef = null;
let headWeightAttrRef = null;
let basePosAttrRef = null;

let mouthWeightAttrRef = null;
let mouthSideAttrRef = null;

// =========================
// JS smoothstep (una sola vez)
// =========================
function smoothstepJS(edge0, edge1, x) {
  const d = edge1 - edge0;
  if (Math.abs(d) < 1e-8) return x < edge0 ? 0 : 1;
  const t = Math.max(0, Math.min(1, (x - edge0) / d));
  return t * t * (3 - 2 * t);
}

// =========================
// Recalcular aHeadWeight en caliente (API pública)
// =========================
let _neckRecomputePending = false;

function logNeckTuning(reason = 'update') {
  const t = window.NeckTuning;
  console.info(`[neck] ${reason}`, {
    centerX: t.centerX,
    width: t.width,
    topY: t.topY,
    bottomY: t.bottomY,
    curve: t.curve,
    neckPivotY: t.neckPivotY,
    bodyPivotY: t.bodyPivotY,
  });
  console.log('[neck] Pega esto en app.js:\nwindow.NeckTuning = ' + JSON.stringify(t, null, 2) + ';');
}

function recomputeHeadWeightsNow() {
  if (!headWeightAttrRef || !basePosAttrRef) {
    console.warn('[neck] aHeadWeight todavía no está listo (espera a que cargue el GLB).');
    return;
  }

  const t0 = performance.now();
  const t = window.NeckTuning;

  const arr = headWeightAttrRef.array;
  const pos = basePosAttrRef.array;

  const wAbs = Math.max(1e-6, Math.abs(t.width));

  for (let i = 0; i < headWeightAttrRef.count; i++) {
    const x = pos[i * 3 + 0];
    const y = pos[i * 3 + 1];

    const dx = x - t.centerX;
    const insideWidth = Math.abs(dx) <= wAbs;

    const nx = dx / wAbs;
    const nxClamped = Math.max(-1, Math.min(1, nx));
    const curve = t.curve * nxClamped * nxClamped;

    let yTop = insideWidth ? (t.topY - curve) : t.topY;
    let yBot = insideWidth ? (t.bottomY - curve) : t.bottomY;

    if (yTop < yBot) { const tmp = yTop; yTop = yBot; yBot = tmp; }

    let hw = 0.0;
    if (y >= yTop) hw = 1.0;
    else if (y <= yBot) hw = 0.0;
    else hw = smoothstepJS(yBot, yTop, y);

    arr[i] = hw;
  }

  headWeightAttrRef.needsUpdate = true;
  const dt = performance.now() - t0;
  console.info('[neck] aHeadWeight recalculado', { ms: dt.toFixed(2) });
}

function scheduleRecomputeHeadWeights(reason = 'change') {
  if (_neckRecomputePending) return;
  if (DEBUG_MOTION_VERBOSE) console.info('[debug-motion] scheduleRecomputeHeadWeights', { reason });
  _neckRecomputePending = true;
  requestAnimationFrame(() => {
    _neckRecomputePending = false;
    recomputeHeadWeightsNow();
    logNeckTuning(reason);
  });
}

window.recomputeHeadWeights = () => scheduleRecomputeHeadWeights('manual');

// =========================
// Recalcular aMouthWeight/aMouthSide en caliente (API pública)
// =========================
let _mouthRecomputePending = false;

function logMouthTuning(reason = 'update') {
  const t = window.MouthTuning;
  console.info(`[mouth] ${reason}`, {
    centerX: t.centerX,
    centerY: t.centerY,
    width: t.width,
    height: t.height,
    curve: t.curve,
  });
  console.log('[mouth] Pega esto en app.js:\nwindow.MouthTuning = ' + JSON.stringify(t, null, 2) + ';');
}

function recomputeMouthWeightsNow() {
  if (!mouthWeightAttrRef || !mouthSideAttrRef || !basePosAttrRef) {
    console.warn('[mouth] aMouthWeight/aMouthSide todavía no está listo (espera a que cargue el GLB).');
    return;
  }

  const t0 = performance.now();
  const t = window.MouthTuning;

  const wArr = mouthWeightAttrRef.array;
  const sArr = mouthSideAttrRef.array;
  const pos = basePosAttrRef.array;

  const wAbs = Math.max(1e-6, Math.abs(t.width));
  const hAbs = Math.max(1e-6, Math.abs(t.height));

  for (let i = 0; i < mouthWeightAttrRef.count; i++) {
    const x = pos[i * 3 + 0];
    const y = pos[i * 3 + 1];

    let dx = x - t.centerX;
    let ax = Math.abs(dx);

    let weight = 0.0;
    let side = 0.0;

    if (ax <= wAbs) {
      let normX = dx / wAbs;
      let curveY = t.centerY - t.curve * normX * normX;
      let dy = y - curveY;
      let ay = Math.abs(dy);

      if (ay <= hAbs) {
        let wx = 1.0 - ax / wAbs;
        let wy = 1.0 - ay / hAbs;
        weight = wx * wy;

        if (weight < 0.0) weight = 0.0;
        if (weight > 1.0) weight = 1.0;

        if (dy > 0.0) side = 1.0;
        else if (dy < 0.0) side = -1.0;
        else side = 0.0;
      }
    }

    wArr[i] = weight;
    sArr[i] = side;
  }

  mouthWeightAttrRef.needsUpdate = true;
  mouthSideAttrRef.needsUpdate = true;

  const dt = performance.now() - t0;
  console.info('[mouth] aMouthWeight recalculado', { ms: dt.toFixed(2) });
}

function scheduleRecomputeMouthWeights(reason = 'change') {
  if (_mouthRecomputePending) return;
  _mouthRecomputePending = true;
  requestAnimationFrame(() => {
    _mouthRecomputePending = false;
    recomputeMouthWeightsNow();
    logMouthTuning(reason);
  });
}

window.recomputeMouthWeights = () => scheduleRecomputeMouthWeights('manual');

// =========================
// 2. Shaders de partículas
// =========================

// Vertex: movimiento tipo “campo” + respiración + boca hablando + rig cabeza/cuerpo + tamaño fijo
const vertexShader = /* glsl */ `
precision highp float;

uniform float uPointSize;
uniform float uTime;
uniform float uGlobalAmp;
uniform float uClusterAmp;
uniform float uNoiseAmp;

// habla
uniform float uTalk;
uniform float uTalkAmpTop;
uniform float uTalkAmpBot;
uniform float uTalkFreq;
uniform float uLipDepthAmp;
uniform float uRestOpen;

// respiración
uniform float uBreathAmp;
uniform float uBreathFreq;

// rig procedural cabeza/cuerpo
uniform vec3 uHeadRot;
uniform vec3 uBodyRot;
uniform vec3 uBodyOffset;
uniform vec3 uNeckPivot;
uniform vec3 uBodyPivot;
uniform float uDissolveStart;
uniform float uDissolveEnd;
uniform float uDissolveMotionAmp;

attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;
attribute float aHeightFromTop;

// boca
attribute float aMouthWeight;
attribute float aMouthSide;

// peso cabeza (0=cuerpo, 1=cabeza)
attribute float aHeadWeight;

varying vec2 vUv;
varying float vHeadWeight;
varying float vHeightFromTop;
varying float vDissolveSeed;

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

vec3 rotateAroundPivot(vec3 p, vec3 pivot, vec3 r) {
  vec3 q = p - pivot;
  q = rotY(r.y) * rotX(r.x) * rotZ(r.z) * q;
  return q + pivot;
}

void main() {
  vUv = aUv;
  vHeadWeight = aHeadWeight;
  vHeightFromTop = aHeightFromTop;
  vDissolveSeed = aRandom.x;

  vec3 pos = aBasePosition;
  float t = uTime;

  float globalPhase = t * 0.5;
  float swayX = sin(globalPhase + aRandom.x * 6.2831);
  float swayY = cos(globalPhase * 0.8 + aRandom.y * 6.2831);

  vec3 globalOffset = vec3(
    swayX * 0.003,
    swayY * 0.002,
    0.0
  );

  float clusterPhase = hash11(aClusterId + 10.0) * 6.2831;
  float clusterAnim = sin(t * 0.8 + clusterPhase);

  vec3 clusterDir = normalize(vec3(
    hash11(aClusterId + 1.0) - 0.5,
    hash11(aClusterId + 2.0) - 0.5,
    hash11(aClusterId + 3.0) - 0.5
  ));

  vec3 clusterOffset = clusterDir * clusterAnim * 0.004;

  float n = simpleNoise(aBasePosition * 1.5, t * 0.6);
  float micro = (n - 0.5);
  vec3 microDir = normalize(aRandom * 2.0 - 1.0);
  vec3 microOffset = microDir * micro * 0.002;

  float breathPhase = sin(uTime * uBreathFreq) * 0.5 + 0.5;
  float heightFactor = clamp(1.0 - (aBasePosition.y + 0.3) * 2.0, 0.0, 1.0);
  float breath = breathPhase * heightFactor * uBreathAmp;
  vec3 breathOffset = vec3(0.0, breath * 0.01, breath * 0.005);

  float phase = sin(uTime * uTalkFreq);
  float talkOpen = max(phase, 0.0) * uTalk;

  float totalOpen = uRestOpen + talkOpen;
  totalOpen = clamp(totalOpen, 0.0, 1.0);

  float side = aMouthSide;
  float lipAmp = mix(uTalkAmpBot, uTalkAmpTop, step(0.0, side));

  float mouthFactor = aMouthWeight * totalOpen;

  float verticalOffset = side * lipAmp * mouthFactor;
  float depthOffset = -uLipDepthAmp * mouthFactor;
  vec3 mouthOffset = vec3(0.0, verticalOffset, depthOffset);

  vec3 displaced = pos
    + globalOffset * uGlobalAmp
    + clusterOffset * uClusterAmp
    + microOffset * uNoiseAmp
    + breathOffset
    + mouthOffset;

  float dissolveBand = smoothstep(uDissolveStart, uDissolveEnd, aHeightFromTop);
  float dissolveWave = sin(uTime * 2.8 + aRandom.x * 17.0 + aBasePosition.y * 9.0);
  vec3 dissolveOffset = vec3(
    (aRandom.x - 0.5) * 0.0035,
    (0.4 + 0.6 * (0.5 + 0.5 * dissolveWave)) * 0.01,
    (aRandom.y - 0.5) * 0.003
  ) * dissolveBand * uDissolveMotionAmp;
  displaced += dissolveOffset;

  vec3 bodyPos = rotateAroundPivot(displaced, uBodyPivot, uBodyRot) + uBodyOffset;
  vec3 headPos = rotateAroundPivot(bodyPos, uNeckPivot, uHeadRot);
  vec3 finalPos = mix(bodyPos, headPos, aHeadWeight);

  vec4 mvPosition = modelViewMatrix * vec4(finalPos, 1.0);

  gl_PointSize = uPointSize;
  gl_Position = projectionMatrix * mvPosition;
}
`;

// Fragment: disco suave + modulación por textura (normal) + debug por aHeadWeight
const fragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform sampler2D uColorMap;
uniform float uUseMap;
uniform float uDebugHeadWeight;

// Remapeo perceptual de densidad/alpha para soportar fondo claro sin
// romper el modo oscuro ni duplicar shader.
uniform float uDensityInMin;
uniform float uDensityInMax;
uniform float uDensityGamma;
uniform float uDensityOutMin;
uniform float uDensityOutMax;
uniform float uAlphaGain;
uniform float uAlphaClip;
uniform float uShadeMin;
uniform float uShadeMax;
uniform float uUseTextureColor;
uniform float uUseLumaDensity;
uniform float uSaturation;
uniform float uLowDensityAlphaFloor;
uniform float uInvertDensityAsInk;
uniform float uInkFloor;
uniform float uInkAlphaFloor;
uniform float uDissolveStart;
uniform float uDissolveEnd;
uniform float uDissolveStrength;
uniform float uDissolveSpeed;
uniform float uTime;

varying vec2 vUv;
varying float vHeadWeight;
varying float vHeightFromTop;
varying float vDissolveSeed;

float hash21(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float ellipseMask(vec2 uv, vec2 center, vec2 radius) {
  vec2 d = (uv - center) / radius;
  float r = length(d);
  return 1.0 - smoothstep(0.82, 1.0, r);
}

float bandMask(float x, float minX, float maxX, float feather) {
  float left = smoothstep(minX - feather, minX + feather, x);
  float right = 1.0 - smoothstep(maxX - feather, maxX + feather, x);
  return clamp(left * right, 0.0, 1.0);
}

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(p, p);
  if (r2 > 1.0) discard;

  float r = sqrt(r2);
  float circle = 1.0 - smoothstep(0.7, 1.0, r);
  if (circle < 0.02) discard;

  if (uDebugHeadWeight > 0.5) {
    vec3 dbg = vec3(clamp(vHeadWeight, 0.0, 1.0));
    gl_FragColor = vec4(dbg, circle);
    return;
  }

  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  float densityRaw = (texColor.r + texColor.g + texColor.b) / 3.0;
  float densityBase = mix(1.0, densityRaw, uUseMap * uUseLumaDensity);

  float densityNorm = smoothstep(uDensityInMin, uDensityInMax, densityBase);
  float density = mix(uDensityOutMin, uDensityOutMax, pow(densityNorm, uDensityGamma));
  float ink = mix(density, 1.0 - density, uInvertDensityAsInk);
  float inkClamped = max(ink, uInkFloor);
  float inkAlpha = max(ink, uInkAlphaFloor);

  float alpha = circle * (uLowDensityAlphaFloor + inkAlpha * (1.0 - uLowDensityAlphaFloor)) * uAlphaGain;

  float dissolveBand = smoothstep(uDissolveStart, uDissolveEnd, vHeightFromTop);
  float temporalStep = floor(uTime * uDissolveSpeed * 18.0) / 18.0;
  float dissolveNoise = hash21(vec2(vDissolveSeed * 173.3, temporalStep + vUv.y * 4.0));
  float dissolvePulse = 0.65 + 0.35 * sin(uTime * (uDissolveSpeed * 1.7) + vDissolveSeed * 29.0);
  float dissolveAmount = dissolveBand * (0.45 + 0.55 * dissolveNoise) * dissolvePulse * uDissolveStrength;
  alpha *= (1.0 - clamp(dissolveAmount, 0.0, 1.0));

  if (alpha < uAlphaClip) discard;

  vec3 baseColor = mix(uColor, texColor, uUseTextureColor);
  float baseLuma = dot(baseColor, vec3(0.2126, 0.7152, 0.0722));
  baseColor = mix(vec3(baseLuma), baseColor, uSaturation);
  vec3 finalColor = mix(baseColor * uShadeMax, baseColor * uShadeMin, inkClamped);
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
  srcGeometry.computeBoundingBox();
  const box = srcGeometry.boundingBox;
  const minY = box ? box.min.y : -1.0;
  const maxY = box ? box.max.y : 1.0;
  const yRange = Math.max(1e-6, maxY - minY);

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

  const basePositions = new Float32Array(positions.length);
  basePositions.set(positions);

  const randoms = new Float32Array(count * 3);
  const clusterIds = new Float32Array(count);
  const heightFromTop = new Float32Array(count);

  const mouthWeights = new Float32Array(count);
  const mouthSides = new Float32Array(count);

  const headWeights = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    randoms[i * 3 + 0] = Math.random();
    randoms[i * 3 + 1] = Math.random();
    randoms[i * 3 + 2] = Math.random();

    const x = positions[i * 3 + 0];
    const y = positions[i * 3 + 1];

    const y01 = (y - minY) / yRange;
    heightFromTop[i] = THREE.MathUtils.clamp(1.0 - y01, 0.0, 1.0);

    const cx = Math.floor((x + 0.4) * 10.0);
    const cy = Math.floor((y + 0.4) * 10.0);
    clusterIds[i] = cx + cy * 10.0;

    // ------- Boca (desde window.MouthTuning) -------
    const mt = window.MouthTuning;
    const mwAbs = Math.max(1e-6, Math.abs(mt.width));
    const mhAbs = Math.max(1e-6, Math.abs(mt.height));

    let dx = x - mt.centerX;
    let ax = Math.abs(dx);

    let weight = 0.0;
    let side = 0.0;

    if (ax <= mwAbs) {
      let normX = dx / mwAbs;
      let curveY = mt.centerY - mt.curve * normX * normX;
      let dy = y - curveY;
      let ay = Math.abs(dy);

      if (ay <= mhAbs) {
        let wx = 1.0 - ax / mwAbs;
        let wy = 1.0 - ay / mhAbs;
        weight = wx * wy;

        if (weight < 0.0) weight = 0.0;
        if (weight > 1.0) weight = 1.0;

        if (dy > 0.0) side = 1.0;
        else if (dy < 0.0) side = -1.0;
        else side = 0.0;
      }
    }

    mouthWeights[i] = weight;
    mouthSides[i] = side;

    // ------- Cuello (desde window.NeckTuning) -------
    const t = window.NeckTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));

    const dxN = x - t.centerX;
    const insideWidth = Math.abs(dxN) <= wAbs;

    const nx = dxN / wAbs;
    const nxClamped = Math.max(-1, Math.min(1, nx));
    const curve = t.curve * nxClamped * nxClamped;

    let yTop = insideWidth ? (t.topY - curve) : t.topY;
    let yBot = insideWidth ? (t.bottomY - curve) : t.bottomY;

    if (yTop < yBot) {
      const tmp = yTop;
      yTop = yBot;
      yBot = tmp;
    }

    let hw = 0.0;
    if (y >= yTop) hw = 1.0;
    else if (y <= yBot) hw = 0.0;
    else hw = smoothstepJS(yBot, yTop, y);

    headWeights[i] = hw;
  }

  const particlesGeo = new THREE.BufferGeometry();
  particlesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  particlesGeo.setAttribute('aUv', new THREE.BufferAttribute(uvs, 2));
  particlesGeo.setAttribute('aBasePosition', new THREE.BufferAttribute(basePositions, 3));
  particlesGeo.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 3));
  particlesGeo.setAttribute('aClusterId', new THREE.BufferAttribute(clusterIds, 1));
  particlesGeo.setAttribute('aHeightFromTop', new THREE.BufferAttribute(heightFromTop, 1));
  particlesGeo.setAttribute('aMouthWeight', new THREE.BufferAttribute(mouthWeights, 1));
  particlesGeo.setAttribute('aMouthSide', new THREE.BufferAttribute(mouthSides, 1));
  particlesGeo.setAttribute('aHeadWeight', new THREE.BufferAttribute(headWeights, 1));

  return particlesGeo;
}

// Tamaño de punto fijo
const POINT_SIZE = 3.5 * window.devicePixelRatio;
const HEAD_CUT_CAP = {
  radius: 0.56,
  scaleX: 0.9,
  scaleY: 1.15,
  y: 0.14,
  z: -0.055,
};

// =========================
// 4. Cargar GLB, fusionar capas, crear partículas
// =========================
const loader = new GLTFLoader();

let particleMaterial = null;
let particleMaterials = [];
let particlePoints = null;
let particlePointsDetail = null;
let particleSurfaceMesh = null;
let headCutCapMesh = null;
let mouthPoints = null;
let mouthPointsMaterial = null;
let mouthOpenVisual = 0.0;
let mouthPointsVisibleLatched = false;
let realisticSurfaceDebugOriginal = null;
let realisticSurfaceDebugSetupDone = false;


window.MouthRenderTuning = window.MouthRenderTuning || {
  rimA: 0.26,
  rimB: 0.46,
  rimC: 0.68,
  rimD: 0.84,
  innerA: 0.70,
  innerB: 0.82,
  innerGain: 0.22,
  maskMin: 0.08,
  upsampleMinPoints: 260,
  upsampleAmpMin: 0.0007,
  upsampleAmpMax: 0.0015,
  rimResampleFactor: 50,
  pointsOn: 0.050,
  pointsOff: 0.032,
  mouthAttack: 26.0,
  mouthRelease: 12.0,
  pointsAlpha: 0.50,
  pointsAlphaClip: 0.012,
  pointsSizeNear: 3.0 * window.devicePixelRatio,
  pointsSizeFar: 2.3 * window.devicePixelRatio,
  pointsColorMul: 0.95,
  pointsLumaFloor: 0.12,
  pointsLumaStrength: 1.0,
  pointsLumaPreserveHue: 1.0,
  pointsLumaDebug: false,
  meshFade: 0.42,
  meshFeather: 0.12,
  meshAlphaMin: 0.01,
  meshFadeGamma: 3.0,
  meshFadeGain: 2.2,
  useDiamondFade: true,
  fadeDiamondCX: -0.045,
  fadeDiamondCY: 0.16,
  fadeDiamondRX: 0.11,
  fadeDiamondRY: 0.07,
  fadeDiamondRot: 0.0,
};

window.MouthRenderTuning.pointsLumaFloor ??= 0.12;
window.MouthRenderTuning.pointsLumaStrength ??= 1.0;
window.MouthRenderTuning.pointsLumaPreserveHue ??= 1.0;
window.MouthRenderTuning.pointsLumaDebug ??= false;
window.MouthRenderTuning.pointsCullBack ??= true;
window.MouthRenderTuning.pointsDebugBackOnly ??= false;


const MOUTH_DIAMOND_STORAGE_KEY = 'avatar_mouth_diamond_v1';

function loadMouthDiamondFromStorage() {
  if (!DEBUG_EDIT_ENABLED) return;
  try {
    const raw = localStorage.getItem(MOUTH_DIAMOND_STORAGE_KEY);
    if (!raw) return;
    const v = JSON.parse(raw);
    if (!v || typeof v !== 'object') return;
    const t = window.MouthRenderTuning;
    for (const k of ['fadeDiamondCX', 'fadeDiamondCY', 'fadeDiamondRX', 'fadeDiamondRY', 'fadeDiamondRot']) {
      if (Number.isFinite(v[k])) t[k] = v[k];
    }
    if (typeof v.useDiamondFade === 'boolean') t.useDiamondFade = v.useDiamondFade;
  } catch (err) {
    console.warn('[mouth-diamond] no se pudo cargar localStorage', err);
  }
}

function saveMouthDiamondToStorage() {
  if (!DEBUG_EDIT_ENABLED) return;
  try {
    const t = window.MouthRenderTuning;
    localStorage.setItem(MOUTH_DIAMOND_STORAGE_KEY, JSON.stringify({
      fadeDiamondCX: t.fadeDiamondCX,
      fadeDiamondCY: t.fadeDiamondCY,
      fadeDiamondRX: t.fadeDiamondRX,
      fadeDiamondRY: t.fadeDiamondRY,
      fadeDiamondRot: t.fadeDiamondRot,
      useDiamondFade: !!t.useDiamondFade,
    }));
  } catch (err) {
    console.warn('[mouth-diamond] no se pudo guardar localStorage', err);
  }
}

function logMouthDiamondSnippet(reason = 'manual') {
  const t = window.MouthRenderTuning;
  console.info(`[mouth-diamond] ${reason}`, {
    cx: t.fadeDiamondCX,
    cy: t.fadeDiamondCY,
    rx: t.fadeDiamondRX,
    ry: t.fadeDiamondRY,
    rot: t.fadeDiamondRot,
  });
  console.log('Object.assign(window.MouthRenderTuning, ' + JSON.stringify({
    fadeDiamondCX: t.fadeDiamondCX,
    fadeDiamondCY: t.fadeDiamondCY,
    fadeDiamondRX: t.fadeDiamondRX,
    fadeDiamondRY: t.fadeDiamondRY,
    fadeDiamondRot: t.fadeDiamondRot,
    useDiamondFade: !!t.useDiamondFade,
  }, null, 2) + ');');
}

loadMouthDiamondFromStorage();

function mouthRimMaskFromWeight(w, tuning = window.MouthRenderTuning) {
  const rimMask = smoothstepJS(tuning.rimA, tuning.rimB, w) * (1.0 - smoothstepJS(tuning.rimC, tuning.rimD, w));
  const innerTiny = smoothstepJS(tuning.innerA, tuning.innerB, w) * tuning.innerGain;
  return THREE.MathUtils.clamp(rimMask + innerTiny, 0.0, 1.0);
}

function stableHash3(x, y, z, salt = 0.0) {
  const seed = x * 127.1 + y * 311.7 + z * 74.7 + salt * 19.19;
  const v = Math.sin(seed) * 43758.5453123;
  return v - Math.floor(v);
}

function buildMouthPointsGeometryFromAnimatedSurface(srcGeometry) {
  const basePosAttr = srcGeometry.getAttribute('aBasePosition') || srcGeometry.getAttribute('position');
  const posAttr = srcGeometry.getAttribute('position') || basePosAttr;
  const uvAttr = srcGeometry.getAttribute('aUv') || srcGeometry.getAttribute('uv');
  const mouthWeightAttr = srcGeometry.getAttribute('aMouthWeight');
  const mouthSideAttr = srcGeometry.getAttribute('aMouthSide');
  const headWeightAttr = srcGeometry.getAttribute('aHeadWeight');
  if (!basePosAttr || !posAttr || !uvAttr || !mouthWeightAttr || !mouthSideAttr || !headWeightAttr) {
    console.warn('[mouth-points] Faltan atributos requeridos para construir la geometría de boca.');
    return { geometry: null, pointCount: 0, sourceCount: 0, resampledCount: 0, rimResampleFactor: 0 };
  }

  const tuning = window.MouthRenderTuning;
  const p = [];
  const b = [];
  const uv = [];
  const mw = [];
  const ms = [];
  const hw = [];
  const ov = [];
  const addPoint = (x, y, z, bx, by, bz, u, v, mouthWeight, mouthSide, headWeight, overlay) => {
    p.push(x, y, z);
    b.push(bx, by, bz);
    uv.push(u, v);
    mw.push(mouthWeight);
    ms.push(mouthSide);
    hw.push(headWeight);
    ov.push(overlay);
  };

  const overlayByVertex = new Float32Array(basePosAttr.count);
  for (let i = 0; i < basePosAttr.count; i++) {
    const w = mouthWeightAttr.getX(i);
    const overlay = mouthRimMaskFromWeight(w, tuning);
    overlayByVertex[i] = overlay;
    if (overlay <= tuning.maskMin) continue;
    const x = posAttr.getX(i);
    const y = posAttr.getY(i);
    const z = posAttr.getZ(i);
    const bx = basePosAttr.getX(i);
    const by = basePosAttr.getY(i);
    const bz = basePosAttr.getZ(i);
    addPoint(x, y, z, bx, by, bz, uvAttr.getX(i), uvAttr.getY(i), w, mouthSideAttr.getX(i), headWeightAttr.getX(i), overlay);
  }
  const sourceCount = p.length / 3;
  let frontCountSource = 0;
  let backCountSource = 0;
  for (let i = 0; i < sourceCount; i++) {
    const bz = b[i * 3 + 2];
    if (bz >= 0.0) frontCountSource += 1;
    else backCountSource += 1;
  }

  const indexAttr = srcGeometry.getIndex();
  const triWeights = [];
  const triIndices = [];
  const getIndex = (i) => (indexAttr ? indexAttr.getX(i) : i);
  const triCount = indexAttr ? Math.floor(indexAttr.count / 3) : Math.floor(posAttr.count / 3);

  for (let tIdx = 0; tIdx < triCount; tIdx++) {
    const ia = getIndex(tIdx * 3 + 0);
    const ib = getIndex(tIdx * 3 + 1);
    const ic = getIndex(tIdx * 3 + 2);
    const wa = overlayByVertex[ia];
    const wb = overlayByVertex[ib];
    const wc = overlayByVertex[ic];
    const avgMask = (wa + wb + wc) / 3.0;
    if (avgMask <= tuning.maskMin) continue;

    const ax = basePosAttr.getX(ia), ay = basePosAttr.getY(ia), az = basePosAttr.getZ(ia);
    const bx = basePosAttr.getX(ib), by = basePosAttr.getY(ib), bz = basePosAttr.getZ(ib);
    const cx = basePosAttr.getX(ic), cy = basePosAttr.getY(ic), cz = basePosAttr.getZ(ic);
    const abx = bx - ax, aby = by - ay, abz = bz - az;
    const acx = cx - ax, acy = cy - ay, acz = cz - az;
    const crx = aby * acz - abz * acy;
    const cry = abz * acx - abx * acz;
    const crz = abx * acy - aby * acx;
    const area = 0.5 * Math.sqrt(crx * crx + cry * cry + crz * crz);
    const weight = area * avgMask;
    if (weight <= 0.0) continue;
    triWeights.push(weight);
    triIndices.push([ia, ib, ic, avgMask]);
  }

  let resampledCount = 0;
  let frontCountResampled = 0;
  let backCountResampled = 0;
  if (triIndices.length && tuning.rimResampleFactor > 0) {
    const targetResampled = Math.max(0, Math.round(sourceCount * tuning.rimResampleFactor));
    const totalWeight = triWeights.reduce((a, b) => a + b, 0.0) || 1.0;

    for (let ti = 0; ti < triIndices.length; ti++) {
      const [ia, ib, ic, triMask] = triIndices[ti];
      const weightNorm = triWeights[ti] / totalWeight;
      const n = Math.max(0, Math.round(targetResampled * weightNorm));
      if (n <= 0) continue;

      const ax = basePosAttr.getX(ia), ay = basePosAttr.getY(ia), az = basePosAttr.getZ(ia);
      const bx = basePosAttr.getX(ib), by = basePosAttr.getY(ib), bz = basePosAttr.getZ(ib);
      const cx = basePosAttr.getX(ic), cy = basePosAttr.getY(ic), cz = basePosAttr.getZ(ic);

      const apx = posAttr.getX(ia), apy = posAttr.getY(ia), apz = posAttr.getZ(ia);
      const bpx = posAttr.getX(ib), bpy = posAttr.getY(ib), bpz = posAttr.getZ(ib);
      const cpx = posAttr.getX(ic), cpy = posAttr.getY(ic), cpz = posAttr.getZ(ic);

      const au = uvAttr.getX(ia), av = uvAttr.getY(ia);
      const bu = uvAttr.getX(ib), bv = uvAttr.getY(ib);
      const cu = uvAttr.getX(ic), cv = uvAttr.getY(ic);

      const aw = mouthWeightAttr.getX(ia), bw = mouthWeightAttr.getX(ib), cw = mouthWeightAttr.getX(ic);
      const asd = mouthSideAttr.getX(ia), bsd = mouthSideAttr.getX(ib), csd = mouthSideAttr.getX(ic);
      const ah = headWeightAttr.getX(ia), bh = headWeightAttr.getX(ib), ch = headWeightAttr.getX(ic);
      const ao = overlayByVertex[ia], bo = overlayByVertex[ib], co = overlayByVertex[ic];

      for (let k = 0; k < n; k++) {
        const h1 = stableHash3(ax, by, cz, 1000.0 + ti * 0.73 + k * 0.17);
        const h2 = stableHash3(bx, cy, az, 2000.0 + ti * 0.31 + k * 0.29);
        const su = Math.sqrt(h1);
        const b0 = 1.0 - su;
        const b1 = h2 * su;
        const b2 = 1.0 - b0 - b1;

        const pbx = ax * b0 + bx * b1 + cx * b2;
        const pby = ay * b0 + by * b1 + cy * b2;
        const pbz = az * b0 + bz * b1 + cz * b2;

        const ppx = apx * b0 + bpx * b1 + cpx * b2;
        const ppy = apy * b0 + bpy * b1 + cpy * b2;
        const ppz = apz * b0 + bpz * b1 + cpz * b2;

        const pu = au * b0 + bu * b1 + cu * b2;
        const pv = av * b0 + bv * b1 + cv * b2;

        const pW = aw * b0 + bw * b1 + cw * b2;
        const pS = asd * b0 + bsd * b1 + csd * b2;
        const pH = ah * b0 + bh * b1 + ch * b2;
        const pO = THREE.MathUtils.clamp((ao * b0 + bo * b1 + co * b2) * (0.75 + triMask * 0.25), 0.0, 1.0);

        addPoint(ppx, ppy, ppz, pbx, pby, pbz, pu, pv, pW, pS, pH, pO);
        if (pbz >= 0.0) frontCountResampled += 1;
        else backCountResampled += 1;
        resampledCount += 1;
      }
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(p), 3));
  geo.setAttribute('aBasePosition', new THREE.BufferAttribute(new Float32Array(b), 3));
  geo.setAttribute('aUv', new THREE.BufferAttribute(new Float32Array(uv), 2));
  geo.setAttribute('aMouthWeight', new THREE.BufferAttribute(new Float32Array(mw), 1));
  geo.setAttribute('aMouthSide', new THREE.BufferAttribute(new Float32Array(ms), 1));
  geo.setAttribute('aHeadWeight', new THREE.BufferAttribute(new Float32Array(hw), 1));
  geo.setAttribute('aMouthOverlayMix', new THREE.BufferAttribute(new Float32Array(ov), 1));

  return {
    geometry: geo,
    pointCount: p.length / 3,
    sourceCount,
    resampledCount,
    rimResampleFactor: tuning.rimResampleFactor,
    frontCountSource,
    backCountSource,
    frontCountResampled,
    backCountResampled,
  };
}

const mouthPointsVertexShader = /* glsl */ `
precision highp float;
uniform float uTime;
uniform float uTalk;
uniform float uTalkAmpTop;
uniform float uTalkAmpBot;
uniform float uTalkFreq;
uniform float uLipDepthAmp;
uniform float uRestOpen;
uniform float uPointSizeNear;
uniform float uPointSizeFar;
uniform vec3 uHeadRot;
uniform vec3 uBodyRot;
uniform vec3 uBodyOffset;
uniform vec3 uNeckPivot;
uniform vec3 uBodyPivot;
attribute vec3 aBasePosition;
attribute float aMouthWeight;
attribute float aMouthSide;
attribute float aHeadWeight;
attribute float aMouthOverlayMix;
attribute vec2 aUv;
varying float vMouthOverlayMix;
varying vec2 vUv;
varying float vBaseZ;

mat3 rotX(float a){ float s=sin(a), c=cos(a); return mat3(1.,0.,0.,0.,c,-s,0.,s,c); }
mat3 rotY(float a){ float s=sin(a), c=cos(a); return mat3(c,0.,s,0.,1.,0.,-s,0.,c); }
mat3 rotZ(float a){ float s=sin(a), c=cos(a); return mat3(c,-s,0.,s,c,0.,0.,0.,1.); }
vec3 rotateAroundPivot(vec3 p, vec3 pivot, vec3 r){ vec3 q = p - pivot; q = rotY(r.y) * rotX(r.x) * rotZ(r.z) * q; return q + pivot; }

void main() {
  vMouthOverlayMix = aMouthOverlayMix;
  vUv = aUv;
  vBaseZ = aBasePosition.z;

  float talkOpen = max(sin(uTime * uTalkFreq), 0.0) * uTalk;
  float totalOpen = clamp(uRestOpen + talkOpen, 0.0, 1.0);
  float mouthFactor = aMouthWeight * totalOpen;
  float lipAmp = mix(uTalkAmpBot, uTalkAmpTop, step(0.0, aMouthSide));
  float verticalOffset = aMouthSide * lipAmp * mouthFactor;
  float depthOffset = -uLipDepthAmp * mouthFactor;

  vec3 displaced = aBasePosition + vec3(0.0, verticalOffset, depthOffset);
  vec3 bodyPos = rotateAroundPivot(displaced, uBodyPivot, uBodyRot) + uBodyOffset;
  vec3 headPos = rotateAroundPivot(bodyPos, uNeckPivot, uHeadRot);
  vec3 finalPos = mix(bodyPos, headPos, aHeadWeight);
  vec4 mvPosition = modelViewMatrix * vec4(finalPos, 1.0);
  float dist = max(0.0, -mvPosition.z);
  float distNorm = clamp((dist - 1.0) / 1.7, 0.0, 1.0);
  gl_PointSize = mix(uPointSizeNear, uPointSizeFar, distNorm);
  gl_Position = projectionMatrix * mvPosition;
}
`;

const mouthPointsFragmentShader = /* glsl */ `
precision highp float;
uniform sampler2D uColorMap;
uniform float uUseMap;
uniform float uMouthPointsAlpha;
uniform float uMouthPointsAlphaClip;
uniform float uMouthPointsColorMul;
uniform float uPointsLumaFloor;
uniform float uPointsLumaStrength;
uniform float uPointsLumaPreserveHue;
uniform float uPointsLumaDebug;
uniform float uMouthPointsCullBack;
uniform float uMouthPointsDebugBackOnly;
varying float vMouthOverlayMix;
varying vec2 vUv;
varying float vBaseZ;

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(p, p);
  if (r2 > 1.0) discard;
  float r = sqrt(r2);
  float circle = 1.0 - smoothstep(0.68, 1.0, r);
  float alpha = circle * uMouthPointsAlpha * clamp(vMouthOverlayMix, 0.0, 1.0);
  if (alpha < uMouthPointsAlphaClip) discard;
  if (uMouthPointsCullBack > 0.5 && vBaseZ < 0.0) discard;
  if (uMouthPointsDebugBackOnly > 0.5 && vBaseZ >= 0.0) discard;
  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  float l = dot(texColor, vec3(0.2126, 0.7152, 0.0722));
  float floorL = max(uPointsLumaFloor, 1e-4);
  float targetL = max(l, floorL);
  float lift = clamp((targetL - l) / floorL, 0.0, 1.0);
  lift *= clamp(uPointsLumaStrength, 0.0, 1.0);
  vec3 scaled = texColor * (targetL / max(l, 1e-4));
  texColor = mix(texColor, scaled, clamp(uPointsLumaPreserveHue, 0.0, 1.0) * lift);
  if (uPointsLumaDebug > 0.5) {
    vec3 debugLift = mix(vec3(0.0, 0.2, 0.8), vec3(1.0, 0.1, 0.1), lift);
    gl_FragColor = vec4(debugLift, alpha);
    return;
  }
  vec3 baseColor = mix(vec3(0.8), texColor, uUseMap);
  gl_FragColor = vec4(baseColor * uMouthPointsColorMul, alpha);
}
`;

// =========================
// Bloque temático "realistic"
// - Concentrado en esta sección para activar/desactivar fácil.
// =========================
function generateAnimatedSurfaceGeometry(srcGeometry) {
  // Random estable por posición para evitar grietas visuales en costuras UV.
  // Si dos vértices comparten posición espacial, recibirán el mismo offset.
  const stableHash = (n) => {
    const x = Math.sin(n) * 43758.5453123;
    return x - Math.floor(x);
  };
  const stableRandomFromPosition = (x, y, z, salt = 0.0) => {
    const qx = Math.round(x * 10000.0) / 10000.0;
    const qy = Math.round(y * 10000.0) / 10000.0;
    const qz = Math.round(z * 10000.0) / 10000.0;
    const seed = qx * 127.1 + qy * 311.7 + qz * 74.7 + salt * 19.19;
    return stableHash(seed);
  };

  const geo = srcGeometry.clone();
  const srcPos = geo.getAttribute('position');
  const srcUv = geo.getAttribute('uv');
  const count = srcPos.count;

  const basePositions = new Float32Array(count * 3);
  const randoms = new Float32Array(count * 3);
  const clusterIds = new Float32Array(count);
  const heightFromTop = new Float32Array(count);
  const mouthWeights = new Float32Array(count);
  const mouthSides = new Float32Array(count);
  const headWeights = new Float32Array(count);
  const uvArray = new Float32Array(count * 2);

  geo.computeBoundingBox();
  const box = geo.boundingBox;
  const minY = box ? box.min.y : -1.0;
  const maxY = box ? box.max.y : 1.0;
  const yRange = Math.max(1e-6, maxY - minY);

  const v = new THREE.Vector3();
  const uv = new THREE.Vector2();

  for (let i = 0; i < count; i++) {
    v.fromBufferAttribute(srcPos, i);
    basePositions[i * 3 + 0] = v.x;
    basePositions[i * 3 + 1] = v.y;
    basePositions[i * 3 + 2] = v.z;

    if (srcUv) {
      uv.fromBufferAttribute(srcUv, i);
      uvArray[i * 2 + 0] = uv.x;
      uvArray[i * 2 + 1] = uv.y;
    }

    randoms[i * 3 + 0] = stableRandomFromPosition(v.x, v.y, v.z, 1.0);
    randoms[i * 3 + 1] = stableRandomFromPosition(v.x, v.y, v.z, 2.0);
    randoms[i * 3 + 2] = stableRandomFromPosition(v.x, v.y, v.z, 3.0);

    const y01 = (v.y - minY) / yRange;
    heightFromTop[i] = THREE.MathUtils.clamp(1.0 - y01, 0.0, 1.0);

    const cx = Math.floor((v.x + 0.4) * 10.0);
    const cy = Math.floor((v.y + 0.4) * 10.0);
    clusterIds[i] = cx + cy * 10.0;

    const mt = window.MouthTuning;
    const mwAbs = Math.max(1e-6, Math.abs(mt.width));
    const mhAbs = Math.max(1e-6, Math.abs(mt.height));

    const dx = v.x - mt.centerX;
    const ax = Math.abs(dx);
    let weight = 0.0;
    let side = 0.0;

    if (ax <= mwAbs) {
      const normX = dx / mwAbs;
      const curveY = mt.centerY - mt.curve * normX * normX;
      const dy = v.y - curveY;
      const ay = Math.abs(dy);
      if (ay <= mhAbs) {
        const wx = 1.0 - ax / mwAbs;
        const wy = 1.0 - ay / mhAbs;
        weight = THREE.MathUtils.clamp(wx * wy, 0.0, 1.0);
        side = dy > 0.0 ? 1.0 : (dy < 0.0 ? -1.0 : 0.0);
      }
    }
    mouthWeights[i] = weight;
    mouthSides[i] = side;

    const t = window.NeckTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));
    const dxN = v.x - t.centerX;
    const insideWidth = Math.abs(dxN) <= wAbs;
    const nx = dxN / wAbs;
    const curve = t.curve * THREE.MathUtils.clamp(nx, -1.0, 1.0) ** 2;
    let yTop = insideWidth ? (t.topY - curve) : t.topY;
    let yBot = insideWidth ? (t.bottomY - curve) : t.bottomY;
    if (yTop < yBot) [yTop, yBot] = [yBot, yTop];
    headWeights[i] = v.y >= yTop ? 1.0 : (v.y <= yBot ? 0.0 : smoothstepJS(yBot, yTop, v.y));
  }

  geo.setAttribute('aUv', new THREE.BufferAttribute(uvArray, 2));
  geo.setAttribute('aBasePosition', new THREE.BufferAttribute(basePositions, 3));
  geo.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 3));
  geo.setAttribute('aClusterId', new THREE.BufferAttribute(clusterIds, 1));
  geo.setAttribute('aHeightFromTop', new THREE.BufferAttribute(heightFromTop, 1));
  geo.setAttribute('aMouthWeight', new THREE.BufferAttribute(mouthWeights, 1));
  geo.setAttribute('aMouthSide', new THREE.BufferAttribute(mouthSides, 1));
  geo.setAttribute('aHeadWeight', new THREE.BufferAttribute(headWeights, 1));

  return geo;
}

const realisticSurfaceVertexShader = /* glsl */ `
precision highp float;
uniform float uTime;
uniform float uGlobalAmp;
uniform float uClusterAmp;
uniform float uNoiseAmp;
uniform float uTalk;
uniform float uTalkAmpTop;
uniform float uTalkAmpBot;
uniform float uTalkFreq;
uniform float uLipDepthAmp;
uniform float uRestOpen;
uniform float uBreathAmp;
uniform float uBreathFreq;
uniform vec3 uHeadRot;
uniform vec3 uBodyRot;
uniform vec3 uBodyOffset;
uniform vec3 uNeckPivot;
uniform vec3 uBodyPivot;
uniform float uDissolveStart;
uniform float uDissolveEnd;
uniform float uDissolveMotionAmp;
uniform float uMouthOpenVisual;
attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;
attribute float aHeightFromTop;
attribute float aMouthWeight;
attribute float aMouthSide;
attribute float aHeadWeight;
varying vec2 vUv;
varying float vHeadWeight;
varying float vBaseZ;
varying vec2 vBaseXY;
varying float vMouthWeight;

float hash11(float p){ return fract(sin(p * 127.1) * 43758.5453123); }
float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453123); }
float simpleNoise(vec3 p, float t){ return (hash21(p.xy + t) + hash21(p.yz - t * 0.5)) * 0.5; }
mat3 rotX(float a){ float s=sin(a), c=cos(a); return mat3(1.,0.,0.,0.,c,-s,0.,s,c); }
mat3 rotY(float a){ float s=sin(a), c=cos(a); return mat3(c,0.,s,0.,1.,0.,-s,0.,c); }
mat3 rotZ(float a){ float s=sin(a), c=cos(a); return mat3(c,-s,0.,s,c,0.,0.,0.,1.); }
vec3 rotateAroundPivot(vec3 p, vec3 pivot, vec3 r){ vec3 q = p - pivot; q = rotY(r.y) * rotX(r.x) * rotZ(r.z) * q; return q + pivot; }

void main() {
  vUv = aUv;
  vHeadWeight = aHeadWeight;
  vBaseZ = aBasePosition.z;
  vBaseXY = aBasePosition.xy;
  vMouthWeight = aMouthWeight;

  vec3 pos = aBasePosition;
  float t = uTime;
  vec3 globalOffset = vec3(sin(t * 0.5 + aRandom.x * 6.2831) * 0.003, cos(t * 0.4 + aRandom.y * 6.2831) * 0.002, 0.0);
  float clusterPhase = hash11(aClusterId + 10.0) * 6.2831;
  vec3 clusterDir = normalize(vec3(hash11(aClusterId + 1.0) - 0.5, hash11(aClusterId + 2.0) - 0.5, hash11(aClusterId + 3.0) - 0.5));
  vec3 clusterOffset = clusterDir * sin(t * 0.8 + clusterPhase) * 0.004;
  float micro = simpleNoise(aBasePosition * 1.5, t * 0.6) - 0.5;
  vec3 microOffset = normalize(aRandom * 2.0 - 1.0) * micro * 0.002;
  float breathPhase = sin(uTime * uBreathFreq) * 0.5 + 0.5;
  float heightFactor = clamp(1.0 - (aBasePosition.y + 0.3) * 2.0, 0.0, 1.0);
  vec3 breathOffset = vec3(0.0, breathPhase * heightFactor * uBreathAmp * 0.01, breathPhase * heightFactor * uBreathAmp * 0.005);
  float totalOpen = clamp(uRestOpen + max(sin(uTime * uTalkFreq), 0.0) * uTalk, 0.0, 1.0);
  float mouthFactor = aMouthWeight * totalOpen;
  vec3 mouthOffset = vec3(0.0, aMouthSide * mix(uTalkAmpBot, uTalkAmpTop, step(0.0, aMouthSide)) * mouthFactor, -uLipDepthAmp * mouthFactor);

  vec3 displaced = pos + globalOffset * uGlobalAmp + clusterOffset * uClusterAmp + microOffset * uNoiseAmp + breathOffset + mouthOffset;
  float dissolveBand = smoothstep(uDissolveStart, uDissolveEnd, aHeightFromTop);
  vec3 dissolveOffset = vec3((aRandom.x - 0.5) * 0.0035, (0.4 + 0.6 * (0.5 + 0.5 * sin(uTime * 2.8 + aRandom.x * 17.0 + aBasePosition.y * 9.0))) * 0.01, (aRandom.y - 0.5) * 0.003) * dissolveBand * uDissolveMotionAmp;
  displaced += dissolveOffset;

  vec3 bodyPos = rotateAroundPivot(displaced, uBodyPivot, uBodyRot) + uBodyOffset;
  vec3 headPos = rotateAroundPivot(bodyPos, uNeckPivot, uHeadRot);
  vec3 finalPos = mix(bodyPos, headPos, aHeadWeight);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(finalPos, 1.0);
}
`;

const realisticSurfaceFragmentShader = /* glsl */ `
precision highp float;
uniform sampler2D uColorMap;
uniform float uUseMap;
uniform vec3 uColor;
uniform float uDebugHeadWeight;
uniform float uBlink;
uniform vec4 uEyeLeftMain;   // centerX, centerY, halfWidth, rotation
uniform vec4 uEyeLeftUpper;  // offsetY, curve, reserved, reserved
uniform vec4 uEyeLeftLower;  // offsetY, curve, reserved, reserved
uniform vec4 uEyeRightMain;
uniform vec4 uEyeRightUpper;
uniform vec4 uEyeRightLower;
uniform float uDebugBrows;
uniform float uBrowYOffset;
uniform float uBrowThickness;
uniform float uBrowXSpan;
uniform float uEyeMarkerAspect;
uniform float uEyeMarkerScale;
uniform float uEyeMarkerFeather;
uniform float uDebugBlinkCover;
uniform float uMouthOpenVisual;
uniform float uMouthMeshFade;
uniform float uMouthFeather;
uniform float uMouthMeshAlphaMin;
uniform float uMouthMeshFadeGamma;
uniform float uMouthMeshFadeGain;
uniform float uDebugMouthFade;
uniform float uUseDiamondFade;
uniform float uFadeDiamondCX;
uniform float uFadeDiamondCY;
uniform float uFadeDiamondRX;
uniform float uFadeDiamondRY;
uniform float uFadeDiamondRot;
uniform float uMouthHoleActive;
uniform float uDebugMouthDiamond;
varying vec2 vUv;
varying float vHeadWeight;
varying float vBaseZ;
varying vec2 vBaseXY;
varying float vMouthWeight;

mat2 invRot(float a) {
  float s = sin(a);
  float c = cos(a);
  return mat2(c, s, -s, c);
}

float blinkCover(vec2 baseXY, vec4 eyeMain, vec4 upperCfg, vec4 lowerCfg, float blink) {
  vec2 local = invRot(eyeMain.w) * (baseXY - eyeMain.xy);
  float halfWidth = max(eyeMain.z, 1e-4);
  float xN = clamp(local.x / halfWidth, -1.0, 1.0);

  float upperBase = upperCfg.x + upperCfg.y * (xN * xN);
  float lowerBase = lowerCfg.x + lowerCfg.y * (xN * xN);

  float upperNow = mix(upperBase, lowerBase, blink);
  float yFeather = max(0.003, halfWidth * 0.08);
  float xMask = 1.0 - smoothstep(halfWidth * 0.96, halfWidth * 1.08, abs(local.x));

  float aboveMoved = smoothstep(upperNow - yFeather, upperNow + yFeather, local.y);
  float belowBase = 1.0 - smoothstep(upperBase - yFeather, upperBase + yFeather, local.y);

  return xMask * aboveMoved * belowBase;
}

void main() {
  if (uDebugHeadWeight > 0.5) {
    gl_FragColor = vec4(vec3(clamp(vHeadWeight, 0.0, 1.0)), 1.0);
    return;
  }
  if (vBaseZ < 0.0) discard;

  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  vec3 finalColor = mix(uColor, texColor, uUseMap);

  float blink = clamp(uBlink, 0.0, 1.0);
  float leftCover = blinkCover(vBaseXY, uEyeLeftMain, uEyeLeftUpper, uEyeLeftLower, blink);
  float rightCover = blinkCover(vBaseXY, uEyeRightMain, uEyeRightUpper, uEyeRightLower, blink);
  float cover = max(leftCover, rightCover) * smoothstep(0.02, 0.95, blink);

  vec3 lidColor = texture2D(uColorMap, clamp(vUv + vec2(0.0, 0.03), 0.0, 1.0)).rgb;
  finalColor = mix(finalColor, lidColor, cover);

  float innerFadeMask = smoothstep(0.62 - uMouthFeather, 0.88 + uMouthFeather, vMouthWeight);
  float mouthFadeRaw = clamp(uMouthOpenVisual * uMouthMeshFadeGain * innerFadeMask, 0.0, 1.0);
  float mouthFade = pow(mouthFadeRaw, max(0.01, uMouthMeshFadeGamma));
  mouthFade = clamp(mouthFade * uMouthMeshFade, 0.0, 1.0);

  vec2 localDiamond = invRot(uFadeDiamondRot) * (vBaseXY - vec2(uFadeDiamondCX, uFadeDiamondCY));
  float diamondField = abs(localDiamond.x) / max(1e-5, abs(uFadeDiamondRX)) + abs(localDiamond.y) / max(1e-5, abs(uFadeDiamondRY));
  float diamondInside = step(diamondField, 1.0);
  float mouthHoleActive = step(0.5, uMouthHoleActive) * step(0.5, uUseDiamondFade);
  if (mouthHoleActive > 0.5 && diamondInside > 0.5) {
    discard;
  }
  finalColor = mix(finalColor, finalColor * 0.88, mouthFade * 0.35);

  if (uDebugBrows > 0.5) {
    vec2 leftLocal = invRot(uEyeLeftMain.w) * (vBaseXY - uEyeLeftMain.xy);
    vec2 rightLocal = invRot(uEyeRightMain.w) * (vBaseXY - uEyeRightMain.xy);

    float markerScale = max(1e-4, uEyeMarkerScale);
    float markerAspect = max(1e-4, uEyeMarkerAspect);
    float markerInner = max(0.0, 1.0 - max(0.0, uEyeMarkerFeather));

    float leftEyeMarker = 1.0 - smoothstep(markerInner, 1.0, length(vec2(leftLocal.x / max(1e-4, uEyeLeftMain.z * markerScale), leftLocal.y / max(1e-4, uEyeLeftMain.z * markerAspect * markerScale))));
    float rightEyeMarker = 1.0 - smoothstep(markerInner, 1.0, length(vec2(rightLocal.x / max(1e-4, uEyeRightMain.z * markerScale), rightLocal.y / max(1e-4, uEyeRightMain.z * markerAspect * markerScale))));

    float browY = 0.5 * (uEyeLeftMain.y + uEyeRightMain.y) + uBrowYOffset;
    float browBand = 1.0 - smoothstep(0.0, max(1e-4, uBrowThickness), abs(vBaseXY.y - browY));
    float browXMask = 1.0 - smoothstep(max(0.0, uBrowXSpan), max(0.0, uBrowXSpan) + 0.06, abs(vBaseXY.x));
    browBand *= browXMask;

    float centerLine = 1.0 - smoothstep(0.0, 0.006, abs(vBaseXY.x));

    float coverOpen = max(blinkCover(vBaseXY, uEyeLeftMain, uEyeLeftUpper, uEyeLeftLower, 0.0), blinkCover(vBaseXY, uEyeRightMain, uEyeRightUpper, uEyeRightLower, 0.0));
    float coverClosed = max(blinkCover(vBaseXY, uEyeLeftMain, uEyeLeftUpper, uEyeLeftLower, 1.0), blinkCover(vBaseXY, uEyeRightMain, uEyeRightUpper, uEyeRightLower, 1.0));
    float coverOpenLine = smoothstep(0.25, 0.35, coverOpen) - smoothstep(0.35, 0.45, coverOpen);
    float coverClosedLine = smoothstep(0.70, 0.80, coverClosed) - smoothstep(0.80, 0.90, coverClosed);

    vec3 overlay = vec3(0.0);
    overlay += vec3(1.0, 0.2, 0.2) * max(leftEyeMarker, rightEyeMarker);
    overlay += vec3(0.15, 0.95, 0.2) * browBand;
    overlay += vec3(0.2, 0.6, 1.0) * centerLine * 0.6;
    if (uDebugBlinkCover > 0.5) {
      overlay += vec3(0.9, 0.2, 1.0) * coverOpenLine;
      overlay += vec3(0.2, 1.0, 1.0) * coverClosedLine;
    }
    float overlayMask = clamp(max(max(leftEyeMarker, rightEyeMarker), browBand) * 0.75 + centerLine * 0.25, 0.0, 0.85);
    if (uDebugBlinkCover > 0.5) {
      overlayMask = max(overlayMask, clamp(max(coverOpenLine, coverClosedLine) * 0.9, 0.0, 0.9));
    }
    finalColor = mix(finalColor, overlay, overlayMask);
  }

  if (uDebugMouthFade > 0.5 || uDebugMouthDiamond > 0.5) {
    vec3 dbg = mix(finalColor, vec3(1.0, 0.1, 0.1), clamp(mouthFade, 0.0, 0.8));
    if (uDebugMouthDiamond > 0.5) {
      float edge = 1.0 - smoothstep(0.98, 1.02, diamondField);
      dbg = mix(dbg, vec3(1.0, 0.0, 1.0), clamp(edge, 0.0, 0.8));
    }
    float dbgAlpha = mix(1.0, clamp(uMouthMeshAlphaMin, 0.0, 1.0), mouthFade);
    gl_FragColor = vec4(dbg, dbgAlpha);
    return;
  }

  float outAlpha = mix(1.0, clamp(uMouthMeshAlphaMin, 0.0, 1.0), mouthFade);
  gl_FragColor = vec4(finalColor, outAlpha);
}
`;

function logBrowsDiagnostics(geo, material) {
  if (!DEBUG_BROWS_ENABLED || browsDiagnosticsLogged || !geo) return;
  const baseAttr = geo.getAttribute('aBasePosition');
  const uvAttr = geo.getAttribute('aUv');
  if (!baseAttr) {
    console.warn('[debug-brows] No hay aBasePosition en la geometría renderizada.');
    return;
  }

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const yValues = new Float32Array(baseAttr.count);
  for (let i = 0; i < baseAttr.count; i++) {
    const x = baseAttr.getX(i);
    const y = baseAttr.getY(i);
    yValues[i] = y;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }

  const sortedY = Array.from(yValues).sort((a, b) => a - b);
  const yCut = sortedY[Math.floor((sortedY.length - 1) * 0.9)] ?? maxY;

  const bins = 10;
  const binCounts = Array.from({ length: bins }, () => ({ count: 0, sumX: 0, sumY: 0, sumU: 0, sumV: 0 }));
  let topCount = 0;
  let topSumX = 0;
  let topSumY = 0;
  for (let i = 0; i < baseAttr.count; i++) {
    const x = baseAttr.getX(i);
    const y = baseAttr.getY(i);
    if (y < yCut) continue;
    topCount += 1;
    topSumX += x;
    topSumY += y;
    const t = (x - minX) / Math.max(1e-6, maxX - minX);
    const idx = Math.max(0, Math.min(bins - 1, Math.floor(t * bins)));
    const b = binCounts[idx];
    b.count += 1;
    b.sumX += x;
    b.sumY += y;
    if (uvAttr) {
      b.sumU += uvAttr.getX(i);
      b.sumV += uvAttr.getY(i);
    }
  }

  const left = window.EyeBlinkTuning?.left;
  const right = window.EyeBlinkTuning?.right;
  console.info('[debug-brows] realistic geometry aBasePosition bbox XY', { minX, maxX, minY, maxY, vertexCount: baseAttr.count });
  console.info('[debug-brows] EyeBlinkTuning snapshot', { left, right, blink: EyelidMotionState.value });
  console.info('[debug-brows] top-band (10% superior en Y)', {
    yCut,
    topCount,
    centerOfMass: {
      x: topCount ? topSumX / topCount : null,
      y: topCount ? topSumY / topCount : null,
    },
  });
  console.table(binCounts.map((b, i) => ({
    bin: i,
    xRange: [minX + (i / bins) * (maxX - minX), minX + ((i + 1) / bins) * (maxX - minX)],
    count: b.count,
    avgX: b.count ? b.sumX / b.count : null,
    avgY: b.count ? b.sumY / b.count : null,
    avgU: b.count && uvAttr ? b.sumU / b.count : null,
    avgV: b.count && uvAttr ? b.sumV / b.count : null,
  })));

  if (material?.uniforms) {
    console.info('[debug-brows] material/uniform sanity', {
      hasBlinkUniform: !!material.uniforms.uBlink,
      hasEyeLeftUniform: !!material.uniforms.uEyeLeftMain,
      hasEyeRightUniform: !!material.uniforms.uEyeRightMain,
      hasDebugBrowsUniform: !!material.uniforms.uDebugBrows,
      materialType: material.type,
    });
  }
  browsDiagnosticsLogged = true;
}



function materialSideToLabel(side) {
  if (side === THREE.FrontSide) return 'FrontSide';
  if (side === THREE.BackSide) return 'BackSide';
  if (side === THREE.DoubleSide) return 'DoubleSide';
  return `Unknown(${String(side)})`;
}

function setupRealisticSurfaceDebugTools() {
  if (realisticSurfaceDebugSetupDone) return;
  realisticSurfaceDebugSetupDone = true;

  const debugApi = {
    listVisibleMeshes() {
      const rows = [];
      scene.traverse((obj) => {
        if (!obj?.isMesh || !obj.visible) return;
        const mat = obj.material;
        if (!mat) return;
        rows.push({
          name: obj.name || '(unnamed)',
          materialType: mat.type,
          side: materialSideToLabel(mat.side),
          transparent: !!mat.transparent,
          depthTest: !!mat.depthTest,
          depthWrite: !!mat.depthWrite,
          renderOrder: obj.renderOrder ?? 0,
        });
      });
      console.table(rows);
      return rows;
    },
    setSurfaceSide(mode = 'front') {
      if (!particleSurfaceMesh?.material) return false;
      const mat = particleSurfaceMesh.material;
      if (mode === 'front') mat.side = THREE.FrontSide;
      else if (mode === 'double') mat.side = THREE.DoubleSide;
      else if (mode === 'back') mat.side = THREE.BackSide;
      else {
        console.warn('[mouth-artifact-debug] side inválido. Use front|double|back');
        return false;
      }
      mat.needsUpdate = true;
      console.info('[mouth-artifact-debug] surface.side', materialSideToLabel(mat.side));
      return true;
    },
    setSurfaceDepthWrite(enabled = false) {
      if (!particleSurfaceMesh?.material) return false;
      particleSurfaceMesh.material.depthWrite = !!enabled;
      particleSurfaceMesh.material.needsUpdate = true;
      console.info('[mouth-artifact-debug] surface.depthWrite', !!enabled);
      return true;
    },
    setSurfaceTransparent(enabled = true) {
      if (!particleSurfaceMesh?.material) return false;
      particleSurfaceMesh.material.transparent = !!enabled;
      particleSurfaceMesh.material.needsUpdate = true;
      console.info('[mouth-artifact-debug] surface.transparent', !!enabled);
      return true;
    },
    setSurfaceVisible(enabled = true) {
      if (!particleSurfaceMesh) return false;
      particleSurfaceMesh.visible = !!enabled;
      console.info('[mouth-artifact-debug] surface.visible', !!enabled);
      return true;
    },
    setMouthPointsCullBack(enabled = true) {
      if (!mouthPointsMaterial?.uniforms?.uMouthPointsCullBack) return false;
      mouthPointsMaterial.uniforms.uMouthPointsCullBack.value = enabled ? 1.0 : 0.0;
      if (window.MouthRenderTuning) window.MouthRenderTuning.pointsCullBack = !!enabled;
      console.info('[mouth-artifact-debug] mouthPoints.cullBack', !!enabled);
      return true;
    },
    setMouthPointsDebugBackOnly(enabled = false) {
      if (!mouthPointsMaterial?.uniforms?.uMouthPointsDebugBackOnly) return false;
      mouthPointsMaterial.uniforms.uMouthPointsDebugBackOnly.value = enabled ? 1.0 : 0.0;
      if (window.MouthRenderTuning) window.MouthRenderTuning.pointsDebugBackOnly = !!enabled;
      console.info('[mouth-artifact-debug] mouthPoints.debugBackOnly', !!enabled);
      return true;
    },
    resetSurfaceMaterial() {
      if (!particleSurfaceMesh?.material || !realisticSurfaceDebugOriginal) return false;
      const mat = particleSurfaceMesh.material;
      mat.side = realisticSurfaceDebugOriginal.side;
      mat.depthWrite = realisticSurfaceDebugOriginal.depthWrite;
      mat.transparent = realisticSurfaceDebugOriginal.transparent;
      mat.needsUpdate = true;
      console.info('[mouth-artifact-debug] surface material reset', {
        side: materialSideToLabel(mat.side),
        depthWrite: mat.depthWrite,
        transparent: mat.transparent,
      });
      return true;
    },
    help() {
      console.log('[mouth-artifact-debug] comandos:', {
        listVisibleMeshes: 'window.RealisticMouthArtifactDebug.listVisibleMeshes()',
        sideFront: "window.RealisticMouthArtifactDebug.setSurfaceSide('front')",
        sideDouble: "window.RealisticMouthArtifactDebug.setSurfaceSide('double')",
        depthWriteOff: 'window.RealisticMouthArtifactDebug.setSurfaceDepthWrite(false)',
        depthWriteOn: 'window.RealisticMouthArtifactDebug.setSurfaceDepthWrite(true)',
        transparentOff: 'window.RealisticMouthArtifactDebug.setSurfaceTransparent(false)',
        transparentOn: 'window.RealisticMouthArtifactDebug.setSurfaceTransparent(true)',
        hideSurface: 'window.RealisticMouthArtifactDebug.setSurfaceVisible(false)',
        showSurface: 'window.RealisticMouthArtifactDebug.setSurfaceVisible(true)',
        reset: 'window.RealisticMouthArtifactDebug.resetSurfaceMaterial()',
        cullBackOn: 'window.RealisticMouthArtifactDebug.setMouthPointsCullBack(true)',
        cullBackOff: 'window.RealisticMouthArtifactDebug.setMouthPointsCullBack(false)',
        backOnlyOn: 'window.RealisticMouthArtifactDebug.setMouthPointsDebugBackOnly(true)',
        backOnlyOff: 'window.RealisticMouthArtifactDebug.setMouthPointsDebugBackOnly(false)',
      });
    },
  };

  window.RealisticMouthArtifactDebug = debugApi;
}

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
    const realisticSurfaceGeo = generateAnimatedSurfaceGeometry(mergedGeom);

    // refs para edición / recompute
    const t = window.NeckTuning;

    const createParticleMaterial = ({
      pointSize = POINT_SIZE,
      color = activeTheme.particleColor,
      blending = THREE.NormalBlending,
      depthWrite = true,
      blancoMode = 0.0,
      blancoLayer = 0.0,
      blancoInkGamma = 1.85,
      featureBoost = 0.0,
    } = {}) => new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite,
      blending,
      uniforms: {
        uPointSize: { value: pointSize },
        uColor: { value: new THREE.Color(color) },
        uColorMap: { value: colorMap },
        uUseMap: { value: colorMap ? 1.0 : 0.0 },

        // Uniforms perceptuales por tema (single shader, sin bifurcar lógica)
        uDensityInMin: { value: activeTheme.densityInMin },
        uDensityInMax: { value: activeTheme.densityInMax },
        uDensityGamma: { value: activeTheme.densityGamma },
        uDensityOutMin: { value: activeTheme.densityOutMin },
        uDensityOutMax: { value: activeTheme.densityOutMax },
        uAlphaGain: { value: activeTheme.alphaGain },
        uAlphaClip: { value: activeTheme.alphaClip },
        uShadeMin: { value: activeTheme.shadeMin },
        uShadeMax: { value: activeTheme.shadeMax },
        uUseTextureColor: { value: activeTheme.useTextureColor ? 1.0 : 0.0 },
        uUseLumaDensity: { value: activeTheme.useLumaDensity === false ? 0.0 : 1.0 },
        uSaturation: { value: activeTheme.saturation ?? 1.0 },
        uLowDensityAlphaFloor: { value: activeTheme.lowDensityAlphaFloor ?? 0.0 },
        uInvertDensityAsInk: { value: activeTheme.invertDensityAsInk ? 1.0 : 0.0 },
        uInkFloor: { value: activeTheme.inkFloor ?? 0.0 },
        uInkAlphaFloor: { value: activeTheme.inkAlphaFloor ?? 0.0 },
        uDissolveStart: { value: 0.9 },
        uDissolveEnd: { value: 1.0 },
        uDissolveStrength: { value: 0.92 },
        uDissolveSpeed: { value: 1.45 },
        uDissolveMotionAmp: { value: 1.0 },

        uTime: { value: 0.0 },
        uGlobalAmp: { value: 1.5 },
        uClusterAmp: { value: 1.5 },
        uNoiseAmp: { value: 1.6 },

        // habla
        uTalk: { value: 0.0 },
        uTalkAmpTop: { value: 0.024 },
        uTalkAmpBot: { value: 0.075 },
        uTalkFreq: { value: 24.0 },
        uLipDepthAmp: { value: 0.1 },
        uRestOpen: { value: 0.30 },

        // respiración
        uBreathAmp: { value: 1.0 },
        uBreathFreq: { value: 0.6 },

        // rig procedural
        uHeadRot: { value: new THREE.Vector3(0, 0, 0) },
        uBodyRot: { value: new THREE.Vector3(0, 0, 0) },
        uBodyOffset: { value: new THREE.Vector3(0, 0, 0) },
        uNeckPivot: { value: new THREE.Vector3(0.0, t.neckPivotY, 0.0) },
        uBodyPivot: { value: new THREE.Vector3(0.0, t.bodyPivotY, 0.0) },

        // DEBUG
        uDebugHeadWeight: { value: DebugView.headWeight ? 1.0 : 0.0 },
      },
    });

    if (isRealisticTheme) {
      particleMaterial = new THREE.ShaderMaterial({
        vertexShader: realisticSurfaceVertexShader,
        fragmentShader: realisticSurfaceFragmentShader,
        // FrontSide evita contribuciones de backfaces en el recorte de boca
        // (rombo trasero pequeño detectado en modo realistic).
        side: THREE.FrontSide,
        transparent: true,
        uniforms: {
          uColor: { value: new THREE.Color(0xffffff) },
          uColorMap: { value: colorMap },
          uUseMap: { value: colorMap ? 1.0 : 0.0 },
          uTime: { value: 0.0 },
          uGlobalAmp: { value: 1.5 },
          uClusterAmp: { value: 1.5 },
          uNoiseAmp: { value: 1.6 },
          uTalk: { value: 0.0 },
          uTalkAmpTop: { value: 0.024 },
          uTalkAmpBot: { value: 0.075 },
          uTalkFreq: { value: 24.0 },
          uLipDepthAmp: { value: 0.1 },
          uRestOpen: { value: 0.30 },
          uBreathAmp: { value: 1.0 },
          uBreathFreq: { value: 0.6 },
          uHeadRot: { value: new THREE.Vector3(0, 0, 0) },
          uBodyRot: { value: new THREE.Vector3(0, 0, 0) },
          uBodyOffset: { value: new THREE.Vector3(0, 0, 0) },
          uNeckPivot: { value: new THREE.Vector3(0.0, t.neckPivotY, 0.0) },
          uBodyPivot: { value: new THREE.Vector3(0.0, t.bodyPivotY, 0.0) },
          uDissolveStart: { value: 0.9 },
          uDissolveEnd: { value: 1.0 },
          uDissolveMotionAmp: { value: 1.0 },
          uBlink: { value: 0.0 },
          uEyeLeftMain: { value: new THREE.Vector4(0, 0, 0.1, 0) },
          uEyeLeftUpper: { value: new THREE.Vector4(0.03, -0.01, 0, 0) },
          uEyeLeftLower: { value: new THREE.Vector4(-0.03, 0.01, 0, 0) },
          uEyeRightMain: { value: new THREE.Vector4(0, 0, 0.1, 0) },
          uEyeRightUpper: { value: new THREE.Vector4(0.03, -0.01, 0, 0) },
          uEyeRightLower: { value: new THREE.Vector4(-0.03, 0.01, 0, 0) },
          uDebugBrows: { value: (DEBUG_BROWS_ENABLED || DEBUG_EDIT_ENABLED) ? 1.0 : 0.0 },
          uBrowYOffset: { value: window.BrowsDebugTuning.browYOffset },
          uBrowThickness: { value: window.BrowsDebugTuning.browThickness },
          uBrowXSpan: { value: window.BrowsDebugTuning.browXSpan },
          uEyeMarkerAspect: { value: window.BrowsDebugTuning.eyeMarkerAspectY },
          uEyeMarkerScale: { value: window.BrowsDebugTuning.eyeMarkerRadiusScale },
          uEyeMarkerFeather: { value: window.BrowsDebugTuning.eyeMarkerFeather },
          uDebugBlinkCover: { value: DEBUG_BLINK_COVER_ENABLED ? 1.0 : 0.0 },
          uDebugHeadWeight: { value: DebugView.headWeight ? 1.0 : 0.0 },
          uMouthOpenVisual: { value: 0.0 },
          uMouthMeshFade: { value: window.MouthRenderTuning.meshFade },
          uMouthFeather: { value: window.MouthRenderTuning.meshFeather },
          uMouthMeshAlphaMin: { value: window.MouthRenderTuning.meshAlphaMin },
          uMouthMeshFadeGamma: { value: window.MouthRenderTuning.meshFadeGamma },
          uMouthMeshFadeGain: { value: window.MouthRenderTuning.meshFadeGain },
          uDebugMouthFade: { value: DEBUG_MOUTH_FADE_ENABLED ? 1.0 : 0.0 },
          uUseDiamondFade: { value: window.MouthRenderTuning.useDiamondFade ? 1.0 : 0.0 },
          uFadeDiamondCX: { value: window.MouthRenderTuning.fadeDiamondCX },
          uFadeDiamondCY: { value: window.MouthRenderTuning.fadeDiamondCY },
          uFadeDiamondRX: { value: window.MouthRenderTuning.fadeDiamondRX },
          uFadeDiamondRY: { value: window.MouthRenderTuning.fadeDiamondRY },
          uFadeDiamondRot: { value: window.MouthRenderTuning.fadeDiamondRot },
          uMouthHoleActive: { value: 0.0 },
          uDebugMouthDiamond: { value: DEBUG_MOUTH_DIAMOND_ENABLED ? 1.0 : 0.0 },
        },
      });
      particleMaterials = [particleMaterial];
      particleSurfaceMesh = new THREE.Mesh(realisticSurfaceGeo, particleMaterial);
      particleSurfaceMesh.name = 'realisticSurfaceMesh';
      particleSurfaceMesh.frustumCulled = false;
      particleSurfaceMesh.renderOrder = 2;
      realisticSurfaceDebugOriginal = {
        side: particleMaterial.side,
        depthWrite: particleMaterial.depthWrite,
        transparent: particleMaterial.transparent,
      };
      setupRealisticSurfaceDebugTools();
      particlePoints = null;
      particlePointsDetail = null;

      particlesGeometryRef = realisticSurfaceGeo;
      headWeightAttrRef = realisticSurfaceGeo.getAttribute('aHeadWeight');
      basePosAttrRef = realisticSurfaceGeo.getAttribute('aBasePosition');
      mouthWeightAttrRef = realisticSurfaceGeo.getAttribute('aMouthWeight');
      mouthSideAttrRef = realisticSurfaceGeo.getAttribute('aMouthSide');
      logBrowsDiagnostics(realisticSurfaceGeo, particleMaterial);
      const mouthBuild = buildMouthPointsGeometryFromAnimatedSurface(realisticSurfaceGeo);
      if (mouthBuild.geometry && mouthBuild.pointCount > 0) {
        mouthPointsMaterial = new THREE.ShaderMaterial({
          vertexShader: mouthPointsVertexShader,
          fragmentShader: mouthPointsFragmentShader,
          transparent: true,
          depthTest: true,
          depthWrite: false,
          blending: THREE.NormalBlending,
          uniforms: {
            uTime: { value: 0.0 },
            uTalk: { value: 0.0 },
            uTalkAmpTop: { value: 0.024 },
            uTalkAmpBot: { value: 0.075 },
            uTalkFreq: { value: 24.0 },
            uLipDepthAmp: { value: 0.1 },
            uRestOpen: { value: 0.03 },
            uPointSizeNear: { value: window.MouthRenderTuning ? window.MouthRenderTuning.pointsSizeNear ?? (3.0 * window.devicePixelRatio) : (3.0 * window.devicePixelRatio) },
            uPointSizeFar: { value: window.MouthRenderTuning ? window.MouthRenderTuning.pointsSizeFar ?? (2.3 * window.devicePixelRatio) : (2.3 * window.devicePixelRatio) },
            uMouthPointsAlpha: { value: window.MouthRenderTuning.pointsAlpha },
            uMouthPointsAlphaClip: { value: window.MouthRenderTuning.pointsAlphaClip },
            uColorMap: { value: colorMap },
            uUseMap: { value: colorMap ? 1.0 : 0.0 },
            uMouthPointsColorMul: { value: window.MouthRenderTuning.pointsColorMul },
            uPointsLumaFloor: { value: window.MouthRenderTuning.pointsLumaFloor },
            uPointsLumaStrength: { value: window.MouthRenderTuning.pointsLumaStrength },
            uPointsLumaPreserveHue: { value: window.MouthRenderTuning.pointsLumaPreserveHue },
            uPointsLumaDebug: { value: window.MouthRenderTuning.pointsLumaDebug ? 1.0 : 0.0 },
            uMouthPointsCullBack: { value: window.MouthRenderTuning.pointsCullBack ? 1.0 : 0.0 },
            uMouthPointsDebugBackOnly: { value: window.MouthRenderTuning.pointsDebugBackOnly ? 1.0 : 0.0 },
            uHeadRot: { value: new THREE.Vector3(0, 0, 0) },
            uBodyRot: { value: new THREE.Vector3(0, 0, 0) },
            uBodyOffset: { value: new THREE.Vector3(0, 0, 0) },
            uNeckPivot: { value: new THREE.Vector3(0.0, t.neckPivotY, 0.0) },
            uBodyPivot: { value: new THREE.Vector3(0.0, t.bodyPivotY, 0.0) },
          },
        });
        mouthPoints = new THREE.Points(mouthBuild.geometry, mouthPointsMaterial);
        mouthPoints.name = 'mouthPoints';
        mouthPoints.frustumCulled = false;
        mouthPoints.renderOrder = 3;
        mouthPoints.visible = false;
        if (DEBUG_MOUTH_POINTS_ENABLED) {
          console.info('[mouth-points] built', {
            sourceCount: mouthBuild.sourceCount,
            resampleFactor: mouthBuild.rimResampleFactor,
            resampledCount: mouthBuild.resampledCount,
            pointCount: mouthBuild.pointCount,
            frontCountSource: mouthBuild.frontCountSource,
            backCountSource: mouthBuild.backCountSource,
            frontCountResampled: mouthBuild.frontCountResampled,
            backCountResampled: mouthBuild.backCountResampled,
          });
          console.info('[mouth-points] luma-tuning', {
            pointsLumaFloor: window.MouthRenderTuning.pointsLumaFloor,
            pointsLumaStrength: window.MouthRenderTuning.pointsLumaStrength,
            pointsLumaPreserveHue: window.MouthRenderTuning.pointsLumaPreserveHue,
            pointsLumaDebug: !!window.MouthRenderTuning.pointsLumaDebug,
          });
          if (window.RealisticMouthArtifactDebug) {
            console.info('[mouth-artifact-debug] realistic defaults', {
              surface: 'realisticSurfaceMesh',
              side: materialSideToLabel(particleMaterial.side),
              depthWrite: particleMaterial.depthWrite,
              transparent: particleMaterial.transparent,
              renderOrder: particleSurfaceMesh.renderOrder,
            });
            console.info('[mouth-artifact-debug] mouthPoints defaults', {
              cullBack: !!window.MouthRenderTuning.pointsCullBack,
              debugBackOnly: !!window.MouthRenderTuning.pointsDebugBackOnly,
            });
            window.RealisticMouthArtifactDebug.help();
          }
        }
      }
    } else {
      particleMaterial = createParticleMaterial();
      particleMaterials = [particleMaterial];
      particlePoints = new THREE.Points(particlesGeo, particleMaterial);
      particlePoints.frustumCulled = false;
      particlePoints.renderOrder = 2;
      particlePointsDetail = null;

      particlesGeometryRef = particlesGeo;
      headWeightAttrRef = particlesGeo.getAttribute('aHeadWeight');
      basePosAttrRef = particlesGeo.getAttribute('aBasePosition');
      mouthWeightAttrRef = particlesGeo.getAttribute('aMouthWeight');
      mouthSideAttrRef = particlesGeo.getAttribute('aMouthSide');
    }

    if (!activeTheme.removeHeadCutCap) {
      const capGeometry = new THREE.CircleGeometry(HEAD_CUT_CAP.radius, 96);
      const capMaterial = new THREE.MeshBasicMaterial({
        color: activeTheme.background,
        transparent: false,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      headCutCapMesh = new THREE.Mesh(capGeometry, capMaterial);
      headCutCapMesh.scale.set(HEAD_CUT_CAP.scaleX, HEAD_CUT_CAP.scaleY, 1.0);
      headCutCapMesh.position.set(0.0, HEAD_CUT_CAP.y, HEAD_CUT_CAP.z);
      headCutCapMesh.renderOrder = 1;

      scene.add(headCutCapMesh);
    }
    if (particlePoints) scene.add(particlePoints);
    if (particlePointsDetail) scene.add(particlePointsDetail);
    if (particleSurfaceMesh) scene.add(particleSurfaceMesh);
    if (mouthPoints) scene.add(mouthPoints);

    controls.target.set(0, 0.15, 0);
    controls.update();

    // por si se tocó NeckTuning/MouthTuning antes de cargar
    scheduleRecomputeHeadWeights('after_load');
    scheduleRecomputeMouthWeights('after_load');
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
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  resizeNeckEditorOverlay();
  if (DEBUG_MOTION_VERBOSE) {
    console.info('[debug-motion] resize', {
      w,
      h,
      dpr: Number(window.devicePixelRatio.toFixed(2)),
    });
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

    await ctx.resume();

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

  await ctx.resume();

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
  const prevMode = AvatarState.mode;
  AvatarState.mode = nextMode;
  if (DEBUG_MOTION_VERBOSE) {
    MotionDebugState.modeTransitions += 1;
    console.info('[debug-motion] mode-change', {
      from: prevMode,
      to: nextMode,
      elapsed: Number(clock.getElapsedTime().toFixed(3)),
      transitions: MotionDebugState.modeTransitions,
    });
  }
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

function getTalkLevelFromAudio() {
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
// Movimiento humano "espontáneo" (targets + pausas)
// =========================
function randRange(a, b) {
  return a + (b - a) * Math.random();
}

const MOTION_NO_MICRO = URL_PARAMS.get('motionNoMicro') === '1';
const MOTION_NO_NOD = URL_PARAMS.get('motionNoNod') === '1';
const MOTION_NO_HEAD = URL_PARAMS.get('motionNoHead') === '1';
const MOTION_NO_BODY = URL_PARAMS.get('motionNoBody') === '1';

const MotionConfig = {
  head: {
    name: 'head',
    ampYaw: resolveNumberParam('motionAmpHeadYaw', resolveNumberParam('motionAmpHead', 0.040)),
    ampPitch: resolveNumberParam('motionAmpHeadPitch', resolveNumberParam('motionAmpHead', 0.036)),
    ampRoll: resolveNumberParam('motionAmpHeadRoll', resolveNumberParam('motionAmpHead', 0.022)),
    holdMin: resolveNumberParam('motionHoldHeadMin', 1.3),
    holdMax: resolveNumberParam('motionHoldHeadMax', 3.8),
    smooth: resolveNumberParam('motionSmoothHead', 8.0),
    rampDur: resolveNumberParam('motionRampHeadDur', 0.32),
  },
  body: {
    name: 'body',
    ampYaw: resolveNumberParam('motionAmpBodyYaw', 0.010),
    ampPitch: resolveNumberParam('motionAmpBodyPitch', 0.008),
    ampRoll: resolveNumberParam('motionAmpBodyRoll', 0.008),
    holdMin: resolveNumberParam('motionHoldBodyMin', 1.6),
    holdMax: resolveNumberParam('motionHoldBodyMax', 4.2),
    smooth: resolveNumberParam('motionSmoothBody', 5.0),
    rampDur: resolveNumberParam('motionRampBodyDur', 0.40),
  },
  micro: {
    yaw: resolveNumberParam('motionAmpMicroYaw', 0.0045),
    pitch: resolveNumberParam('motionAmpMicroPitch', 0.0030),
    roll: resolveNumberParam('motionAmpMicroRoll', 0.0026),
  },
};

const HEAD_MOTION_GAIN = resolveNumberParam('motionGain', isRealisticTheme ? 1.35 : 1.0);

const MotionState = {
  seed: Math.random() * 1000.0,
  head: {
    current: new THREE.Vector3(0, 0, 0),
    target: new THREE.Vector3(0, 0, 0),
    targetFrom: new THREE.Vector3(0, 0, 0),
    targetTo: new THREE.Vector3(0, 0, 0),
    nextSwitch: 0,
    targetT0: 0,
  },
  body: {
    current: new THREE.Vector3(0, 0, 0),
    target: new THREE.Vector3(0, 0, 0),
    targetFrom: new THREE.Vector3(0, 0, 0),
    targetTo: new THREE.Vector3(0, 0, 0),
    nextSwitch: 0,
    targetT0: 0,
  },
  nod: { active: false, t0: 0, dur: 0.32, amp: 0.012 },
};

const ZERO_VEC3 = new THREE.Vector3(0, 0, 0);
const HEAD_ROT_TMP = new THREE.Vector3(0, 0, 0);
const BODY_ROT_TMP = new THREE.Vector3(0, 0, 0);

if (DEBUG_MOTION_ENABLED) {
  console.info('[debug-motion] params', {
    level: DEBUG_MOTION_LEVEL,
    hud: DEBUG_MOTION_HUD_ENABLED,
    debugControls: DEBUG_CONTROLS_ENABLED,
    headGain: HEAD_MOTION_GAIN,
    noMicro: MOTION_NO_MICRO,
    noNod: MOTION_NO_NOD,
    noHead: MOTION_NO_HEAD,
    noBody: MOTION_NO_BODY,
    head: MotionConfig.head,
    body: MotionConfig.body,
    micro: MotionConfig.micro,
  });
}

function clamp01(v) {
  return THREE.MathUtils.clamp(v, 0.0, 1.0);
}

function nextBlinkInterval() {
  return randRange(2.0, 6.0);
}

function scheduleEyelidBlink(now, minDelay = 0.0) {
  EyelidMotionState.nextBlinkAt = now + minDelay;
}

function scheduleNextRegularBlink(now) {
  scheduleEyelidBlink(now, nextBlinkInterval());
}

function startEyelidBlink(durationSec) {
  EyelidMotionState.phase = 'closing';
  EyelidMotionState.timer = 0.0;
  EyelidMotionState.duration = durationSec;
  EyelidMotionState.value = 0.0;
}

function updateEyelidBlink(elapsed, delta) {
  if (!isRealisticTheme) {
    EyelidMotionState.value = 0.0;
    return;
  }

  if (FORCE_BLINK_ENABLED && elapsed <= EyelidMotionState.forceUntil) {
    EyelidMotionState.value = 1.0;
    return;
  }

  if (FREEZE_IN_EDIT) {
    EyelidMotionState.value = 0.0;
    return;
  }

  if (!EyelidMotionState.initialized) {
    EyelidMotionState.initialized = true;
    scheduleEyelidBlink(elapsed, randRange(0.45, 1.35));
  }

  if (EyelidMotionState.phase === 'idle') {
    if (elapsed >= EyelidMotionState.nextBlinkAt) {
      startEyelidBlink(randRange(0.09, 0.15));
      EyelidMotionState.pendingDouble = Math.random() < 0.2;
    }
    return;
  }

  EyelidMotionState.timer += delta;
  const closeDuration = EyelidMotionState.duration * 0.34;
  const openDuration = EyelidMotionState.duration * 0.66;

  if (EyelidMotionState.phase === 'closing') {
    const t = clamp01(EyelidMotionState.timer / closeDuration);
    EyelidMotionState.value = t;
    if (t >= 1.0) {
      EyelidMotionState.phase = 'opening';
      EyelidMotionState.timer = 0.0;
    }
    return;
  }

  const t = clamp01(EyelidMotionState.timer / openDuration);
  EyelidMotionState.value = 1.0 - t;
  if (t >= 1.0) {
    EyelidMotionState.phase = 'idle';
    EyelidMotionState.timer = 0.0;
    EyelidMotionState.value = 0.0;
    if (EyelidMotionState.pendingDouble) {
      EyelidMotionState.pendingDouble = false;
      EyelidMotionState.nextBlinkAt = elapsed + randRange(0.08, 0.16);
    } else {
      scheduleNextRegularBlink(elapsed);
    }
  }
}

function getBrowsDebugTuning() {
  const t = window.BrowsDebugTuning || {};
  return {
    eyeMarkerAspectY: Math.max(1e-4, Number.isFinite(t.eyeMarkerAspectY) ? t.eyeMarkerAspectY : 0.7),
    eyeMarkerRadiusScale: Math.max(1e-4, Number.isFinite(t.eyeMarkerRadiusScale) ? t.eyeMarkerRadiusScale : 1.0),
    eyeMarkerFeather: Math.max(0.0, Number.isFinite(t.eyeMarkerFeather) ? t.eyeMarkerFeather : 0.18),
    browYOffset: Number.isFinite(t.browYOffset) ? t.browYOffset : 0.085,
    browThickness: Math.max(1e-4, Number.isFinite(t.browThickness) ? t.browThickness : 0.018),
    browXSpan: Math.max(0.0, Number.isFinite(t.browXSpan) ? t.browXSpan : 10.0),
  };
}

function applyBrowsDebugUniforms(mat) {
  if (!mat?.uniforms) return;
  const t = getBrowsDebugTuning();
  if (mat.uniforms.uBrowYOffset) mat.uniforms.uBrowYOffset.value = t.browYOffset;
  if (mat.uniforms.uBrowThickness) mat.uniforms.uBrowThickness.value = t.browThickness;
  if (mat.uniforms.uBrowXSpan) mat.uniforms.uBrowXSpan.value = t.browXSpan;
  if (mat.uniforms.uEyeMarkerAspect) mat.uniforms.uEyeMarkerAspect.value = t.eyeMarkerAspectY;
  if (mat.uniforms.uEyeMarkerScale) mat.uniforms.uEyeMarkerScale.value = t.eyeMarkerRadiusScale;
  if (mat.uniforms.uEyeMarkerFeather) mat.uniforms.uEyeMarkerFeather.value = t.eyeMarkerFeather;
}

function applyEyeBlinkUniforms(mat) {
  const left = window.EyeBlinkTuning.left;
  const right = window.EyeBlinkTuning.right;

  if (mat.uniforms.uBlink) mat.uniforms.uBlink.value = EyelidMotionState.value;

  if (mat.uniforms.uEyeLeftMain) {
    mat.uniforms.uEyeLeftMain.value.set(left.centerX, left.centerY, Math.max(1e-4, Math.abs(left.halfWidth)), left.rotation || 0.0);
    mat.uniforms.uEyeLeftUpper.value.set(left.upper.offset, left.upper.curve, 0.0, 0.0);
    mat.uniforms.uEyeLeftLower.value.set(left.lower.offset, left.lower.curve, 0.0, 0.0);
  }

  if (mat.uniforms.uEyeRightMain) {
    mat.uniforms.uEyeRightMain.value.set(right.centerX, right.centerY, Math.max(1e-4, Math.abs(right.halfWidth)), right.rotation || 0.0);
    mat.uniforms.uEyeRightUpper.value.set(right.upper.offset, right.upper.curve, 0.0, 0.0);
    mat.uniforms.uEyeRightLower.value.set(right.lower.offset, right.lower.curve, 0.0, 0.0);
  }

  applyBrowsDebugUniforms(mat);

  if ((DEBUG_BROWS_ENABLED || FORCE_BLINK_ENABLED) && performance.now() - lastBrowsUniformLogMs > 1200) {
    lastBrowsUniformLogMs = performance.now();
    console.info('[debug-brows] uniforms frame snapshot', {
      blink: EyelidMotionState.value,
      leftMain: mat.uniforms.uEyeLeftMain?.value ? {
        x: mat.uniforms.uEyeLeftMain.value.x,
        y: mat.uniforms.uEyeLeftMain.value.y,
        halfWidth: mat.uniforms.uEyeLeftMain.value.z,
        rotation: mat.uniforms.uEyeLeftMain.value.w,
      } : null,
      rightMain: mat.uniforms.uEyeRightMain?.value ? {
        x: mat.uniforms.uEyeRightMain.value.x,
        y: mat.uniforms.uEyeRightMain.value.y,
        halfWidth: mat.uniforms.uEyeRightMain.value.z,
        rotation: mat.uniforms.uEyeRightMain.value.w,
      } : null,
      debugBrowsUniform: mat.uniforms.uDebugBrows?.value,
      browsDebugTuning: getBrowsDebugTuning(),
    });
  }
}

function getEyeHandlePoint(side, lid, part) {
  const eye = window.EyeBlinkTuning[side];
  const hw = Math.max(1e-4, Math.abs(eye.halfWidth));
  const cfg = eye[lid];
  const xLocal = part === 'left' ? -hw : (part === 'right' ? hw : 0.0);
  const yLocal = cfg.offset + (part === 'center' ? 0.0 : cfg.curve);
  const s = Math.sin(eye.rotation || 0.0);
  const c = Math.cos(eye.rotation || 0.0);
  return {
    x: eye.centerX + xLocal * c - yLocal * s,
    y: eye.centerY + xLocal * s + yLocal * c,
  };
}

function worldToEyeLocal(side, worldPoint, startEyeTuning) {
  const eye = startEyeTuning[side];
  const dx = worldPoint.x - eye.centerX;
  const dy = worldPoint.y - eye.centerY;
  const s = Math.sin(eye.rotation || 0.0);
  const c = Math.cos(eye.rotation || 0.0);
  return {
    x: dx * c + dy * s,
    y: -dx * s + dy * c,
  };
}

function logEyeBlinkTuning(reason = 'update') {
  console.info(`[blink-editor] ${reason}`, window.EyeBlinkTuning);
  console.log('[blink-editor] Pega esto en app.js\nwindow.EyeBlinkTuning = ' + JSON.stringify(window.EyeBlinkTuning, null, 2) + ';');
}

function pickTarget(cfg) {
  const bias = 0.65;
  const s = () => (Math.random() * 2 - 1);
  const soften = () => (Math.random() < bias ? 0.35 : 1.0) * randRange(0.4, 1.0);

  return new THREE.Vector3(
    s() * cfg.ampPitch * soften(),
    s() * cfg.ampYaw * soften(),
    s() * cfg.ampRoll * soften(),
  );
}

function updateChannel(ch, cfg, t, dt) {
  if (t >= ch.nextSwitch) {
    ch.targetFrom.copy(ch.target);
    ch.targetTo.copy(pickTarget(cfg));
    ch.targetT0 = t;
    ch.nextSwitch = t + randRange(cfg.holdMin, cfg.holdMax);
    MotionDebugState.lastTargetSwitchAt = t;
    if (DEBUG_MOTION_ENABLED) {
      console.info('[debug-motion] target-switch', {
        channel: cfg.name,
        now: Number(t.toFixed(3)),
        nextSwitch: Number(ch.nextSwitch.toFixed(3)),
        from: {
          pitch: Number(ch.targetFrom.x.toFixed(4)),
          yaw: Number(ch.targetFrom.y.toFixed(4)),
          roll: Number(ch.targetFrom.z.toFixed(4)),
        },
        to: {
          pitch: Number(ch.targetTo.x.toFixed(4)),
          yaw: Number(ch.targetTo.y.toFixed(4)),
          roll: Number(ch.targetTo.z.toFixed(4)),
        },
        rampDur: Number(cfg.rampDur.toFixed(3)),
      });
    }
  }

  const rampDur = Math.max(0.001, cfg.rampDur || 0.001);
  const rampT = clamp01((t - ch.targetT0) / rampDur);
  const rampS = rampT * rampT * (3.0 - 2.0 * rampT);
  ch.target.copy(ch.targetFrom).lerp(ch.targetTo, rampS);

  const k = 1.0 - Math.exp(-dt * cfg.smooth);
  ch.current.lerp(ch.target, k);
  return k;
}

function updateNod(t, dt) {
  if (!MotionState.nod.active && AvatarState.mode === 'LISTENING') {
    const p = 0.18;
    if (Math.random() < p * dt) {
      MotionState.nod.active = true;
      MotionState.nod.t0 = t;
      MotionState.nod.dur = randRange(0.28, 0.40);
      MotionState.nod.amp = randRange(0.010, 0.014);
    }
  }

  if (!MotionState.nod.active) return 0.0;

  const u = (t - MotionState.nod.t0) / MotionState.nod.dur;
  if (u >= 1.0) {
    MotionState.nod.active = false;
    return 0.0;
  }

  const s = Math.sin(u * 3.14159);
  return -MotionState.nod.amp * s;
}

// =========================
// 7. Loop + modo test labios
// =========================
let lipTestActive = false;
let lipTestStartTime = 0;
let testLipsBtn = null;
let prevFrameElapsed = 0;
let motionTime = 0;

const SNAP_THRESHOLD_CURRENT = resolveNumberParam('motionSnapCurrentThreshold', 0.018);
const SNAP_THRESHOLD_UNIFORM = resolveNumberParam('motionSnapUniformThreshold', 0.030);

function ensureMotionDebugHud() {
  if (!DEBUG_MOTION_HUD_ENABLED || MotionDebugState.hudEl) return;
  const hud = document.createElement('div');
  hud.id = 'motion-debug-hud';
  hud.style.position = 'fixed';
  hud.style.top = '10px';
  hud.style.right = '10px';
  hud.style.zIndex = '9999';
  hud.style.padding = '8px 10px';
  hud.style.font = '12px/1.4 monospace';
  hud.style.color = '#0f0';
  hud.style.background = 'rgba(0,0,0,0.7)';
  hud.style.border = '1px solid rgba(80,255,80,0.45)';
  hud.style.borderRadius = '6px';
  hud.style.whiteSpace = 'pre';
  hud.style.pointerEvents = 'none';
  document.body.appendChild(hud);
  MotionDebugState.hudEl = hud;
}

const reportMotionFrameDebug = ({
  elapsed,
  elapsedJump,
  deltaRaw,
  dtMotion,
  kHead,
  kBody,
  head,
  body,
  headRot,
  bodyRot,
  headRotMag,
  microYaw,
  microPitch,
  microRoll,
  nodPitch,
  offY,
}) => {
  if (!DEBUG_MOTION_ENABLED) return;

  MotionDebugState.deltaMin = Math.min(MotionDebugState.deltaMin, deltaRaw);
  MotionDebugState.deltaMax = Math.max(MotionDebugState.deltaMax, deltaRaw);
  MotionDebugState.deltaSum += deltaRaw;
  MotionDebugState.deltaCount += 1;

  const headCurrentDelta = head.distanceTo(MotionDebugState.prevHeadCurrent);
  const headUniformDelta = headRot.distanceTo(MotionDebugState.prevHeadUniform);
  const bodyUniformDelta = bodyRot.distanceTo(MotionDebugState.prevBodyUniform);

  const snapDetected = headCurrentDelta > SNAP_THRESHOLD_CURRENT || headUniformDelta > SNAP_THRESHOLD_UNIFORM;
  if (snapDetected) {
    MotionDebugState.snapCount += 1;
    console.warn('[debug-motion] SNAP DETECTED', {
      elapsed: Number(elapsed.toFixed(3)),
      deltaRaw: Number(deltaRaw.toFixed(4)),
      dtMotion: Number(dtMotion.toFixed(4)),
      kHead: Number(kHead.toFixed(4)),
      kBody: Number(kBody.toFixed(4)),
      headCurrentDelta: Number(headCurrentDelta.toFixed(4)),
      headUniformDelta: Number(headUniformDelta.toFixed(4)),
      bodyUniformDelta: Number(bodyUniformDelta.toFixed(4)),
      motionTime: Number(motionTime.toFixed(4)),
      headCurrent: { pitch: Number(head.x.toFixed(4)), yaw: Number(head.y.toFixed(4)), roll: Number(head.z.toFixed(4)) },
      headTarget: {
        pitch: Number(MotionState.head.target.x.toFixed(4)),
        yaw: Number(MotionState.head.target.y.toFixed(4)),
        roll: Number(MotionState.head.target.z.toFixed(4)),
      },
      bodyCurrent: { pitch: Number(body.x.toFixed(4)), yaw: Number(body.y.toFixed(4)), roll: Number(body.z.toFixed(4)) },
      bodyTarget: {
        pitch: Number(MotionState.body.target.x.toFixed(4)),
        yaw: Number(MotionState.body.target.y.toFixed(4)),
        roll: Number(MotionState.body.target.z.toFixed(4)),
      },
      microYaw: Number(microYaw.toFixed(4)),
      microPitch: Number(microPitch.toFixed(4)),
      microRoll: Number(microRoll.toFixed(4)),
      nodPitch: Number(nodPitch.toFixed(4)),
      uHeadRot: { x: Number(headRot.x.toFixed(4)), y: Number(headRot.y.toFixed(4)), z: Number(headRot.z.toFixed(4)) },
      uBodyRot: { x: Number(bodyRot.x.toFixed(4)), y: Number(bodyRot.y.toFixed(4)), z: Number(bodyRot.z.toFixed(4)) },
      headRotMag: Number(headRotMag.toFixed(4)),
      offY: Number(offY.toFixed(4)),
      lastTargetSwitchAgo: Number((elapsed - MotionDebugState.lastTargetSwitchAt).toFixed(3)),
      mode: AvatarState.mode,
    });
  }

  const deltaSpikeLevel = deltaRaw > 0.1 ? 100 : (deltaRaw > 0.05 ? 50 : 0);
  if (deltaSpikeLevel > 0) {
    MotionDebugState.spikeCount += 1;
    if (DEBUG_MOTION_VERBOSE && (elapsed - MotionDebugState.lastSpikeLogAt >= 0.25)) {
      MotionDebugState.lastSpikeLogAt = elapsed;
      console.warn(`[debug-motion] delta spike > ${deltaSpikeLevel}ms`, {
        elapsed: Number(elapsed.toFixed(3)),
        elapsedJump: Number(elapsedJump.toFixed(4)),
        deltaRaw: Number(deltaRaw.toFixed(4)),
        dtMotion: Number(dtMotion.toFixed(4)),
        microYaw: Number(microYaw.toFixed(4)),
        microPitch: Number(microPitch.toFixed(4)),
        microRoll: Number(microRoll.toFixed(4)),
        offY: Number(offY.toFixed(4)),
      });
    }
  }

  if (DEBUG_MOTION_VERBOSE && (elapsed - MotionDebugState.lastFrameLogAt >= 0.2)) {
    MotionDebugState.lastFrameLogAt = elapsed;
    console.info('[debug-motion] frame-200ms', {
      elapsed: Number(elapsed.toFixed(3)),
      deltaRaw: Number(deltaRaw.toFixed(4)),
      dtMotion: Number(dtMotion.toFixed(4)),
      motionTime: Number(motionTime.toFixed(4)),
      kHead: Number(kHead.toFixed(4)),
      kBody: Number(kBody.toFixed(4)),
      headCurrent: { pitch: Number(head.x.toFixed(4)), yaw: Number(head.y.toFixed(4)), roll: Number(head.z.toFixed(4)) },
      headTarget: {
        pitch: Number(MotionState.head.target.x.toFixed(4)),
        yaw: Number(MotionState.head.target.y.toFixed(4)),
        roll: Number(MotionState.head.target.z.toFixed(4)),
      },
      bodyCurrent: { pitch: Number(body.x.toFixed(4)), yaw: Number(body.y.toFixed(4)), roll: Number(body.z.toFixed(4)) },
      bodyTarget: {
        pitch: Number(MotionState.body.target.x.toFixed(4)),
        yaw: Number(MotionState.body.target.y.toFixed(4)),
        roll: Number(MotionState.body.target.z.toFixed(4)),
      },
      microYaw: Number(microYaw.toFixed(4)),
      microPitch: Number(microPitch.toFixed(4)),
      microRoll: Number(microRoll.toFixed(4)),
      nodPitch: Number(nodPitch.toFixed(4)),
      uHeadRot: { x: Number(headRot.x.toFixed(4)), y: Number(headRot.y.toFixed(4)), z: Number(headRot.z.toFixed(4)) },
      uBodyRot: { x: Number(bodyRot.x.toFixed(4)), y: Number(bodyRot.y.toFixed(4)), z: Number(bodyRot.z.toFixed(4)) },
      headRotMag: Number(headRotMag.toFixed(4)),
      offY: Number(offY.toFixed(4)),
    });
  }

  if (DEBUG_MOTION_VERBOSE && (elapsed - MotionDebugState.lastFrameLogAt >= 0.2)) {
    MotionDebugState.lastFrameLogAt = elapsed;
    console.info('[debug-motion] frame-200ms', {
      elapsed: Number(elapsed.toFixed(3)),
      deltaRaw: Number(deltaRaw.toFixed(4)),
      dtMotion: Number(dtMotion.toFixed(4)),
      motionTime: Number(motionTime.toFixed(4)),
      kHead: Number(kHead.toFixed(4)),
      kBody: Number(kBody.toFixed(4)),
      headCurrent: { pitch: Number(head.x.toFixed(4)), yaw: Number(head.y.toFixed(4)), roll: Number(head.z.toFixed(4)) },
      headTarget: {
        pitch: Number(MotionState.head.target.x.toFixed(4)),
        yaw: Number(MotionState.head.target.y.toFixed(4)),
        roll: Number(MotionState.head.target.z.toFixed(4)),
      },
      bodyCurrent: { pitch: Number(body.x.toFixed(4)), yaw: Number(body.y.toFixed(4)), roll: Number(body.z.toFixed(4)) },
      bodyTarget: {
        pitch: Number(MotionState.body.target.x.toFixed(4)),
        yaw: Number(MotionState.body.target.y.toFixed(4)),
        roll: Number(MotionState.body.target.z.toFixed(4)),
      },
      microYaw: Number(microYaw.toFixed(4)),
      microPitch: Number(microPitch.toFixed(4)),
      microRoll: Number(microRoll.toFixed(4)),
      nodPitch: Number(nodPitch.toFixed(4)),
      uHeadRot: { x: Number(headRot.x.toFixed(4)), y: Number(headRot.y.toFixed(4)), z: Number(headRot.z.toFixed(4)) },
      uBodyRot: { x: Number(bodyRot.x.toFixed(4)), y: Number(bodyRot.y.toFixed(4)), z: Number(bodyRot.z.toFixed(4)) },
      headRotMag: Number(headRotMag.toFixed(4)),
      offY: Number(offY.toFixed(4)),
    });
  }

  if (elapsed - MotionDebugState.lastReportAt >= 1.0) {
    const deltaAvg = MotionDebugState.deltaCount > 0 ? MotionDebugState.deltaSum / MotionDebugState.deltaCount : 0.0;
    console.info('[debug-motion] 1s-report', {
      elapsed: Number(elapsed.toFixed(3)),
      elapsedJump: Number(elapsedJump.toFixed(4)),
      deltaRaw: Number(deltaRaw.toFixed(4)),
      dtMotion: Number(dtMotion.toFixed(4)),
      deltaMin: Number(MotionDebugState.deltaMin.toFixed(4)),
      deltaMax: Number(MotionDebugState.deltaMax.toFixed(4)),
      deltaAvg: Number(deltaAvg.toFixed(4)),
      kHead: Number(kHead.toFixed(4)),
      kBody: Number(kBody.toFixed(4)),
      headCurrentDelta: Number(headCurrentDelta.toFixed(4)),
      headUniformDelta: Number(headUniformDelta.toFixed(4)),
      snapCount: MotionDebugState.snapCount,
      spikeCount: MotionDebugState.spikeCount,
      microYaw: Number(microYaw.toFixed(4)),
      microPitch: Number(microPitch.toFixed(4)),
      microRoll: Number(microRoll.toFixed(4)),
      nodPitch: Number(nodPitch.toFixed(4)),
      offY: Number(offY.toFixed(4)),
      headRotMag: Number(headRotMag.toFixed(4)),
      lastTargetSwitchAgo: Number((elapsed - MotionDebugState.lastTargetSwitchAt).toFixed(3)),
      mode: AvatarState.mode,
    });
    MotionDebugState.deltaMin = Number.POSITIVE_INFINITY;
    MotionDebugState.deltaMax = 0;
    MotionDebugState.deltaSum = 0;
    MotionDebugState.deltaCount = 0;
    MotionDebugState.spikeCount = 0;
    MotionDebugState.lastReportAt = elapsed;
  }

  ensureMotionDebugHud();
  if (MotionDebugState.hudEl && (elapsed - MotionDebugState.lastHudUpdateAt >= 0.2)) {
    MotionDebugState.lastHudUpdateAt = elapsed;
    MotionDebugState.hudEl.textContent = [
      `dtRaw: ${deltaRaw.toFixed(4)}`,
      `dtMotion: ${dtMotion.toFixed(4)}`,
      `kHead: ${kHead.toFixed(4)}`,
      `headRotMag: ${headRotMag.toFixed(4)}`,
      `lastSwitchAgo: ${(elapsed - MotionDebugState.lastTargetSwitchAt).toFixed(3)}s`,
      `snaps: ${MotionDebugState.snapCount}`,
    ].join('\n');
  }

  MotionDebugState.prevHeadCurrent.copy(head);
  MotionDebugState.prevHeadUniform.copy(headRot);
  MotionDebugState.prevBodyUniform.copy(bodyRot);
};


function reportFrameBudget(elapsed, renderMs, overlayMs) {
  if (!DEBUG_MOTION_ENABLED) return;

  MotionDebugState.renderMsSum += renderMs;
  MotionDebugState.renderMsMax = Math.max(MotionDebugState.renderMsMax, renderMs);
  MotionDebugState.overlayMsSum += overlayMs;
  MotionDebugState.overlayMsMax = Math.max(MotionDebugState.overlayMsMax, overlayMs);
  MotionDebugState.frameBudgetCount += 1;

  const nowMs = performance.now();
  if (nowMs - MotionDebugState.lastFrameBudgetLogMs < 1000) return;

  const n = Math.max(1, MotionDebugState.frameBudgetCount);
  console.info('[debug-motion] frame-budget-1s', {
    elapsed: Number(elapsed.toFixed(3)),
    renderMsAvg: Number((MotionDebugState.renderMsSum / n).toFixed(3)),
    renderMsMax: Number(MotionDebugState.renderMsMax.toFixed(3)),
    overlayMsAvg: Number((MotionDebugState.overlayMsSum / n).toFixed(3)),
    overlayMsMax: Number(MotionDebugState.overlayMsMax.toFixed(3)),
    samples: n,
  });

  MotionDebugState.renderMsSum = 0;
  MotionDebugState.renderMsMax = 0;
  MotionDebugState.overlayMsSum = 0;
  MotionDebugState.overlayMsMax = 0;
  MotionDebugState.frameBudgetCount = 0;
  MotionDebugState.lastFrameBudgetReportAt = elapsed;
  MotionDebugState.lastFrameBudgetLogMs = nowMs;
}

function animate() {
  requestAnimationFrame(animate);

  // Usamos una sola lectura de tiempo por frame para evitar dt≈0 por doble muestreo del clock.
  const elapsed = clock.getElapsedTime();
  const elapsedJump = prevFrameElapsed > 0 ? Math.max(0.0, elapsed - prevFrameElapsed) : 0.0;
  const deltaRaw = elapsedJump;
  prevFrameElapsed = elapsed;

  // dt separado para evitar snaps en motion con spikes de RAF (tab switch/frame drops)
  const dtBlink = Math.min(deltaRaw, 0.05);
  const dtMotion = Math.min(deltaRaw, 1.0 / 30.0);
  motionTime += dtMotion;
  updateEyelidBlink(elapsed, dtBlink);

  const mouthHeadRot = HEAD_ROT_TMP.set(0, 0, 0);
  const mouthBodyRot = BODY_ROT_TMP.set(0, 0, 0);
  let mouthOffY = 0.0;

  if (particleMaterials.length) {
    let targetTalk = 0.0;
    if (lipHoldActive) targetTalk = 1.0;
    else targetTalk = getTalkLevelFromAudio();

    AvatarState.talkLevel = targetTalk;

    const mouthTuning = window.MouthRenderTuning;
    const mouthSpeed = targetTalk > mouthOpenVisual ? mouthTuning.mouthAttack : mouthTuning.mouthRelease;
    const mouthSmoothing = 1.0 - Math.exp(-Math.max(0.0, dtMotion) * mouthSpeed);
    mouthOpenVisual += (targetTalk - mouthOpenVisual) * mouthSmoothing;

    if (!mouthPointsVisibleLatched && mouthOpenVisual > mouthTuning.pointsOn) {
      mouthPointsVisibleLatched = true;
      if (DEBUG_MOUTH_POINTS_ENABLED) console.info('[mouth-points] latch ON', { mouthOpenVisual: Number(mouthOpenVisual.toFixed(3)) });
    } else if (mouthPointsVisibleLatched && mouthOpenVisual < mouthTuning.pointsOff) {
      mouthPointsVisibleLatched = false;
      if (DEBUG_MOUTH_POINTS_ENABLED) console.info('[mouth-points] latch OFF', { mouthOpenVisual: Number(mouthOpenVisual.toFixed(3)) });
    }

    let microYaw = 0.0;
    let microPitch = 0.0;
    let microRoll = 0.0;
    let nodPitch = 0.0;
    let offY = 0.0;
    let kHead = 0.0;
    let kBody = 0.0;

    if (!FREEZE_IN_EDIT) {
      if (!MOTION_NO_HEAD) kHead = updateChannel(MotionState.head, MotionConfig.head, motionTime, dtMotion);
      if (!MOTION_NO_BODY) kBody = updateChannel(MotionState.body, MotionConfig.body, motionTime, dtMotion);

      if (!MOTION_NO_MICRO) {
        microYaw =
          (Math.sin(motionTime * 2.1 + MotionState.seed) * MotionConfig.micro.yaw) +
          (Math.sin(motionTime * 3.7 + MotionState.seed * 0.3) * MotionConfig.micro.yaw * 0.45);

        microPitch =
          (Math.sin(motionTime * 1.8 + MotionState.seed * 0.7) * MotionConfig.micro.pitch) +
          (Math.sin(motionTime * 3.2 + MotionState.seed * 0.2) * MotionConfig.micro.pitch * 0.45);

        microRoll =
          (Math.sin(motionTime * 1.5 + MotionState.seed * 1.3) * MotionConfig.micro.roll) +
          (Math.sin(motionTime * 2.9 + MotionState.seed * 0.4) * MotionConfig.micro.roll * 0.45);
      }

      if (!MOTION_NO_NOD) nodPitch = updateNod(motionTime, dtMotion);

      if (AvatarState.idleMotionEnabled) {
        offY = 0.01 * Math.sin(motionTime * 0.9) + 0.005 * Math.sin(motionTime * 0.37);
      }
    }

    const head = (FREEZE_IN_EDIT || MOTION_NO_HEAD) ? ZERO_VEC3 : MotionState.head.current;
    const body = (FREEZE_IN_EDIT || MOTION_NO_BODY) ? ZERO_VEC3 : MotionState.body.current;
    const headRot = HEAD_ROT_TMP.set(
      (head.x + microPitch + nodPitch) * HEAD_MOTION_GAIN,
      (head.y + microYaw) * HEAD_MOTION_GAIN,
      (head.z + microRoll) * HEAD_MOTION_GAIN,
    );
    const bodyRot = BODY_ROT_TMP.set(
      body.x + microPitch * 0.25,
      body.y + microYaw * 0.25,
      body.z + microRoll * 0.25,
    );
    mouthHeadRot.copy(headRot);
    mouthBodyRot.copy(bodyRot);
    mouthOffY = offY;
    const headRotMag = headRot.length();
    reportMotionFrameDebug({
      elapsed,
      elapsedJump,
      deltaRaw,
      dtMotion,
      kHead,
      kBody,
      head,
      body,
      headRot,
      bodyRot,
      headRotMag,
      microYaw,
      microPitch,
      microRoll,
      nodPitch,
      offY,
    });

    for (const mat of particleMaterials) {
      mat.uniforms.uTime.value = elapsed;
      mat.uniforms.uTalk.value = AvatarState.talkLevel;
      mat.uniforms.uRestOpen.value = 0.03;
      applyEyeBlinkUniforms(mat);
      mat.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;
      if (mat.uniforms.uMouthOpenVisual) mat.uniforms.uMouthOpenVisual.value = mouthOpenVisual;
      if (mat.uniforms.uMouthMeshFade) mat.uniforms.uMouthMeshFade.value = window.MouthRenderTuning.meshFade;
      if (mat.uniforms.uMouthFeather) mat.uniforms.uMouthFeather.value = window.MouthRenderTuning.meshFeather;
      if (mat.uniforms.uMouthMeshAlphaMin) mat.uniforms.uMouthMeshAlphaMin.value = window.MouthRenderTuning.meshAlphaMin;
      if (mat.uniforms.uMouthMeshFadeGamma) mat.uniforms.uMouthMeshFadeGamma.value = window.MouthRenderTuning.meshFadeGamma;
      if (mat.uniforms.uMouthMeshFadeGain) mat.uniforms.uMouthMeshFadeGain.value = window.MouthRenderTuning.meshFadeGain;
      if (mat.uniforms.uUseDiamondFade) mat.uniforms.uUseDiamondFade.value = window.MouthRenderTuning.useDiamondFade ? 1.0 : 0.0;
      if (mat.uniforms.uFadeDiamondCX) mat.uniforms.uFadeDiamondCX.value = window.MouthRenderTuning.fadeDiamondCX;
      if (mat.uniforms.uFadeDiamondCY) mat.uniforms.uFadeDiamondCY.value = window.MouthRenderTuning.fadeDiamondCY;
      if (mat.uniforms.uFadeDiamondRX) mat.uniforms.uFadeDiamondRX.value = window.MouthRenderTuning.fadeDiamondRX;
      if (mat.uniforms.uFadeDiamondRY) mat.uniforms.uFadeDiamondRY.value = window.MouthRenderTuning.fadeDiamondRY;
      if (mat.uniforms.uFadeDiamondRot) mat.uniforms.uFadeDiamondRot.value = window.MouthRenderTuning.fadeDiamondRot;
      if (mat.uniforms.uMouthHoleActive) mat.uniforms.uMouthHoleActive.value = mouthPointsVisibleLatched ? 1.0 : 0.0;
      if (mat.uniforms.uDebugMouthDiamond) mat.uniforms.uDebugMouthDiamond.value = DEBUG_MOUTH_DIAMOND_ENABLED ? 1.0 : 0.0;
      if (mat.uniforms.uDebugMouthFade) mat.uniforms.uDebugMouthFade.value = DEBUG_MOUTH_FADE_ENABLED ? 1.0 : 0.0;

      mat.uniforms.uHeadRot.value.copy(headRot);

      mat.uniforms.uBodyRot.value.copy(bodyRot);

      mat.uniforms.uBodyOffset.value.set(0.0, offY, 0.0);

      if (DEBUG_EDIT_ENABLED) {
        const t = window.NeckTuning;
        mat.uniforms.uNeckPivot.value.set(0.0, t.neckPivotY, 0.0);
        mat.uniforms.uBodyPivot.value.set(0.0, t.bodyPivotY, 0.0);
      }
    }
  }

  if (mouthPoints && mouthPointsMaterial) {
    mouthPoints.visible = MOUTH_POINTS_ONLY_ENABLED ? true : mouthPointsVisibleLatched;
    mouthPointsMaterial.uniforms.uTime.value = elapsed;
    mouthPointsMaterial.uniforms.uTalk.value = AvatarState.talkLevel;
    mouthPointsMaterial.uniforms.uRestOpen.value = 0.03;
    mouthPointsMaterial.uniforms.uMouthPointsAlpha.value = window.MouthRenderTuning.pointsAlpha;
    mouthPointsMaterial.uniforms.uMouthPointsAlphaClip.value = window.MouthRenderTuning.pointsAlphaClip;
    mouthPointsMaterial.uniforms.uPointSizeNear.value = window.MouthRenderTuning.pointsSizeNear;
    mouthPointsMaterial.uniforms.uPointSizeFar.value = window.MouthRenderTuning.pointsSizeFar;
    if (mouthPointsMaterial.uniforms.uMouthPointsColorMul) mouthPointsMaterial.uniforms.uMouthPointsColorMul.value = window.MouthRenderTuning.pointsColorMul;
    if (mouthPointsMaterial.uniforms.uPointsLumaFloor) mouthPointsMaterial.uniforms.uPointsLumaFloor.value = window.MouthRenderTuning.pointsLumaFloor;
    if (mouthPointsMaterial.uniforms.uPointsLumaStrength) mouthPointsMaterial.uniforms.uPointsLumaStrength.value = window.MouthRenderTuning.pointsLumaStrength;
    if (mouthPointsMaterial.uniforms.uPointsLumaPreserveHue) mouthPointsMaterial.uniforms.uPointsLumaPreserveHue.value = window.MouthRenderTuning.pointsLumaPreserveHue;
    if (mouthPointsMaterial.uniforms.uPointsLumaDebug) mouthPointsMaterial.uniforms.uPointsLumaDebug.value = window.MouthRenderTuning.pointsLumaDebug ? 1.0 : 0.0;
    if (mouthPointsMaterial.uniforms.uMouthPointsCullBack) mouthPointsMaterial.uniforms.uMouthPointsCullBack.value = window.MouthRenderTuning.pointsCullBack ? 1.0 : 0.0;
    if (mouthPointsMaterial.uniforms.uMouthPointsDebugBackOnly) mouthPointsMaterial.uniforms.uMouthPointsDebugBackOnly.value = window.MouthRenderTuning.pointsDebugBackOnly ? 1.0 : 0.0;
    mouthPointsMaterial.uniforms.uHeadRot.value.copy(mouthHeadRot);
    mouthPointsMaterial.uniforms.uBodyRot.value.copy(mouthBodyRot);
    mouthPointsMaterial.uniforms.uBodyOffset.value.set(0.0, mouthOffY, 0.0);
    if (DEBUG_EDIT_ENABLED) {
      const t = window.NeckTuning;
      mouthPointsMaterial.uniforms.uNeckPivot.value.set(0.0, t.neckPivotY, 0.0);
      mouthPointsMaterial.uniforms.uBodyPivot.value.set(0.0, t.bodyPivotY, 0.0);
    }
  }
  if (particleSurfaceMesh) {
    particleSurfaceMesh.visible = !MOUTH_POINTS_ONLY_ENABLED;
  }

  if (particlePoints) {
    particlePoints.rotation.set(0, 0, 0);
    particlePoints.position.set(0, 0, 0);
  }
  if (particlePointsDetail) {
    particlePointsDetail.rotation.set(0, 0, 0);
    particlePointsDetail.position.set(0, 0, 0);
  }
  if (particleSurfaceMesh) {
    particleSurfaceMesh.rotation.set(0, 0, 0);
    particleSurfaceMesh.position.set(0, 0, 0);
  }
  if (mouthPoints) {
    mouthPoints.rotation.set(0, 0, 0);
    mouthPoints.position.set(0, 0, 0);
  }

  controls.update();
  const renderT0 = performance.now();
  renderer.render(scene, camera);
  const renderMs = performance.now() - renderT0;

  let overlayMs = 0;
  if (NeckEditor && NeckEditor.visible) {
    const overlayT0 = performance.now();
    drawNeckEditorOverlay();
    overlayMs = performance.now() - overlayT0;
  }

  reportFrameBudget(elapsed, renderMs, overlayMs);
}

if (!window.__avatarRAFStarted) {
  window.__avatarRAFStarted = true;
  animate();
} else if (DEBUG_MOTION_ENABLED) {
  console.warn('[debug-motion] animate() ya estaba iniciado; se evita doble RAF loop.');
}

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

const chatUiContainers = [
  ui.replyContainer,
  document.querySelector('.bottom-bar'),
  ui.permissionOverlay,
  ui.listeningGlow,
].filter(Boolean);

if (DEBUG_EDIT_ENABLED) {
  // Refuerzo: volvemos a ocultar UI conversacional cuando ya están resueltos todos los nodos `ui`.
  hideConversationUiForDebugEdit();
}

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
let recorderMimeType = 'audio/webm;codecs=opus';
let discardRecording = false;
let orbLevel = 0;

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
    const rmsNorm = Math.min(1, rms * 6);
    level = Math.max(rmsNorm, idle);
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

  discardRecording = false;
  audioStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

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
  await waveAudioCtx.resume();
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;
  const source = waveAudioCtx.createMediaStreamSource(audioStream);
  source.connect(waveAnalyser);
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
  if (demoFeedbackMode.isFinished()) return;

  enterThinking();
  updateReplyText('…');

  try {
    const demoTurn = demoFeedbackMode.getReplyForTurn();
    const turnReply = demoTurn.shouldSkipBackend
      ? {
          replyText: demoTurn.replyText,
          emotion: demoTurn.emotion,
          intensity: demoTurn.intensity,
        }
      : await fetchAgentReply(message, { mode: currentAgentMode });

    updateReplyText(turnReply.replyText);
    await enterSpeaking(turnReply.replyText, {
      emotion: turnReply.emotion,
      intensity: turnReply.intensity,
    });
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
  const ok = await requestMicPermissions();
  if (!ok) {
    // Fallback no bloqueante: permitir continuar en modo texto si no hay micro.
    if (ui.permissionError) {
      ui.permissionError.textContent = 'No pudimos acceder al micrófono. Continuamos en modo escritura.';
    }
    if (ui.permissionOverlay) ui.permissionOverlay.style.display = 'none';
    setInputMode(InputMode.WRITE);
    enterIdle();
    updateReplyText('No detectamos micrófono. Puedes escribir tu mensaje y continuar.');
    flashStatus('Micrófono no disponible. Modo escritura activado.');
    return;
  }

  try {
    await getOrCreateAudioContext().resume();
    warmupFrontendTts();
  } catch (_) {}

  if (ui.permissionOverlay) ui.permissionOverlay.style.display = 'none';
  setInputMode(InputMode.TALK);
  updateReplyText('Te escucho. Empieza a hablar cuando quieras.');
  await enterListening();
}

if (!DEBUG_EDIT_ENABLED) {
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

  demoFeedbackMode.mount({
    hiddenContainers: chatUiContainers,
    onFinish: () => {
      stopInputOrb();
      cancelRecording();
      cleanupAudio();
      setListeningGlowEnabled(false);
      enterIdle();
    },
  });

  setInputMode(currentInputMode);
  setAgentMode(currentAgentMode);
  updateUiForMode();
}

// =========================
// 10. Botón "Hablar (test)" – solo frontend, sin backend (debug)
// =========================
if (!DEBUG_EDIT_ENABLED && URL_PARAMS.get('debugTalk') === '1') {
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


function setNeckEditorVisible(v) {
  if (!NeckEditor.enabled) return;
  if (!NeckEditor.overlay) initNeckEditorOverlay();
  NeckEditor.visible = !!v;
  NeckEditor.overlay.style.display = NeckEditor.visible ? 'block' : 'none';
  if (NeckEditor.infoEl) NeckEditor.infoEl.style.display = NeckEditor.visible ? 'block' : 'none';
  NeckEditor.overlay.style.pointerEvents = NeckEditor.visible ? 'auto' : 'none';
}

function initNeckEditorOverlay() {
  if (!NeckEditor.enabled || NeckEditor.overlay) return;

  const overlay = document.createElement('canvas');
  overlay.id = 'neck-editor-overlay';
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
  NeckEditor.overlay = overlay;
  NeckEditor.ctx = overlay.getContext('2d');

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
    maxWidth: '420px',
    userSelect: 'none',
  });
  info.innerHTML = `
    <div style="font-weight:700; margin-bottom:6px;">Neck + Mouth + Eyelid Editor</div>
    <div>Arrastra handles. Tecla <b>E</b> ocultar/mostrar.</div>
    <div style="margin-top:6px; opacity:.9">
      <div><span style="color:#ff6b6b">■</span> Neck: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>, <b>neckPivot</b>, <b>bodyPivot</b></div>
      <div style="margin-top:4px;"><span style="color:#67e8f9">■</span> Mouth: <b>mouth_center</b>, <b>mouth_left</b>, <b>mouth_right</b>, <b>mouth_top</b>, <b>mouth_bottom</b>, <b>mouth_curve</b></div>
      <div style="margin-top:4px;"><span style="color:#fde047">■</span> Blink: <b>eye_*_center</b> + <b>eye_*_upper/lower_(left|center|right)</b> + <b>eye_*_rotate</b></div>
    </div>
    <div style="margin-top:8px; opacity:.85">Cada cambio imprime JSON en consola (neck, mouth y blink).</div>
  `;
  document.body.appendChild(info);
  NeckEditor.infoEl = info;

  overlay.addEventListener('mousemove', onNeckEditorMove);
  overlay.addEventListener('mousedown', onNeckEditorDown);
  window.addEventListener('mouseup', onNeckEditorUp);

  overlay.addEventListener('touchstart', onNeckEditorTouchStart, { passive: false });
  overlay.addEventListener('touchmove', onNeckEditorTouchMove, { passive: false });
  overlay.addEventListener('touchend', onNeckEditorTouchEnd, { passive: false });

  resizeNeckEditorOverlay();
  setNeckEditorVisible(true);
}

function resizeNeckEditorOverlay() {
  if (!NeckEditor.overlay) return;
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  NeckEditor.dpr = dpr;
  NeckEditor.overlay.width = Math.floor(window.innerWidth * dpr);
  NeckEditor.overlay.height = Math.floor(window.innerHeight * dpr);
  NeckEditor.overlay.style.width = '100vw';
  NeckEditor.overlay.style.height = '100vh';
  const ctx = NeckEditor.ctx;
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
  NeckEditor.raycaster.setFromCamera(ndc, camera);
  const out = new THREE.Vector3();
  const hit = NeckEditor.raycaster.ray.intersectPlane(NeckEditor.plane, out);
  return hit ? out.clone() : null;
}

function getHandlesModel() {
  const t = window.NeckTuning;
  const midY = (t.topY + t.bottomY) * 0.5;
  const wAbs = Math.max(1e-6, Math.abs(t.width));
  const curveX = t.centerX + wAbs;
  const curveY = t.topY - t.curve;

  const m = window.MouthTuning;
  const mwAbs = Math.max(1e-6, Math.abs(m.width));
  const mhAbs = Math.max(1e-6, Math.abs(m.height));
  const mCurveX = m.centerX + mwAbs;
  const mCurveY = m.centerY - m.curve;

  return {
    center: { x: t.centerX, y: midY },
    top: { x: t.centerX, y: t.topY },
    bottom: { x: t.centerX, y: t.bottomY },
    left: { x: t.centerX - wAbs, y: midY },
    right: { x: t.centerX + wAbs, y: midY },
    curve: { x: curveX, y: curveY },
    neckPivot: { x: t.centerX, y: t.neckPivotY },
    bodyPivot: { x: t.centerX, y: t.bodyPivotY },

    mouth_center: { x: m.centerX, y: m.centerY },
    mouth_left: { x: m.centerX - mwAbs, y: m.centerY },
    mouth_right: { x: m.centerX + mwAbs, y: m.centerY },
    mouth_top: { x: m.centerX, y: m.centerY + mhAbs },
    mouth_bottom: { x: m.centerX, y: m.centerY - mhAbs },
    mouth_curve: { x: mCurveX, y: mCurveY },

    mouth_diamond_center: { x: window.MouthRenderTuning.fadeDiamondCX, y: window.MouthRenderTuning.fadeDiamondCY },
    mouth_diamond_rx: (() => {
      const t = window.MouthRenderTuning;
      return { x: t.fadeDiamondCX + Math.cos(t.fadeDiamondRot) * Math.max(1e-6, Math.abs(t.fadeDiamondRX)), y: t.fadeDiamondCY + Math.sin(t.fadeDiamondRot) * Math.max(1e-6, Math.abs(t.fadeDiamondRX)) };
    })(),
    mouth_diamond_ry: (() => {
      const t = window.MouthRenderTuning;
      return { x: t.fadeDiamondCX - Math.sin(t.fadeDiamondRot) * Math.max(1e-6, Math.abs(t.fadeDiamondRY)), y: t.fadeDiamondCY + Math.cos(t.fadeDiamondRot) * Math.max(1e-6, Math.abs(t.fadeDiamondRY)) };
    })(),
    mouth_diamond_rot: (() => {
      const t = window.MouthRenderTuning;
      const r = Math.max(Math.abs(t.fadeDiamondRX), Math.abs(t.fadeDiamondRY)) + 0.05;
      return { x: t.fadeDiamondCX + Math.cos(t.fadeDiamondRot) * r, y: t.fadeDiamondCY + Math.sin(t.fadeDiamondRot) * r };
    })(),

    eye_left_center: { x: window.EyeBlinkTuning.left.centerX, y: window.EyeBlinkTuning.left.centerY },
    eye_left_upper_left: getEyeHandlePoint('left', 'upper', 'left'),
    eye_left_upper_center: getEyeHandlePoint('left', 'upper', 'center'),
    eye_left_upper_right: getEyeHandlePoint('left', 'upper', 'right'),
    eye_left_lower_left: getEyeHandlePoint('left', 'lower', 'left'),
    eye_left_lower_center: getEyeHandlePoint('left', 'lower', 'center'),
    eye_left_lower_right: getEyeHandlePoint('left', 'lower', 'right'),
    eye_left_rotate: (() => { const e = window.EyeBlinkTuning.left; const r = e.rotation || 0.0; return { x: e.centerX + Math.cos(r) * (e.halfWidth + 0.06), y: e.centerY + Math.sin(r) * (e.halfWidth + 0.06) }; })(),

    eye_right_center: { x: window.EyeBlinkTuning.right.centerX, y: window.EyeBlinkTuning.right.centerY },
    eye_right_upper_left: getEyeHandlePoint('right', 'upper', 'left'),
    eye_right_upper_center: getEyeHandlePoint('right', 'upper', 'center'),
    eye_right_upper_right: getEyeHandlePoint('right', 'upper', 'right'),
    eye_right_lower_left: getEyeHandlePoint('right', 'lower', 'left'),
    eye_right_lower_center: getEyeHandlePoint('right', 'lower', 'center'),
    eye_right_lower_right: getEyeHandlePoint('right', 'lower', 'right'),
    eye_right_rotate: (() => { const e = window.EyeBlinkTuning.right; const r = e.rotation || 0.0; return { x: e.centerX + Math.cos(r) * (e.halfWidth + 0.06), y: e.centerY + Math.sin(r) * (e.halfWidth + 0.06) }; })(),

    brow_line_center: (() => {
      const t = getBrowsDebugTuning();
      const browY = 0.5 * (window.EyeBlinkTuning.left.centerY + window.EyeBlinkTuning.right.centerY) + t.browYOffset;
      return { x: 0.0, y: browY };
    })(),
    brow_thickness: (() => {
      const t = getBrowsDebugTuning();
      const browY = 0.5 * (window.EyeBlinkTuning.left.centerY + window.EyeBlinkTuning.right.centerY) + t.browYOffset;
      return { x: 0.0, y: browY + t.browThickness };
    })(),
    brow_span: (() => {
      const t = getBrowsDebugTuning();
      const browY = 0.5 * (window.EyeBlinkTuning.left.centerY + window.EyeBlinkTuning.right.centerY) + t.browYOffset;
      return { x: t.browXSpan, y: browY };
    })(),
    eye_marker_scale_left: (() => {
      const t = getBrowsDebugTuning();
      const e = window.EyeBlinkTuning.left;
      return { x: e.centerX + e.halfWidth * t.eyeMarkerRadiusScale, y: e.centerY };
    })(),
    eye_marker_aspect_left: (() => {
      const t = getBrowsDebugTuning();
      const e = window.EyeBlinkTuning.left;
      return { x: e.centerX, y: e.centerY + e.halfWidth * t.eyeMarkerRadiusScale * t.eyeMarkerAspectY };
    })(),
    eye_marker_feather_left: (() => {
      const t = getBrowsDebugTuning();
      const e = window.EyeBlinkTuning.left;
      return { x: e.centerX + e.halfWidth * t.eyeMarkerRadiusScale * (1.0 - t.eyeMarkerFeather), y: e.centerY };
    })(),
  };
}

function pickHandle(clientX, clientY) {
  const handles = getHandlesModel();
  let best = null;
  let bestD = Infinity;
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);
    const dx = s.x - clientX;
    const dy = s.y - clientY;
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < NeckEditor.handlesRadius && d < bestD) {
      bestD = d;
      best = key;
    }
  }
  return best;
}

function applyDrag(key, worldPoint, startPoint, startNeckTuning, startMouthTuning, startEyeBlinkTuning, startMouthRenderTuning) {
  const minBand = 1e-4;

  if (key.startsWith('brow_') || key.startsWith('eye_marker_')) {
    const t = getBrowsDebugTuning();
    const midEyeY = 0.5 * (window.EyeBlinkTuning.left.centerY + window.EyeBlinkTuning.right.centerY);
    const browY = midEyeY + t.browYOffset;

    if (key === 'brow_line_center') {
      window.BrowsDebugTuning.browYOffset = worldPoint.y - midEyeY;
      return;
    }

    if (key === 'brow_thickness') {
      window.BrowsDebugTuning.browThickness = Math.max(1e-4, Math.abs(worldPoint.y - browY));
      return;
    }

    if (key === 'brow_span') {
      window.BrowsDebugTuning.browXSpan = Math.max(0.0, Math.abs(worldPoint.x));
      return;
    }

    const baseHalf = Math.max(1e-4, Math.abs(window.EyeBlinkTuning.left.halfWidth));
    if (key === 'eye_marker_scale_left') {
      window.BrowsDebugTuning.eyeMarkerRadiusScale = Math.max(0.1, Math.abs(worldPoint.x - window.EyeBlinkTuning.left.centerX) / baseHalf);
      return;
    }

    if (key === 'eye_marker_aspect_left') {
      const denom = baseHalf * Math.max(1e-4, getBrowsDebugTuning().eyeMarkerRadiusScale);
      window.BrowsDebugTuning.eyeMarkerAspectY = Math.max(0.1, Math.abs(worldPoint.y - window.EyeBlinkTuning.left.centerY) / denom);
      return;
    }

    if (key === 'eye_marker_feather_left') {
      const scale = Math.max(1e-4, getBrowsDebugTuning().eyeMarkerRadiusScale);
      const outerX = window.EyeBlinkTuning.left.centerX + baseHalf * scale;
      const innerX = Math.max(window.EyeBlinkTuning.left.centerX, Math.min(outerX, worldPoint.x));
      const ratio = (innerX - window.EyeBlinkTuning.left.centerX) / Math.max(1e-4, outerX - window.EyeBlinkTuning.left.centerX);
      window.BrowsDebugTuning.eyeMarkerFeather = Math.max(0.0, Math.min(0.95, 1.0 - ratio));
      return;
    }
  }

  if (key.startsWith('eye_')) {
    const parts = key.split('_');
    const side = parts[1]; // left/right
    const eye = window.EyeBlinkTuning[side];
    const startEye = startEyeBlinkTuning[side];

    if (parts[2] === 'center') {
      const dx = worldPoint.x - startPoint.x;
      const dy = worldPoint.y - startPoint.y;
      eye.centerX = startEye.centerX + dx;
      eye.centerY = startEye.centerY + dy;
      return;
    }

    if (parts[2] === 'rotate') {
      eye.rotation = Math.atan2(worldPoint.y - eye.centerY, worldPoint.x - eye.centerX);
      return;
    }

    const lid = parts[2]; // upper/lower
    const part = parts[3]; // left/center/right
    const local = worldToEyeLocal(side, worldPoint, startEyeBlinkTuning);

    if (part === 'center') {
      eye[lid].offset = local.y;
      return;
    }

    eye.halfWidth = Math.max(0.03, Math.abs(local.x));
    eye[lid].curve = local.y - eye[lid].offset;
    return;
  }

  if (key.startsWith('mouth_diamond_')) {
    const t = window.MouthRenderTuning;
    const start = NeckEditor.dragging?.startMouthRenderTuning || { ...window.MouthRenderTuning };
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;

    if (key === 'mouth_diamond_center') {
      t.fadeDiamondCX = start.fadeDiamondCX + dx;
      t.fadeDiamondCY = start.fadeDiamondCY + dy;
    }

    if (key === 'mouth_diamond_rx') {
      const ax = Math.cos(start.fadeDiamondRot);
      const ay = Math.sin(start.fadeDiamondRot);
      const vx = worldPoint.x - t.fadeDiamondCX;
      const vy = worldPoint.y - t.fadeDiamondCY;
      t.fadeDiamondRX = Math.max(1e-4, Math.abs(vx * ax + vy * ay));
    }

    if (key === 'mouth_diamond_ry') {
      const ax = -Math.sin(start.fadeDiamondRot);
      const ay = Math.cos(start.fadeDiamondRot);
      const vx = worldPoint.x - t.fadeDiamondCX;
      const vy = worldPoint.y - t.fadeDiamondCY;
      t.fadeDiamondRY = Math.max(1e-4, Math.abs(vx * ax + vy * ay));
    }

    if (key === 'mouth_diamond_rot') {
      t.fadeDiamondRot = Math.atan2(worldPoint.y - t.fadeDiamondCY, worldPoint.x - t.fadeDiamondCX);
    }

    saveMouthDiamondToStorage();
    return;
  }

  if (!key.startsWith('mouth_')) {
    const t = window.NeckTuning;

    if (key === 'center') {
      const dx = worldPoint.x - startPoint.x;
      const dy = worldPoint.y - startPoint.y;

      t.centerX = startNeckTuning.centerX + dx;
      t.topY = startNeckTuning.topY + dy;
      t.bottomY = startNeckTuning.bottomY + dy;
      t.neckPivotY = startNeckTuning.neckPivotY + dy;
      t.bodyPivotY = startNeckTuning.bodyPivotY + dy;
    }

    if (key === 'top') {
      t.topY = worldPoint.y;
      if (t.topY < t.bottomY + minBand) t.topY = t.bottomY + minBand;
    }

    if (key === 'bottom') {
      t.bottomY = worldPoint.y;
      if (t.bottomY > t.topY - minBand) t.bottomY = t.topY - minBand;
      t.neckPivotY = t.bottomY;
      t.bodyPivotY = t.bottomY - 0.12;
    }

    if (key === 'left') {
      const w = startNeckTuning.centerX - worldPoint.x;
      t.width = Math.max(1e-6, Math.abs(w));
    }

    if (key === 'right') {
      const w = worldPoint.x - startNeckTuning.centerX;
      t.width = Math.max(1e-6, Math.abs(w));
    }

    if (key === 'curve') {
      t.curve = (t.topY - worldPoint.y);
    }

    if (key === 'neckPivot') t.neckPivotY = worldPoint.y;
    if (key === 'bodyPivot') t.bodyPivotY = worldPoint.y;

    scheduleRecomputeHeadWeights(`drag:${key}`);
    return;
  }

  const m = window.MouthTuning;

  if (key === 'mouth_center') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;

    m.centerX = startMouthTuning.centerX + dx;
    m.centerY = startMouthTuning.centerY + dy;
  }

  if (key === 'mouth_left') {
    const w = startMouthTuning.centerX - worldPoint.x;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'mouth_right') {
    const w = worldPoint.x - startMouthTuning.centerX;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'mouth_top') {
    const h = worldPoint.y - startMouthTuning.centerY;
    m.height = Math.max(1e-6, Math.abs(h));
  }

  if (key === 'mouth_bottom') {
    const h = startMouthTuning.centerY - worldPoint.y;
    m.height = Math.max(1e-6, Math.abs(h));
  }

  if (key === 'mouth_curve') {
    m.curve = (m.centerY - worldPoint.y);
  }

  scheduleRecomputeMouthWeights(`drag:${key}`);
}

function onNeckEditorDown(e) {
  if (!NeckEditor.visible) return;
  const key = pickHandle(e.clientX, e.clientY);
  if (!key) return;

  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  NeckEditor.dragging = {
    key,
    startPoint: p,
    startNeckTuning: { ...window.NeckTuning },
    startMouthTuning: { ...window.MouthTuning },
    startMouthRenderTuning: { ...window.MouthRenderTuning },
    startEyeBlinkTuning: JSON.parse(JSON.stringify(window.EyeBlinkTuning)),
  };

  controls.enabled = false;
  e.preventDefault();
}

function onNeckEditorMove(e) {
  if (!NeckEditor.visible) return;

  if (!NeckEditor.dragging) {
    NeckEditor.hoverKey = pickHandle(e.clientX, e.clientY);
    return;
  }

  const { key, startPoint, startNeckTuning, startMouthTuning, startEyeBlinkTuning, startMouthRenderTuning } = NeckEditor.dragging;
  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  applyDrag(key, p, startPoint, startNeckTuning, startMouthTuning, startEyeBlinkTuning, startMouthRenderTuning);
  e.preventDefault();
}

function onNeckEditorUp() {
  if (!NeckEditor.dragging) return;
  const draggedKey = NeckEditor.dragging.key;
  NeckEditor.dragging = null;
  controls.enabled = true;
  if (draggedKey.startsWith('eye_')) logEyeBlinkTuning(`drag:${draggedKey}`);
  if (draggedKey.startsWith('brow_') || draggedKey.startsWith('eye_marker_')) {
    console.info('[brows-debug-editor] update', window.BrowsDebugTuning);
    console.log('[brows-debug-editor] Pega esto en app.js\nwindow.BrowsDebugTuning = ' + JSON.stringify(window.BrowsDebugTuning, null, 2) + ';');
  }
}

function onNeckEditorTouchStart(e) {
  if (!NeckEditor.visible) return;
  if (!e.touches?.length) return;
  const t = e.touches[0];
  onNeckEditorDown({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onNeckEditorTouchMove(e) {
  if (!NeckEditor.visible) return;
  if (!e.touches?.length) return;
  const t = e.touches[0];
  onNeckEditorMove({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onNeckEditorTouchEnd(e) {
  onNeckEditorUp(e);
  e.preventDefault();
}

function drawHandle(ctx, key, color, filled, clientX, clientY) {
  const r = NeckEditor.handlesRadius;
  const isHover = NeckEditor.hoverKey === key;
  const isDrag = NeckEditor.dragging?.key === key;

  ctx.save();
  ctx.beginPath();
  ctx.arc(clientX, clientY, r, 0, Math.PI * 2);

  ctx.lineWidth = isDrag ? 3 : (isHover ? 2 : 1.5);
  ctx.strokeStyle = color;

  if (filled) {
    ctx.fillStyle = color.includes('67e8f9')
      ? 'rgba(103,232,249,0.12)'
      : (color.includes('253,224,71') ? 'rgba(253,224,71,0.16)' : (color.includes('34,197,94') ? 'rgba(34,197,94,0.16)' : 'rgba(255,0,0,0.15)'));
    ctx.fill();
  }

  ctx.stroke();
  ctx.restore();
}

function drawNeckEditorOverlay() {
  if (!NeckEditor.enabled || !NeckEditor.visible) return;
  if (!NeckEditor.overlay) initNeckEditorOverlay();

  const ctx = NeckEditor.ctx;
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

  // =========================
  // NECK CURVES (rojo)
  // =========================
  {
    const t = window.NeckTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));

    const segments = 64;
    const x0 = t.centerX - wAbs;
    const x1 = t.centerX + wAbs;

    const topPts = [];
    const botPts = [];

    for (let i = 0; i <= segments; i++) {
      const u = i / segments;
      const x = x0 + (x1 - x0) * u;

      const dx = x - t.centerX;
      const nx = dx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const c = t.curve * nxClamped * nxClamped;

      const yTop = t.topY - c;
      const yBot = t.bottomY - c;

      topPts.push(screenProject(x, yTop, 0));
      botPts.push(screenProject(x, yBot, 0));
    }

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    // top
    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    // bottom
    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    // bordes verticales (aprox)
    const leftTop = topPts[0], leftBot = botPts[0];
    const rightTop = topPts[topPts.length - 1], rightBot = botPts[botPts.length - 1];

    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(leftTop.x, leftTop.y); ctx.lineTo(leftBot.x, leftBot.y);
    ctx.moveTo(rightTop.x, rightTop.y); ctx.lineTo(rightBot.x, rightBot.y);
    ctx.stroke();

    ctx.restore();
  }

  // =========================
  // MOUTH REGION (cyan)
  // =========================
  {
    const m = window.MouthTuning;
    const wAbs = Math.max(1e-6, Math.abs(m.width));
    const hAbs = Math.max(1e-6, Math.abs(m.height));

    const segments = 64;
    const x0 = m.centerX - wAbs;
    const x1 = m.centerX + wAbs;

    const midPts = [];
    const topPts = [];
    const botPts = [];

    for (let i = 0; i <= segments; i++) {
      const u = i / segments;
      const x = x0 + (x1 - x0) * u;

      const dx = x - m.centerX;
      const nx = dx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const c = m.curve * nxClamped * nxClamped;

      const yMid = m.centerY - c;
      const yTop = yMid + hAbs;
      const yBot = yMid - hAbs;

      midPts.push(screenProject(x, yMid, 0));
      topPts.push(screenProject(x, yTop, 0));
      botPts.push(screenProject(x, yBot, 0));
    }

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(103,232,249,0.95)';

    // mid (centerline)
    ctx.beginPath();
    ctx.moveTo(midPts[0].x, midPts[0].y);
    for (let i = 1; i < midPts.length; i++) ctx.lineTo(midPts[i].x, midPts[i].y);
    ctx.stroke();

    // top
    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    // bottom
    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    // bordes verticales
    const leftTop = topPts[0], leftBot = botPts[0];
    const rightTop = topPts[topPts.length - 1], rightBot = botPts[botPts.length - 1];

    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(leftTop.x, leftTop.y); ctx.lineTo(leftBot.x, leftBot.y);
    ctx.moveTo(rightTop.x, rightTop.y); ctx.lineTo(rightBot.x, rightBot.y);
    ctx.stroke();

    ctx.restore();
  }

  // =========================
  // MOUTH DIAMOND (magenta)
  // =========================
  if (DEBUG_MOUTH_DIAMOND_ENABLED) {
    const t = window.MouthRenderTuning;
    const cx = t.fadeDiamondCX;
    const cy = t.fadeDiamondCY;
    const rx = Math.max(1e-6, Math.abs(t.fadeDiamondRX));
    const ry = Math.max(1e-6, Math.abs(t.fadeDiamondRY));
    const c = Math.cos(t.fadeDiamondRot);
    const s = Math.sin(t.fadeDiamondRot);
    const vx = { x: c * rx, y: s * rx };
    const vy = { x: -s * ry, y: c * ry };

    const p1 = screenProject(cx + vx.x, cy + vx.y, 0);
    const p2 = screenProject(cx + vy.x, cy + vy.y, 0);
    const p3 = screenProject(cx - vx.x, cy - vx.y, 0);
    const p4 = screenProject(cx - vy.x, cy - vy.y, 0);

    ctx.save();
    ctx.strokeStyle = 'rgba(244,63,94,0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.lineTo(p4.x, p4.y);
    ctx.closePath();
    ctx.stroke();
    ctx.fillStyle = 'rgba(244,63,94,0.12)';
    ctx.fill();

    const cpt = screenProject(cx, cy, 0);
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.font = '12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';
    ctx.fillText(`diamond cx=${cx.toFixed(3)} cy=${cy.toFixed(3)} rx=${rx.toFixed(3)} ry=${ry.toFixed(3)} rot=${t.fadeDiamondRot.toFixed(3)}`, cpt.x + 12, cpt.y + 22);
    ctx.restore();
  }

  // =========================
  // EYES (amarillo / verde)
  // =========================
  {
    const drawEye = (side, colorUpper, colorLower) => {
      const eye = window.EyeBlinkTuning[side];
      const hw = Math.max(1e-4, Math.abs(eye.halfWidth));
      const rot = eye.rotation || 0.0;
      const s = Math.sin(rot);
      const c = Math.cos(rot);
      const seg = 48;

      const upperPts = [];
      const lowerPts = [];

      for (let i = 0; i <= seg; i++) {
        const u = i / seg;
        const x = -hw + 2.0 * hw * u;
        const xN = x / hw;

        const yUpper = eye.upper.offset + eye.upper.curve * xN * xN;
        const yLower = eye.lower.offset + eye.lower.curve * xN * xN;

        const ux = eye.centerX + x * c - yUpper * s;
        const uy = eye.centerY + x * s + yUpper * c;
        const lx = eye.centerX + x * c - yLower * s;
        const ly = eye.centerY + x * s + yLower * c;

        upperPts.push(screenProject(ux, uy, 0));
        lowerPts.push(screenProject(lx, ly, 0));
      }

      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = colorUpper;
      ctx.beginPath();
      ctx.moveTo(upperPts[0].x, upperPts[0].y);
      for (let i = 1; i < upperPts.length; i++) ctx.lineTo(upperPts[i].x, upperPts[i].y);
      ctx.stroke();

      ctx.strokeStyle = colorLower;
      ctx.beginPath();
      ctx.moveTo(lowerPts[0].x, lowerPts[0].y);
      for (let i = 1; i < lowerPts.length; i++) ctx.lineTo(lowerPts[i].x, lowerPts[i].y);
      ctx.stroke();

      const cpt = screenProject(eye.centerX, eye.centerY, 0);
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';
      ctx.fillText(`eye_${side}`, cpt.x + 8, cpt.y - 8);
      ctx.restore();
    };

    drawEye('left', 'rgba(253,224,71,0.95)', 'rgba(250,204,21,0.75)');
    drawEye('right', 'rgba(34,197,94,0.95)', 'rgba(22,163,74,0.75)');
  }

  // =========================
  // HANDLES (neck + mouth + blink)
  // =========================
  const handles = getHandlesModel();
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);

    const isMouth = key.startsWith('mouth_');
    const isEye = key.startsWith('eye_');
    const isBrow = key.startsWith('brow_');
    const isEyeMarker = key.startsWith('eye_marker_');
    const isPivot = (key === 'neckPivot' || key === 'bodyPivot');
    const isCurve = (key === 'curve' || key === 'mouth_curve');

    let color = 'rgba(255,0,0,0.95)';
    if (key.startsWith('mouth_diamond_')) color = 'rgba(244,63,94,0.95)';
    else if (isMouth) color = 'rgba(103,232,249,0.95)';
    else if (isEye && key.startsWith('eye_left')) color = 'rgba(253,224,71,0.95)';
    else if (isEye && key.startsWith('eye_right')) color = 'rgba(34,197,94,0.95)';
    else if (isBrow) color = 'rgba(34,197,94,0.95)';
    else if (isEyeMarker) color = 'rgba(244,63,94,0.95)';
    else if (isPivot) color = 'rgba(255,0,0,0.75)';
    else if (isCurve) color = 'rgba(255,0,0,0.95)';

    drawHandle(ctx, key, color, true, s.x, s.y);

    // labels chiquitas
    ctx.save();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';
    ctx.fillText(key, s.x + 12, s.y - 10);
    ctx.restore();
  }
}

// init overlay si aplica
if (DEBUG_EDIT_ENABLED) {
  initNeckEditorOverlay();
}
