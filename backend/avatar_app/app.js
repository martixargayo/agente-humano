import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

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
  minRms: 0.02,
  scale: 10,
  logIntervalMs: 1000,
};

(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('audioDebug') === '1') AudioDebug.enabled = true;
  const minRms = parseFloat(params.get('minRms'));
  if (!Number.isNaN(minRms)) AudioDebug.minRms = minRms;
  const scale = parseFloat(params.get('levelScale'));
  if (!Number.isNaN(scale)) AudioDebug.scale = scale;
  const logIntervalMs = parseFloat(params.get('logIntervalMs'));
  if (!Number.isNaN(logIntervalMs)) AudioDebug.logIntervalMs = logIntervalMs;

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

let audioElement = null;
let audioCtx = null;
let analyser = null;
let analyserData = null;
let lastAudioDebugLog = 0;
let lastMissingAnalyserLog = 0;
let silentFrameCount = 0;


function cleanupAudio() {
  if (audioElement) {
    audioElement.pause();
    audioElement.src = '';
    audioElement = null;
  }
  if (audioCtx) {
    audioCtx.close();
    audioCtx = null;
  }
  analyser = null;
  analyserData = null;
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
// =========================
const MOUTH_CENTER_Y = 0.16; // posición vertical del centro de la boca
const MOUTH_CENTER_X = -0.045; // posición horizontal del centro de la boca
const MOUTH_WIDTH = 0.18; // ancho de la región de boca
const MOUTH_HEIGHT = 0.2; // alto máximo (labios + hueco)
const MOUTH_CURVE = 0.0; // curvatura en U (0 = recto)

// =========================
// 2. Shaders de partículas
// =========================

// Vertex: movimiento tipo “campo” + respiración + boca hablando + tamaño fijo
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
uniform float uRestOpen;   // apertura mínima en reposo

// respiración
uniform float uBreathAmp;
uniform float uBreathFreq;

attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;

// boca
attribute float aMouthWeight;
attribute float aMouthSide;

varying vec2 vUv;

// --- helpers de ruido simples --- //
float hash11(float p) {
  return fract(sin(p * 127.1) * 43758.5453123);
}

float hash21(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float simpleNoise(vec3 p, float t) {
  float n1 = hash21(p.xy + t);
  float n2 = hash21(p.yz - t * 0.5);
  return (n1 + n2) * 0.5; // 0..1
}

void main() {
  vUv = aUv;

  vec3 pos = aBasePosition;
  float t = uTime;

  // 1) ONDA GLOBAL SUAVE (como “campo” de la cara)
  float globalPhase = t * 0.5;
  float swayX = sin(globalPhase + aRandom.x * 6.2831);
  float swayY = cos(globalPhase * 0.8 + aRandom.y * 6.2831);

  vec3 globalOffset = vec3(
    swayX * 0.003,
    swayY * 0.002,
    0.0
  ) * uGlobalAmp;

  // 2) MOVIMIENTO POR CLUSTERS (manchas)
  float clusterPhase = hash11(aClusterId + 10.0) * 6.2831;
  float clusterAnim = sin(t * 0.8 + clusterPhase);

  vec3 clusterDir = normalize(vec3(
    hash11(aClusterId + 1.0) - 0.5,
    hash11(aClusterId + 2.0) - 0.5,
    hash11(aClusterId + 3.0) - 0.5
  ));

  vec3 clusterOffset = clusterDir * clusterAnim * 0.004 * uClusterAmp;

  // 3) MICRO-NOISE (ligero temblor elegante)
  float n = simpleNoise(aBasePosition * 1.5, t * 0.6);
  float micro = (n - 0.5); // -0.5..+0.5

  vec3 microDir = normalize(aRandom * 2.0 - 1.0);
  vec3 microOffset = microDir * micro * 0.002 * uNoiseAmp;

  // 3.5) RESPIRACIÓN SUAVE (más peso en zona baja)
  float breathPhase = sin(uTime * uBreathFreq) * 0.5 + 0.5; // 0..1
  float heightFactor = clamp(1.0 - (aBasePosition.y + 0.3) * 2.0, 0.0, 1.0);
  float breath = breathPhase * heightFactor * uBreathAmp;
  vec3 breathOffset = vec3(0.0, breath * 0.01, breath * 0.005);

  // 4) HABLA: labios arriba/abajo + un poco hacia dentro (Z-)
  float phase = sin(uTime * uTalkFreq);
  float talkOpen = max(phase, 0.0) * uTalk; // apertura por habla (0..1)

  // apertura total = rest + habla
  float totalOpen = uRestOpen + talkOpen;
  totalOpen = clamp(totalOpen, 0.0, 1.0);

  // +1 labio superior, -1 labio inferior
  float side = aMouthSide;

  // amplitud distinta arriba/abajo
  float lipAmp = mix(uTalkAmpBot, uTalkAmpTop, step(0.0, side));

  // factor total según peso de boca y apertura
  float mouthFactor = aMouthWeight * totalOpen;

  // desplazamiento vertical
  float verticalOffset = side * lipAmp * mouthFactor;

  // pequeño desplazamiento hacia dentro (Z-)
  float depthOffset = -uLipDepthAmp * mouthFactor;

  vec3 mouthOffset = vec3(
    0.0,
    verticalOffset,
    depthOffset
  );

  // POSICIÓN FINAL
  vec3 displaced = pos
    + globalOffset
    + clusterOffset
    + microOffset
    + breathOffset
    + mouthOffset;

  vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);

  // Tamaño FIJO en pantalla (no depende de la distancia)
  gl_PointSize = uPointSize;

  gl_Position = projectionMatrix * mvPosition;
}
`;

// Fragment: disco suave + modulación por textura de color (zonas claras/oscuras)
const fragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform sampler2D uColorMap;
uniform float uUseMap; // 1.0 si hay textura, 0.0 si no

varying vec2 vUv;

void main() {
  // 1) círculo suave
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(p, p);
  if (r2 > 1.0) discard;

  float r = sqrt(r2);
  float circle = 1.0 - smoothstep(0.7, 1.0, r);

  // 2) leer color de la textura de piel (si existe)
  vec3 texColor = texture2D(uColorMap, vUv).rgb;

  // brillo 0..1
  float densityRaw = (texColor.r + texColor.g + texColor.b) / 3.0;
  // si no hay textura, usamos 1.0 (todo visible)
  float density = mix(1.0, densityRaw, uUseMap);

  // 3) mapear brillo → alpha (zonas oscuras casi desaparecen)
  float alphaMask = density;
  float alpha = circle * alphaMask;

  if (alpha < 0.02) discard;

  // 4) color final: base gris, ligeramente modulado por el brillo
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

    // Corte frontal: solo puntos con Z >= 0 (ajusta si ves la cara al revés)
    if (v.z < 0.0) continue;

    posArray.push(v.x, v.y, v.z);

    if (srcUv) {
      uv.fromBufferAttribute(srcUv, i);
      uvArray.push(uv.x, uv.y);
    } else {
      // por si no hay UV, ponemos algo por defecto
      uvArray.push(0.0, 0.0);
    }
  }

  const positions = new Float32Array(posArray);
  const uvs = new Float32Array(uvArray);
  const count = positions.length / 3;

  // Atributos extra para movimiento tipo Phantom
  const basePositions = new Float32Array(positions.length);
  basePositions.set(positions);

  const randoms = new Float32Array(count * 3);
  const clusterIds = new Float32Array(count);

  // Boca
  const mouthWeights = new Float32Array(count);
  const mouthSides = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    // random por punto
    randoms[i * 3 + 0] = Math.random();
    randoms[i * 3 + 1] = Math.random();
    randoms[i * 3 + 2] = Math.random();

    const x = positions[i * 3 + 0];
    const y = positions[i * 3 + 1];

    // clusterId simple a partir de X/Y (para mover “manchas” juntas)
    const cx = Math.floor((x + 0.4) * 10.0);
    const cy = Math.floor((y + 0.4) * 10.0);
    clusterIds[i] = cx + cy * 10.0;

    // ------- Cálculo de región de boca -------
    let dx = x - MOUTH_CENTER_X;
    let ax = Math.abs(dx);

    let weight = 0.0;
    let side = 0.0;

    if (ax <= MOUTH_WIDTH) {
      let normX = dx / MOUTH_WIDTH;
      let curveY = MOUTH_CENTER_Y - MOUTH_CURVE * normX * normX;
      let dy = y - curveY;
      let ay = Math.abs(dy);

      if (ay <= MOUTH_HEIGHT) {
        let wx = 1.0 - ax / MOUTH_WIDTH; // centro horizontal más peso
        let wy = 1.0 - ay / MOUTH_HEIGHT; // cerca de la curva, más peso
        weight = wx * wy;

        if (weight < 0.0) weight = 0.0;
        if (weight > 1.0) weight = 1.0;

        if (dy > 0.0) {
          side = 1.0; // labio superior
        } else if (dy < 0.0) {
          side = -1.0; // labio inferior
        } else {
          side = 0.0;
        }
      }
    }

    mouthWeights[i] = weight;
    mouthSides[i] = side;
  }

  const particlesGeo = new THREE.BufferGeometry();
  particlesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  particlesGeo.setAttribute('aUv', new THREE.BufferAttribute(uvs, 2));
  particlesGeo.setAttribute('aBasePosition', new THREE.BufferAttribute(basePositions, 3));
  particlesGeo.setAttribute('aRandom', new THREE.BufferAttribute(randoms, 3));
  particlesGeo.setAttribute('aClusterId', new THREE.BufferAttribute(clusterIds, 1));
  particlesGeo.setAttribute('aMouthWeight', new THREE.BufferAttribute(mouthWeights, 1));
  particlesGeo.setAttribute('aMouthSide', new THREE.BufferAttribute(mouthSides, 1));

  return particlesGeo;
}

// Tamaño de punto fijo
const POINT_SIZE = 3.5 * window.devicePixelRatio;

// =========================
// 4. Cargar GLB, fusionar capas, crear partículas
// =========================
const loader = new GLTFLoader();

let particleMaterial = null;
let particlePoints = null; // referencia global para mover la cabeza

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

    // intentar recuperar la textura de color de la cara
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

    // centrar la malla fusionada
    mergedGeom.computeBoundingBox();
    const box = mergedGeom.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    mergedGeom.translate(-center.x, -center.y, -center.z);

    // Generar partículas a partir de los vértices (solo frontal) + UV
    const particlesGeo = generateFaceParticlesFromVertices(mergedGeom);

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
        uTalkAmpTop: { value: 0.012 }, // apertura labio superior
        uTalkAmpBot: { value: 0.035 }, // apertura labio inferior
        uTalkFreq: { value: 24.0 }, // velocidad "bla bla"
        uLipDepthAmp: { value: 0.03 }, // cuánto entra hacia dentro

        // rest pose (apertura mínima constante)
        uRestOpen: { value: 0.08 },

        // respiración
        uBreathAmp: { value: 1.0 }, // cantidad de respiración
        uBreathFreq: { value: 0.6 }, // velocidad respiración (lenta)
      },
    });

    particlePoints = new THREE.Points(particlesGeo, particleMaterial);
    particlePoints.frustumCulled = false;
    scene.add(particlePoints);

    controls.target.set(0, 0.15, 0);
    controls.update();
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
});

// =========================
// 6. Utilidades de red y audio
// =========================
function base64ToAudioUrl(b64, mimeType = 'audio/wav') {
  const byteChars = atob(b64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: mimeType });
  return URL.createObjectURL(blob);
}

const BACKEND_URL = '';

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
  const audioUrl = base64ToAudioUrl(data.audio_base64, data.audio_mime_type || 'audio/wav');
  return audioUrl;
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

    const audioUrl = await requestTTS(replyText);
    await playAudioFromUrl(audioUrl, { emotion, speechIntensity: intensity });
  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    if (lastReplyEl) lastReplyEl.textContent = err.message || 'Error de red';
    AvatarState.mode = 'IDLE';
  }
}

async function playAudioFromUrl(audioUrl, { emotion = 'neutral', speechIntensity = 1.0 } = {}) {
  cleanupAudio();

  audioElement = new Audio(audioUrl);
  audioElement.crossOrigin = 'anonymous';

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaElementSource(audioElement);

  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  analyserData = new Uint8Array(analyser.frequencyBinCount);

  source.connect(analyser);
  analyser.connect(audioCtx.destination);

  await audioCtx.resume();

  AvatarState.mode = 'SPEAKING';
  AvatarState.emotion = emotion;
  AvatarState.speechIntensity = speechIntensity;

  const logPlay = () => {
    console.info('[audio-debug] Reproduciendo audio', {
      duration: audioElement?.duration,
      emotion,
      speechIntensity,
    });
  };
  audioElement.addEventListener('play', () => AudioDebug.enabled && logPlay());
  audioElement.addEventListener('playing', () => AudioDebug.enabled && logPlay());
  audioElement.onerror = (e) => {
    console.error('[audio] Error en elemento de audio', e?.message || e);
  };

  if (AudioDebug.enabled) {
    console.info('[audio-debug] Inicio reproducción', {
      emotion,
      speechIntensity,
      analyserFftSize: analyser.fftSize,
      minRms: AudioDebug.minRms,
      scale: AudioDebug.scale,
    });
  }

  audioElement.onended = () => {
    AvatarState.mode = 'IDLE';
    AvatarState.speechIntensity = 1.0;
    AvatarState.talkLevel = 0;
    cleanupAudio();
  };

  audioElement.play();
}

function getTalkLevelFromAudio() {
  // Se mide la energía RMS del waveform para detectar presencia de voz y
  // mapearla a la apertura de la boca. Así el movimiento depende sólo del
  // audio real: si llega señal suben los labios, si no, se cierran.
  if (!(AvatarState.mode === 'SPEAKING' && analyser && analyserData)) {
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
    return 0;
  }

  analyser.getByteTimeDomainData(analyserData);
  let sum = 0;
  for (let i = 0; i < analyserData.length; i++) {
    const v = analyserData[i] / 128 - 1; // -1..1
    sum += v * v;
  }

  const rms = Math.sqrt(sum / analyserData.length);
  const intensity = AvatarState.speechIntensity || 1.0;

  // Umbral mínimo para evitar ruido y escala lineal hasta 1.0.
  const normalized = Math.min(1, Math.max(0, (rms - AudioDebug.minRms) * AudioDebug.scale));
  const talk = normalized * intensity;

  if (AudioDebug.enabled) {
    const now = performance.now();
    if (now - lastAudioDebugLog > AudioDebug.logIntervalMs) {
      lastAudioDebugLog = now;
      console.info('[audio-debug] RMS', {
        rms: Number(rms.toFixed(4)),
        intensity,
        normalized: Number(normalized.toFixed(3)),
        talk: Number(talk.toFixed(3)),
        bufferSample: analyserData.slice(0, 8),
      });
    }

    if (rms < AudioDebug.minRms) {
      silentFrameCount += 1;
      if (silentFrameCount % 30 === 0) {
        console.warn('[audio-debug] Señal de audio por debajo del umbral', {
          rms: Number(rms.toFixed(4)),
          minRms: AudioDebug.minRms,
          silentFrames: silentFrameCount,
        });
      }
    } else {
      silentFrameCount = 0;
    }
  }

  return talk;
}


// =========================
// 7. Loop
// =========================
function animate() {
  requestAnimationFrame(animate);

  const elapsed = clock.getElapsedTime();
  if (particleMaterial) {
    particleMaterial.uniforms.uTime.value = elapsed;

    const targetTalk = getTalkLevelFromAudio();
    const smoothing = 1 - Math.exp(-clock.getDelta() * 15);
    AvatarState.talkLevel += (targetTalk - AvatarState.talkLevel) * smoothing;

    particleMaterial.uniforms.uTalk.value = AvatarState.talkLevel;
    particleMaterial.uniforms.uRestOpen.value = AvatarState.mode === 'SPEAKING' ? 0.07 : 0.03;
  }

  // movimiento global de cabeza/cuello (más vivo y menos lineal)
  if (particlePoints) {
    const t = elapsed;

    // combinamos varias senoidales para que no parezca péndulo perfecto
    const headYaw = Math.sin(t * 0.8) * 0.025 + Math.sin(t * 1.7) * 0.03; // izquierda-derecha

    const headPitch = Math.sin(t * 0.6 + 1.0) * 0.03 + Math.sin(t * 1.3) * 0.02; // arriba-abajo

    const headRoll = Math.sin(t * 0.45 + 2.0) * 0.03; // cabeceo lateral

    particlePoints.rotation.y = headYaw;
    particlePoints.rotation.x = headPitch;
    particlePoints.rotation.z = headRoll;

    // movimiento del cuerpo/cuello tipo “acomodo”
    if (AvatarState.idleMotionEnabled) {
      particlePoints.position.y = 0.01 * Math.sin(t * 0.9) + 0.005 * Math.sin(t * 0.37);
    }
  }

  controls.update();
  renderer.render(scene, camera);
}

animate();

// =========================
// 8. UI básica (texto → agente → TTS)
// =========================
const sendToAgentBtn = document.getElementById('sendToAgentBtn');
const userTextEl = document.getElementById('userText');
const textOnlyCheckbox = document.getElementById('textOnly');
const idleMotionToggle = document.getElementById('idleMotionToggle');

if (sendToAgentBtn) {
  sendToAgentBtn.addEventListener('click', async () => {
    const text = (userTextEl?.value || '').trim();
    if (!text) return;
    const modeRadio = document.querySelector('input[name="agentMode"]:checked');
    const mode = modeRadio ? modeRadio.value : 'negociar';
    const withAudio = !textOnlyCheckbox?.checked;
    sendToAgentBtn.disabled = true;
    sendToAgentBtn.textContent = 'Hablando...';
    try {
      await sendTextToAgent(text, { mode, withAudio });
    } finally {
      sendToAgentBtn.disabled = false;
      sendToAgentBtn.textContent = 'Enviar al agente';
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

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) return alert('getUserMedia no soportado');
  audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(audioStream);
  audioChunks = [];
  mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: 'audio/webm' });
    console.log('Audio grabado (no enviado en esta demo):', blob.size, 'bytes');
  };
  mediaRecorder.start();
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
  if (mediaRecorder && isRecording) mediaRecorder.stop();
  if (audioStream) audioStream.getTracks().forEach((t) => t.stop());
  isRecording = false;
  if (micLabel) micLabel.textContent = 'Pulsa el micro y habla';
  if (waveAudioCtx) waveAudioCtx.close();
  waveAudioCtx = null;
  cancelAnimationFrame(waveAnimationId);
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