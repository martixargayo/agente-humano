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
const demoFeedbackMode = createDemoFeedbackMode({ urlParams: URL_PARAMS });

// =========================
// Tema perceptual del avatar (dark/light)
// - Geometría, rig, lipsync y animación NO cambian con el tema.
// - Solo cambia la capa perceptual: fondo + respuesta tonal/alpha del shader.
// =========================
const DEFAULT_THEME = 'dark';

const THEME_PRESETS = {
  dark: {
    background: 0x000000,
    particleColor: 0xdddddd,
    // Dark actual: preservar respuesta histórica sin remapeo.
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
  light: {
    background: 0xf2f4f7, // off-white técnico (no blanco puro)
    particleColor: 0x2f3640, // grafito oscuro (no negro puro)
    // Recalibración perceptual:
    // - limpia bajas densidades periféricas (menos grano)
    // - comprime altas densidades (evita manchas tipo tinta)
    densityInMin: 0.22,
    densityInMax: 0.92,
    densityGamma: 1.12,
    densityOutMin: 0.08,
    densityOutMax: 0.72,
    alphaGain: 0.94,
    alphaClip: 0.03,
    shadeMin: 0.72,
    shadeMax: 1.0,
  },
  white: {
    // Fondo claro con contraste alto en rasgos: luces casi invisibles + sombras marcadas.
    background: 0xf7f7f5,
    particleColor: 0xffffff,
    densityInMin: 0.08,
    // Empuja más área al tramo claro para que más puntos queden "blancos/invisibles".
    densityInMax: 0.88,
    densityGamma: 1.1,
    densityOutMin: 0.0,
    densityOutMax: 1.0,
    alphaGain: 0.8,
    // Umbral tipo 1..40 blanco: ink bajo queda recortado y no se pinta.
    alphaClip: 0.32,
    // 30% menos oscuridad en el tono más oscuro del tema white.
    shadeMin: 0.26,
    shadeMax: 1.0,
    lowDensityAlphaFloor: 0.0,
    invertDensityAsInk: true,
    inkFloor: 0.21,
    removeHeadCutCap: true,
  },
  whiteColor: {
    // Igual que white en comportamiento tonal/alpha, pero usando el color real de la textura.
    background: 0xf7f7f5,
    particleColor: 0xffffff,
    densityInMin: 0.08,
    densityInMax: 0.88,
    densityGamma: 1.1,
    densityOutMin: 0.0,
    densityOutMax: 1.0,
    alphaGain: 0.8,
    alphaClip: 0.32,
    shadeMin: 0.26,
    shadeMax: 1.0,
    lowDensityAlphaFloor: 0.0,
    invertDensityAsInk: true,
    inkFloor: 0.21,
    useTextureColor: true,
    useLumaDensity: true,
    saturation: 1.0,
    removeHeadCutCap: true,
  },
};

function resolveTheme() {
  const urlTheme = URL_PARAMS.get('theme');
  if (!urlTheme) return DEFAULT_THEME;

  const normalizedTheme = urlTheme.trim();
  const lowerTheme = normalizedTheme.toLowerCase();

  if (lowerTheme === 'blanco') return 'white';
  if (lowerTheme === 'whitecolor' || lowerTheme === 'white-color') return 'whiteColor';

  if (THEME_PRESETS[normalizedTheme]) return normalizedTheme;
  if (THEME_PRESETS[lowerTheme]) return lowerTheme;

  return DEFAULT_THEME;
}

const activeThemeName = resolveTheme();
const activeTheme = THEME_PRESETS[activeThemeName];
document.documentElement.dataset.avatarTheme = activeThemeName;
console.info('[theme] Avatar perceptual theme:', activeThemeName);

const isWhiteCanvasTheme = activeThemeName === 'white' || activeThemeName === 'whiteColor';
if (isWhiteCanvasTheme) {
  const canvasBg = `#${activeTheme.background.toString(16).padStart(6, '0')}`;
  document.body.style.backgroundColor = canvasBg;
  const stageEl = document.getElementById('stage');
  if (stageEl) stageEl.style.backgroundColor = canvasBg;
  const bgEl = document.getElementById('bg');
  if (bgEl) {
    bgEl.style.backgroundColor = canvasBg;
    bgEl.style.backgroundImage = 'none';
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
})();

window.addEventListener('keydown', (e) => {
  if (e.key === 'n' || e.key === 'N') {
    DebugView.headWeight = !DebugView.headWeight;
    console.info('[debug] Debug cuello/cabeza (aHeadWeight):', DebugView.headWeight ? 'ON' : 'OFF');
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

const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
rimLight.position.set(-2, 3, -2);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.2);
scene.add(ambient);

// Ajuste lumínico mínimo en modo claro: recuperar separación de planos
// sin tocar tipos de luz ni lógica de animación.
if (activeThemeName === 'light') {
  keyLight.intensity = 0.84;
  rimLight.intensity = 0.46;
  ambient.intensity = 0.26;
}

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

attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;

// boca
attribute float aMouthWeight;
attribute float aMouthSide;

// peso cabeza (0=cuerpo, 1=cabeza)
attribute float aHeadWeight;

varying vec2 vUv;
varying float vHeadWeight;

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

varying vec2 vUv;
varying float vHeadWeight;

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

  float alpha = circle * (uLowDensityAlphaFloor + inkClamped * (1.0 - uLowDensityAlphaFloor)) * uAlphaGain;
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

  const mouthWeights = new Float32Array(count);
  const mouthSides = new Float32Array(count);

  const headWeights = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    randoms[i * 3 + 0] = Math.random();
    randoms[i * 3 + 1] = Math.random();
    randoms[i * 3 + 2] = Math.random();

    const x = positions[i * 3 + 0];
    const y = positions[i * 3 + 1];

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
let headCutCapMesh = null;

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
    headWeightAttrRef = particlesGeo.getAttribute('aHeadWeight');
    basePosAttrRef = particlesGeo.getAttribute('aBasePosition');

    mouthWeightAttrRef = particlesGeo.getAttribute('aMouthWeight');
    mouthSideAttrRef = particlesGeo.getAttribute('aMouthSide');

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

    if (activeThemeName === 'white' || activeThemeName === 'whiteColor' || activeThemeName === 'blanco') {
      particleMaterial = createParticleMaterial({
        pointSize: POINT_SIZE,
        color: activeTheme.particleColor,
        blending: THREE.NormalBlending,
        depthWrite: false,
        blancoMode: 1.0,
        blancoLayer: 0.0,
        blancoInkGamma: 1.9,
      });
      particleMaterials = [particleMaterial];

      particlePoints = new THREE.Points(particlesGeo, particleMaterial);
      particlePoints.frustumCulled = false;
      particlePoints.renderOrder = 2;
      particlePointsDetail = null;
    } else {
      particleMaterial = createParticleMaterial();
      particleMaterials = [particleMaterial];
      particlePoints = new THREE.Points(particlesGeo, particleMaterial);
      particlePoints.frustumCulled = false;
      particlePoints.renderOrder = 2;
      particlePointsDetail = null;
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
    scene.add(particlePoints);
    if (particlePointsDetail) scene.add(particlePointsDetail);

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

const MotionConfig = {
  head: { ampYaw: 0.055, ampPitch: 0.050, ampRoll: 0.030, holdMin: 1.0, holdMax: 3.2, smooth: 10.0 },
  body: { ampYaw: 0.012, ampPitch: 0.010, ampRoll: 0.010, holdMin: 1.2, holdMax: 4.0, smooth: 6.0 },
  micro: { yaw: 0.006, pitch: 0.004, roll: 0.004 },
};

const MotionState = {
  seed: Math.random() * 1000.0,
  head: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  body: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  nod: { active: false, t0: 0, dur: 0.32, amp: 0.012 },
};

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
    ch.target.copy(pickTarget(cfg));
    ch.nextSwitch = t + randRange(cfg.holdMin, cfg.holdMax);
  }
  const k = 1.0 - Math.exp(-dt * cfg.smooth);
  ch.current.lerp(ch.target, k);
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

function animate() {
  requestAnimationFrame(animate);

  const elapsed = clock.getElapsedTime();
  const delta = clock.getDelta();

  if (particleMaterials.length) {
    let targetTalk = 0.0;
    if (lipHoldActive) targetTalk = 1.0;
    else targetTalk = getTalkLevelFromAudio();

    AvatarState.talkLevel = targetTalk;

    updateChannel(MotionState.head, MotionConfig.head, elapsed, delta);
    updateChannel(MotionState.body, MotionConfig.body, elapsed, delta);

    const microYaw =
      (Math.sin(elapsed * 2.1 + MotionState.seed) * MotionConfig.micro.yaw) +
      (Math.sin(elapsed * 3.7 + MotionState.seed * 0.3) * MotionConfig.micro.yaw * 0.45);

    const microPitch =
      (Math.sin(elapsed * 1.8 + MotionState.seed * 0.7) * MotionConfig.micro.pitch) +
      (Math.sin(elapsed * 3.2 + MotionState.seed * 0.2) * MotionConfig.micro.pitch * 0.45);

    const microRoll =
      (Math.sin(elapsed * 1.5 + MotionState.seed * 1.3) * MotionConfig.micro.roll) +
      (Math.sin(elapsed * 2.9 + MotionState.seed * 0.4) * MotionConfig.micro.roll * 0.45);

    const nodPitch = updateNod(elapsed, delta);

    const head = MotionState.head.current;
    const body = MotionState.body.current;

    let offY = 0.0;
    if (AvatarState.idleMotionEnabled) {
      offY = 0.01 * Math.sin(elapsed * 0.9) + 0.005 * Math.sin(elapsed * 0.37);
    }

    for (const mat of particleMaterials) {
      mat.uniforms.uTime.value = elapsed;
      mat.uniforms.uTalk.value = AvatarState.talkLevel;
      mat.uniforms.uRestOpen.value = 0.03;
      mat.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;

      mat.uniforms.uHeadRot.value.set(
        head.x + microPitch + nodPitch,
        head.y + microYaw,
        head.z + microRoll
      );

      mat.uniforms.uBodyRot.value.set(
        body.x + microPitch * 0.25,
        body.y + microYaw * 0.25,
        body.z + microRoll * 0.25
      );

      mat.uniforms.uBodyOffset.value.set(0.0, offY, 0.0);

      if (DEBUG_EDIT_ENABLED) {
        const t = window.NeckTuning;
        mat.uniforms.uNeckPivot.value.set(0.0, t.neckPivotY, 0.0);
        mat.uniforms.uBodyPivot.value.set(0.0, t.bodyPivotY, 0.0);
      }
    }
  }

  if (particlePoints) {
    particlePoints.rotation.set(0, 0, 0);
    particlePoints.position.set(0, 0, 0);
  }
  if (particlePointsDetail) {
    particlePointsDetail.rotation.set(0, 0, 0);
    particlePointsDetail.position.set(0, 0, 0);
  }

  controls.update();
  renderer.render(scene, camera);

  if (NeckEditor && NeckEditor.visible) drawNeckEditorOverlay();
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

const chatUiContainers = [
  ui.replyContainer,
  document.querySelector('.bottom-bar'),
  ui.permissionOverlay,
  ui.listeningGlow,
].filter(Boolean);

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
  enterIdle();
  updateReplyText('Te escucho. Cuando quieras, empieza tú.');
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
    <div style="font-weight:700; margin-bottom:6px;">Neck + Mouth Editor</div>
    <div>Arrastra handles. Tecla <b>E</b> ocultar/mostrar.</div>
    <div style="margin-top:6px; opacity:.9">
      <div><span style="color:#ff6b6b">■</span> Neck: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>, <b>neckPivot</b>, <b>bodyPivot</b></div>
      <div style="margin-top:4px;"><span style="color:#67e8f9">■</span> Mouth: <b>mouth_center</b>, <b>mouth_left</b>, <b>mouth_right</b>, <b>mouth_top</b>, <b>mouth_bottom</b>, <b>mouth_curve</b></div>
    </div>
    <div style="margin-top:8px; opacity:.85">Cada cambio imprime JSON en consola (neck y/o mouth).</div>
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

  // curve handle: lo ponemos en el borde derecho del top (x = centerX + width)
  const curveX = t.centerX + wAbs;
  const curveY = t.topY - t.curve; // coincide con fórmula en el borde (nx=1)

  // Mouth handles
  const m = window.MouthTuning;
  const mwAbs = Math.max(1e-6, Math.abs(m.width));
  const mhAbs = Math.max(1e-6, Math.abs(m.height));
  const mCurveX = m.centerX + mwAbs;
  const mCurveY = m.centerY - m.curve; // en el borde (nx=1), centro de la banda

  return {
    // Neck
    center: { x: t.centerX, y: midY },
    top: { x: t.centerX, y: t.topY },
    bottom: { x: t.centerX, y: t.bottomY },
    left: { x: t.centerX - wAbs, y: midY },
    right: { x: t.centerX + wAbs, y: midY },
    curve: { x: curveX, y: curveY },
    neckPivot: { x: t.centerX, y: t.neckPivotY },
    bodyPivot: { x: t.centerX, y: t.bodyPivotY },

    // Mouth
    mouth_center: { x: m.centerX, y: m.centerY },
    mouth_left: { x: m.centerX - mwAbs, y: m.centerY },
    mouth_right: { x: m.centerX + mwAbs, y: m.centerY },
    mouth_top: { x: m.centerX, y: m.centerY + mhAbs },
    mouth_bottom: { x: m.centerX, y: m.centerY - mhAbs },
    mouth_curve: { x: mCurveX, y: mCurveY },
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

function applyDrag(key, worldPoint, startPoint, startNeckTuning, startMouthTuning) {
  const minBand = 1e-4;

  // ======================
  // NECK
  // ======================
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

      // si quieres que pivotes sigan al bottom por defecto:
      // (comenta estas dos líneas si NO quieres auto-follow)
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
      // curve = topY - y_en_el_borde (nx=1)
      const newCurve = (t.topY - worldPoint.y);
      t.curve = newCurve;
    }

    if (key === 'neckPivot') {
      t.neckPivotY = worldPoint.y;
    }

    if (key === 'bodyPivot') {
      t.bodyPivotY = worldPoint.y;
    }

    scheduleRecomputeHeadWeights(`drag:${key}`);
    return;
  }

  // ======================
  // MOUTH
  // ======================
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
    // en el borde (nx=1): y = centerY - curve  => curve = centerY - y
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

  const { key, startPoint, startNeckTuning, startMouthTuning } = NeckEditor.dragging;
  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  applyDrag(key, p, startPoint, startNeckTuning, startMouthTuning);
  e.preventDefault();
}

function onNeckEditorUp() {
  if (!NeckEditor.dragging) return;
  NeckEditor.dragging = null;
  controls.enabled = true;
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
    ctx.fillStyle = color.includes('67e8f9') ? 'rgba(103,232,249,0.12)' : 'rgba(255,0,0,0.15)';
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
  // HANDLES (neck + mouth)
  // =========================
  const handles = getHandlesModel();
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);

    const isMouth = key.startsWith('mouth_');
    const isPivot = (key === 'neckPivot' || key === 'bodyPivot');
    const isCurve = (key === 'curve' || key === 'mouth_curve');

    const color = isMouth
      ? 'rgba(103,232,249,0.95)'
      : (isPivot ? 'rgba(255,0,0,0.75)' : (isCurve ? 'rgba(255,0,0,0.95)' : 'rgba(255,0,0,0.95)'));

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
