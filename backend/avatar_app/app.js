// app.js (avatar en Codespaces)
alert('avatar app.js cargando (Codespaces)');

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
camera.position.set(0, 1.6, 2.8);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true
});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);

// Controles de cámara
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 1.6, 0);
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

// Mapa simple visema → blendshape
const VISEME_TO_BLEND = {
  REST: null,

  AA: 'V_Open',
  E:  'V_Wide',
  I:  'V_Wide',
  O:  'V_Tight_O',
  U:  'V_Tight',

  MBP: 'Mouth_Close',
  FV:  'V_Dental_Lip',
  CH:  'V_Affricate',

  W:   'V_Lip_Open',
  EXP: 'V_Explosive'
};

let visemeTimeline = [];

let audioElement = null;
let audioCtx = null;
let audioStartTime = 0;
let isPlaying = false;

function setVisemeTimeline(timeline) {
  visemeTimeline = (timeline || []).slice().sort((a, b) => a.start - b.start);
}

function getActiveViseme(t) {
  if (!visemeTimeline || visemeTimeline.length === 0) return 'REST';
  for (let i = 0; i < visemeTimeline.length; i++) {
    const seg = visemeTimeline[i];
    if (t >= seg.start && t < seg.end) {
      return seg.viseme;
    }
  }
  return 'REST';
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

function updateLipsync() {
  if (!avatar) return;

  let audioTime = 0;
  if (audioCtx && isPlaying) {
    audioTime = audioCtx.currentTime - audioStartTime;
    if (audioTime < 0) audioTime = 0;
  }

  const activeViseme = getActiveViseme(audioTime);

  const targets = {};
  Object.values(VISEME_TO_BLEND).forEach(blendName => {
    if (!blendName) return;
    targets[blendName] = 0;
  });

  const blendForActive = VISEME_TO_BLEND[activeViseme];
  if (blendForActive) {
    targets[blendForActive] = 1;
  }

  const smoothing = 0.25;
  Object.keys(targets).forEach(blendName => {
    const target = targets[blendName];
    const current = visemeInfluences[blendName] ?? 0;
    const next = lerp(current, target, smoothing);
    visemeInfluences[blendName] = next;
    applyBlendshape(blendName, next);
  });
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

// Carga GLB + encuadre automático con Box3
const loader = new GLTFLoader();

loader.load(
  './avatar_cc4_male.glb',
  gltf => {
    console.log('GLB cargado correctamente');
    avatar = gltf.scene;
    scene.add(avatar);

    const box = new THREE.Box3().setFromObject(avatar);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();

    // Encajar modelo en cámara
    const fitDist = size / (2 * Math.tan((Math.PI * camera.fov) / 360));
    const dir = new THREE.Vector3(0, 0, 1);
    camera.position.copy(center).add(dir.multiplyScalar(fitDist));
    camera.near = size / 100;
    camera.far = size * 10;
    camera.updateProjectionMatrix();

    controls.target.copy(center);
    controls.update();

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
    { start: 0.00, end: 0.15, viseme: 'MBP' },
    { start: 0.15, end: 0.35, viseme: 'AA' },
    { start: 0.35, end: 0.55, viseme: 'E' },
    { start: 0.55, end: 0.75, viseme: 'O' },
    { start: 0.75, end: 0.95, viseme: 'U' },
    { start: 0.95, end: 1.20, viseme: 'AA' },
    { start: 1.20, end: 1.50, viseme: 'REST' }
  ];

  setVisemeTimeline(demoTimeline);

  audioCtx && audioCtx.close();
  audioCtx = null;
  isPlaying = false;
  audioElement = null;

  let t = 0;
  const duration = 1.5;

  const updateFake = () => {
    if (t > duration) return;
    const delta = 1 / 60;
    t += delta;

    const activeViseme = getActiveViseme(t);
    const targets = {};
    Object.values(VISEME_TO_BLEND).forEach(b => b && (targets[b] = 0));
    const blendForActive = VISEME_TO_BLEND[activeViseme];
    if (blendForActive) targets[blendForActive] = 1;

    const smoothing = 0.3;
    Object.keys(targets).forEach(blendName => {
      const target = targets[blendName];
      const current = visemeInfluences[blendName] ?? 0;
      const next = lerp(current, target, smoothing);
      visemeInfluences[blendName] = next;
      applyBlendshape(blendName, next);
    });

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
