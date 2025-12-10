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
  // Más sensible para ver movimiento de labios␊
  minRms: 0.004,  // umbral de silencio medido con TTS
  scale: 28,      // factor para llevar RMS útil al rango 0..1
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


function cleanupAudio() {
  if (audioSource) {
    try {
      audioSource.stop();
    } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] Error al parar source', err);
    }
    try {
      audioSource.disconnect();
    } catch (err) {
      if (AudioDebug.enabled) console.warn('[audio-debug] Error al desconectar source', err);
    }
    audioSource = null;
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
        uTalkAmpTop: { value: 0.12 }, // apertura labio superior
        uTalkAmpBot: { value: 0.35 }, // apertura labio inferior
        uTalkFreq: { value: 24.0 }, // velocidad "bla bla"
        uLipDepthAmp: { value: 0.3 }, // cuánto entra hacia dentro

        // rest pose (apertura mínima constante) – alto para ver la separación
        uRestOpen: { value: 0.30 },

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
function base64ToAudioData(b64, mimeType = 'audio/wav') {
  if (typeof b64 !== 'string' || !b64.trim()) {
    throw new Error('Respuesta TTS sin audio_base64 válido');
  }

  // Normalizamos por si viniera con prefijo data: o espacios/saltos de línea
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
  // Si estaba el test de labios activo, lo apagamos
  lipTestActive = false;
  if (testLipsBtn) testLipsBtn.textContent = 'Test labios';

  cleanupAudio();

  if (!audioData?.arrayBuffer) {
    throw new Error('Audio inválido (sin buffer)');
  }

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();

  let audioBuffer;
  try {
    const bufferForDecode = audioData.arrayBuffer.slice(0);
    audioBuffer = await audioCtx.decodeAudioData(bufferForDecode);
  } catch (err) {
    console.error('[audio] No se pudo decodificar audio_base64', err);
    AvatarState.mode = 'IDLE';
    AvatarState.talkLevel = 0;
    cleanupAudio();
    throw err;
  }

  if (AudioDebug.enabled) {
  console.log('[avatar] TTS decodificado', {
    mimeType: audioData?.mimeType,
    blobSize: audioData?.blob?.size,
    duration: audioBuffer?.duration,
  });
}

  // === DESCARGAR EL AUDIO EXACTO QUE SE VA A REPRODUCIR ===
  try {
    let blob;
    if (audioData?.blob) {
      blob = audioData.blob;
    } else {
      blob = new Blob([audioData.arrayBuffer], { type: "audio/mpeg" });
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tts-output.mp3";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch (err) {
    console.warn("[audio] No se pudo descargar el audio TTS", err);
  }


  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  analyserData = new Uint8Array(analyser.frequencyBinCount);

  audioSource = audioCtx.createBufferSource();
  audioSource.buffer = audioBuffer;

  audioSource.connect(analyser);
  analyser.connect(audioCtx.destination);

  await audioCtx.resume();

  AvatarState.mode = 'SPEAKING';
  AvatarState.emotion = emotion;
  AvatarState.speechIntensity = speechIntensity;

  if (AudioDebug.enabled) {
    console.info('[audio-debug] Inicio reproducción', {
      emotion,
      speechIntensity,
      analyserFftSize: analyser.fftSize,
      minRms: AudioDebug.minRms,
      scale: AudioDebug.scale,
    });
  }

  audioSource.onended = () => {
    if (AudioDebug.enabled) {
      console.log('[avatar] TTS terminado');
    }
    AvatarState.mode = 'IDLE';
    AvatarState.speechIntensity = 1.0;
    AvatarState.talkLevel = 0;
    cleanupAudio();
  };

  if (AudioDebug.enabled) {
    console.log('[avatar] TTS playback start');
  }
  audioSource.start();
}

function getTalkLevelFromAudio() {
  // Si no hay analyser, no hay audio → cerramos boca
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

  // 1) RMS crudo del audio
  analyser.getByteTimeDomainData(analyserData);
  let sum = 0;
  for (let i = 0; i < analyserData.length; i++) {
    const v = analyserData[i] / 128 - 1; // -1..1
    sum += v * v;
  }

  const rms = Math.sqrt(sum / analyserData.length);
  const intensity = AvatarState.speechIntensity || 1.0;

  // 2) Normalizar volumen → 0..1 con minRms y scale
  const normalized = Math.min(
    1,
    Math.max(0, (rms - AudioDebug.minRms) * AudioDebug.scale),
  );
  const rawTalk = normalized * intensity; // valor “rápido” sin suavizar

  // 3) Target según modo usando NORMALIZED (no RMS directo)
  let target = 0.0;

  if (AvatarState.mode === 'SPEAKING') {
    if (normalized < 0.06) {
      // silencio / ruido muy bajo → boca cerrada
      target = 0.0;
    } else if (normalized < 0.25) {
      // susurros / consonantes suaves
      target = 0.25;
    } else if (normalized < 0.55) {
      // voz normal
      target = 0.5;
    } else if (normalized < 0.85) {
      // sílabas marcadas
      target = 0.8;
    } else {
      // picos fuertes
      target = 1.0;
    }
  } else {
    // IDLE / LISTENING / THINKING → boca cerrada
    target = 0.0;
  }

  // 4) Envelope: ataque rápido, release más lento (no vibra feo)
  const dt = 1 / 60; // aprox 60 FPS
  const speed =
    target > lipsyncLevel ? LipsyncConfig.attack : LipsyncConfig.release;
  const smoothing = 1 - Math.exp(-dt * speed);

  lipsyncLevel += (target - lipsyncLevel) * smoothing;

  // 5) Debug detallado: stats por segundo
  if (AudioDebug.enabled) {
    debugStats.frames += 1;
    debugStats.rmsSum += rms;
    debugStats.rmsMin = Math.min(debugStats.rmsMin, rms);
    debugStats.rmsMax = Math.max(debugStats.rmsMax, rms);
    debugStats.normalizedMin = Math.min(debugStats.normalizedMin, normalized);
    debugStats.normalizedMax = Math.max(debugStats.normalizedMax, normalized);
    debugStats.rawTalkMin = Math.min(debugStats.rawTalkMin, rawTalk);
    debugStats.rawTalkMax = Math.max(debugStats.rawTalkMax, rawTalk);
    debugStats.targetMin = Math.min(debugStats.targetMin, target);
    debugStats.targetMax = Math.max(debugStats.targetMax, target);

    if (rms >= AudioDebug.minRms) {
      debugStats.speakingFrames += 1;
    } else {
      debugStats.silentFrames += 1;
    }

    const now = performance.now();
    if (now - lastAudioDebugLog > AudioDebug.logIntervalMs) {
      lastAudioDebugLog = now;
      const avgRms = debugStats.frames ? debugStats.rmsSum / debugStats.frames : 0;
      console.info('[audio-debug] RMS', {
        rms: Number(rms.toFixed(4)),
        normalized: Number(normalized.toFixed(3)),
        rawTalk: Number(rawTalk.toFixed(3)),
        lipsyncLevel: Number(lipsyncLevel.toFixed(3)),
        target: Number(target.toFixed(3)),
        stats: {
          frames: debugStats.frames,
          rmsMin: Number(debugStats.rmsMin.toFixed(4)),
          rmsMax: Number(debugStats.rmsMax.toFixed(4)),
          rmsAvg: Number(avgRms.toFixed(4)),
          normalizedMin: Number(debugStats.normalizedMin.toFixed(3)),
          normalizedMax: Number(debugStats.normalizedMax.toFixed(3)),
          rawTalkMin: Number(debugStats.rawTalkMin.toFixed(3)),
          rawTalkMax: Number(debugStats.rawTalkMax.toFixed(3)),
          targetMin: Number(debugStats.targetMin.toFixed(3)),
          targetMax: Number(debugStats.targetMax.toFixed(3)),
          speakingFrames: debugStats.speakingFrames,
          silentFrames: debugStats.silentFrames,
        },
      });

      // reset stats
      debugStats.frames = 0;
      debugStats.rmsSum = 0;
      debugStats.rmsMin = Number.POSITIVE_INFINITY;
      debugStats.rmsMax = 0;
      debugStats.normalizedMin = Number.POSITIVE_INFINITY;
      debugStats.normalizedMax = 0;
      debugStats.rawTalkMin = Number.POSITIVE_INFINITY;
      debugStats.rawTalkMax = 0;
      debugStats.targetMin = Number.POSITIVE_INFINITY;
      debugStats.targetMax = 0;
      debugStats.speakingFrames = 0;
      debugStats.silentFrames = 0;
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

  return lipsyncLevel;
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

    if (lipHoldActive) {
      // Modo test: igual que el sistema antiguo
      // uTalk = 1.0 constante y el shader se encarga del bla-bla
      targetTalk = 1.0;
    } else {
      // Modo normal: nivel desde el audio
      const audioTalk = getTalkLevelFromAudio();
      targetTalk = audioTalk;
    }

    const smoothing = 1 - Math.exp(-delta * 15);
    AvatarState.talkLevel += (targetTalk - AvatarState.talkLevel) * smoothing;

    particleMaterial.uniforms.uTalk.value = AvatarState.talkLevel;

    // Un poco más abierto cuando habla o durante el test
    particleMaterial.uniforms.uRestOpen.value =
      (AvatarState.mode === 'SPEAKING' || lipHoldActive) ? 0.08 : 0.03;
  }

  // movimiento global de cabeza/cuello (más vivo y menos lineal)
  if (particlePoints) {
    const t = elapsed;

    const headYaw = Math.sin(t * 0.8) * 0.025 + Math.sin(t * 1.7) * 0.03; // izquierda-derecha
    const headPitch = Math.sin(t * 0.6 + 1.0) * 0.03 + Math.sin(t * 1.3) * 0.02; // arriba-abajo
    const headRoll = Math.sin(t * 0.45 + 2.0) * 0.03; // cabeceo lateral

    particlePoints.rotation.y = headYaw;
    particlePoints.rotation.x = headPitch;
    particlePoints.rotation.z = headRoll;

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
  (e) => {
    e.preventDefault();
    startLipTest();
  },
  { passive: false },
);

testTalkBtn.addEventListener(
  'touchend',
  (e) => {
    e.preventDefault();
    stopLipTest();
  },
  { passive: false },
);
