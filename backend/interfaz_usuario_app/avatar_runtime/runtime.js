import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

function randRange(a, b) {
  return a + (b - a) * Math.random();
}

function clamp01(v) {
  return THREE.MathUtils.clamp(v, 0, 1);
}

function smoothstepJS(edge0, edge1, x) {
  if (edge0 === edge1) return x < edge0 ? 0 : 1;
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3.0 - 2.0 * t);
}

const vertexShader = /* glsl */ `
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

const fragmentShader = /* glsl */ `
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
varying vec2 vUv;
varying float vBaseZ;
varying vec2 vBaseXY;

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
  if (vBaseZ < 0.0) discard;
  vec3 texColor = texture2D(uColorMap, vUv).rgb;
  vec3 finalColor = mix(uColor, texColor, uUseMap);
  float blink = clamp(uBlink, 0.0, 1.0);
  float leftCover = blinkCover(vBaseXY, uEyeLeftMain, uEyeLeftUpper, uEyeLeftLower, blink);
  float rightCover = blinkCover(vBaseXY, uEyeRightMain, uEyeRightUpper, uEyeRightLower, blink);
  float cover = max(leftCover, rightCover) * smoothstep(0.02, 0.95, blink);
  vec3 lidColor = texture2D(uColorMap, clamp(vUv + vec2(0.0, 0.03), 0.0, 1.0)).rgb;
  finalColor = mix(finalColor, lidColor, cover);
  gl_FragColor = vec4(finalColor, 1.0);
}
`;

export function createAvatarRuntime({ stageEl, config }) {
  const canvas = document.createElement('canvas');
  canvas.id = 'avatarCanvas';
  canvas.style.position = 'absolute';
  canvas.style.inset = '0';
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.zIndex = '2';
  canvas.style.display = 'block';
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

  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2, 4, 3);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.5);
  rim.position.set(-2, 3, -2);
  scene.add(rim);
  scene.add(new THREE.AmbientLight(0xffffff, 0.2));

  const clock = new THREE.Clock();

  const state = {
    mode: 'IDLE',
    talkLevel: 0,
    manualTalkLevel: 0,
    analyser: null,
    analyserData: null,
    lipsyncLevel: 0,
  };

  const NeckTuning = {
    centerX: -0.055,
    width: 0.23,
    curve: 0.0,
    topY: 0.12,
    bottomY: 0.03,
    neckPivotY: 0.09,
    bodyPivotY: -0.05,
  };

  const MouthTuning = {
    centerY: 0.16,
    centerX: -0.045,
    width: 0.18,
    height: 0.14,
    curve: 0.0,
  };

  const EyeBlinkTuning = {
    left: {
      centerX: -0.21262084897756595,
      centerY: 0.49398826434773013,
      halfWidth: 0.06927066702311041,
      rotation: -0.07747718419813834,
      upper: { offset: 0.015333409431849491, curve: -0.01375947353731123 },
      lower: { offset: -0.012817365534143615, curve: 0.004398359546727952 },
    },
    right: {
      centerX: 0.09769628198016435,
      centerY: 0.48632749262174674,
      halfWidth: 0.07165083081892201,
      rotation: 0.05966598604243294,
      upper: { offset: 0.009755191469550624, curve: -0.013990511698837487 },
      lower: { offset: -0.018494072161187834, curve: 0.0027252480420008746 },
    },
  };

  const EyelidMotionState = {
    value: 0,
    phase: 'idle',
    timer: 0,
    duration: 0.12,
    nextBlinkAt: 2.2,
    pendingDouble: false,
    initialized: false,
  };

  const MotionConfig = {
    head: { ampYaw: 0.040, ampPitch: 0.036, ampRoll: 0.022, holdMin: 1.3, holdMax: 3.8, smooth: 8.0, rampDur: 0.32 },
    body: { ampYaw: 0.010, ampPitch: 0.008, ampRoll: 0.008, holdMin: 1.6, holdMax: 4.2, smooth: 5.0, rampDur: 0.40 },
    micro: { yaw: 0.0045, pitch: 0.0030, roll: 0.0026 },
  };

  const MotionState = {
    seed: Math.random() * 1000,
    head: { current: new THREE.Vector3(), target: new THREE.Vector3(), targetFrom: new THREE.Vector3(), targetTo: new THREE.Vector3(), nextSwitch: 0, targetT0: 0 },
    body: { current: new THREE.Vector3(), target: new THREE.Vector3(), targetFrom: new THREE.Vector3(), targetTo: new THREE.Vector3(), nextSwitch: 0, targetT0: 0 },
    nod: { active: false, t0: 0, dur: 0.32, amp: 0.012 },
  };

  const loader = new GLTFLoader();
  let material = null;
  let mesh = null;

  function nextBlinkInterval() {
    return randRange(2.0, 6.0);
  }

  function startEyelidBlink(durationSec) {
    EyelidMotionState.phase = 'closing';
    EyelidMotionState.timer = 0;
    EyelidMotionState.duration = durationSec;
    EyelidMotionState.value = 0;
  }

  function updateEyelidBlink(elapsed, delta) {
    if (!EyelidMotionState.initialized) {
      EyelidMotionState.initialized = true;
      EyelidMotionState.nextBlinkAt = elapsed + randRange(0.45, 1.35);
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
        EyelidMotionState.timer = 0;
      }
      return;
    }

    const t = clamp01(EyelidMotionState.timer / openDuration);
    EyelidMotionState.value = 1.0 - t;
    if (t >= 1.0) {
      EyelidMotionState.phase = 'idle';
      EyelidMotionState.timer = 0;
      EyelidMotionState.value = 0;
      EyelidMotionState.nextBlinkAt = elapsed + (EyelidMotionState.pendingDouble ? randRange(0.08, 0.16) : nextBlinkInterval());
      EyelidMotionState.pendingDouble = false;
    }
  }

  function pickTarget(cfg) {
    const bias = 0.65;
    const s = () => (Math.random() * 2 - 1);
    const soften = () => (Math.random() < bias ? 0.35 : 1.0) * randRange(0.4, 1.0);
    return new THREE.Vector3(s() * cfg.ampPitch * soften(), s() * cfg.ampYaw * soften(), s() * cfg.ampRoll * soften());
  }

  function updateChannel(ch, cfg, t, dt) {
    if (t >= ch.nextSwitch) {
      ch.targetFrom.copy(ch.target);
      ch.targetTo.copy(pickTarget(cfg));
      ch.targetT0 = t;
      ch.nextSwitch = t + randRange(cfg.holdMin, cfg.holdMax);
    }
    const rampDur = Math.max(0.001, cfg.rampDur || 0.001);
    const rampT = clamp01((t - ch.targetT0) / rampDur);
    const rampS = rampT * rampT * (3.0 - 2.0 * rampT);
    ch.target.copy(ch.targetFrom).lerp(ch.targetTo, rampS);
    const k = 1.0 - Math.exp(-dt * cfg.smooth);
    ch.current.lerp(ch.target, k);
  }

  function updateNod(t, dt) {
    if (!MotionState.nod.active && state.mode === 'LISTENING' && Math.random() < 0.18 * dt) {
      MotionState.nod.active = true;
      MotionState.nod.t0 = t;
      MotionState.nod.dur = randRange(0.28, 0.40);
      MotionState.nod.amp = randRange(0.010, 0.014);
    }
    if (!MotionState.nod.active) return 0;
    const u = (t - MotionState.nod.t0) / MotionState.nod.dur;
    if (u >= 1.0) {
      MotionState.nod.active = false;
      return 0;
    }
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
    const SILENCE_RMS = 0.01;
    const VOICE_RMS = 0.12;
    let target = clamp01((rms - SILENCE_RMS) / (VOICE_RMS - SILENCE_RMS));
    if (target > 0) target = 0.12 + (1.0 - 0.12) * target;
    const dt = 1 / 60;
    const speed = target > state.lipsyncLevel ? 32 : 12;
    const smoothing = 1 - Math.exp(-dt * speed);
    state.lipsyncLevel += (target - state.lipsyncLevel) * smoothing;
    return state.lipsyncLevel;
  }

  function applyEyeUniforms(mat) {
    const left = EyeBlinkTuning.left;
    const right = EyeBlinkTuning.right;
    mat.uniforms.uBlink.value = EyelidMotionState.value;
    mat.uniforms.uEyeLeftMain.value.set(left.centerX, left.centerY, Math.max(1e-4, Math.abs(left.halfWidth)), left.rotation || 0.0);
    mat.uniforms.uEyeLeftUpper.value.set(left.upper.offset, left.upper.curve, 0, 0);
    mat.uniforms.uEyeLeftLower.value.set(left.lower.offset, left.lower.curve, 0, 0);
    mat.uniforms.uEyeRightMain.value.set(right.centerX, right.centerY, Math.max(1e-4, Math.abs(right.halfWidth)), right.rotation || 0.0);
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
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      basePositions[i * 3 + 0] = x;
      basePositions[i * 3 + 1] = y;
      basePositions[i * 3 + 2] = z;
      randoms[i * 3 + 0] = Math.random();
      randoms[i * 3 + 1] = Math.random();
      randoms[i * 3 + 2] = Math.random();
      uvArray[i * 2 + 0] = uv ? uv.getX(i) : 0;
      uvArray[i * 2 + 1] = uv ? uv.getY(i) : 0;
      const y01 = (y - minY) / yRange;
      heightFromTop[i] = clamp01(1.0 - y01);
      const cx = Math.floor((x + 0.4) * 10.0);
      const cy = Math.floor((y + 0.4) * 10.0);
      clusterIds[i] = cx + cy * 10.0;

      const mwAbs = Math.max(1e-6, Math.abs(MouthTuning.width));
      const mhAbs = Math.max(1e-6, Math.abs(MouthTuning.height));
      const dx = x - MouthTuning.centerX;
      const ax = Math.abs(dx);
      let weight = 0;
      let side = 0;
      if (ax <= mwAbs) {
        const normX = dx / mwAbs;
        const curveY = MouthTuning.centerY - MouthTuning.curve * normX * normX;
        const dy = y - curveY;
        const ay = Math.abs(dy);
        if (ay <= mhAbs) {
          weight = clamp01((1.0 - ax / mwAbs) * (1.0 - ay / mhAbs));
          side = dy > 0 ? 1.0 : (dy < 0 ? -1.0 : 0);
        }
      }
      mouthWeights[i] = weight;
      mouthSides[i] = side;

      const wAbs = Math.max(1e-6, Math.abs(NeckTuning.width));
      const dxN = x - NeckTuning.centerX;
      const insideWidth = Math.abs(dxN) <= wAbs;
      const nx = clamp01((dxN / wAbs + 1) * 0.5) * 2 - 1;
      const curve = NeckTuning.curve * nx * nx;
      let yTop = insideWidth ? (NeckTuning.topY - curve) : NeckTuning.topY;
      let yBot = insideWidth ? (NeckTuning.bottomY - curve) : NeckTuning.bottomY;
      if (yTop < yBot) [yTop, yBot] = [yBot, yTop];
      headWeights[i] = y >= yTop ? 1.0 : (y <= yBot ? 0.0 : smoothstepJS(yBot, yTop, y));
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

  function loadModel() {
    loader.load(
      config.modelUrl,
      (gltf) => {
        const meshes = [];
        gltf.scene.traverse((obj) => {
          if (obj.isMesh) meshes.push(obj);
        });
        if (!meshes.length) {
          console.error('[avatar-runtime] No se encontraron mallas en GLB');
          return;
        }

        let colorMap = null;
        for (const m of meshes) {
          if (m.material && m.material.map) {
            colorMap = m.material.map;
            break;
          }
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
          console.error('[avatar-runtime] Fallo al fusionar geometrías');
          return;
        }
        mergedGeom.computeVertexNormals();
        mergedGeom.computeBoundingBox();
        const center = new THREE.Vector3();
        mergedGeom.boundingBox.getCenter(center);
        mergedGeom.translate(-center.x, -center.y, -center.z);

        const geo = generateAnimatedSurfaceGeometry(mergedGeom);
        material = new THREE.ShaderMaterial({
          vertexShader,
          fragmentShader,
          transparent: true,
          uniforms: {
            uTime: { value: 0 },
            uGlobalAmp: { value: 1.5 },
            uClusterAmp: { value: 1.5 },
            uNoiseAmp: { value: 1.6 },
            uTalk: { value: 0 },
            uTalkAmpTop: { value: 0.024 },
            uTalkAmpBot: { value: 0.075 },
            uTalkFreq: { value: 24.0 },
            uLipDepthAmp: { value: 0.1 },
            uRestOpen: { value: 0.03 },
            uBreathAmp: { value: 1.0 },
            uBreathFreq: { value: 0.6 },
            uHeadRot: { value: new THREE.Vector3() },
            uBodyRot: { value: new THREE.Vector3() },
            uBodyOffset: { value: new THREE.Vector3() },
            uNeckPivot: { value: new THREE.Vector3(0, NeckTuning.neckPivotY, 0) },
            uBodyPivot: { value: new THREE.Vector3(0, NeckTuning.bodyPivotY, 0) },
            uDissolveStart: { value: 0.9 },
            uDissolveEnd: { value: 1.0 },
            uDissolveMotionAmp: { value: 1.0 },
            uColorMap: { value: colorMap },
            uUseMap: { value: colorMap ? 1.0 : 0.0 },
            uColor: { value: new THREE.Color(0xffffff) },
            uBlink: { value: 0 },
            uEyeLeftMain: { value: new THREE.Vector4() },
            uEyeLeftUpper: { value: new THREE.Vector4() },
            uEyeLeftLower: { value: new THREE.Vector4() },
            uEyeRightMain: { value: new THREE.Vector4() },
            uEyeRightUpper: { value: new THREE.Vector4() },
            uEyeRightLower: { value: new THREE.Vector4() },
          },
        });

        mesh = new THREE.Mesh(geo, material);
        mesh.frustumCulled = false;
        mesh.scale.setScalar(config.transform.scale || 1.0);
        mesh.position.fromArray(config.transform.offset || [0, 0, 0]);
        scene.add(mesh);
      },
      undefined,
      (err) => {
        console.warn(`[avatar-runtime] No se pudo cargar GLB en ${config.modelUrl}. Debes colocar manualmente el asset en esa ruta.`, err);
      },
    );
  }

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
    const offY = 0.01 * Math.sin(elapsed * 0.9) + 0.005 * Math.sin(elapsed * 0.37);

    const head = MotionState.head.current;
    const body = MotionState.body.current;
    const headRot = new THREE.Vector3(head.x + microPitch + nodPitch, head.y + microYaw, head.z + microRoll).multiplyScalar(1.35);
    const bodyRot = new THREE.Vector3(body.x + microPitch * 0.25, body.y + microYaw * 0.25, body.z + microRoll * 0.25);

    const targetTalk = clamp01(Math.max(state.manualTalkLevel, getTalkLevelFromAnalyser()));
    state.talkLevel = targetTalk;

    if (material) {
      material.uniforms.uTime.value = elapsed;
      material.uniforms.uTalk.value = state.talkLevel;
      material.uniforms.uHeadRot.value.copy(headRot);
      material.uniforms.uBodyRot.value.copy(bodyRot);
      material.uniforms.uBodyOffset.value.set(0, offY, 0);
      applyEyeUniforms(material);
    }

    controls.update();
    renderer.render(scene, camera);
  }

  function onResize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }

  window.addEventListener('resize', onResize);
  loadModel();
  tick();

  return {
    setMode(mode) {
      state.mode = mode;
      if (mode !== 'SPEAKING') state.manualTalkLevel = 0;
    },
    setTalkLevel(level) {
      state.manualTalkLevel = clamp01(level);
    },
    connectAnalyser(analyserNode) {
      state.analyser = analyserNode || null;
      state.analyserData = analyserNode ? new Uint8Array(analyserNode.frequencyBinCount) : null;
    },
    destroy() {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
      controls.dispose();
      renderer.dispose();
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    },
  };
}
