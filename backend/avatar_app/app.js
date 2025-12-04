alert('app.js está cargando');

import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160/build/three.module.js';
import { GLTFLoader } from 'https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/controls/OrbitControls.js';

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

// --- Config ULTRA de visemas → conjunto de blendshapes ---

const VISEME_CONFIG = {
  REST: {
    type: 'rest',
    shapes: {
      Mouth_Close: 0.1,
      Jaw_Open: 0.05
    }
  },
  AA: {
    type: 'vowel',
    shapes: {
      Jaw_Open: 0.65,
      V_Open: 0.9,
      Mouth_Shrug_Lower: 0.25
    }
  },
  E: {
    type: 'vowel',
    shapes: {
      V_Wide: 0.85,
      Jaw_Open: 0.28,
      Mouth_Stretch_L: 0.7,
      Mouth_Stretch_R: 0.7,
      Mouth_Smile_L: 0.15,
      Mouth_Smile_R: 0.15
    }
  },
  I: {
    type: 'vowel',
    shapes: {
      V_Wide: 0.8,
      Jaw_Open: 0.24,
      Mouth_Stretch_L: 0.6,
      Mouth_Stretch_R: 0.6,
      Mouth_Smile_Sharp_L: 0.25,
      Mouth_Smile_Sharp_R: 0.25
    }
  },
  O: {
    type: 'vowel',
    shapes: {
      V_Tight_O: 0.9,
      Jaw_Open: 0.42,
      Mouth_Pucker_Up_L: 0.65,
      Mouth_Pucker_Up_R: 0.65,
      Mouth_Pucker_Down_L: 0.55,
      Mouth_Pucker_Down_R: 0.55
    }
  },
  U: {
    type: 'vowel',
    shapes: {
      V_Tight: 0.9,
      Jaw_Open: 0.28,
      Mouth_Pucker_Up_L: 0.55,
      Mouth_Pucker_Up_R: 0.55,
      Mouth_Pucker_Down_L: 0.45,
      Mouth_Pucker_Down_R: 0.45
    }
  },
  MBP: {
    type: 'mbp',
    shapes: {
      Mouth_Close: 1.0,
      V_Explosive: 0.6,
      Jaw_Open: 0.05
    }
  },
  MBP_PRE: {
    type: 'mbp',
    shapes: {
      Mouth_Close: 0.6,
      V_Explosive: 0.3,
      Jaw_Open: 0.08
    }
  },
  MBP_RELEASE: {
    type: 'mbp',
    shapes: {
      Mouth_Close: 0.3,
      V_Explosive: 0.2,
      Jaw_Open: 0.12
    }
  },
  FV: {
    type: 'consonant',
    shapes: {
      V_Dental_Lip: 1.0,
      Mouth_Close: 0.3,
      Jaw_Open: 0.15
    }
  },
  CH: {
    type: 'consonant',
    shapes: {
      V_Affricate: 1.0,
      Jaw_Open: 0.32,
      Mouth_Tighten_L: 0.2,
      Mouth_Tighten_R: 0.2
    }
  },
  W: {
    type: 'semiVowel',
    shapes: {
      V_Lip_Open: 0.7,
      Mouth_Pucker_Up_L: 0.4,
      Mouth_Pucker_Up_R: 0.4,
      Mouth_Pucker_Down_L: 0.4,
      Mouth_Pucker_Down_R: 0.4
    }
  },
  EXP: {
    type: 'consonant',
    shapes: {
      V_Explosive: 1.0,
      Jaw_Open: 0.2
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
    return { REST: 1.0 };
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
    return { REST: 1.0 };
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
    return { REST: 1.0 };
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
    const cfg = VISEME_CONFIG[visemeName] || VISEME_CONFIG.REST;
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
    { start: 0.08, end: 0.24, viseme: 'O' },
    { start: 0.24, end: 0.36, viseme: 'E' },
    { start: 0.36, end: 0.56, viseme: 'AA' },

    { start: 0.56, end: 0.64, viseme: 'REST' },

    { start: 0.64, end: 0.80, viseme: 'E' },
    { start: 0.80, end: 1.00, viseme: 'O' },
    { start: 1.00, end: 1.20, viseme: 'I' },

    { start: 1.20, end: 1.28, viseme: 'REST' },

    { start: 1.28, end: 1.44, viseme: 'MBP' },
    { start: 1.44, end: 1.64, viseme: 'AA' },
    { start: 1.64, end: 1.84, viseme: 'E' },
    { start: 1.84, end: 2.04, viseme: 'E' },

    { start: 2.04, end: 2.12, viseme: 'REST' },

    { start: 2.12, end: 2.28, viseme: 'E' },
    { start: 2.28, end: 2.44, viseme: 'AA' },
    { start: 2.44, end: 2.64, viseme: 'E' },
    { start: 2.64, end: 2.86, viseme: 'O' },

    { start: 2.86, end: 2.94, viseme: 'REST' },

    { start: 2.94, end: 3.08, viseme: 'E' },
    { start: 3.08, end: 3.28, viseme: 'O' },
    { start: 3.28, end: 3.44, viseme: 'E' },
    { start: 3.44, end: 3.64, viseme: 'E' },
    { start: 3.64, end: 3.88, viseme: 'E' },

    { start: 3.88, end: 4.20, viseme: 'REST' }
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

// mismo origen que FastAPI
const BACKEND_URL = ""; // rutas relativas

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
      return; // Solo texto, no TTS
    }

    // 2) TTS + visemas
    const ttsRes = await fetch(`${BACKEND_URL}/tts_with_visemes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: replyText })
    });

    if (!ttsRes.ok) {
      const errText = await ttsRes.text();
      console.error('Error TTS+visemes:', errText);
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
