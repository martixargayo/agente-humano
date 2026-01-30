import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';
import { smoothstepJS } from './state.js';
import { DebugView } from './state.js';

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

let particleMaterial = null;
let particlePoints = null;

let sceneRef = null;
let controlsRef = null;

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

export function scheduleRecomputeHeadWeights(reason = 'change') {
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

export function scheduleRecomputeMouthWeights(reason = 'change') {
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
  if (!sceneRef) return;

  if (!blinkPoints) {
    const geo = createBlinkCurtainGeometry();
    blinkPoints = new THREE.Points(geo, particleMaterial);
    blinkPoints.frustumCulled = false;
    sceneRef.add(blinkPoints);
  } else {
    const old = blinkPoints.geometry;
    blinkPoints.geometry = createBlinkCurtainGeometry();
    try { old.dispose(); } catch (_) {}
  }

  logEyeTuning(reason);
}

export function scheduleRebuildBlinkCurtain(reason = 'change') {
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
export function initAvatarParticles({ scene, controls }) {
  sceneRef = scene;
  controlsRef = controls;

  const loader = new GLTFLoader();

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
      sceneRef.add(particlePoints);

      // Blink overlay points
      rebuildBlinkCurtain('after_load');

      controlsRef.target.set(0, 0.15, 0);
      controlsRef.update();

      // por si se tocó NeckTuning/MouthTuning antes de cargar
      scheduleRecomputeHeadWeights('after_load');
      scheduleRecomputeMouthWeights('after_load');
    },
    undefined,
    (err) => {
      console.error('Error cargando FaceVolumen.glb', err);
    },
  );
}

// =========================
// Getters
// =========================
export function getParticleMaterial() { return particleMaterial; }
export function getParticlePoints() { return particlePoints; }

// (Opcional) helper para toggles: mantiene compatibilidad si quieres llamarlo desde fuera
export function setDebugHeadWeight(enabled) {
  DebugView.headWeight = !!enabled;
  if (particleMaterial) particleMaterial.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;
}
