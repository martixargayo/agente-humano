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
// ✅ Neck Editor state (DEBE existir antes de animate() y keydown)
//   (ahora actúa como editor general: neck/mouth/eyes)
// ============================================================================
const NeckEditor = {
  enabled: DEBUG_EDIT_ENABLED,
  visible: DEBUG_EDIT_ENABLED,
  mode: 'neck', // 'neck' | 'mouth' | 'eyes'
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
  mode: 'IDLE', // IDLE | LISTENING | THINKING | SPEAKING
  emotion: 'neutral',
  talkLevel: 0,
  speechIntensity: 1.0,
  idleMotionEnabled: true,
};

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
    console.info('[neck-editor] Modo editor ACTIVADO (?debugEdit=1). Tecla E para ocultar/mostrar. Modos: 1=Neck, 2=Mouth, 3=Eyes');
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

  if (DEBUG_EDIT_ENABLED && (e.key === '1' || e.key === '2' || e.key === '3')) {
    NeckEditor.mode = (e.key === '1') ? 'neck' : (e.key === '2') ? 'mouth' : 'eyes';
    console.info('[neck-editor] Modo:', NeckEditor.mode.toUpperCase());
    updateNeckEditorInfo();
  }

  // Ajuste rápido de densidad de parpadeo
  if (DEBUG_EDIT_ENABLED && NeckEditor.mode === 'eyes') {
    if (e.key === '[') {
      window.EyeTuning.pointsPerEye = Math.max(40, (window.EyeTuning.pointsPerEye | 0) - 40);
      scheduleRebuildBlinkCurtain('eyes:points--');
    }
    if (e.key === ']') {
      window.EyeTuning.pointsPerEye = Math.min(2000, (window.EyeTuning.pointsPerEye | 0) + 40);
      scheduleRebuildBlinkCurtain('eyes:points++');
    }
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
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.01, 100);
camera.position.set(0, 0.25, 1.9);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
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

const clock = new THREE.Clock();

// =========================
// Config boca (ajustable a mano)
//   -> ahora se expone como window.MouthTuning (editable)
// =========================
const MOUTH_CENTER_Y = 0.16; // posición vertical del centro de la boca
const MOUTH_CENTER_X = -0.045; // posición horizontal del centro de la boca
const MOUTH_WIDTH = 0.18; // ancho de la región de boca
const MOUTH_HEIGHT = 0.14; // alto máximo (labios + hueco)
const MOUTH_CURVE = 0.0; // curvatura en U (0 = recto)

window.MouthTuning = window.MouthTuning || {
  centerX: MOUTH_CENTER_X,
  centerY: MOUTH_CENTER_Y,
  width: MOUTH_WIDTH,
  height: MOUTH_HEIGHT,
  curve: MOUTH_CURVE,
};

// =========================
// Config cuello / separación cabeza-cuerpo (TUNED)
// =========================
window.NeckTuning = window.NeckTuning || {
  centerX: -0.05540768292619062,
  width: 0.3289615614114691,
  topY: -0.3029435623085454,
  bottomY: -0.5299623850146092,
  curve: -0.18449820086885416,
  neckPivotY: -0.5299623850146092,
  bodyPivotY: -0.6499623850146092
};

// =========================
// Config ojos / parpadeo (cortina de puntos)
//   -> editable con editor modo EYES (tecla 3)
// =========================
window.EyeTuning = {
  leftCenterX: -0.2790878109748029,
  rightCenterX: 0.12250231427620147,
  centerY: 0.592741067776794,
  width: 0.06666211982918908,
  height: 0.028326739143716306,
  lidCurve: 0.012,
  z: 0.017249169318488914,
  hideOffsetY: 0.046115941012340955,
  pointsPerEye: 260,
  alpha: 0.7
};

// =========================
// Refs para recalcular pesos en caliente
// =========================
let particlesGeometryRef = null;
let headWeightAttrRef = null;
let basePosAttrRef = null;

let mouthWeightAttrRef = null;
let mouthSideAttrRef = null;

let blinkPoints = null;

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
// Helpers random
// =========================
function randRange(a, b) {
  return a + (b - a) * Math.random();
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
// Recalcular boca (aMouthWeight/aMouthSide) en caliente
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
    console.warn('[mouth] aMouthWeight todavía no está listo (espera a que cargue el GLB).');
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

    const dx = x - t.centerX;
    const ax = Math.abs(dx);

    let weight = 0.0;
    let side = 0.0;

    if (ax <= wAbs) {
      const normX = dx / wAbs;
      const curveY = t.centerY - t.curve * normX * normX;
      const dy = y - curveY;
      const ay = Math.abs(dy);

      if (ay <= hAbs) {
        const wx = 1.0 - ax / wAbs;
        const wy = 1.0 - ay / hAbs;
        weight = wx * wy;
        weight = Math.max(0.0, Math.min(1.0, weight));

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
  console.info('[mouth] Pesos recalculados', { ms: dt.toFixed(2) });
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
// Parpadeo: estado y timing
// =========================
const BlinkState = {
  value: 0.0,         // 0=open, 1=closed
  phase: 'idle',      // idle | closing | hold | opening | gap
  t0: 0,
  next: 0,
  doDouble: false,
  doubleDone: false,
};

function scheduleNextBlink(now) {
  BlinkState.next = now + randRange(2.6, 6.2);
  BlinkState.doDouble = Math.random() < 0.16;
  BlinkState.doubleDone = false;
}

scheduleNextBlink(0);

function startBlink(now) {
  BlinkState.phase = 'closing';
  BlinkState.t0 = now;
}

function updateBlink(now) {
  // si está idle, chequea si toca parpadear
  if (BlinkState.phase === 'idle') {
    if (now >= BlinkState.next) startBlink(now);
    BlinkState.value = 0.0;
    return BlinkState.value;
  }

  // timings súper rápidos (casi imperceptible)
  const CLOSE_S = 0.045;
  const HOLD_S = 0.018;
  const OPEN_S = 0.075;
  const GAP_S = 0.10; // si hay doble blink

  if (BlinkState.phase === 'closing') {
    const u = (now - BlinkState.t0) / CLOSE_S;
    BlinkState.value = Math.max(0, Math.min(1, u));
    if (u >= 1) {
      BlinkState.phase = 'hold';
      BlinkState.t0 = now;
      BlinkState.value = 1.0;
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'hold') {
    BlinkState.value = 1.0;
    if ((now - BlinkState.t0) >= HOLD_S) {
      BlinkState.phase = 'opening';
      BlinkState.t0 = now;
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'opening') {
    const u = (now - BlinkState.t0) / OPEN_S;
    BlinkState.value = 1.0 - Math.max(0, Math.min(1, u));
    if (u >= 1) {
      BlinkState.value = 0.0;
      if (BlinkState.doDouble && !BlinkState.doubleDone) {
        BlinkState.doubleDone = true;
        BlinkState.phase = 'gap';
        BlinkState.t0 = now;
      } else {
        BlinkState.phase = 'idle';
        scheduleNextBlink(now);
      }
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'gap') {
    BlinkState.value = 0.0;
    if ((now - BlinkState.t0) >= GAP_S) {
      BlinkState.phase = 'closing';
      BlinkState.t0 = now;
    }
    return BlinkState.value;
  }

  BlinkState.phase = 'idle';
  BlinkState.value = 0.0;
  scheduleNextBlink(now);
  return BlinkState.value;
}

// =========================
// Rebuild “cortinas” de ojos
// =========================
let _blinkRebuildPending = false;

function logEyeTuning(reason = 'update') {
  const t = window.EyeTuning;
  console.info(`[eyes] ${reason}`, {
    leftCenterX: t.leftCenterX,
    rightCenterX: t.rightCenterX,
    centerY: t.centerY,
    width: t.width,
    height: t.height,
    lidCurve: t.lidCurve,
    z: t.z,
    hideOffsetY: t.hideOffsetY,
    pointsPerEye: t.pointsPerEye,
    alpha: t.alpha,
  });
  console.log('[eyes] Pega esto en app.js:\nwindow.EyeTuning = ' + JSON.stringify(t, null, 2) + ';');
}

function createBlinkCurtainGeometry() {
  const t = window.EyeTuning;

  const pointsPerEye = Math.max(20, (t.pointsPerEye | 0));
  const total = pointsPerEye * 2;

  const positions = new Float32Array(total * 3);
  const basePositions = new Float32Array(total * 3);
  const uvs = new Float32Array(total * 2);
  const randoms = new Float32Array(total * 3);
  const clusterIds = new Float32Array(total);

  const mouthWeights = new Float32Array(total);
  const mouthSides = new Float32Array(total);
  const headWeights = new Float32Array(total);

  const blinkMask = new Float32Array(total);
  const blinkHideOffset = new Float32Array(total * 3);

  const wAbs = Math.max(1e-6, Math.abs(t.width));
  const hAbs = Math.max(1e-6, Math.abs(t.height));

  const centers = [
    { x: t.leftCenterX, y: t.centerY },
    { x: t.rightCenterX, y: t.centerY },
  ];

  let idx = 0;
  for (let eye = 0; eye < 2; eye++) {
    const cx = centers[eye].x;
    const cy = centers[eye].y;

    for (let p = 0; p < pointsPerEye; p++) {
      const rx = (Math.random() * 2 - 1) * wAbs;
      const ry = (Math.random() * 2 - 1) * hAbs;

      const nx = rx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const curve = t.lidCurve * nxClamped * nxClamped;

      // Cortina: rellena el área del ojo con un arqueo leve (más natural)
      const x = cx + rx;
      const y = cy + ry - curve;
      const z = t.z;

      positions[idx * 3 + 0] = x;
      positions[idx * 3 + 1] = y;
      positions[idx * 3 + 2] = z;

      basePositions[idx * 3 + 0] = x;
      basePositions[idx * 3 + 1] = y;
      basePositions[idx * 3 + 2] = z;

      uvs[idx * 2 + 0] = 0.0;
      uvs[idx * 2 + 1] = 0.0;

      randoms[idx * 3 + 0] = Math.random();
      randoms[idx * 3 + 1] = Math.random();
      randoms[idx * 3 + 2] = Math.random();

      clusterIds[idx] = 0.0;

      mouthWeights[idx] = 0.0;
      mouthSides[idx] = 0.0;
      headWeights[idx] = 1.0;

      blinkMask[idx] = 1.0;

      // cuando está abierto, sube y se “esconde”
      blinkHideOffset[idx * 3 + 0] = 0.0;
      blinkHideOffset[idx * 3 + 1] = Math.max(0.001, t.hideOffsetY);
      blinkHideOffset[idx * 3 + 2] = 0.0;

      idx++;
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('aUv', new THREE.BufferAttribute(uvs, 2));
  geo.setAttribute('aBasePosition', new THREE.BufferAttribute(basePositions, 3));
  geo.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 3));
  geo.setAttribute('aClusterId', new THREE.BufferAttribute(clusterIds, 1));
  geo.setAttribute('aMouthWeight', new THREE.BufferAttribute(mouthWeights, 1));
  geo.setAttribute('aMouthSide', new THREE.BufferAttribute(mouthSides, 1));
  geo.setAttribute('aHeadWeight', new THREE.BufferAttribute(headWeights, 1));
  geo.setAttribute('aBlinkMask', new THREE.BufferAttribute(blinkMask, 1));
  geo.setAttribute('aBlinkHideOffset', new THREE.BufferAttribute(blinkHideOffset, 3));
  return geo;
}

function rebuildBlinkCurtain(reason = 'change') {
  if (!particleMaterial) return;

  if (!blinkPoints) {
    const geo = createBlinkCurtainGeometry();
    blinkPoints = new THREE.Points(geo, particleMaterial);
    blinkPoints.frustumCulled = false;
    scene.add(blinkPoints);
  } else {
    const old = blinkPoints.geometry;
    blinkPoints.geometry = createBlinkCurtainGeometry();
    try { old.dispose(); } catch (_) {}
  }

  logEyeTuning(reason);
}

function scheduleRebuildBlinkCurtain(reason = 'change') {
  if (_blinkRebuildPending) return;
  _blinkRebuildPending = true;
  requestAnimationFrame(() => {
    _blinkRebuildPending = false;
    rebuildBlinkCurtain(reason);
  });
}

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

// parpadeo
uniform float uBlink;

attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;

// boca
attribute float aMouthWeight;
attribute float aMouthSide;

// peso cabeza (0=cuerpo, 1=cabeza)
attribute float aHeadWeight;

// blink overlay
attribute float aBlinkMask;
attribute vec3 aBlinkHideOffset;

varying vec2 vUv;
varying float vHeadWeight;
varying float vBlinkMask;

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
  vBlinkMask = aBlinkMask;

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

  // blink overlay: cuando uBlink=0 (abierto) -> sube y se esconde
  displaced += aBlinkHideOffset * (1.0 - uBlink) * aBlinkMask;

  vec3 bodyPos = rotateAroundPivot(displaced, uBodyPivot, uBodyRot) + uBodyOffset;
  vec3 headPos = rotateAroundPivot(bodyPos, uNeckPivot, uHeadRot);
  vec3 finalPos = mix(bodyPos, headPos, aHeadWeight);

  vec4 mvPosition = modelViewMatrix * vec4(finalPos, 1.0);

  gl_PointSize = uPointSize;
  gl_Position = projectionMatrix * mvPosition;
}
`;

// Fragment: disco suave + modulación por textura (normal) + debug por aHeadWeight + blink overlay
const fragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform sampler2D uColorMap;
uniform float uUseMap;
uniform float uDebugHeadWeight;

// blink
uniform float uBlink;
uniform float uBlinkAlpha;

varying vec2 vUv;
varying float vHeadWeight;
varying float vBlinkMask;

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

  // Blink overlay: puntos oscuros que aparecen muy rápido
  if (vBlinkMask > 0.5) {
    float a = circle * uBlinkAlpha * smoothstep(0.02, 0.12, uBlink);
    if (a < 0.02) discard;
    vec3 c = vec3(0.03); // casi negro
    gl_FragColor = vec4(c, a);
    return;
  }

  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  float densityRaw = (texColor.r + texColor.g + texColor.b) / 3.0;
  float density = mix(1.0, densityRaw, uUseMap);

  float alpha = circle * density;
  if (alpha < 0.02) discard;

  vec3 baseColor = uColor;
  vec3 finalColor = mix(baseColor * 0.6, baseColor, density);
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

  // blink attrs (en cara normal -> 0)
  const blinkMask = new Float32Array(count);
  const blinkHideOffset = new Float32Array(count * 3);

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
    const m = window.MouthTuning;
    const mwAbs = Math.max(1e-6, Math.abs(m.width));
    const mhAbs = Math.max(1e-6, Math.abs(m.height));

    let dx = x - m.centerX;
    let ax = Math.abs(dx);

    let weight = 0.0;
    let side = 0.0;

    if (ax <= mwAbs) {
      let normX = dx / mwAbs;
      let curveY = m.centerY - m.curve * normX * normX;
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

    // blink defaults (cara)
    blinkMask[i] = 0.0;
    blinkHideOffset[i * 3 + 0] = 0.0;
    blinkHideOffset[i * 3 + 1] = 0.0;
    blinkHideOffset[i * 3 + 2] = 0.0;
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
  particlesGeo.setAttribute('aBlinkMask', new THREE.BufferAttribute(blinkMask, 1));
  particlesGeo.setAttribute('aBlinkHideOffset', new THREE.BufferAttribute(blinkHideOffset, 3));

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
    headWeightAttrRef = particlesGeo.getAttribute('aHeadWeight');
    basePosAttrRef = particlesGeo.getAttribute('aBasePosition');

    mouthWeightAttrRef = particlesGeo.getAttribute('aMouthWeight');
    mouthSideAttrRef = particlesGeo.getAttribute('aMouthSide');

    const t = window.NeckTuning;

    particleMaterial = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: true,
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

        // blink
        uBlink: { value: 0.0 },
        uBlinkAlpha: { value: window.EyeTuning.alpha ?? 0.7 },

        // DEBUG
        uDebugHeadWeight: { value: DebugView.headWeight ? 1.0 : 0.0 },
      },
    });

    particlePoints = new THREE.Points(particlesGeo, particleMaterial);
    particlePoints.frustumCulled = false;
    scene.add(particlePoints);

    // Blink overlay points
    rebuildBlinkCurtain('after_load');

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

  const startTime = ctx.currentTime + 0.05;
  audioSource.start(startTime);
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
const MotionConfig = {
  head: { ampYaw: 0.055, ampPitch: 0.050, ampRoll: 0.030, holdMin: 1.0, holdMax: 3.2, smooth: 10.0 },
  body: { ampYaw: 0.012, ampPitch: 0.010, ampRoll: 0.010, holdMin: 1.2, holdMax: 4.0, smooth: 6.0 },
  micro: { yaw: 0.006, pitch: 0.004, roll: 0.004 },
};

const MotionState = {
  seed: Math.random() * 1000.0,
  head: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  body: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  nod: { active: false, t0: 0, dur: 0.32, amp: 0.012, count: 1 },
};

// === NUEVO: Focus al empezar a hablar (recoloca + hold) y speaking “más suave”
const SpeakFocus = {
  wasSpeaking: false,
  holdUntil: 0,
  speakingBlend: 0,     // 0..1 (smooth)
  leanZ: 0,
  centerBias: 0,        // 0..1 (smooth) ✅ nuevo: para mirar al centro de forma orgánica
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
  // ✅ Solo inicia nods aleatorios cuando está escuchando, pero si ya empezó NO se corta aunque cambie el modo
  if (!MotionState.nod.active && AvatarState.mode === 'LISTENING') {
    const p = 0.12; // probabilidad por segundo aprox. (sutil)
    if (Math.random() < p * dt) {
      MotionState.nod.active = true;
      MotionState.nod.t0 = t;
      MotionState.nod.count = (Math.random() < 0.42) ? 2 : 1; // 1 o 2 “aja”
      MotionState.nod.dur = (MotionState.nod.count === 1)
        ? randRange(0.32, 0.48)
        : randRange(0.62, 0.92);
      MotionState.nod.amp = randRange(0.010, 0.014);
    }
  }

  if (!MotionState.nod.active) return 0.0;

  const u = (t - MotionState.nod.t0) / MotionState.nod.dur;
  if (u >= 1.0) {
    MotionState.nod.active = false;
    return 0.0;
  }

  // 1 o 2 nods: pulsos de media-seno, con el segundo más suave y con fade-out final
  const n = Math.max(1, MotionState.nod.count | 0);
  const segU = u * n;
  const idx = Math.min(n - 1, Math.floor(segU));
  const localU = segU - idx;

  const ampSeg = MotionState.nod.amp * (idx === 0 ? 1.0 : 0.65); // segundo nod más pequeño
  const pulse = -ampSeg * Math.sin(localU * Math.PI);

  // envelope suave (entra y sale imperceptible)
  const envIn = smoothstepJS(0.0, 0.14, u);
  const envOut = 1.0 - smoothstepJS(0.72, 1.0, u);

  return pulse * envIn * envOut;
}

function onSpeakStart(now) {
  // ✅ Recolocar mirando al centro, pero ORGÁNICO: no forzamos target=0 (solo marcamos el hold)
  const hold = randRange(2.0, 3.0);
  SpeakFocus.holdUntil = now + hold;

  console.info('[speak-focus] start', { holdSec: hold.toFixed(2) });
}

function onSpeakEnd() {
  console.info('[speak-focus] end');
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

  const speakingNow = (AvatarState.mode === 'SPEAKING') || lipHoldActive;

  // detectar transición speaking start/end
  if (speakingNow && !SpeakFocus.wasSpeaking) onSpeakStart(elapsed);
  if (!speakingNow && SpeakFocus.wasSpeaking) onSpeakEnd(elapsed);
  SpeakFocus.wasSpeaking = speakingNow;

  // speaking blend suave (para “concentrado”)
  const targetBlend = speakingNow ? 1.0 : 0.0;
  SpeakFocus.speakingBlend += (targetBlend - SpeakFocus.speakingBlend) * (1.0 - Math.exp(-delta * 6.5));

  // lean in/out muy sutil
  const targetLean = speakingNow ? 0.028 : 0.0;
  SpeakFocus.leanZ += (targetLean - SpeakFocus.leanZ) * (1.0 - Math.exp(-delta * 7.0));

  // blink value
  const blink = updateBlink(elapsed);

  if (particleMaterial) {
    particleMaterial.uniforms.uTime.value = elapsed;

    let targetTalk = 0.0;
    if (lipHoldActive) targetTalk = 1.0;
    else targetTalk = getTalkLevelFromAudio();

    AvatarState.talkLevel = targetTalk;
    particleMaterial.uniforms.uTalk.value = AvatarState.talkLevel;

    particleMaterial.uniforms.uRestOpen.value = 0.03;

    particleMaterial.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;

    // ✅ Patch 1: preview de blink en modo editor + eyes
    let blinkVal = blink;
    if (DEBUG_EDIT_ENABLED && NeckEditor?.visible && NeckEditor?.mode === 'eyes') {
      blinkVal = Math.max(blinkVal, NeckEditor.dragging ? 1.0 : 0.65);
    }

    // blink uniforms
    particleMaterial.uniforms.uBlink.value = blinkVal;
    particleMaterial.uniforms.uBlinkAlpha.value = window.EyeTuning.alpha ?? 0.7;

    // speaking => amplitud más pequeña + smoothing más alto (más calmado)
    const sB = SpeakFocus.speakingBlend;
    const headCfg = {
      ...MotionConfig.head,
      ampYaw: MotionConfig.head.ampYaw * (1.0 - 0.45 * sB),
      ampPitch: MotionConfig.head.ampPitch * (1.0 - 0.45 * sB),
      ampRoll: MotionConfig.head.ampRoll * (1.0 - 0.55 * sB),
      smooth: MotionConfig.head.smooth * (1.0 + 0.35 * sB),
      holdMin: MotionConfig.head.holdMin * (1.0 + 0.15 * sB),
      holdMax: MotionConfig.head.holdMax * (1.0 + 0.25 * sB),
    };

    const bodyCfg = {
      ...MotionConfig.body,
      ampYaw: MotionConfig.body.ampYaw * (1.0 - 0.35 * sB),
      ampPitch: MotionConfig.body.ampPitch * (1.0 - 0.35 * sB),
      ampRoll: MotionConfig.body.ampRoll * (1.0 - 0.40 * sB),
      smooth: MotionConfig.body.smooth * (1.0 + 0.25 * sB),
    };

    updateChannel(MotionState.head, headCfg, elapsed, delta);
    updateChannel(MotionState.body, bodyCfg, elapsed, delta);

    // micro más suave cuando habla (se nota concentrado)
    const microMul = 1.0 - 0.55 * sB;

    const microYaw =
      ((Math.sin(elapsed * 2.1 + MotionState.seed) * MotionConfig.micro.yaw) +
      (Math.sin(elapsed * 3.7 + MotionState.seed * 0.3) * MotionConfig.micro.yaw * 0.45)) * microMul;

    const microPitch =
      ((Math.sin(elapsed * 1.8 + MotionState.seed * 0.7) * MotionConfig.micro.pitch) +
      (Math.sin(elapsed * 3.2 + MotionState.seed * 0.2) * MotionConfig.micro.pitch * 0.45)) * microMul;

    const microRoll =
      ((Math.sin(elapsed * 1.5 + MotionState.seed * 1.3) * MotionConfig.micro.roll) +
      (Math.sin(elapsed * 2.9 + MotionState.seed * 0.4) * MotionConfig.micro.roll * 0.45)) * microMul;

    const nodPitch = updateNod(elapsed, delta);

    // ✅ Ajuste 2: “mirar al centro” orgánico y suave (sin snap)
    const holdActive = speakingNow && (elapsed < SpeakFocus.holdUntil);
    const targetCenterBias = holdActive ? 0.92 : (0.22 * sB); // durante hold fuerte, luego leve mientras habla

    const centerSpeed = (targetCenterBias > SpeakFocus.centerBias) ? 4.8 : 2.2; // sube rápido natural, baja más lento
    SpeakFocus.centerBias += (targetCenterBias - SpeakFocus.centerBias) * (1.0 - Math.exp(-delta * centerSpeed));

    const centerBias = SpeakFocus.centerBias;

    const head = MotionState.head.current;
    let hx = head.x + microPitch + nodPitch;
    let hy = head.y + microYaw;
    let hz = head.z + microRoll;

    // bias a mirar al centro (0,0,0) de forma suave
    hx *= (1.0 - centerBias);
    hy *= (1.0 - centerBias);
    hz *= (1.0 - centerBias);

    particleMaterial.uniforms.uHeadRot.value.set(hx, hy, hz);

    const body = MotionState.body.current;
    particleMaterial.uniforms.uBodyRot.value.set(
      body.x + microPitch * 0.25,
      body.y + microYaw * 0.25,
      body.z + microRoll * 0.25
    );

    let offY = 0.0;
    if (AvatarState.idleMotionEnabled) {
      offY = 0.01 * Math.sin(elapsed * 0.9) + 0.005 * Math.sin(elapsed * 0.37);
    }

    // ✅ Lean en Z al hablar (muy sutil)
    particleMaterial.uniforms.uBodyOffset.value.set(0.0, offY, SpeakFocus.leanZ);

    // ✅ pivotes live SOLO en modo editor (producción más “fijo”)
    if (DEBUG_EDIT_ENABLED) {
      const t = window.NeckTuning;
      particleMaterial.uniforms.uNeckPivot.value.set(0.0, t.neckPivotY, 0.0);
      particleMaterial.uniforms.uBodyPivot.value.set(0.0, t.bodyPivotY, 0.0);
    }
  }

  if (particlePoints) {
    particlePoints.rotation.set(0, 0, 0);
    particlePoints.position.set(0, 0, 0);
  }

  controls.update();
  renderer.render(scene, camera);

  if (NeckEditor && NeckEditor.visible) drawNeckEditorOverlay();
}

animate();

// =========================
// 8. UI básica (texto → agente → TTS)
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

if (sendToAgentBtn) {
  sendToAgentBtn.addEventListener('click', async () => {
    const text = (userTextEl?.value || '').trim();
    if (!text) return;
    const modeRadio = document.querySelector('input[name="agentMode"]:checked');
    const mode = modeRadio ? modeRadio.value : 'negociar';
    const withAudio = !textOnlyCheckbox?.checked;
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

// =========================
// 9. Mic simple (visual)
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

// =========================
// 10. Botón "Hablar (test)" – solo frontend, sin backend
// =========================
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

// =========================
// Editor overlay helpers
// =========================
function setNeckEditorVisible(v) {
  if (!NeckEditor.enabled) return;
  if (!NeckEditor.overlay) initNeckEditorOverlay();
  NeckEditor.visible = !!v;
  NeckEditor.overlay.style.display = NeckEditor.visible ? 'block' : 'none';
  if (NeckEditor.infoEl) NeckEditor.infoEl.style.display = NeckEditor.visible ? 'block' : 'none';
  NeckEditor.overlay.style.pointerEvents = NeckEditor.visible ? 'auto' : 'none';
}

function updateNeckEditorInfo() {
  if (!NeckEditor.infoEl) return;

  const mode = NeckEditor.mode;
  let handlesLine = '';
  if (mode === 'neck') {
    handlesLine = 'Handles: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>, <b>neckPivot</b>, <b>bodyPivot</b>';
  } else if (mode === 'mouth') {
    handlesLine = 'Handles: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>';
  } else {
    handlesLine = 'Handles: <b>leftCenter</b>, <b>rightCenter</b>, <b>width</b>, <b>height</b>, <b>curve</b>, <b>hide</b>, <b>z</b> &nbsp;(<b>[</b>/<b>]</b> densidad)';
  }

  // ✅ Patch 2: botones clicables
  NeckEditor.infoEl.innerHTML = `
    <div style="font-weight:700; margin-bottom:6px;">Editor (${mode.toUpperCase()})</div>

    <div style="margin-bottom:8px;">
      <button data-mode="neck"  style="margin-right:6px; padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Neck</button>
      <button data-mode="mouth" style="margin-right:6px; padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Mouth</button>
      <button data-mode="eyes"  style="padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Eyes</button>
    </div>

    <div>Tecla <b>E</b> ocultar/mostrar. (También: <b>1</b>/<b>2</b>/<b>3</b>)</div>
    <div style="margin-top:6px; opacity:.92">${handlesLine}</div>
    <div style="margin-top:8px; opacity:.85">Cada cambio imprime JSON en consola.</div>
  `;
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
  NeckEditor.infoEl = info;

  // ✅ Patch 2: listener botones modo
  info.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-mode]');
    if (!btn) return;
    NeckEditor.mode = btn.dataset.mode;
    console.info('[neck-editor] Modo:', NeckEditor.mode.toUpperCase());
    updateNeckEditorInfo();
  });

  updateNeckEditorInfo();
  document.body.appendChild(info);

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

// -------- Handles Models (neck/mouth/eyes) --------
function getNeckHandlesModel() {
  const t = window.NeckTuning;
  const midY = (t.topY + t.bottomY) * 0.5;
  const wAbs = Math.max(1e-6, Math.abs(t.width));

  const curveX = t.centerX + wAbs;
  const curveY = t.topY - t.curve;

  return {
    center: { x: t.centerX, y: midY },
    top: { x: t.centerX, y: t.topY },
    bottom: { x: t.centerX, y: t.bottomY },
    left: { x: t.centerX - wAbs, y: midY },
    right: { x: t.centerX + wAbs, y: midY },
    curve: { x: curveX, y: curveY },
    neckPivot: { x: t.centerX, y: t.neckPivotY },
    bodyPivot: { x: t.centerX, y: t.bodyPivotY },
  };
}

function getMouthHandlesModel() {
  const m = window.MouthTuning;
  const wAbs = Math.max(1e-6, Math.abs(m.width));
  const hAbs = Math.max(1e-6, Math.abs(m.height));

  // curve handle en borde derecho (nx=1): curveY = centerY - curve
  const curveX = m.centerX + wAbs;
  const curveY = m.centerY - m.curve;

  return {
    center: { x: m.centerX, y: m.centerY },
    top: { x: m.centerX, y: m.centerY + hAbs },
    bottom: { x: m.centerX, y: m.centerY - hAbs },
    left: { x: m.centerX - wAbs, y: m.centerY },
    right: { x: m.centerX + wAbs, y: m.centerY },
    curve: { x: curveX, y: curveY },
  };
}

function getEyeHandlesModel() {
  const t = window.EyeTuning;
  const wAbs = Math.max(1e-6, Math.abs(t.width));
  const hAbs = Math.max(1e-6, Math.abs(t.height));

  // Un handle de “width/height/curve/hide/z” global, y centers por ojo
  return {
    leftCenter: { x: t.leftCenterX, y: t.centerY },
    rightCenter: { x: t.rightCenterX, y: t.centerY },

    width: { x: t.rightCenterX + wAbs, y: t.centerY },
    height: { x: t.rightCenterX, y: t.centerY + hAbs },

    curve: { x: t.rightCenterX + wAbs, y: t.centerY - t.lidCurve },
    hide: { x: t.rightCenterX, y: t.centerY + (t.hideOffsetY || 0.07) },

    z: { x: t.rightCenterX + wAbs * 0.6, y: t.centerY - hAbs * 1.6 },
  };
}

function getHandlesModel() {
  if (NeckEditor.mode === 'mouth') return getMouthHandlesModel();
  if (NeckEditor.mode === 'eyes') return getEyeHandlesModel();
  return getNeckHandlesModel();
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

// -------- Apply drags per mode --------
function applyNeckDrag(key, worldPoint, startPoint, startTuning) {
  const t = window.NeckTuning;
  const minBand = 1e-4;

  if (key === 'center') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;

    t.centerX = startTuning.centerX + dx;
    t.topY = startTuning.topY + dy;
    t.bottomY = startTuning.bottomY + dy;
    t.neckPivotY = startTuning.neckPivotY + dy;
    t.bodyPivotY = startTuning.bodyPivotY + dy;
  }

  if (key === 'top') {
    t.topY = worldPoint.y;
    if (t.topY < t.bottomY + minBand) t.topY = t.bottomY + minBand;
  }

  if (key === 'bottom') {
    t.bottomY = worldPoint.y;
    if (t.bottomY > t.topY - minBand) t.bottomY = t.topY - minBand;

    // auto-follow pivots por defecto
    t.neckPivotY = t.bottomY;
    t.bodyPivotY = t.bottomY - 0.12;
  }

  if (key === 'left') {
    const w = startTuning.centerX - worldPoint.x;
    t.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'right') {
    const w = worldPoint.x - startTuning.centerX;
    t.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'curve') {
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
}

function applyMouthDrag(key, worldPoint, startPoint, startTuning) {
  const m = window.MouthTuning;
  const minBand = 1e-4;

  if (key === 'center') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    m.centerX = startTuning.centerX + dx;
    m.centerY = startTuning.centerY + dy;
  }

  if (key === 'left') {
    const w = startTuning.centerX - worldPoint.x;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'right') {
    const w = worldPoint.x - startTuning.centerX;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'top') {
    m.height = Math.max(1e-6, Math.abs(worldPoint.y - m.centerY));
  }

  if (key === 'bottom') {
    m.height = Math.max(1e-6, Math.abs(m.centerY - worldPoint.y));
  }

  if (key === 'curve') {
    // curve = centerY - y_en_borde (nx=1)
    m.curve = (m.centerY - worldPoint.y);
  }

  scheduleRecomputeMouthWeights(`drag:${key}`);
}

function applyEyeDrag(key, worldPoint, startPoint, startTuning) {
  const t = window.EyeTuning;
  const minBand = 1e-4;

  if (key === 'leftCenter') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    t.leftCenterX = startTuning.leftCenterX + dx;
    t.centerY = startTuning.centerY + dy;
  }

  if (key === 'rightCenter') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    t.rightCenterX = startTuning.rightCenterX + dx;
    t.centerY = startTuning.centerY + dy;
  }

  if (key === 'width') {
    t.width = Math.max(1e-6, Math.abs(worldPoint.x - t.rightCenterX));
  }

  if (key === 'height') {
    t.height = Math.max(1e-6, Math.abs(worldPoint.y - t.centerY));
  }

  if (key === 'curve') {
    // lidCurve = centerY - y_at_edge (nx=1)
    t.lidCurve = (t.centerY - worldPoint.y);
  }

  if (key === 'hide') {
    t.hideOffsetY = Math.max(0.001, Math.abs(worldPoint.y - t.centerY));
  }

  if (key === 'z') {
    // z handle: usa Y para mapear z (simple y práctico)
    // cuanto más arriba el handle, más cerca (z mayor)
    const dz = (startPoint.y - worldPoint.y) * 0.05;
    t.z = Math.max(0.0, startTuning.z + dz);
  }

  scheduleRebuildBlinkCurtain(`drag:${key}`);
}

function applyDrag(key, worldPoint, startPoint, startTuning) {
  if (NeckEditor.mode === 'mouth') return applyMouthDrag(key, worldPoint, startPoint, startTuning);
  if (NeckEditor.mode === 'eyes') return applyEyeDrag(key, worldPoint, startPoint, startTuning);
  return applyNeckDrag(key, worldPoint, startPoint, startTuning);
}

function onNeckEditorDown(e) {
  if (!NeckEditor.visible) return;
  const key = pickHandle(e.clientX, e.clientY);
  if (!key) return;

  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  let startTuning = null;
  if (NeckEditor.mode === 'mouth') startTuning = { ...window.MouthTuning };
  else if (NeckEditor.mode === 'eyes') startTuning = { ...window.EyeTuning };
  else startTuning = { ...window.NeckTuning };

  NeckEditor.dragging = {
    key,
    startPoint: p,
    startTuning,
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

  const { key, startPoint, startTuning } = NeckEditor.dragging;
  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  applyDrag(key, p, startPoint, startTuning);
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
    ctx.fillStyle = 'rgba(255,0,0,0.15)';
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

  // ========= Draw per mode =========
  if (NeckEditor.mode === 'neck') {
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

    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    const leftTop = topPts[0], leftBot = botPts[0];
    const rightTop = topPts[topPts.length - 1], rightBot = botPts[botPts.length - 1];

    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(leftTop.x, leftTop.y); ctx.lineTo(leftBot.x, leftBot.y);
    ctx.moveTo(rightTop.x, rightTop.y); ctx.lineTo(rightBot.x, rightBot.y);
    ctx.stroke();

    ctx.restore();
  }

  if (NeckEditor.mode === 'mouth') {
    const m = window.MouthTuning;
    const wAbs = Math.max(1e-6, Math.abs(m.width));
    const hAbs = Math.max(1e-6, Math.abs(m.height));

    const segments = 64;
    const x0 = m.centerX - wAbs;
    const x1 = m.centerX + wAbs;

    const topPts = [];
    const midPts = [];
    const botPts = [];

    for (let i = 0; i <= segments; i++) {
      const u = i / segments;
      const x = x0 + (x1 - x0) * u;

      const dx = x - m.centerX;
      const nx = dx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const c = m.curve * nxClamped * nxClamped;

      const curveY = m.centerY - c;
      topPts.push(screenProject(x, curveY + hAbs, 0));
      midPts.push(screenProject(x, curveY, 0));
      botPts.push(screenProject(x, curveY - hAbs, 0));
    }

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    // mid
    ctx.beginPath();
    ctx.moveTo(midPts[0].x, midPts[0].y);
    for (let i = 1; i < midPts.length; i++) ctx.lineTo(midPts[i].x, midPts[i].y);
    ctx.stroke();

    // top
    ctx.globalAlpha = 0.65;
    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    // bottom
    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    ctx.restore();
  }

  if (NeckEditor.mode === 'eyes') {
    const t = window.EyeTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));
    const hAbs = Math.max(1e-6, Math.abs(t.height));

    const eyes = [
      { cx: t.leftCenterX, cy: t.centerY },
      { cx: t.rightCenterX, cy: t.centerY },
    ];

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    for (const e of eyes) {
      const x0 = e.cx - wAbs, x1 = e.cx + wAbs;
      const y0 = e.cy - hAbs, y1 = e.cy + hAbs;

      const p0 = screenProject(x0, y0, 0);
      const p1 = screenProject(x1, y0, 0);
      const p2 = screenProject(x1, y1, 0);
      const p3 = screenProject(x0, y1, 0);

      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p3.x, p3.y);
      ctx.closePath();
      ctx.stroke();
    }

    // dibuja un arco de lidCurve (visual)
    const segments = 48;
    for (const e of eyes) {
      const pts = [];
      for (let i = 0; i <= segments; i++) {
        const u = i / segments;
        const x = (e.cx - wAbs) + (2.0 * wAbs) * u;
        const dx = x - e.cx;
        const nx = dx / wAbs;
        const nxClamped = Math.max(-1, Math.min(1, nx));
        const c = t.lidCurve * nxClamped * nxClamped;
        const y = e.cy + hAbs - c;
        pts.push(screenProject(x, y, 0));
      }
      ctx.globalAlpha = 0.70;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      ctx.stroke();
      ctx.globalAlpha = 1.0;
    }

    // ✅ Patch 3: cruces grandes en centros (imposible “no verlos”)
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 2;

    const centers = [
      { x: t.leftCenterX, y: t.centerY, label: 'L' },
      { x: t.rightCenterX, y: t.centerY, label: 'R' },
    ];

    for (const c of centers) {
      const s = screenProject(c.x, c.y, 0);
      const size = 18;

      ctx.beginPath();
      ctx.moveTo(s.x - size, s.y);
      ctx.lineTo(s.x + size, s.y);
      ctx.moveTo(s.x, s.y - size);
      ctx.lineTo(s.x, s.y + size);
      ctx.stroke();

      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.font = '14px ui-monospace, monospace';
      ctx.fillText(c.label, s.x + size + 6, s.y + 5);
    }
    ctx.restore();

    ctx.restore();
  }

  // --- Handles ---
  const handles = getHandlesModel();
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);

    const isPivot = (key === 'neckPivot' || key === 'bodyPivot');
    const color = isPivot ? 'rgba(255,0,0,0.75)' : 'rgba(255,0,0,0.95)';

    drawHandle(ctx, key, color, true, s.x, s.y);

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
