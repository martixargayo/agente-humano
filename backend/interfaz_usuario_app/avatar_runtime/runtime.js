import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

const URL_PARAMS = new URLSearchParams(window.location.search);
const DEBUG_EDIT_ENABLED = URL_PARAMS.get('debugEdit') === '1';
const DEBUG_MOUTH_POINTS_ENABLED = URL_PARAMS.get('debugMouthPoints') === '1';

function randRange(a, b) { return a + (b - a) * Math.random(); }
function clamp01(v) { return THREE.MathUtils.clamp(v, 0, 1); }
function smoothstepJS(edge0, edge1, x) {
  if (edge0 === edge1) return x < edge0 ? 0 : 1;
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3.0 - 2.0 * t);
}

function deepMerge(base, override) {
  if (!override || typeof override !== 'object' || Array.isArray(override)) {
    return Array.isArray(base) ? [...base] : { ...base };
  }
  const out = Array.isArray(base) ? [...base] : { ...base };
  Object.entries(override).forEach(([key, value]) => {
    if (typeof value === 'undefined') return;
    if (Array.isArray(value)) {
      out[key] = [...value];
      return;
    }
    if (value && typeof value === 'object' && !Array.isArray(value) && out[key] && typeof out[key] === 'object' && !Array.isArray(out[key])) {
      out[key] = deepMerge(out[key], value);
      return;
    }
    out[key] = value;
  });
  return out;
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
attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;
attribute float aHeightFromTop;
attribute float aMouthWeight;
attribute float aMouthSide;
attribute float aHeadWeight;
varying vec2 vUv;
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
uniform float uBlink;
uniform vec4 uEyeLeftMain;
uniform vec4 uEyeLeftUpper;
uniform vec4 uEyeLeftLower;
uniform vec4 uEyeRightMain;
uniform vec4 uEyeRightUpper;
uniform vec4 uEyeRightLower;
uniform float uMouthOpenVisual;
uniform float uMouthMeshFade;
uniform float uMouthFeather;
uniform float uMouthMeshAlphaMin;
uniform float uMouthMeshFadeGamma;
uniform float uMouthMeshFadeGain;
uniform float uUseDiamondFade;
uniform float uFadeDiamondCX;
uniform float uFadeDiamondCY;
uniform float uFadeDiamondRX;
uniform float uFadeDiamondRY;
uniform float uFadeDiamondRot;
uniform float uMouthHoleActive;
varying vec2 vUv;
varying float vBaseZ;
varying vec2 vBaseXY;
varying float vMouthWeight;
mat2 invRot(float a) { float s = sin(a); float c = cos(a); return mat2(c, s, -s, c); }
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
  if (mouthHoleActive > 0.5 && diamondInside > 0.5) discard;
  finalColor = mix(finalColor, finalColor * 0.88, mouthFade * 0.35);
  float outAlpha = mix(1.0, clamp(uMouthMeshAlphaMin, 0.0, 1.0), mouthFade);
  gl_FragColor = vec4(finalColor, outAlpha);
}
`;

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
  vec3 displaced = aBasePosition + vec3(0.0, aMouthSide * lipAmp * mouthFactor, -uLipDepthAmp * mouthFactor);
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
  float circle = 1.0 - smoothstep(0.68, 1.0, sqrt(r2));
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

export function createAvatarRuntime({ stageEl, config }) {
  const canvas = document.createElement('canvas');
  canvas.id = 'avatarCanvas';
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;z-index:2;display:block;';
  stageEl?.appendChild(canvas);

  const scene = new THREE.Scene();
  scene.background = null;

  const camera = new THREE.PerspectiveCamera(config.camera.fov, window.innerWidth / window.innerHeight, config.camera.near, config.camera.far);
  camera.position.fromArray(config.camera.position);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(0x000000, 0);
  renderer.setSize(window.innerWidth, window.innerHeight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.fromArray(config.controlsTarget);

  const controlsLocked = config.controlsLocked !== false;
  if (controlsLocked) {
    controls.enabled = false;
    controls.enableRotate = false;
    controls.enablePan = false;
    controls.enableZoom = false;
  }

  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2, 4, 3);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.5);
  rim.position.set(-2, 3, -2);
  scene.add(rim);
  scene.add(new THREE.AmbientLight(0xffffff, 0.2));

  const state = { mode: 'IDLE', talkLevel: 0, manualTalkLevel: 0, analyser: null, analyserData: null, lipsyncLevel: 0 };
  let runtimeReady = false;
  let runtimeError = null;
  const readyListeners = new Set();
  const errorListeners = new Set();

  function emitRuntimeReady() {
    runtimeReady = true;
    runtimeError = null;
    window.dispatchEvent(new CustomEvent('avatar-runtime-ready'));
    readyListeners.forEach((cb) => {
      try { cb(); } catch (_) {}
    });
  }

  function emitRuntimeError(error) {
    runtimeReady = false;
    runtimeError = error;
    window.dispatchEvent(new CustomEvent('avatar-runtime-error', { detail: { error } }));
    errorListeners.forEach((cb) => {
      try { cb(error); } catch (_) {}
    });
  }
  const clock = new THREE.Clock();

  function requiredFiniteNumber(value, fieldName) {
    if (!Number.isFinite(Number(value))) {
      throw new Error(`avatar_runtime_missing_${fieldName}`);
    }
    return Number(value);
  }

  function normalizeCalibration(nextCalibration) {
    return {
      mouth: {
        centerX: requiredFiniteNumber(nextCalibration?.mouth?.center_x, 'calibration_mouth_center_x'),
        centerY: requiredFiniteNumber(nextCalibration?.mouth?.center_y, 'calibration_mouth_center_y'),
        width: requiredFiniteNumber(nextCalibration?.mouth?.width, 'calibration_mouth_width'),
        height: requiredFiniteNumber(nextCalibration?.mouth?.height, 'calibration_mouth_height'),
        curve: requiredFiniteNumber(nextCalibration?.mouth?.curve, 'calibration_mouth_curve'),
      },
      neck: {
        centerX: requiredFiniteNumber(nextCalibration?.neck?.center_x, 'calibration_neck_center_x'),
        width: requiredFiniteNumber(nextCalibration?.neck?.width, 'calibration_neck_width'),
        topY: requiredFiniteNumber(nextCalibration?.neck?.top_y, 'calibration_neck_top_y'),
        bottomY: requiredFiniteNumber(nextCalibration?.neck?.bottom_y, 'calibration_neck_bottom_y'),
        curve: requiredFiniteNumber(nextCalibration?.neck?.curve, 'calibration_neck_curve'),
        neckPivotY: requiredFiniteNumber(nextCalibration?.neck?.neck_pivot_y, 'calibration_neck_neck_pivot_y'),
        bodyPivotY: requiredFiniteNumber(nextCalibration?.neck?.body_pivot_y, 'calibration_neck_body_pivot_y'),
      },
      eyes: {
        left: {
          centerX: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.center_x, 'calibration_eyes_left_center_x'),
          centerY: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.center_y, 'calibration_eyes_left_center_y'),
          halfWidth: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.half_width, 'calibration_eyes_left_half_width'),
          rotation: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.rotation, 'calibration_eyes_left_rotation'),
          upper: {
            offset: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.upper?.offset, 'calibration_eyes_left_upper_offset'),
            curve: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.upper?.curve, 'calibration_eyes_left_upper_curve'),
          },
          lower: {
            offset: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.lower?.offset, 'calibration_eyes_left_lower_offset'),
            curve: requiredFiniteNumber(nextCalibration?.eyes?.left_eye?.lower?.curve, 'calibration_eyes_left_lower_curve'),
          },
        },
        right: {
          centerX: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.center_x, 'calibration_eyes_right_center_x'),
          centerY: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.center_y, 'calibration_eyes_right_center_y'),
          halfWidth: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.half_width, 'calibration_eyes_right_half_width'),
          rotation: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.rotation, 'calibration_eyes_right_rotation'),
          upper: {
            offset: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.upper?.offset, 'calibration_eyes_right_upper_offset'),
            curve: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.upper?.curve, 'calibration_eyes_right_upper_curve'),
          },
          lower: {
            offset: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.lower?.offset, 'calibration_eyes_right_lower_offset'),
            curve: requiredFiniteNumber(nextCalibration?.eyes?.right_eye?.lower?.curve, 'calibration_eyes_right_lower_curve'),
          },
        },
      },
      mouthRender: {
        rimA: requiredFiniteNumber(nextCalibration?.mouth_render?.rim_a, 'calibration_mouth_render_rim_a'),
        rimB: requiredFiniteNumber(nextCalibration?.mouth_render?.rim_b, 'calibration_mouth_render_rim_b'),
        rimC: requiredFiniteNumber(nextCalibration?.mouth_render?.rim_c, 'calibration_mouth_render_rim_c'),
        rimD: requiredFiniteNumber(nextCalibration?.mouth_render?.rim_d, 'calibration_mouth_render_rim_d'),
        innerA: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_a, 'calibration_mouth_render_inner_a'),
        innerB: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_b, 'calibration_mouth_render_inner_b'),
        innerGain: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_gain, 'calibration_mouth_render_inner_gain'),
        innerCoreA: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_core_a, 'calibration_mouth_render_inner_core_a'),
        innerCoreB: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_core_b, 'calibration_mouth_render_inner_core_b'),
        innerCoreGain: requiredFiniteNumber(nextCalibration?.mouth_render?.inner_core_gain, 'calibration_mouth_render_inner_core_gain'),
        maskMin: requiredFiniteNumber(nextCalibration?.mouth_render?.mask_min, 'calibration_mouth_render_mask_min'),
        upsampleMinPoints: requiredFiniteNumber(nextCalibration?.mouth_render?.upsample_min_points, 'calibration_mouth_render_upsample_min_points'),
        upsampleAmpMin: requiredFiniteNumber(nextCalibration?.mouth_render?.upsample_amp_min, 'calibration_mouth_render_upsample_amp_min'),
        upsampleAmpMax: requiredFiniteNumber(nextCalibration?.mouth_render?.upsample_amp_max, 'calibration_mouth_render_upsample_amp_max'),
        rimResampleFactor: requiredFiniteNumber(nextCalibration?.mouth_render?.rim_resample_factor, 'calibration_mouth_render_rim_resample_factor'),
        pointsAlpha: requiredFiniteNumber(nextCalibration?.mouth_render?.points_alpha, 'calibration_mouth_render_points_alpha'),
        pointsAlphaClip: requiredFiniteNumber(nextCalibration?.mouth_render?.points_alpha_clip, 'calibration_mouth_render_points_alpha_clip'),
        pointsSizeNear: requiredFiniteNumber(nextCalibration?.mouth_render?.points_size_near, 'calibration_mouth_render_points_size_near') * window.devicePixelRatio,
        pointsSizeFar: requiredFiniteNumber(nextCalibration?.mouth_render?.points_size_far, 'calibration_mouth_render_points_size_far') * window.devicePixelRatio,
        pointsColorMul: requiredFiniteNumber(nextCalibration?.mouth_render?.points_color_mul, 'calibration_mouth_render_points_color_mul'),
        pointsLumaFloor: requiredFiniteNumber(nextCalibration?.mouth_render?.points_luma_floor, 'calibration_mouth_render_points_luma_floor'),
        pointsLumaStrength: requiredFiniteNumber(nextCalibration?.mouth_render?.points_luma_strength, 'calibration_mouth_render_points_luma_strength'),
        pointsLumaPreserveHue: requiredFiniteNumber(nextCalibration?.mouth_render?.points_luma_preserve_hue, 'calibration_mouth_render_points_luma_preserve_hue'),
        pointsLumaDebug: Boolean(nextCalibration?.mouth_render?.points_luma_debug),
        pointsCullBack: Boolean(nextCalibration?.mouth_render?.points_cull_back),
        pointsDebugBackOnly: Boolean(nextCalibration?.mouth_render?.points_debug_back_only),
        meshFade: requiredFiniteNumber(nextCalibration?.mouth_render?.mesh_fade, 'calibration_mouth_render_mesh_fade'),
        meshFeather: requiredFiniteNumber(nextCalibration?.mouth_render?.mesh_feather, 'calibration_mouth_render_mesh_feather'),
        meshAlphaMin: requiredFiniteNumber(nextCalibration?.mouth_render?.mesh_alpha_min, 'calibration_mouth_render_mesh_alpha_min'),
        meshFadeGamma: requiredFiniteNumber(nextCalibration?.mouth_render?.mesh_fade_gamma, 'calibration_mouth_render_mesh_fade_gamma'),
        meshFadeGain: requiredFiniteNumber(nextCalibration?.mouth_render?.mesh_fade_gain, 'calibration_mouth_render_mesh_fade_gain'),
        useDiamondFade: Boolean(nextCalibration?.mouth_render?.use_diamond_fade),
        fadeDiamondCX: requiredFiniteNumber(nextCalibration?.mouth_render?.fade_diamond_cx, 'calibration_mouth_render_fade_diamond_cx'),
        fadeDiamondCY: requiredFiniteNumber(nextCalibration?.mouth_render?.fade_diamond_cy, 'calibration_mouth_render_fade_diamond_cy'),
        fadeDiamondRX: requiredFiniteNumber(nextCalibration?.mouth_render?.fade_diamond_rx, 'calibration_mouth_render_fade_diamond_rx'),
        fadeDiamondRY: requiredFiniteNumber(nextCalibration?.mouth_render?.fade_diamond_ry, 'calibration_mouth_render_fade_diamond_ry'),
        fadeDiamondRot: requiredFiniteNumber(nextCalibration?.mouth_render?.fade_diamond_rot, 'calibration_mouth_render_fade_diamond_rot'),
        alwaysPointsMode: Boolean(nextCalibration?.mouth_render?.always_points_mode),
        pointsOn: requiredFiniteNumber(nextCalibration?.mouth_render?.points_on, 'calibration_mouth_render_points_on'),
        pointsOff: requiredFiniteNumber(nextCalibration?.mouth_render?.points_off, 'calibration_mouth_render_points_off'),
      },
      lipsync: {
        talkAmpTop: requiredFiniteNumber(nextCalibration?.lipsync?.talk_amp_top, 'calibration_lipsync_talk_amp_top'),
        talkAmpBot: requiredFiniteNumber(nextCalibration?.lipsync?.talk_amp_bottom, 'calibration_lipsync_talk_amp_bottom'),
        talkFreq: requiredFiniteNumber(nextCalibration?.lipsync?.talk_freq, 'calibration_lipsync_talk_freq'),
        lipDepthAmp: requiredFiniteNumber(nextCalibration?.lipsync?.lip_depth_amp, 'calibration_lipsync_lip_depth_amp'),
        restOpen: requiredFiniteNumber(nextCalibration?.lipsync?.rest_open, 'calibration_lipsync_rest_open'),
        attack: requiredFiniteNumber(nextCalibration?.lipsync?.attack, 'calibration_lipsync_attack'),
        release: requiredFiniteNumber(nextCalibration?.lipsync?.release, 'calibration_lipsync_release'),
      },
    };
  }

  function normalizeMotion(nextMotion = {}) {
    return {
      head: {
        ampYaw: requiredFiniteNumber(nextMotion?.head?.amp_yaw, 'motion_head_amp_yaw'),
        ampPitch: requiredFiniteNumber(nextMotion?.head?.amp_pitch, 'motion_head_amp_pitch'),
        ampRoll: requiredFiniteNumber(nextMotion?.head?.amp_roll, 'motion_head_amp_roll'),
        holdMin: requiredFiniteNumber(nextMotion?.head?.hold_min, 'motion_head_hold_min'),
        holdMax: requiredFiniteNumber(nextMotion?.head?.hold_max, 'motion_head_hold_max'),
        smooth: requiredFiniteNumber(nextMotion?.head?.smooth, 'motion_head_smooth'),
        rampDur: requiredFiniteNumber(nextMotion?.head?.ramp_dur, 'motion_head_ramp_dur'),
      },
      body: {
        ampYaw: requiredFiniteNumber(nextMotion?.body?.amp_yaw, 'motion_body_amp_yaw'),
        ampPitch: requiredFiniteNumber(nextMotion?.body?.amp_pitch, 'motion_body_amp_pitch'),
        ampRoll: requiredFiniteNumber(nextMotion?.body?.amp_roll, 'motion_body_amp_roll'),
        holdMin: requiredFiniteNumber(nextMotion?.body?.hold_min, 'motion_body_hold_min'),
        holdMax: requiredFiniteNumber(nextMotion?.body?.hold_max, 'motion_body_hold_max'),
        smooth: requiredFiniteNumber(nextMotion?.body?.smooth, 'motion_body_smooth'),
        rampDur: requiredFiniteNumber(nextMotion?.body?.ramp_dur, 'motion_body_ramp_dur'),
      },
      micro: {
        yaw: requiredFiniteNumber(nextMotion?.micro?.yaw, 'motion_micro_yaw'),
        pitch: requiredFiniteNumber(nextMotion?.micro?.pitch, 'motion_micro_pitch'),
        roll: requiredFiniteNumber(nextMotion?.micro?.roll, 'motion_micro_roll'),
      },
      nod: {
        listenProbability: requiredFiniteNumber(nextMotion?.nod?.listen_probability, 'motion_nod_listen_probability'),
        durMin: requiredFiniteNumber(nextMotion?.nod?.dur_min, 'motion_nod_dur_min'),
        durMax: requiredFiniteNumber(nextMotion?.nod?.dur_max, 'motion_nod_dur_max'),
        ampMin: requiredFiniteNumber(nextMotion?.nod?.amp_min, 'motion_nod_amp_min'),
        ampMax: requiredFiniteNumber(nextMotion?.nod?.amp_max, 'motion_nod_amp_max'),
      },
      bodyBob: {
        ampPrimary: requiredFiniteNumber(nextMotion?.body_bob?.amp_primary, 'motion_body_bob_amp_primary'),
        freqPrimary: requiredFiniteNumber(nextMotion?.body_bob?.freq_primary, 'motion_body_bob_freq_primary'),
        ampSecondary: requiredFiniteNumber(nextMotion?.body_bob?.amp_secondary, 'motion_body_bob_amp_secondary'),
        freqSecondary: requiredFiniteNumber(nextMotion?.body_bob?.freq_secondary, 'motion_body_bob_freq_secondary'),
      },
    };
  }

  const Calibration = normalizeCalibration(config.calibration);
  const MouthTuning = Calibration.mouth;
  const NeckTuning = Calibration.neck;
  const EyeBlinkTuning = Calibration.eyes;
  const MouthRenderTuning = Calibration.mouthRender;
  const LipsyncTuning = Calibration.lipsync;

  const MotionConfig = normalizeMotion(config.motion);
  const EyelidMotionState = { value: 0, phase: 'idle', timer: 0, duration: 0.12, nextBlinkAt: 2.2, pendingDouble: false, initialized: false };
  const MotionState = {
    seed: Math.random() * 1000,
    head: { current: new THREE.Vector3(), target: new THREE.Vector3(), targetFrom: new THREE.Vector3(), targetTo: new THREE.Vector3(), nextSwitch: 0, targetT0: 0 },
    body: { current: new THREE.Vector3(), target: new THREE.Vector3(), targetFrom: new THREE.Vector3(), targetTo: new THREE.Vector3(), nextSwitch: 0, targetT0: 0 },
    nod: { active: false, t0: 0, dur: 0.32, amp: 0.012 },
  };

  let surfaceMaterial = null;
  let surfaceMesh = null;
  let mouthPointsMaterial = null;
  let mouthPoints = null;
  let mouthOpenVisual = 0;
  let mouthPointsVisibleLatched = MouthRenderTuning.alwaysPointsMode === true;

  function createStableRandom(x, y, z, salt = 0.0) {
    const qx = Math.round(x * 10000.0) / 10000.0;
    const qy = Math.round(y * 10000.0) / 10000.0;
    const qz = Math.round(z * 10000.0) / 10000.0;
    const seed = qx * 127.1 + qy * 311.7 + qz * 74.7 + salt * 19.19;
    const v = Math.sin(seed) * 43758.5453123;
    return v - Math.floor(v);
  }

  function mouthRimMaskFromWeight(w) {
    const t = MouthRenderTuning;
    const rimMask = smoothstepJS(t.rimA, t.rimB, w) * (1.0 - smoothstepJS(t.rimC, t.rimD, w));
    const innerTiny = smoothstepJS(t.innerA, t.innerB, w) * t.innerGain;
    const innerCore = smoothstepJS(t.innerCoreA, t.innerCoreB, w) * t.innerCoreGain;
    return THREE.MathUtils.clamp(rimMask + innerTiny + innerCore, 0, 1);
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
    if (!basePosAttr || !posAttr || !uvAttr || !mouthWeightAttr || !mouthSideAttr || !headWeightAttr) return null;

    const tuning = MouthRenderTuning;
    const p = []; const b = []; const uv = []; const mw = []; const ms = []; const hw = []; const ov = [];
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
      const overlay = mouthRimMaskFromWeight(w);
      overlayByVertex[i] = overlay;
      if (overlay <= tuning.maskMin) continue;
      const x = posAttr.getX(i); const y = posAttr.getY(i); const z = posAttr.getZ(i);
      const bx = basePosAttr.getX(i); const by = basePosAttr.getY(i); const bz = basePosAttr.getZ(i);
      addPoint(x, y, z, bx, by, bz, uvAttr.getX(i), uvAttr.getY(i), w, mouthSideAttr.getX(i), headWeightAttr.getX(i), overlay);
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

    if (triIndices.length && tuning.rimResampleFactor > 0) {
      const sourceCount = p.length / 3;
      const targetResampled = Math.max(0, Math.round(sourceCount * tuning.rimResampleFactor));
      const totalWeight = triWeights.reduce((a, bb) => a + bb, 0.0) || 1.0;

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
        }
      }
    }

    if (!p.length) return null;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(p), 3));
    geo.setAttribute('aBasePosition', new THREE.BufferAttribute(new Float32Array(b), 3));
    geo.setAttribute('aUv', new THREE.BufferAttribute(new Float32Array(uv), 2));
    geo.setAttribute('aMouthWeight', new THREE.BufferAttribute(new Float32Array(mw), 1));
    geo.setAttribute('aMouthSide', new THREE.BufferAttribute(new Float32Array(ms), 1));
    geo.setAttribute('aHeadWeight', new THREE.BufferAttribute(new Float32Array(hw), 1));
    geo.setAttribute('aMouthOverlayMix', new THREE.BufferAttribute(new Float32Array(ov), 1));
    return geo;
  }

  function applyEyeUniforms(mat) {
    const left = EyeBlinkTuning.left;
    const right = EyeBlinkTuning.right;
    mat.uniforms.uBlink.value = EyelidMotionState.value;
    mat.uniforms.uEyeLeftMain.value.set(left.centerX, left.centerY, Math.max(1e-4, Math.abs(left.halfWidth)), left.rotation || 0);
    mat.uniforms.uEyeLeftUpper.value.set(left.upper.offset, left.upper.curve, 0, 0);
    mat.uniforms.uEyeLeftLower.value.set(left.lower.offset, left.lower.curve, 0, 0);
    mat.uniforms.uEyeRightMain.value.set(right.centerX, right.centerY, Math.max(1e-4, Math.abs(right.halfWidth)), right.rotation || 0);
    mat.uniforms.uEyeRightUpper.value.set(right.upper.offset, right.upper.curve, 0, 0);
    mat.uniforms.uEyeRightLower.value.set(right.lower.offset, right.lower.curve, 0, 0);
  }

  function generateAnimatedSurfaceGeometry(srcGeometry) {
    const geo = srcGeometry.clone();
    const pos = geo.getAttribute('position');
    const uv = geo.getAttribute('uv');
    const count = pos.count;
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
    const minY = box ? box.min.y : -1;
    const maxY = box ? box.max.y : 1;
    const yRange = Math.max(1e-6, maxY - minY);
    for (let i = 0; i < count; i++) {
      const x = pos.getX(i); const y = pos.getY(i); const z = pos.getZ(i);
      basePositions[i * 3] = x; basePositions[i * 3 + 1] = y; basePositions[i * 3 + 2] = z;
      randoms[i * 3] = createStableRandom(x, y, z, 1.0);
      randoms[i * 3 + 1] = createStableRandom(x, y, z, 2.0);
      randoms[i * 3 + 2] = createStableRandom(x, y, z, 3.0);
      uvArray[i * 2] = uv ? uv.getX(i) : 0; uvArray[i * 2 + 1] = uv ? uv.getY(i) : 0;
      const y01 = (y - minY) / yRange;
      heightFromTop[i] = clamp01(1 - y01);
      const cx = Math.floor((x + 0.4) * 10.0);
      const cy = Math.floor((y + 0.4) * 10.0);
      clusterIds[i] = cx + cy * 10.0;
      const mwAbs = Math.max(1e-6, Math.abs(MouthTuning.width));
      const mhAbs = Math.max(1e-6, Math.abs(MouthTuning.height));
      const dx = x - MouthTuning.centerX; const ax = Math.abs(dx);
      let weight = 0; let side = 0;
      if (ax <= mwAbs) {
        const normX = dx / mwAbs;
        const curveY = MouthTuning.centerY - MouthTuning.curve * normX * normX;
        const dy = y - curveY; const ay = Math.abs(dy);
        if (ay <= mhAbs) { weight = clamp01((1 - ax / mwAbs) * (1 - ay / mhAbs)); side = dy > 0 ? 1 : (dy < 0 ? -1 : 0); }
      }
      mouthWeights[i] = weight; mouthSides[i] = side;
      const wAbs = Math.max(1e-6, Math.abs(NeckTuning.width));
      const dxN = x - NeckTuning.centerX; const insideWidth = Math.abs(dxN) <= wAbs;
      const nx = clamp01((dxN / wAbs + 1) * 0.5) * 2 - 1;
      const curve = NeckTuning.curve * nx * nx;
      let yTop = insideWidth ? (NeckTuning.topY - curve) : NeckTuning.topY;
      let yBot = insideWidth ? (NeckTuning.bottomY - curve) : NeckTuning.bottomY;
      if (yTop < yBot) [yTop, yBot] = [yBot, yTop];
      headWeights[i] = y >= yTop ? 1 : (y <= yBot ? 0 : smoothstepJS(yBot, yTop, y));
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

  function nextBlinkInterval() { return randRange(2.0, 6.0); }
  function startEyelidBlink(durationSec) { EyelidMotionState.phase = 'closing'; EyelidMotionState.timer = 0; EyelidMotionState.duration = durationSec; EyelidMotionState.value = 0; }
  function updateEyelidBlink(elapsed, delta) {
    if (!EyelidMotionState.initialized) { EyelidMotionState.initialized = true; EyelidMotionState.nextBlinkAt = elapsed + randRange(0.45, 1.35); }
    if (EyelidMotionState.phase === 'idle') {
      if (elapsed >= EyelidMotionState.nextBlinkAt) { startEyelidBlink(randRange(0.09, 0.15)); EyelidMotionState.pendingDouble = Math.random() < 0.2; }
      return;
    }
    EyelidMotionState.timer += delta;
    const closeDuration = EyelidMotionState.duration * 0.34;
    const openDuration = EyelidMotionState.duration * 0.66;
    if (EyelidMotionState.phase === 'closing') {
      const t = clamp01(EyelidMotionState.timer / closeDuration);
      EyelidMotionState.value = t;
      if (t >= 1) { EyelidMotionState.phase = 'opening'; EyelidMotionState.timer = 0; }
      return;
    }
    const t = clamp01(EyelidMotionState.timer / openDuration);
    EyelidMotionState.value = 1 - t;
    if (t >= 1) { EyelidMotionState.phase = 'idle'; EyelidMotionState.timer = 0; EyelidMotionState.value = 0; EyelidMotionState.nextBlinkAt = elapsed + (EyelidMotionState.pendingDouble ? randRange(0.08, 0.16) : nextBlinkInterval()); EyelidMotionState.pendingDouble = false; }
  }

  function pickTarget(cfg) {
    const bias = 0.65; const s = () => (Math.random() * 2 - 1);
    const soften = () => (Math.random() < bias ? 0.35 : 1.0) * randRange(0.4, 1.0);
    return new THREE.Vector3(s() * cfg.ampPitch * soften(), s() * cfg.ampYaw * soften(), s() * cfg.ampRoll * soften());
  }
  function updateChannel(ch, cfg, t, dt) {
    if (t >= ch.nextSwitch) { ch.targetFrom.copy(ch.target); ch.targetTo.copy(pickTarget(cfg)); ch.targetT0 = t; ch.nextSwitch = t + randRange(cfg.holdMin, cfg.holdMax); }
    const rampT = clamp01((t - ch.targetT0) / Math.max(0.001, cfg.rampDur || 0.001));
    const rampS = rampT * rampT * (3 - 2 * rampT);
    ch.target.copy(ch.targetFrom).lerp(ch.targetTo, rampS);
    ch.current.lerp(ch.target, 1 - Math.exp(-dt * cfg.smooth));
  }
  function updateNod(t, dt) {
    if (!MotionState.nod.active && state.mode === 'LISTENING' && Math.random() < MotionConfig.nod.listenProbability * dt) { MotionState.nod.active = true; MotionState.nod.t0 = t; MotionState.nod.dur = randRange(MotionConfig.nod.durMin, MotionConfig.nod.durMax); MotionState.nod.amp = randRange(MotionConfig.nod.ampMin, MotionConfig.nod.ampMax); }
    if (!MotionState.nod.active) return 0;
    const u = (t - MotionState.nod.t0) / MotionState.nod.dur;
    if (u >= 1) { MotionState.nod.active = false; return 0; }
    return Math.sin(u * Math.PI) * MotionState.nod.amp;
  }

  function getTalkLevelFromAnalyser() {
    if (!(state.analyser && state.analyserData) || state.mode !== 'SPEAKING') return state.manualTalkLevel;
    state.analyser.getByteTimeDomainData(state.analyserData);
    let sum = 0;
    for (let i = 0; i < state.analyserData.length; i++) {
      const v = state.analyserData[i] / 128 - 1;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / state.analyserData.length);
    let target = clamp01((rms - 0.01) / (0.12 - 0.01));
    if (target > 0) target = 0.12 + (1 - 0.12) * target;
    const speed = target > state.lipsyncLevel ? 32 : 12;
    state.lipsyncLevel += (target - state.lipsyncLevel) * (1 - Math.exp(-(1 / 60) * speed));
    return state.lipsyncLevel;
  }

  const loader = new GLTFLoader();
  loader.load(config.modelUrl, (gltf) => {
    const meshes = [];
    gltf.scene.traverse((obj) => { if (obj.isMesh) meshes.push(obj); });
    if (!meshes.length) {
      emitRuntimeError(new Error('No se encontraron meshes en el GLTF.'));
      return;
    }
    let colorMap = null;
    for (const m of meshes) { if (m.material?.map) { colorMap = m.material.map; break; } }

    const geoms = [];
    meshes.forEach((m) => { const g = m.geometry.clone(); m.updateWorldMatrix(true, false); g.applyMatrix4(m.matrixWorld); geoms.push(g); });
    const mergeFn = BufferGeometryUtils.mergeGeometries || BufferGeometryUtils.mergeBufferGeometries;
    const mergedGeom = mergeFn(geoms, true);
    if (!mergedGeom) {
      emitRuntimeError(new Error('No se pudo fusionar geometría del avatar.'));
      return;
    }
    mergedGeom.computeVertexNormals();
    mergedGeom.computeBoundingBox();
    const center = new THREE.Vector3();
    mergedGeom.boundingBox.getCenter(center);
    mergedGeom.translate(-center.x, -center.y, -center.z);

    const animatedSurfaceGeometry = generateAnimatedSurfaceGeometry(mergedGeom);
    surfaceMaterial = new THREE.ShaderMaterial({
      vertexShader: realisticSurfaceVertexShader,
      fragmentShader: realisticSurfaceFragmentShader,
      transparent: true,
      uniforms: {
        uTime: { value: 0 }, uGlobalAmp: { value: 1.5 }, uClusterAmp: { value: 1.5 }, uNoiseAmp: { value: 1.6 },
        uTalk: { value: 0 }, uTalkAmpTop: { value: LipsyncTuning.talkAmpTop }, uTalkAmpBot: { value: LipsyncTuning.talkAmpBot }, uTalkFreq: { value: LipsyncTuning.talkFreq },
        uLipDepthAmp: { value: LipsyncTuning.lipDepthAmp }, uRestOpen: { value: LipsyncTuning.restOpen }, uBreathAmp: { value: 1.0 }, uBreathFreq: { value: 0.6 },
        uHeadRot: { value: new THREE.Vector3() }, uBodyRot: { value: new THREE.Vector3() }, uBodyOffset: { value: new THREE.Vector3() },
        uNeckPivot: { value: new THREE.Vector3(0, NeckTuning.neckPivotY, 0) }, uBodyPivot: { value: new THREE.Vector3(0, NeckTuning.bodyPivotY, 0) },
        uDissolveStart: { value: 0.9 }, uDissolveEnd: { value: 1.0 }, uDissolveMotionAmp: { value: 1.0 },
        uColorMap: { value: colorMap }, uUseMap: { value: colorMap ? 1.0 : 0.0 }, uColor: { value: new THREE.Color(0xffffff) },
        uBlink: { value: 0 }, uEyeLeftMain: { value: new THREE.Vector4() }, uEyeLeftUpper: { value: new THREE.Vector4() },
        uEyeLeftLower: { value: new THREE.Vector4() }, uEyeRightMain: { value: new THREE.Vector4() }, uEyeRightUpper: { value: new THREE.Vector4() },
        uEyeRightLower: { value: new THREE.Vector4() }, uMouthOpenVisual: { value: 0 }, uMouthMeshFade: { value: MouthRenderTuning.meshFade },
        uMouthFeather: { value: MouthRenderTuning.meshFeather }, uMouthMeshAlphaMin: { value: MouthRenderTuning.meshAlphaMin },
        uMouthMeshFadeGamma: { value: MouthRenderTuning.meshFadeGamma }, uMouthMeshFadeGain: { value: MouthRenderTuning.meshFadeGain },
        uUseDiamondFade: { value: MouthRenderTuning.useDiamondFade ? 1 : 0 }, uFadeDiamondCX: { value: MouthRenderTuning.fadeDiamondCX },
        uFadeDiamondCY: { value: MouthRenderTuning.fadeDiamondCY }, uFadeDiamondRX: { value: MouthRenderTuning.fadeDiamondRX },
        uFadeDiamondRY: { value: MouthRenderTuning.fadeDiamondRY }, uFadeDiamondRot: { value: MouthRenderTuning.fadeDiamondRot },
        uMouthHoleActive: { value: 0 },
      },
    });

    surfaceMesh = new THREE.Mesh(animatedSurfaceGeometry, surfaceMaterial);
    surfaceMesh.frustumCulled = false;
    surfaceMesh.scale.setScalar(config.transform.scale || 1.0);
    surfaceMesh.position.fromArray(config.transform.offset || [0, 0, 0]);
    scene.add(surfaceMesh);

    const mouthGeo = buildMouthPointsGeometryFromAnimatedSurface(animatedSurfaceGeometry);
    if (mouthGeo) {
      mouthPointsMaterial = new THREE.ShaderMaterial({
        vertexShader: mouthPointsVertexShader,
        fragmentShader: mouthPointsFragmentShader,
        transparent: true,
        depthWrite: false,
        uniforms: {
          uTime: { value: 0 }, uTalk: { value: 0 }, uTalkAmpTop: { value: LipsyncTuning.talkAmpTop }, uTalkAmpBot: { value: LipsyncTuning.talkAmpBot }, uTalkFreq: { value: LipsyncTuning.talkFreq },
          uLipDepthAmp: { value: LipsyncTuning.lipDepthAmp }, uRestOpen: { value: LipsyncTuning.restOpen }, uPointSizeNear: { value: MouthRenderTuning.pointsSizeNear },
          uPointSizeFar: { value: MouthRenderTuning.pointsSizeFar }, uHeadRot: { value: new THREE.Vector3() }, uBodyRot: { value: new THREE.Vector3() },
          uBodyOffset: { value: new THREE.Vector3() }, uNeckPivot: { value: new THREE.Vector3(0, NeckTuning.neckPivotY, 0) },
          uBodyPivot: { value: new THREE.Vector3(0, NeckTuning.bodyPivotY, 0) }, uColorMap: { value: colorMap }, uUseMap: { value: colorMap ? 1.0 : 0.0 },
          uMouthPointsAlpha: { value: MouthRenderTuning.pointsAlpha }, uMouthPointsAlphaClip: { value: MouthRenderTuning.pointsAlphaClip },
          uMouthPointsColorMul: { value: MouthRenderTuning.pointsColorMul },
          uPointsLumaFloor: { value: MouthRenderTuning.pointsLumaFloor },
          uPointsLumaStrength: { value: MouthRenderTuning.pointsLumaStrength },
          uPointsLumaPreserveHue: { value: MouthRenderTuning.pointsLumaPreserveHue },
          uPointsLumaDebug: { value: MouthRenderTuning.pointsLumaDebug ? 1.0 : 0.0 },
          uMouthPointsCullBack: { value: MouthRenderTuning.pointsCullBack ? 1.0 : 0.0 },
          uMouthPointsDebugBackOnly: { value: MouthRenderTuning.pointsDebugBackOnly ? 1.0 : 0.0 },
        },
      });
      mouthPoints = new THREE.Points(mouthGeo, mouthPointsMaterial);
      mouthPoints.visible = MouthRenderTuning.alwaysPointsMode === true;
      mouthPoints.frustumCulled = false;
      mouthPoints.scale.copy(surfaceMesh.scale);
      mouthPoints.position.copy(surfaceMesh.position);
      scene.add(mouthPoints);
    }

    if (DEBUG_EDIT_ENABLED) {
      const panel = document.createElement('div');
      panel.style.cssText = 'position:fixed;right:8px;top:8px;z-index:50;background:rgba(0,0,0,.7);color:#fff;padding:8px;font:12px sans-serif;max-width:280px';
      panel.innerHTML = '<b>Avatar Debug</b><br/>E: mostrar/ocultar';
      document.body.appendChild(panel);
      window.addEventListener('keydown', (e) => { if (e.key.toLowerCase() === 'e') panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; });
    }
    emitRuntimeReady();
  }, undefined, (error) => {
    console.error('[avatar-runtime] Error cargando avatar', error);
    emitRuntimeError(error);
  });

  let prevElapsed = 0;
  let rafId = null;
  function tick() {
    rafId = requestAnimationFrame(tick);
    const elapsed = clock.getElapsedTime();
    const deltaRaw = prevElapsed > 0 ? Math.max(0, elapsed - prevElapsed) : 0;
    prevElapsed = elapsed;
    const dtBlink = Math.min(deltaRaw, 0.05);
    const dtMotion = Math.min(deltaRaw, 1 / 30);

    updateEyelidBlink(elapsed, dtBlink);
    updateChannel(MotionState.head, MotionConfig.head, elapsed, dtMotion);
    updateChannel(MotionState.body, MotionConfig.body, elapsed, dtMotion);

    const microYaw = Math.sin(elapsed * 2.1 + MotionState.seed) * MotionConfig.micro.yaw + Math.sin(elapsed * 3.7 + MotionState.seed * 0.3) * MotionConfig.micro.yaw * 0.45;
    const microPitch = Math.sin(elapsed * 1.8 + MotionState.seed * 0.7) * MotionConfig.micro.pitch + Math.sin(elapsed * 3.2 + MotionState.seed * 0.2) * MotionConfig.micro.pitch * 0.45;
    const microRoll = Math.sin(elapsed * 1.5 + MotionState.seed * 1.3) * MotionConfig.micro.roll + Math.sin(elapsed * 2.9 + MotionState.seed * 0.4) * MotionConfig.micro.roll * 0.45;
    const nodPitch = updateNod(elapsed, dtMotion);
    const offY = MotionConfig.bodyBob.ampPrimary * Math.sin(elapsed * MotionConfig.bodyBob.freqPrimary) + MotionConfig.bodyBob.ampSecondary * Math.sin(elapsed * MotionConfig.bodyBob.freqSecondary);
    const head = MotionState.head.current;
    const body = MotionState.body.current;
    const headRot = new THREE.Vector3(head.x + microPitch + nodPitch, head.y + microYaw, head.z + microRoll).multiplyScalar(1.35);
    const bodyRot = new THREE.Vector3(body.x + microPitch * 0.25, body.y + microYaw * 0.25, body.z + microRoll * 0.25);

    state.talkLevel = clamp01(Math.max(state.manualTalkLevel, getTalkLevelFromAnalyser()));
    const mouthTarget = clamp01(state.talkLevel);
    const mouthSpeed = mouthTarget > mouthOpenVisual ? LipsyncTuning.attack : LipsyncTuning.release;
    mouthOpenVisual += (mouthTarget - mouthOpenVisual) * (1 - Math.exp(-Math.max(0.0001, deltaRaw || 1 / 60) * mouthSpeed));
    if (!mouthPointsVisibleLatched && mouthOpenVisual >= MouthRenderTuning.pointsOn) mouthPointsVisibleLatched = true;
    if (mouthPointsVisibleLatched && mouthOpenVisual <= MouthRenderTuning.pointsOff) mouthPointsVisibleLatched = false;

    if (surfaceMaterial) {
      surfaceMaterial.uniforms.uTime.value = elapsed;
      surfaceMaterial.uniforms.uTalk.value = state.talkLevel;
      surfaceMaterial.uniforms.uHeadRot.value.copy(headRot);
      surfaceMaterial.uniforms.uBodyRot.value.copy(bodyRot);
      surfaceMaterial.uniforms.uBodyOffset.value.set(0, offY, 0);
      surfaceMaterial.uniforms.uMouthOpenVisual.value = mouthOpenVisual;
      surfaceMaterial.uniforms.uMouthHoleActive.value = (MouthRenderTuning.alwaysPointsMode || mouthPointsVisibleLatched) ? 1 : 0;
      applyEyeUniforms(surfaceMaterial);
    }
    if (mouthPointsMaterial) {
      mouthPointsMaterial.uniforms.uTime.value = elapsed;
      mouthPointsMaterial.uniforms.uTalk.value = state.talkLevel;
      mouthPointsMaterial.uniforms.uHeadRot.value.copy(headRot);
      mouthPointsMaterial.uniforms.uBodyRot.value.copy(bodyRot);
      mouthPointsMaterial.uniforms.uBodyOffset.value.set(0, offY, 0);
    }
    if (mouthPoints) mouthPoints.visible = DEBUG_MOUTH_POINTS_ENABLED || MouthRenderTuning.alwaysPointsMode || mouthPointsVisibleLatched;

    controls.update();
    renderer.render(scene, camera);
  }

  function onResize() {
    const w = window.innerWidth; const h = window.innerHeight;
    camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
  }

  window.addEventListener('resize', onResize);
  tick();


  function getCameraState() {
    return {
      position: [camera.position.x, camera.position.y, camera.position.z],
      target: [controls.target.x, controls.target.y, controls.target.z],
      fov: camera.fov,
      controlsLocked,
    };
  }

  function applyCameraState(next) {
    if (Array.isArray(next?.position) && next.position.length === 3) {
      camera.position.set(next.position[0], next.position[1], next.position[2]);
    }
    if (Array.isArray(next?.target) && next.target.length === 3) {
      controls.target.set(next.target[0], next.target[1], next.target[2]);
    }
    if (Number.isFinite(next?.fov)) {
      camera.fov = next.fov;
      camera.updateProjectionMatrix();
    }
    controls.update();
  }

  window.__avatarRuntimeDebug = {
    getCameraState,
    logCameraState() { console.info('[avatar-camera]', getCameraState()); },
    applyCameraState,
  };

  return {
    isReady() { return runtimeReady; },
    getLastError() { return runtimeError; },
    onReady(cb) {
      if (typeof cb !== 'function') return () => {};
      readyListeners.add(cb);
      if (runtimeReady) {
        try { cb(); } catch (_) {}
      }
      return () => readyListeners.delete(cb);
    },
    onError(cb) {
      if (typeof cb !== 'function') return () => {};
      errorListeners.add(cb);
      if (runtimeError) {
        try { cb(runtimeError); } catch (_) {}
      }
      return () => errorListeners.delete(cb);
    },
    setMode(mode) { state.mode = mode; if (mode !== 'SPEAKING') state.manualTalkLevel = 0; },
    setTalkLevel(level) { state.manualTalkLevel = clamp01(level); },
    connectAnalyser(analyserNode) { state.analyser = analyserNode || null; state.analyserData = analyserNode ? new Uint8Array(analyserNode.frequencyBinCount) : null; },
    getCameraState,
    applyCameraState,
    destroy() {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
      controls.dispose();
      renderer.dispose();
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      readyListeners.clear();
      errorListeners.clear();
    },
  };
}
