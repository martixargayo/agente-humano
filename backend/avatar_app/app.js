import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ----------------------------
// ESCENA BÁSICA
// ----------------------------
const canvas = document.getElementById('c');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.01, 100);
camera.position.set(0.0116, 1.6245, 0.8421);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 1.6, 0);
controls.minDistance = 0.5;
controls.maxDistance = 4;
controls.update();

const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
fillLight.position.set(-3, 2, 1);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.2);
rimLight.position.set(0, 3, -3);
scene.add(rimLight);

scene.add(new THREE.AmbientLight(0xffffff, 0.25));

// ----------------------------
// RIG DEL AVATAR
// ----------------------------
const rig = {
  meshes: [],
  morphs: new Map(), // nombre -> { targets: [{mesh,index}] }
  bones: { head: null, neck: null, spine: null, eyes: { L: null, R: null } },
};

function mapMorphTargets(root) {
  rig.meshes.length = 0;
  rig.morphs.clear();

  root.traverse((obj) => {
    if (obj.isBone) {
      const name = obj.name.toLowerCase();
      if (name.includes('head') && !rig.bones.head) rig.bones.head = obj;
      else if (name.includes('neck') && !rig.bones.neck) rig.bones.neck = obj;
      else if ((name.includes('spine') || name.includes('chest')) && !rig.bones.spine) rig.bones.spine = obj;
      else if (name.includes('eye') && name.includes('l')) rig.bones.eyes.L = obj;
      else if (name.includes('eye') && name.includes('r')) rig.bones.eyes.R = obj;
      return;
    }

    if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
      rig.meshes.push(obj);
      const dict = obj.morphTargetDictionary;
      for (const [name, idx] of Object.entries(dict)) {
        if (!rig.morphs.has(name)) {
          rig.morphs.set(name, { targets: [] });
        }
        rig.morphs.get(name).targets.push({ mesh: obj, index: idx });
      }
    }
  });
}

function setMorph(name, value) {
  const entry = rig.morphs.get(name);
  if (!entry) return;
  for (const { mesh, index } of entry.targets) {
    mesh.morphTargetInfluences[index] = value;
  }
}

function applyMorphState(targets, smoothing = 0.25) {
  for (const [name, targetValue] of Object.entries(targets)) {
    const entry = rig.morphs.get(name);
    if (!entry) continue;
    for (const { mesh, index } of entry.targets) {
      const current = mesh.morphTargetInfluences[index] || 0;
      mesh.morphTargetInfluences[index] = current + (targetValue - current) * smoothing;
    }
  }
}

function mergeTargets(...lists) {
  const result = {};
  lists.forEach((targets) => {
    if (!targets) return;
    for (const [name, value] of Object.entries(targets)) {
      result[name] = Math.min(1, (result[name] || 0) + value);
    }
  });
  return result;
}

// ----------------------------
// CONFIG DE VISEMAS ESPECÍFICOS DE AARON
// ----------------------------
const VISEME_CONFIG = {
  AA: {
    Jaw_Open: 0.85,
    V_Open: 1.0,
    Mouth_UpperLip_Raise_L: 0.2,
    Mouth_UpperLip_Raise_R: 0.2,
    Mouth_LowerLip_Depress_L: 0.35,
    Mouth_LowerLip_Depress_R: 0.35,
    Mouth_Stretch_L: 0.15,
    Mouth_Stretch_R: 0.15,
  },
  E: {
    Jaw_Open: 0.55,
    V_Wide: 0.9,
    Mouth_Stretch_L: 0.4,
    Mouth_Stretch_R: 0.4,
    Cheek_Enhance_L: 0.2,
    Cheek_Enhance_R: 0.2,
  },
  I: {
    Jaw_Open: 0.35,
    V_Wide: 1.0,
    Mouth_Stretch_L: 0.6,
    Mouth_Stretch_R: 0.6,
    Mouth_Dimple_L: 0.3,
    Mouth_Dimple_R: 0.3,
  },
  O: {
    Jaw_Open: 0.45,
    V_Tight_O: 1.0,
    Mouth_Funnel_UL: 0.7,
    Mouth_Funnel_UR: 0.7,
    Mouth_Funnel_DL: 0.7,
    Mouth_Funnel_DR: 0.7,
    Mouth_Lips_Towards_UL: 0.25,
    Mouth_Lips_Towards_UR: 0.25,
    Mouth_Lips_Towards_DL: 0.25,
    Mouth_Lips_Towards_DR: 0.25,
  },
  U: {
    Jaw_Open: 0.3,
    V_Tight_O: 0.9,
    Mouth_Funnel_UL: 0.5,
    Mouth_Funnel_UR: 0.5,
    Mouth_Funnel_DL: 0.5,
    Mouth_Funnel_DR: 0.5,
    Mouth_Lips_Towards_UL: 0.45,
    Mouth_Lips_Towards_UR: 0.45,
    Mouth_Lips_Towards_DL: 0.45,
    Mouth_Lips_Towards_DR: 0.45,
  },
  MBP: {
    Jaw_Open: 0.05,
    V_Explosive: 0.9,
    V_Dental_Lip: 0.2,
    Mouth_Lips_Together_UL: 1.0,
    Mouth_Lips_Together_UR: 1.0,
    Mouth_Lips_Together_DL: 1.0,
    Mouth_Lips_Together_DR: 1.0,
    Mouth_Lips_Press_L: 0.8,
    Mouth_Lips_Press_R: 0.8,
  },
  FV: {
    Jaw_Open: 0.25,
    V_Dental_Lip: 1.0,
    Mouth_Lips_Towards_UL: 0.6,
    Mouth_Lips_Towards_UR: 0.6,
    Mouth_UpperLip_Raise_L: 0.25,
    Mouth_UpperLip_Raise_R: 0.25,
    Mouth_Lips_Press_L: 0.3,
    Mouth_Lips_Press_R: 0.3,
  },
  CH: {
    Jaw_Open: 0.35,
    V_Affricate: 1.0,
    Mouth_Stretch_L: 0.25,
    Mouth_Stretch_R: 0.25,
    Mouth_LowerLip_Depress_L: 0.2,
    Mouth_LowerLip_Depress_R: 0.2,
  },
  W: {
    Jaw_Open: 0.3,
    V_Lip_Open: 1.0,
    Mouth_Lips_Push_UL: 0.6,
    Mouth_Lips_Push_UR: 0.6,
    Mouth_Lips_Push_DL: 0.6,
    Mouth_Lips_Push_DR: 0.6,
  },
  REST: {
    Mouth_Lips_Press_L: 0.2,
    Mouth_Lips_Press_R: 0.2,
  },
};

const COARTICULATION_WEIGHTS = { prev: 0.2, current: 0.6, next: 0.2 };

// ----------------------------
// ESTADO GLOBAL
// ----------------------------
const AvatarState = {
  mode: 'IDLE', // IDLE | LISTENING | THINKING | SPEAKING
  emotion: 'neutral',
  speechIntensity: 1.0,
  visemeTimeline: [],
  audioStart: 0,
  audioDuration: 0,
  idleMotionEnabled: true,
};

// ----------------------------
// LIPSYNC ENGINE
// ----------------------------
const LipsyncEngine = {
  getVisemeWeights(time) {
    const tl = AvatarState.visemeTimeline;
    if (!tl.length) return { REST: 1 };

    let currentIndex = tl.findIndex((v) => time >= v.start && time < v.end);
    if (currentIndex === -1) return { REST: 1 };

    const prev = tl[currentIndex - 1];
    const current = tl[currentIndex];
    const next = tl[currentIndex + 1];

    const weights = {};
    if (prev) weights[prev.viseme] = COARTICULATION_WEIGHTS.prev;
    if (current) weights[current.viseme] = COARTICULATION_WEIGHTS.current;
    if (next) weights[next.viseme] = COARTICULATION_WEIGHTS.next;

    return weights;
  },

  buildTargets(visemeWeights, intensity = 1.0) {
    const targets = {};
    for (const [viseme, weight] of Object.entries(visemeWeights)) {
      const cfg = VISEME_CONFIG[viseme] || VISEME_CONFIG.REST;
      for (const [name, base] of Object.entries(cfg)) {
        targets[name] = (targets[name] || 0) + base * weight * intensity;
      }
    }
    Object.keys(targets).forEach((k) => {
      targets[k] = Math.min(1, targets[k]);
    });
    return targets;
  },
};

// ----------------------------
// EXPRESSION ENGINE
// ----------------------------
const EMOTIONS = {
  neutral: {},
  happy: {
    Mouth_Corner_Pull_L: 0.4,
    Mouth_Corner_Pull_R: 0.4,
    Mouth_Dimple_L: 0.25,
    Mouth_Dimple_R: 0.25,
    Cheek_Enhance_L: 0.3,
    Cheek_Enhance_R: 0.3,
    Eye_Squint_Inner_L: 0.2,
    Eye_Squint_Inner_R: 0.2,
    Brow_Raise_Outer_L: 0.2,
    Brow_Raise_Outer_R: 0.2,
  },
  sad: {
    Mouth_Corner_Depress_L: 0.4,
    Mouth_Corner_Depress_R: 0.4,
    Brow_Raise_In_L: 0.3,
    Brow_Raise_In_R: 0.3,
    Eye_Relax_L: 0.2,
    Eye_Relax_R: 0.2,
  },
  angry: {
    Brow_Down_L: 0.55,
    Brow_Down_R: 0.55,
    Mouth_Lips_Press_L: 0.35,
    Mouth_Lips_Press_R: 0.35,
    Nose_Nostril_Dilate_L: 0.3,
    Nose_Nostril_Dilate_R: 0.3,
    Eye_Squint_Inner_L: 0.25,
    Eye_Squint_Inner_R: 0.25,
    Jaw_Clench_L: 0.2,
    Jaw_Clench_R: 0.2,
  },
};

const ExpressionEngine = {
  weight: 0.3,
  targetWeight: 0.3,
  update(delta) {
    const smoothing = 1 - Math.exp(-delta * 4);
    const emotionBase = AvatarState.emotion === 'neutral' ? 0.6 : 1.0;
    const desired = this.targetWeight * emotionBase;
    this.weight += (desired - this.weight) * smoothing;

    const preset = EMOTIONS[AvatarState.emotion] || {};
    const targets = {};
    for (const [name, value] of Object.entries(preset)) {
      targets[name] = value * this.weight;
    }
    return targets;
  },
};

// ----------------------------
// IDLE ENGINE (parpadeo + micro movimientos)
// ----------------------------
let blinkTimer = 0;
let nextBlink = 2 + Math.random() * 3;
let blinkPhase = 0;
const idleNoise = [
  ['Eye_Squint_Inner_L', 0.05, 1.1],
  ['Eye_Squint_Inner_R', 0.05, 0.9],
  ['Brow_Raise_Outer_L', 0.04, 0.7],
  ['Mouth_Lips_Press_L', 0.05, 0.5],
  ['Mouth_Lips_Press_R', 0.05, 0.6],
];

const IdleEngine = {
  update(delta, time, mode) {
    const targets = {};

    // blink
    blinkTimer += delta;
    if (blinkTimer > nextBlink) {
      blinkTimer = 0;
      nextBlink = 2 + Math.random() * 4;
      blinkPhase = 1;
    }
    if (blinkPhase > 0) {
      blinkPhase = Math.max(0, blinkPhase - delta * 3.5);
      const v = Math.sin(Math.PI * (1 - blinkPhase));
      targets.Eye_Blink_L = v;
      targets.Eye_Blink_R = v;
    }

    // micro expressions
    if (AvatarState.idleMotionEnabled) {
      const idleFactor = mode === 'SPEAKING' ? 0.15 : 0.3;
      idleNoise.forEach(([name, amp, speed], idx) => {
        const wave = Math.sin(time * speed + idx * 1.7);
        targets[name] = Math.max(0, (0.5 + 0.5 * wave) * amp * idleFactor);
      });
    }

    return targets;
  },
};

// ----------------------------
// GAZE + HEAD CONTROLLER
// ----------------------------
const gaze = {
  current: new THREE.Vector3(0, 1.6, 2),
  target: new THREE.Vector3(0, 1.6, 2),
};

function lookAtBone(bone, target, strength = 1) {
  if (!bone) return;
  const dir = new THREE.Vector3().subVectors(target, bone.getWorldPosition(new THREE.Vector3())).normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir);
  bone.quaternion.slerp(q, strength);
}

const GazeHeadController = {
  update(delta, mode) {
    const jitter = mode === 'LISTENING' ? 0.2 : 0.5;
    if (Math.random() < delta * 0.5) {
      this.pickNewTarget(mode, jitter);
    }
    gaze.current.lerp(gaze.target, delta * 0.5);
    lookAtBone(rig.bones.eyes.L, gaze.current, 0.6);
    lookAtBone(rig.bones.eyes.R, gaze.current, 0.6);
    lookAtBone(rig.bones.head, gaze.current, 0.3);
  },

  pickNewTarget(mode, jitter) {
    const base = new THREE.Vector3(0, 1.6, 2);
    if (mode === 'LISTENING') base.set(0, 1.6, 2.5);
    gaze.target = base.add(new THREE.Vector3((Math.random() - 0.5) * jitter, (Math.random() - 0.5) * jitter, 0));
  },
};

// ----------------------------
// AUDIO + TIMELINE
// ----------------------------
let audioElement = null;
let audioCtx = null;

function setVisemeTimeline(timeline) {
  AvatarState.visemeTimeline = (timeline || []).slice().sort((a, b) => a.start - b.start);
  if (AvatarState.visemeTimeline.length) {
    const last = AvatarState.visemeTimeline[AvatarState.visemeTimeline.length - 1];
    AvatarState.audioDuration = last.end;
  }
}

export async function playAudioWithVisemes(audioUrl, timeline, { emotion = 'neutral', speechIntensity = 1.0 } = {}) {
  setVisemeTimeline(timeline);
  AvatarState.mode = 'SPEAKING';
  AvatarState.emotion = emotion;
  AvatarState.speechIntensity = speechIntensity;

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
  AvatarState.audioStart = audioCtx.currentTime;

  audioElement.onended = () => {
    AvatarState.mode = 'IDLE';
  };

  audioElement.play();
}

// ----------------------------
// CARGA DEL AVATAR
// ----------------------------
const ktx2Loader = new KTX2Loader()
  .setTranscoderPath('https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/libs/basis/')
  .detectSupport(renderer);

const loader = new GLTFLoader();
loader.setKTX2Loader(ktx2Loader);
loader.setMeshoptDecoder(MeshoptDecoder);
let avatar = null;
loader.load(
  './aaron_meshopt.glb',
  (gltf) => {
    avatar = gltf.scene;
    scene.add(avatar);
    mapMorphTargets(avatar);
  },
  undefined,
  (err) => console.error('Error cargando GLB', err),
);

// ----------------------------
// LOOP PRINCIPAL
// ----------------------------
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  const time = clock.elapsedTime;

  // actualizar mirada y huesos
  GazeHeadController.update(delta, AvatarState.mode);

  // decidir targets según modo
  let targets = {};
  if (AvatarState.mode === 'SPEAKING') {
    const t = audioCtx ? audioCtx.currentTime - AvatarState.audioStart : 0;
    const visemeWeights = LipsyncEngine.getVisemeWeights(t);
    const lipTargets = LipsyncEngine.buildTargets(visemeWeights, AvatarState.speechIntensity);
    const expressionTargets = ExpressionEngine.update(delta);
    const idleTargets = IdleEngine.update(delta, time, 'SPEAKING');
    targets = mergeTargets(lipTargets, expressionTargets, idleTargets);
  } else if (AvatarState.mode === 'LISTENING' || AvatarState.mode === 'THINKING') {
    const expressionTargets = ExpressionEngine.update(delta);
    const idleTargets = IdleEngine.update(delta, time, 'LISTENING');
    targets = mergeTargets(expressionTargets, idleTargets);
  } else {
    const idleTargets = IdleEngine.update(delta, time, 'IDLE');
    const expressionTargets = ExpressionEngine.update(delta);
    targets = mergeTargets(idleTargets, expressionTargets);
  }

  applyMorphState(targets, 0.25);

  controls.update();
  renderer.render(scene, camera);
}
animate();

// ----------------------------
// UTILIDADES / UI
// ----------------------------
function base64ToAudioUrl(b64, mimeType = 'audio/wav') {
  const byteChars = atob(b64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: mimeType });
  return URL.createObjectURL(blob);
}

const BACKEND_URL = '';
async function sendTextToAgent(message, { mode = 'negociar', withAudio = true } = {}) {
  const lastReplyEl = document.getElementById('lastReply');
  lastReplyEl.textContent = '…';
  AvatarState.mode = 'THINKING';
  try {
    const endpoint = mode === 'chat' ? '/chat' : '/negociar';
    const res = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'test_user', session_id: 'sesion_1', message }),
    });
    if (!res.ok) {
      const errText = await res.text();
      lastReplyEl.textContent = `Error agente: ${res.status} ${errText}`;
      return;
    }
    const data = await res.json();
    const replyText = data.reply || '';
    const emotion = data.emotion || 'neutral';
    const intensity = data.tone === 'excited' ? 1.25 : data.tone === 'calm' ? 0.8 : 1.0;
    lastReplyEl.textContent = replyText;
    AvatarState.emotion = emotion;
    if (!withAudio || !replyText) {
      AvatarState.mode = 'IDLE';
      return;
    }

    const ttsRes = await fetch(`${BACKEND_URL}/tts_with_visemes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: replyText }),
    });
    if (!ttsRes.ok) {
      const errText = await ttsRes.text();
      console.error('Error TTS+visemas:', errText);
      return;
    }
    const ttsData = await ttsRes.json();
    const audioUrl = base64ToAudioUrl(ttsData.audio_base64, ttsData.audio_mime_type);
    const timeline = ttsData.timeline || [];
    await playAudioWithVisemes(audioUrl, timeline, { emotion, speechIntensity: intensity });
  } catch (err) {
    console.error('Error al hablar con el backend:', err);
    lastReplyEl.textContent = 'Error de red con el backend.';
    AvatarState.mode = 'IDLE';
  } finally {
    if (AvatarState.mode !== 'SPEAKING') AvatarState.mode = 'IDLE';
  }
}

const sendToAgentBtn = document.getElementById('sendToAgentBtn');
const userTextEl = document.getElementById('userText');
const textOnlyCheckbox = document.getElementById('textOnly');
const emotionSelect = document.getElementById('emotionSelect');
const expressionSlider = document.getElementById('expressionIntensity');
const expressionValue = document.getElementById('expressionValue');
const idleMotionToggle = document.getElementById('idleMotionToggle');

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

if (emotionSelect) {
  AvatarState.emotion = emotionSelect.value || 'neutral';
  emotionSelect.addEventListener('change', (e) => {
    AvatarState.emotion = e.target.value;
  });
}

if (expressionSlider) {
  const applyIntensity = (value) => {
    const num = parseFloat(value);
    if (Number.isFinite(num)) {
      ExpressionEngine.targetWeight = num;
      if (expressionValue) expressionValue.textContent = num.toFixed(2);
    }
  };
  applyIntensity(expressionSlider.value || '0.45');
  expressionSlider.addEventListener('input', (e) => applyIntensity(e.target.value));
}

if (idleMotionToggle) {
  idleMotionToggle.addEventListener('change', (e) => {
    AvatarState.idleMotionEnabled = e.target.checked;
  });
}

userTextEl.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    sendToAgentBtn.click();
  }
});

// ----------------------------
// MICROFONO (igual que antes)
// ----------------------------
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
  micLabel.textContent = 'Grabando…';
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
  micLabel.textContent = 'Pulsa el micro y habla';
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

// Demo de labios sin audio
const demoBtn = document.getElementById('demoBtn');
if (demoBtn) {
  demoBtn.addEventListener('click', () => {
    AvatarState.mode = 'SPEAKING';
    setVisemeTimeline([
      { start: 0, end: 0.3, viseme: 'AA' },
      { start: 0.3, end: 0.6, viseme: 'E' },
      { start: 0.6, end: 0.9, viseme: 'I' },
      { start: 0.9, end: 1.2, viseme: 'O' },
      { start: 1.2, end: 1.5, viseme: 'U' },
      { start: 1.5, end: 1.8, viseme: 'MBP' },
      { start: 1.8, end: 2.1, viseme: 'FV' },
      { start: 2.1, end: 2.4, viseme: 'CH' },
      { start: 2.4, end: 2.7, viseme: 'W' },
      { start: 2.7, end: 3.0, viseme: 'REST' },
    ]);
    AvatarState.audioStart = audioCtx ? audioCtx.currentTime : 0;
    AvatarState.audioDuration = 3.0;
    setTimeout(() => (AvatarState.mode = 'IDLE'), 3200);
  });
}

window.scene = scene;
window.camera = camera;
window.rig = rig;