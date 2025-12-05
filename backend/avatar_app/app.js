// app.js (avatar_app en Codespaces)
alert('app.js está cargando');

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas = document.getElementById('c');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(
  40,
  window.innerWidth / window.innerHeight,
  0.01,
  100
);
camera.position.set(
  0.011607071591255534,
  1.624524181119318,
  0.8421152437144553
);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true
});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);

// Controles de cámara
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 1.6, 0);   // punto que mira (cabeza/pecho)
controls.minDistance = 0.5;
controls.maxDistance = 4;
controls.update();

// expos para consola
window.controls = controls;
window.camera = camera;
window.scene = scene;

// Luz básica
const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
fillLight.position.set(-3, 2, 1);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.2);
rimLight.position.set(0, 3, -3);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.25);
scene.add(ambient);

// --- Avatar / morph targets ---

let avatar = null;
const skinnedMeshes = [];
const morphNames = new Set();
const visemeInfluences = {}; // {blendshapeName: currentValue}

// --- Config ULTRA de visemas → conjunto de blendshapes CC ---
// Valores en 0–1 (Three.js morphTargetInfluences también usa 0–1)

const VISEME_CONFIG = {
  // Silencio / reposo
  SIL: {
    type: 'rest',
    shapes: {
      Mouth_Close: 0.20,
      Jaw_Open: 0.05,
      Mouth_Shrug_Lower: 0.05,
      Tongue_In: 0.40
    }
  },

  // Alias REST → mismo que SIL (por si en algún sitio aparece REST)
  REST: {
    type: 'rest',
    shapes: {
      Mouth_Close: 0.20,
      Jaw_Open: 0.05,
      Mouth_Shrug_Lower: 0.05,
      Tongue_In: 0.40
    }
  },

  // AA : /a/ abierta ("casa")
  AA: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.75,
      V_Open: 0.85,
      Mouth_Shrug_Lower: 0.35,
      Mouth_Down_Lower_L: 0.35,
      Mouth_Down_Lower_R: 0.35,
      Mouth_Up_Upper_L: 0.20,
      Mouth_Up_Upper_R: 0.20,
      Mouth_Stretch_L: 0.15,
      Mouth_Stretch_R: 0.15,
      Mouth_Pull_Lower_L: 0.15,
      Mouth_Pull_Lower_R: 0.15,
      Tongue_Down: 0.30
    }
  },

  // AE : /a/ algo más cerrada / /e/ abierta
  AE: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.60,
      V_Open: 0.65,
      Mouth_Shrug_Lower: 0.30,
      Mouth_Stretch_L: 0.45,
      Mouth_Stretch_R: 0.45,
      Mouth_Smile_L: 0.10,
      Mouth_Smile_R: 0.10,
      Mouth_Pull_Upper_L: 0.20,
      Mouth_Pull_Upper_R: 0.20,
      Mouth_Pull_Lower_L: 0.20,
      Mouth_Pull_Lower_R: 0.20,
      Tongue_Mid_Up: 0.20
    }
  },

  // EE : /e/ / i/ muy sonriente
  EE: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.25,
      V_Wide: 0.85,
      Mouth_Stretch_L: 0.80,
      Mouth_Stretch_R: 0.80,
      Mouth_Smile_L: 0.20,
      Mouth_Smile_R: 0.20,
      Mouth_Tighten_L: 0.30,
      Mouth_Tighten_R: 0.30,
      Mouth_Pull_Upper_L: 0.30,
      Mouth_Pull_Upper_R: 0.30,
      Tongue_Mid_Up: 0.15
    }
  },

  // IH : /i/ más relajada
  IH: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.18,
      V_Wide: 0.55,
      Mouth_Stretch_L: 0.50,
      Mouth_Stretch_R: 0.50,
      Mouth_Smile_L: 0.15,
      Mouth_Smile_R: 0.15,
      Mouth_Tighten_L: 0.25,
      Mouth_Tighten_R: 0.25,
      Mouth_Pull_Upper_L: 0.20,
      Mouth_Pull_Upper_R: 0.20
    }
  },

  // OH : /o/ media
  OH: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.40,
      V_Tight_O: 0.80,
      Mouth_Funnel_Up_L: 0.75,
      Mouth_Funnel_Up_R: 0.75,
      Mouth_Funnel_Down_L: 0.60,
      Mouth_Funnel_Down_R: 0.60,
      Mouth_Pucker_Up_L: 0.35,
      Mouth_Pucker_Up_R: 0.35,
      Mouth_Pucker_Down_L: 0.25,
      Mouth_Pucker_Down_R: 0.25,
      Mouth_Shrug_Lower: 0.15
    }
  },

  // OO : /u/ / "oo"
  OO: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.18,
      V_Tight: 0.60,
      Mouth_Pucker_Up_L: 0.90,
      Mouth_Pucker_Up_R: 0.90,
      Mouth_Pucker_Down_L: 0.80,
      Mouth_Pucker_Down_R: 0.80,
      Mouth_Funnel_Up_L: 0.40,
      Mouth_Funnel_Up_R: 0.40,
      Mouth_Funnel_Down_L: 0.35,
      Mouth_Funnel_Down_R: 0.35,
      Mouth_Push_Upper_L: 0.55,
      Mouth_Push_Upper_R: 0.55,
      Mouth_Push_Lower_L: 0.55,
      Mouth_Push_Lower_R: 0.55
    }
  },

  // MBP : bilabiales (m, b, p)
  MBP: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.0,
      Mouth_Close: 1.0,
      V_Explosive: 0.90,
      Mouth_Press_L: 0.70,
      Mouth_Press_R: 0.70,
      Mouth_Tighten_L: 0.50,
      Mouth_Tighten_R: 0.50,
      Mouth_Chin_Up: 0.30
    }
  },

  // FV : labiodentales (f, v)
  FV: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.12,
      V_Dental_Lip: 0.90,
      Mouth_Lower_L: 0.70,
      Mouth_Lower_R: 0.70,
      Mouth_Down_Lower_L: 0.60,
      Mouth_Down_Lower_R: 0.60,
      Mouth_Press_L: 0.40,
      Mouth_Press_R: 0.40,
      Mouth_Pull_Lower_L: 0.45,
      Mouth_Pull_Lower_R: 0.45,
      Mouth_Tighten_L: 0.35,
      Mouth_Tighten_R: 0.35
    }
  },

  // TH : lengua entre dientes (θ, ð)
  TH: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.18,
      V_Open: 0.25,
      Mouth_Shrug_Lower: 0.25,
      Mouth_Down_Lower_L: 0.35,
      Mouth_Down_Lower_R: 0.35,
      Tongue_Tip_Up: 0.60,
      Tongue_Out: 0.65,
      Tongue_Extend: 0.50,
      Tongue_Narrow: 0.40
    }
  },

  // L : lateral /L/
  L: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.22,
      V_Lip_Open: 0.30,
      Mouth_Shrug_Lower: 0.25,
      Tongue_Tip_Up: 0.75,
      Tongue_Mid_Up: 0.60,
      Tongue_Extend: 0.25,
      Tongue_Wide: 0.35
    }
  },

  // S : sibilantes / consonantes "planas"
  S: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.12,
      V_Wide: 0.40,
      Mouth_Stretch_L: 0.55,
      Mouth_Stretch_R: 0.55,
      Mouth_Tighten_L: 0.45,
      Mouth_Tighten_R: 0.45,
      Mouth_Pull_Upper_L: 0.30,
      Mouth_Pull_Upper_R: 0.30,
      Tongue_Tip_Up: 0.40,
      Tongue_Narrow: 0.45
    }
  },

  // CH : africadas / post-alveolares
  CH: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.22,
      V_Affricate: 0.80,
      Mouth_Funnel_Up_L: 0.40,
      Mouth_Funnel_Up_R: 0.40,
      Mouth_Funnel_Down_L: 0.35,
      Mouth_Funnel_Down_R: 0.35,
      Mouth_Pucker_Up_L: 0.30,
      Mouth_Pucker_Up_R: 0.30,
      Mouth_Tighten_L: 0.35,
      Mouth_Tighten_R: 0.35,
      Tongue_Mid_Up: 0.35
    }
  },

  // KG : velares (/k/, /g/, /x/)
  KG: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.18,
      V_Open: 0.15,
      Mouth_Shrug_Lower: 0.15,
      Tongue_Roll: 0.70,
      Tongue_Mid_Up: 0.30,
      Tongue_Tip_Down: 0.25
    }
  },

  // R : róticas (r, ɾ)
  R: {
    type: 'consonant',
    shapes: {
      Jaw_Open: 0.15,
      V_Tight: 0.35,
      Mouth_Pucker_Up_L: 0.40,
      Mouth_Pucker_Up_R: 0.40,
      Mouth_Pucker_Down_L: 0.35,
      Mouth_Pucker_Down_R: 0.35,
      Mouth_Stretch_L: 0.25,
      Mouth_Stretch_R: 0.25,
      Mouth_Tighten_L: 0.35,
      Mouth_Tighten_R: 0.35,
      Tongue_Tip_Up: 0.50,
      Tongue_Mid_Up: 0.40,
      Tongue_Narrow: 0.35
    }
  }
};

// Lista de todos los blendshapes que usamos para visemas
const ALL_VISEME_SHAPES = Array.from(
  new Set(
    Object.values(VISEME_CONFIG)
      .flatMap(cfg => Object.keys(cfg.shapes || {}))
  )
);

let visemeTimeline = [];

let audioElement = null;
let audioCtx = null;
let audioStartTime = 0;
let isPlaying = false;

function setVisemeTimeline(timeline) {
  visemeTimeline = (timeline || []).slice().sort((a, b) => a.start - b.start);
}

// --- COARTICULACIÓN ---

const COARTICULATION_WEIGHTS = {
  prev: 0.2,
  current: 0.6,
  next: 0.2
};

function getVisemeBlendAtTime(t) {
  if (!visemeTimeline || visemeTimeline.length === 0) {
    return { SIL: 1.0 };
  }

  let currentIndex = -1;

  for (let i = 0; i < visemeTimeline.length; i++) {
    const seg = visemeTimeline[i];
    if (t >= seg.start && t < seg.end) {
      currentIndex = i;
      break;
    }
  }

  if (currentIndex === -1) {
    return { SIL: 1.0 };
  }

  const result = {};
  const add = (viseme, w) => {
    if (!viseme || w <= 0) return;
    if (!VISEME_CONFIG[viseme]) return;
    result[viseme] = (result[viseme] || 0) + w;
  };

  const segPrev = visemeTimeline[currentIndex - 1];
  const segCurr = visemeTimeline[currentIndex];
  const segNext = visemeTimeline[currentIndex + 1];

  add(segPrev?.viseme, COARTICULATION_WEIGHTS.prev);
  add(segCurr?.viseme, COARTICULATION_WEIGHTS.current);
  add(segNext?.viseme, COARTICULATION_WEIGHTS.next);

  const sum = Object.values(result).reduce((a, b) => a + b, 0);

  if (!sum) {
    return { SIL: 1.0 };
  }

  for (const k of Object.keys(result)) {
    result[k] /= sum;
  }

  return result;
}

// Helpers generales lipsync

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function applyBlendshape(blendName, value) {
  skinnedMeshes.forEach(mesh => {
    if (!mesh.morphTargetDictionary) return;
    const idx = mesh.morphTargetDictionary[blendName];
    if (idx !== undefined) {
      mesh.morphTargetInfluences[idx] = value;
    }
  });
}

const MAX_INFLUENCE = 0.9;

function computeTargetsFromVisemeWeights(visemeWeights) {
  const targets = {};
  ALL_VISEME_SHAPES.forEach(name => {
    targets[name] = 0;
  });

  for (const [visemeName, weight] of Object.entries(visemeWeights)) {
    const cfg = VISEME_CONFIG[visemeName] || VISEME_CONFIG.SIL;
    if (!cfg || !cfg.shapes) continue;

    for (const [shapeName, value] of Object.entries(cfg.shapes)) {
      targets[shapeName] += value * weight;
    }
  }

  if (targets.Jaw_Open !== undefined) {
    targets.Jaw_Open *= 0.95;
  }

  return targets;
}

function applyTargets(targets, smoothing) {
  Object.keys(targets).forEach(blendName => {
    let target = targets[blendName];
    if (target > MAX_INFLUENCE) target = MAX_INFLUENCE;
    if (target < 0) target = 0;

    const current = visemeInfluences[blendName] ?? 0;
    const next = lerp(current, target, smoothing);
    visemeInfluences[blendName] = next;
    applyBlendshape(blendName, next);
  });
}

// --- LIPSYNC PRINCIPAL (audio real) ---

function updateLipsync() {
  if (!avatar) return;

  let audioTime = 0;
  if (audioCtx && isPlaying) {
    audioTime = audioCtx.currentTime - audioStartTime;
    if (audioTime < 0) audioTime = 0;
  }

  const visemeWeights = getVisemeBlendAtTime(audioTime);
  const targets = computeTargetsFromVisemeWeights(visemeWeights);

  const SMOOTHING = 0.22;
  applyTargets(targets, SMOOTHING);
}

// Parpadeo
let blinkTimer = 0;
let nextBlinkTime = 2 + Math.random() * 4;
let blinking = false;
let blinkProgress = 0;

function updateBlink(delta) {
  blinkTimer += delta;

  if (!blinking && blinkTimer >= nextBlinkTime) {
    blinking = true;
    blinkTimer = 0;
    nextBlinkTime = 2 + Math.random() * 4;
  }

  if (blinking) {
    blinkProgress += delta * 8;
    let v = 0;
    if (blinkProgress <= 0.5) v = blinkProgress * 2;
    else if (blinkProgress <= 1.0) v = (1.0 - blinkProgress) * 2;
    else {
      blinking = false;
      blinkProgress = 0;
      v = 0;
    }

    const leftBlink = 'Eye_Blink_L';
    const rightBlink = 'Eye_Blink_R';

    [leftBlink, rightBlink].forEach(blendName => {
      if (!blendName) return;
      visemeInfluences[blendName] = v;
      applyBlendshape(blendName, v);
    });
  }
}

const loader = new GLTFLoader();

loader.load(
  './avatar_cc4_male.glb',
  gltf => {
    console.log('GLB cargado correctamente');
    avatar = gltf.scene;
    scene.add(avatar);

    const box = new THREE.Box3().setFromObject(avatar);
    const center = box.getCenter(new THREE.Vector3());
    console.log('Centro del avatar:', center);

    avatar.traverse(obj => {
      if (obj.isMesh && obj.morphTargetDictionary) {
        skinnedMeshes.push(obj);
        const dict = obj.morphTargetDictionary;
        for (const name in dict) {
          morphNames.add(name);
        }
      }
    });

    console.log('Blendshapes detectados:', Array.from(morphNames));
  },
  undefined,
  err => {
    console.error('Error cargando GLB:', err);
  }
);

export async function playAudioWithVisemes(audioUrl, timeline) {
  setVisemeTimeline(timeline);

  if (audioCtx) {
    audioCtx.close();
    audioCtx = null;
  }

  audioElement = new Audio(audioUrl);
  audioElement.crossOrigin = 'anonymous';

  audioCtx = new AudioContext();
  const source = audioCtx.createMediaElementSource(audioElement);
  source.connect(audioCtx.destination);

  await audioCtx.resume();
  audioStartTime = audioCtx.currentTime;
  isPlaying = true;

  audioElement.onended = () => {
    isPlaying = false;
  };

  audioElement.play();
}

// Demo sin audio real
function playFakeDemoTimeline() {
  const demoTimeline = [
    { start: 0.00, end: 0.08, viseme: 'CH' },
    { start: 0.08, end: 0.24, viseme: 'OH' },
    { start: 0.24, end: 0.36, viseme: 'EE' },
    { start: 0.36, end: 0.56, viseme: 'AA' },

    { start: 0.56, end: 0.64, viseme: 'SIL' },

    { start: 0.64, end: 0.80, viseme: 'EE' },
    { start: 0.80, end: 1.00, viseme: 'OH' },
    { start: 1.00, end: 1.20, viseme: 'IH' },

    { start: 1.20, end: 1.28, viseme: 'SIL' },

    { start: 1.28, end: 1.44, viseme: 'MBP' },
    { start: 1.44, end: 1.64, viseme: 'AA' },
    { start: 1.64, end: 1.84, viseme: 'EE' },
    { start: 1.84, end: 2.04, viseme: 'EE' },

    { start: 2.04, end: 2.12, viseme: 'SIL' },

    { start: 2.12, end: 2.28, viseme: 'EE' },
    { start: 2.28, end: 2.44, viseme: 'AA' },
    { start: 2.44, end: 2.64, viseme: 'EE' },
    { start: 2.64, end: 2.86, viseme: 'OH' },

    { start: 2.86, end: 2.94, viseme: 'SIL' },

    { start: 2.94, end: 3.08, viseme: 'EE' },
    { start: 3.08, end: 3.28, viseme: 'OH' },
    { start: 3.28, end: 3.44, viseme: 'EE' },
    { start: 3.44, end: 3.64, viseme: 'EE' },
    { start: 3.64, end: 3.88, viseme: 'EE' },

    { start: 3.88, end: 4.20, viseme: 'SIL' }
  ];

  setVisemeTimeline(demoTimeline);

  audioCtx && audioCtx.close();
  audioCtx = null;
  isPlaying = false;
  audioElement = null;

  let t = 0;
  const duration = 4.2;

  const updateFake = () => {
    if (t > duration) return;
    const delta = 1 / 60;
    t += delta;

    const visemeWeights = getVisemeBlendAtTime(t);
    const targets = computeTargetsFromVisemeWeights(visemeWeights);

    const DEMO_SMOOTHING = 0.3;
    applyTargets(targets, DEMO_SMOOTHING);

    requestAnimationFrame(updateFake);
  };

  updateFake();
}

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();

  updateLipsync();
  updateBlink(delta);

  controls.update();
  renderer.render(scene, camera);
}

animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

document.getElementById('demoBtn').addEventListener('click', () => {
  playFakeDemoTimeline();
});

// ============================
// INTEGRACIÓN CON EL BACKEND
// ============================

// Misma máquina / mismo origen
const BACKEND_URL = ""; // → fetch('/chat'), '/negociar', '/tts_with_visemes'

function base64ToAudioUrl(b64, mimeType = 'audio/wav') {
  const byteChars = atob(b64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: mimeType });
  return URL.createObjectURL(blob);
}

async function sendTextToAgent(message, { mode = 'negociar', withAudio = true } = {}) {
  const lastReplyEl = document.getElementById('lastReply');
  lastReplyEl.textContent = '…';

  try {
    const endpoint = mode === 'chat' ? '/chat' : '/negociar';

    // 1) Llamada al agente (texto)
    const res = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 'test_user',
        session_id: 'sesion_1',
        message
      })
    });

    if (!res.ok) {
      const errText = await res.text();
      lastReplyEl.textContent = `Error agente: ${res.status} ${errText}`;
      return;
    }

    const data = await res.json();
    const replyText = data.reply || '';

    lastReplyEl.textContent = replyText;

    if (!withAudio || !replyText) {
      return; // Solo texto
    }

    // 2) TTS + visemas
    const ttsRes = await fetch(`${BACKEND_URL}/tts_with_visemes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: replyText })
    });

    if (!ttsRes.ok) {
      const errText = await ttsRes.text();
      console.error('Error TTS+visemas:', errText);
      return;
    }

    const ttsData = await ttsRes.json();
    const audioUrl = base64ToAudioUrl(ttsData.audio_base64, ttsData.audio_mime_type);
    const timeline = ttsData.timeline || [];

    await playAudioWithVisemes(audioUrl, timeline);
  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    lastReplyEl.textContent = 'Error de red con el backend.';
  }
}

// Hook del botón "Enviar al agente"
const sendToAgentBtn = document.getElementById('sendToAgentBtn');
const userTextEl = document.getElementById('userText');
const textOnlyCheckbox = document.getElementById('textOnly');

sendToAgentBtn.addEventListener('click', async () => {
  const text = (userTextEl.value || '').trim();
  if (!text) return;

  const modeRadio = document.querySelector('input[name="agentMode"]:checked');
  const mode = modeRadio ? modeRadio.value : 'negociar';
  const withAudio = !textOnlyCheckbox.checked;

  sendToAgentBtn.disabled = true;
  sendToAgentBtn.textContent = 'Hablando...';

  try {
    await sendTextToAgent(text, { mode, withAudio });
  } finally {
    sendToAgentBtn.disabled = false;
    sendToAgentBtn.textContent = 'Enviar al agente';
  }
});

// Permitir Enter+Ctrl como atajo opcional
userTextEl.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    sendToAgentBtn.click();
  }
});

// ============================
// GOOGLE STT (MICRÓFONO)
// ============================

const micBtn = document.getElementById('micBtn');
const waveCanvas = document.getElementById('waveCanvas');
const micLabel = document.getElementById('micLabel');

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioStream = null;

// Para las ondas
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

    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
    x += sliceWidth;
  }

  ctx.lineTo(width, height / 2);
  ctx.stroke();
}

async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Tu navegador no permite usar el micrófono.');
    return;
  }

  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // MediaRecorder para capturar audio en webm/opus
    mediaRecorder = new MediaRecorder(audioStream, {
      mimeType: 'audio/webm;codecs=opus'
    });

    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = async () => {
      // Parar ondas
      if (waveAnimationId) cancelAnimationFrame(waveAnimationId);
      waveAnimationId = null;

      if (waveAudioCtx) {
        waveAudioCtx.close();
        waveAudioCtx = null;
      }

      if (audioStream) {
        audioStream.getTracks().forEach(t => t.stop());
        audioStream = null;
      }

      micBtn.textContent = '🎤 Hablar';
      micLabel.textContent = 'Procesando audio...';

      const blob = new Blob(audioChunks, { type: 'audio/webm' });

      try {
        const text = await sendAudioToGoogleSTT(blob);
        if (!text) {
          micLabel.textContent = 'No se ha entendido el audio';
          return;
        }

        // Volcamos el texto al textarea
        userTextEl.value = text;
        micLabel.textContent = 'Texto reconocido, enviando al agente...';

        const modeRadio = document.querySelector('input[name="agentMode"]:checked');
        const mode = modeRadio ? modeRadio.value : 'negociar';
        const withAudio = !textOnlyCheckbox.checked;

        sendToAgentBtn.disabled = true;
        sendToAgentBtn.textContent = 'Hablando...';
        try {
          await sendTextToAgent(text, { mode, withAudio });
        } finally {
          sendToAgentBtn.disabled = false;
          sendToAgentBtn.textContent = 'Enviar al agente';
          micLabel.textContent = 'Pulsa el micro y habla';
        }
      } catch (err) {
        console.error('Error en STT:', err);
        micLabel.textContent = 'Error al reconocer el audio';
      }
    };

    mediaRecorder.start();

    // Preparar ondas con Web Audio API
    waveAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = waveAudioCtx.createMediaStreamSource(audioStream);
    waveAnalyser = waveAudioCtx.createAnalyser();
    waveAnalyser.fftSize = 2048;
    const bufferLength = waveAnalyser.fftSize;
    waveDataArray = new Uint8Array(bufferLength);
    source.connect(waveAnalyser);

    drawWaveform();

    micBtn.textContent = '■ Detener';
    micLabel.textContent = 'Grabando... habla ahora';
    isRecording = true;
  } catch (err) {
    console.error('Error al iniciar grabación:', err);
    micLabel.textContent = 'No se ha podido acceder al micrófono';
  }
}

function stopRecording() {
  if (!mediaRecorder) return;
  mediaRecorder.stop();
  isRecording = false;
}

// Llamada al backend /stt_google
async function sendAudioToGoogleSTT(audioBlob) {
  const formData = new FormData();
  formData.append('file', audioBlob, 'speech.webm');

  const res = await fetch(`${BACKEND_URL}/stt_google`, {
    method: 'POST',
    body: formData
  });

  if (!res.ok) {
    const errText = await res.text();
    console.error('Error STT backend:', errText);
    throw new Error(`STT error ${res.status}`);
  }

  const data = await res.json();
  return data.text || '';
}

// Click del botón de micro
if (micBtn) {
  micBtn.addEventListener('click', () => {
    if (!isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  });
}
