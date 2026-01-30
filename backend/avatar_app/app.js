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

varying vec2 vUv;
varying float vHeadWeight;

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

        // DEBUG
        uDebugHeadWeight: { value: DebugView.headWeight ? 1.0 : 0.0 },
      },
    });

    particlePoints = new THREE.Points(particlesGeo, particleMaterial);
    particlePoints.frustumCulled = false;
    scene.add(particlePoints);

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

  if (particleMaterial) {
    particleMaterial.uniforms.uTime.value = elapsed;

    let targetTalk = 0.0;
    if (lipHoldActive) targetTalk = 1.0;
    else targetTalk = getTalkLevelFromAudio();

    AvatarState.talkLevel = targetTalk;
    particleMaterial.uniforms.uTalk.value = AvatarState.talkLevel;

    particleMaterial.uniforms.uRestOpen.value = 0.03;

    particleMaterial.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;

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
    particleMaterial.uniforms.uHeadRot.value.set(
      head.x + microPitch + nodPitch,
      head.y + microYaw,
      head.z + microRoll
    );

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
    particleMaterial.uniforms.uBodyOffset.value.set(0.0, offY, 0.0);

    // ✅ (CAMBIO #1) pivotes live SOLO cuando estás en modo editor
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
// 8. UI voice-first (pacto + modos + input)
// =========================
const UI = {
  // Overlays
  voicePact: document.getElementById('voicePact'),
  voicePactEnableBtn: document.getElementById('voicePactEnableBtn'),
  voicePactSkipBtn: document.getElementById('voicePactSkipBtn'),

  // Voice HUD
  voiceHud: document.getElementById('voiceHud'),
  voiceWaveCanvas: document.getElementById('voiceWaveCanvas'),
  voiceStopBtn: document.getElementById('voiceStopBtn'),
  switchToTextBtn: document.getElementById('switchToTextBtn'),

  // Text bar
  textBar: document.getElementById('textBar'),
  textInput: document.getElementById('textInput'),
  textSendBtn: document.getElementById('textSendBtn'),
  textMicBtn: document.getElementById('textMicBtn'),

  // Optional legacy (si aún existe)
  lastReplyEl: document.getElementById('lastReply'),

  // Optional toast (si existe)
  replyToast: document.getElementById('replyToast'),
  replyToastText: document.getElementById('replyToastText'),
};

const VoiceFirst = {
  lsKeyGranted: 'voice_pact_granted_v1',
  pactGranted: false,
  inputMode: 'VOICE', // VOICE | TEXT
  uiMode: 'INIT',     // INIT | READY | LISTENING | THINKING | SPEAKING | TEXT
};

function readBoolLS(key) {
  try { return localStorage.getItem(key) === '1'; } catch (_) { return false; }
}

function writeBoolLS(key, v) {
  try { localStorage.setItem(key, v ? '1' : '0'); } catch (_) {}
}

function showVoicePact(show) {
  if (!UI.voicePact) return;
  UI.voicePact.classList.toggle('is-hidden', !show);
}

function setReply(text) {
  if (UI.lastReplyEl) UI.lastReplyEl.textContent = text ?? '';
  if (UI.replyToast && UI.replyToastText) {
    UI.replyToastText.textContent = text ?? '';
    UI.replyToast.classList.toggle('is-hidden', !text);
  }
}

function hideReplyToast() {
  if (UI.replyToast) UI.replyToast.classList.add('is-hidden');
}

function setBodyModeClass(mode) {
  const cls = [
    'mode-init',
    'mode-ready',
    'mode-listening',
    'mode-thinking',
    'mode-speaking',
    'mode-text',
  ];
  document.body.classList.remove(...cls);

  const map = {
    INIT: 'mode-init',
    READY: 'mode-ready',
    LISTENING: 'mode-listening',
    THINKING: 'mode-thinking',
    SPEAKING: 'mode-speaking',
    TEXT: 'mode-text',
  };
  document.body.classList.add(map[mode] || 'mode-init');
}

function setUIMode(mode) {
  VoiceFirst.uiMode = mode;
  setBodyModeClass(mode);

  // Visibilidad módulos
  if (UI.voiceHud) UI.voiceHud.classList.toggle('is-hidden', !(mode === 'READY' || mode === 'LISTENING'));
  if (UI.textBar) UI.textBar.classList.toggle('is-hidden', mode !== 'TEXT');

  // Interacciones básicas (sin sobrepensarlo)
  const disableText = (mode === 'THINKING' || mode === 'SPEAKING' || mode === 'LISTENING');
  if (UI.textInput) UI.textInput.disabled = disableText;
  if (UI.textSendBtn) UI.textSendBtn.disabled = disableText || !(UI.textInput?.value || '').trim();

  if (UI.voiceStopBtn) UI.voiceStopBtn.disabled = (mode !== 'LISTENING');

  // Mantener coherencia con AvatarState (para nods/lipsync)
  if (mode === 'SPEAKING') AvatarState.mode = 'SPEAKING';
  else if (mode === 'LISTENING') AvatarState.mode = 'LISTENING';
  else if (mode === 'THINKING') AvatarState.mode = 'THINKING';
  else AvatarState.mode = 'IDLE';
}

async function requestVoicePact() {
  // AudioContext + permiso mic dentro de un gesto (click)
  const ctx = getOrCreateAudioContext();
  try { await ctx.resume(); } catch (_) {}

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('getUserMedia no soportado');
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  // Cerramos inmediatamente: solo queremos “permiso” para la sesión
  try { stream.getTracks().forEach((t) => t.stop()); } catch (_) {}

  VoiceFirst.pactGranted = true;
  writeBoolLS(VoiceFirst.lsKeyGranted, true);
}

function getSelectedAgentMode() {
  const modeRadio = document.querySelector('input[name="agentMode"]:checked');
  return modeRadio ? modeRadio.value : 'negociar';
}

function setInputModeVoice() {
  VoiceFirst.inputMode = 'VOICE';
  if (VoiceFirst.pactGranted) {
    setUIMode('READY');
    autoStartListeningSoon('switch_to_voice');
  } else {
    showVoicePact(true);
    setUIMode('TEXT');
  }
}

function setInputModeText() {
  VoiceFirst.inputMode = 'TEXT';
  setUIMode('TEXT');
  try { UI.textInput?.focus(); } catch (_) {}
}

function autoStartListeningSoon(reason = 'auto') {
  if (!VoiceFirst.pactGranted) return;
  if (VoiceFirst.inputMode !== 'VOICE') return;
  if (VoiceFirst.uiMode !== 'READY') return;

  // Pequeño delay para que la transición se sienta suave
  setTimeout(async () => {
    if (!VoiceFirst.pactGranted) return;
    if (VoiceFirst.inputMode !== 'VOICE') return;
    if (VoiceFirst.uiMode !== 'READY') return;
    if (isRecording) return;

    try {
      await startRecording();
      setUIMode('LISTENING');
    } catch (err) {
      console.warn('[voice] No se pudo iniciar grabación automática', err);
      setInputModeText();
    }
  }, 140);
}

function attachPostTtsHookOnce() {
  // Envolvemos el onended del audio para entrar en READY + auto-mic
  if (!audioSource) return;

  // Evitar wrap doble
  if (audioSource.__voiceFirstWrapped) return;
  audioSource.__voiceFirstWrapped = true;

  const prev = audioSource.onended;
  audioSource.onended = () => {
    try { prev?.(); } catch (_) {}

    // Si el usuario está en modo texto, no forzamos nada
    if (VoiceFirst.inputMode !== 'VOICE') {
      setUIMode('TEXT');
      return;
    }

    // Turno del usuario
    setUIMode('READY');
    autoStartListeningSoon('tts_end');
  };
}

async function sendTextToAgentVoiceFirst(message, { withAudio = true } = {}) {
  const text = (message || '').trim();
  if (!text) return;

  hideReplyToast();
  setReply('…');
  setUIMode('THINKING');

  try {
    const mode = getSelectedAgentMode();
    const endpoint = mode === 'chat' ? '/chat' : '/negociar';

    const res = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'web_user', session_id: 'sesion_demo', message: text }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Error agente: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const replyText = data.reply || '';
    const emotion = data.emotion || 'neutral';
    const intensity = data.tone === 'excited' ? 1.25 : data.tone === 'calm' ? 0.8 : 1.0;

    setReply(replyText);

    if (!withAudio || !replyText) {
      // Si no hay audio: turno usuario igualmente
      if (VoiceFirst.inputMode === 'VOICE' && VoiceFirst.pactGranted) {
        setUIMode('READY');
        autoStartListeningSoon('no_audio_reply');
      } else {
        setUIMode('TEXT');
      }
      return;
    }

    // TTS
    setUIMode('SPEAKING');
    const audioData = await requestTTS(replyText);
    await playAudioFromAudioData(audioData, { emotion, speechIntensity: intensity });

    // Engancha el final del TTS -> READY -> auto-mic
    attachPostTtsHookOnce();

  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    setReply(err?.message || 'Error de red');
    setUIMode('TEXT');
  }
}

// ---- Wiring UI ----
if (UI.voicePactEnableBtn) {
  UI.voicePactEnableBtn.addEventListener('click', async () => {
    try {
      await requestVoicePact();
      showVoicePact(false);
      setInputModeVoice();
    } catch (err) {
      console.warn('[voice-pact] Falló permiso mic', err);
      setInputModeText();
    }
  });
}

if (UI.voicePactSkipBtn) {
  UI.voicePactSkipBtn.addEventListener('click', () => {
    // Sin pacto: entramos en texto y dejamos mic como “opt-in”
    showVoicePact(false);
    setInputModeText();
  });
}

if (UI.switchToTextBtn) {
  UI.switchToTextBtn.addEventListener('click', () => {
    // Cancela grabación si estaba escuchando
    if (isRecording) stopRecording({ cancel: true });
    setInputModeText();
  });
}

if (UI.textMicBtn) {
  UI.textMicBtn.addEventListener('click', () => {
    setInputModeVoice();
  });
}

if (UI.textSendBtn) {
  UI.textSendBtn.addEventListener('click', async () => {
    const v = (UI.textInput?.value || '').trim();
    if (!v) return;
    UI.textInput.value = '';
    if (UI.textSendBtn) UI.textSendBtn.disabled = true;
    await sendTextToAgentVoiceFirst(v, { withAudio: true });
  });
}

if (UI.textInput) {
  UI.textInput.addEventListener('input', () => {
    if (UI.textSendBtn) UI.textSendBtn.disabled = !(UI.textInput.value || '').trim();
  });

  UI.textInput.addEventListener('keydown', (e) => {
    // Enter envía (sin shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      UI.textSendBtn?.click();
    }
  });
}

if (UI.voiceStopBtn) {
  UI.voiceStopBtn.addEventListener('click', () => {
    if (VoiceFirst.uiMode === 'LISTENING') {
      stopRecording({ cancel: false }); // envía STT -> agente
      setUIMode('THINKING');
    }
  });
}

// Key handling: SPACE termina voz | typing cancela voz y pasa a texto
window.addEventListener('keydown', (e) => {
  // SPACE para terminar cuando está escuchando
  if (VoiceFirst.uiMode === 'LISTENING' && e.code === 'Space') {
    e.preventDefault();
    stopRecording({ cancel: false });
    setUIMode('THINKING');
    return;
  }

  // Si está en READY/LISTENING y el usuario teclea texto, cancelamos voz y pasamos a TEXT
  const isTextKey =
    e.key &&
    e.key.length === 1 &&
    !e.ctrlKey &&
    !e.metaKey &&
    !e.altKey;

  if (isTextKey && (VoiceFirst.uiMode === 'READY' || VoiceFirst.uiMode === 'LISTENING')) {
    // Cancelar grabación sin enviar
    if (isRecording) stopRecording({ cancel: true });

    setInputModeText();
    // Insertar el carácter “capturado”
    if (UI.textInput) {
      e.preventDefault();
      UI.textInput.value = (UI.textInput.value || '') + e.key;
      UI.textInput.dispatchEvent(new Event('input'));
      try { UI.textInput.focus(); } catch (_) {}
    }
  }
});

// Init UI
(() => {
  VoiceFirst.pactGranted = readBoolLS(VoiceFirst.lsKeyGranted);

  if (!VoiceFirst.pactGranted) {
    // Mostrar “pacto” al inicio y default a texto
    showVoicePact(true);
    VoiceFirst.inputMode = 'TEXT';
    setUIMode('TEXT');
  } else {
    // Voice-first por defecto
    showVoicePact(false);
    VoiceFirst.inputMode = 'VOICE';
    setUIMode('READY');
    autoStartListeningSoon('init');
  }
})();

// =========================
// 9. Mic simple (voice-first)
// =========================
const waveCanvas = UI.voiceWaveCanvas; // nuevo canvas pequeño para onda
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioStream = null;
let waveAudioCtx = null;
let waveAnalyser = null;
let waveDataArray = null;
let waveAnimationId = null;

let recorderMimeType = 'audio/webm;codecs=opus';
let cancelNextRecording = false;

function drawWaveform() {
  if (!waveCanvas || !waveAnalyser) return;
  const ctx = waveCanvas.getContext('2d');

  // Asegurar tamaño real del canvas (por si el CSS lo escala)
  if (waveCanvas.width !== waveCanvas.clientWidth || waveCanvas.height !== waveCanvas.clientHeight) {
    waveCanvas.width = Math.max(1, waveCanvas.clientWidth);
    waveCanvas.height = Math.max(1, waveCanvas.clientHeight);
  }

  const width = waveCanvas.width;
  const height = waveCanvas.height;

  waveAnimationId = requestAnimationFrame(drawWaveform);
  waveAnalyser.getByteTimeDomainData(waveDataArray);

  ctx.clearRect(0, 0, width, height);

  // Fondo muy sutil (blanco/transparente)
  ctx.fillStyle = 'rgba(255,255,255,0.03)';
  ctx.fillRect(0, 0, width, height);

  ctx.lineWidth = 2;
  ctx.strokeStyle = 'rgba(255,255,255,0.70)';
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
  if (isRecording) return;
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('getUserMedia no soportado');

  try {
    getOrCreateAudioContext().resume().catch(() => {});
    warmupFrontendTts();
  } catch (_) {}

  cancelNextRecording = false;

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
    let hadError = false;

    // Si fue cancelado (typing/switch), no enviamos nada
    if (cancelNextRecording) {
      cancelNextRecording = false;
      teardownMic();
      isRecording = false;
      return;
    }

    setUIMode('THINKING');

    try {
      if (!blob.size) throw new Error('No se capturó audio. Intenta de nuevo.');

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

      teardownMic();
      isRecording = false;

      await sendTextToAgentVoiceFirst(text, { withAudio: true });

    } catch (err) {
      hadError = true;
      teardownMic();
      isRecording = false;

      console.error('Error al transcribir/enviar audio:', err);
      setReply(err?.message || 'Error de transcripción');
      setUIMode('TEXT');
    } finally {
      if (!hadError) {
        // Si el mensaje se envió, el flujo seguirá:
        // THINKING -> SPEAKING -> READY -> auto mic (si VOICE)
      }
    }
  };

  // Arranca
  mediaRecorder.start(250);
  isRecording = true;

  // Analizador para waveform UI
  waveAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;

  const source = waveAudioCtx.createMediaStreamSource(audioStream);
  source.connect(waveAnalyser);

  waveDataArray = new Uint8Array(waveAnalyser.frequencyBinCount);
  drawWaveform();
}

function stopRecording({ cancel = false } = {}) {
  if (cancel) cancelNextRecording = true;

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
