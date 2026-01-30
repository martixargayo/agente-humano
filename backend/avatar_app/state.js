import * as THREE from 'three';

// =========================
// URL params
// =========================
export const URL_PARAMS = new URLSearchParams(window.location.search);
export const DEBUG_EDIT_ENABLED = URL_PARAMS.get('debugEdit') === '1';

// ============================================================================
// ✅ Neck Editor state (DEBE existir antes de animate() y keydown)
//   (ahora actúa como editor general: neck/mouth/eyes)
// ============================================================================
export const NeckEditor = {
  enabled: DEBUG_EDIT_ENABLED,
  visible: DEBUG_EDIT_ENABLED,
  mode: 'neck', // 'neck' | 'mouth' | 'eyes'
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
export const AvatarState = {
  mode: 'IDLE', // IDLE | LISTENING | THINKING | SPEAKING
  emotion: 'neutral',
  talkLevel: 0,
  speechIntensity: 1.0,
  idleMotionEnabled: true,
};

export const AudioDebug = {
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
export const DebugView = { headWeight: false };

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
    console.info('[neck-editor] Modo editor ACTIVADO (?debugEdit=1). Tecla E para ocultar/mostrar. Modos: 1=Neck, 2=Mouth, 3=Eyes');
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

// =========================
// JS smoothstep (una sola vez)
// =========================
export function smoothstepJS(edge0, edge1, x) {
  const d = edge1 - edge0;
  if (Math.abs(d) < 1e-8) return x < edge0 ? 0 : 1;
  const t = Math.max(0, Math.min(1, (x - edge0) / d));
  return t * t * (3 - 2 * t);
}

// =========================
// Helpers random
// =========================
export function randRange(a, b) {
  return a + (b - a) * Math.random();
}

// =========================
// Lipsync config
// =========================
export const LipsyncConfig = {
  attack: 32,          // rapidez al subir (abrir boca)
  release: 12,         // rapidez al bajar (cerrar)
  floorSpeaking: 0.12, // mínima apertura cuando hay voz clara
};

// =========================
// Parpadeo: estado y timing
// =========================
export const BlinkState = {
  value: 0.0,         // 0=open, 1=closed
  phase: 'idle',      // idle | closing | hold | opening | gap
  t0: 0,
  next: 0,
  doDouble: false,
  doubleDone: false,
};

function scheduleNextBlink(now) {
  BlinkState.next = now + randRange(2.6, 6.2);
  BlinkState.doDouble = Math.random() < 0.16;
  BlinkState.doubleDone = false;
}

scheduleNextBlink(0);

function startBlink(now) {
  BlinkState.phase = 'closing';
  BlinkState.t0 = now;
}

export function updateBlink(now) {
  // si está idle, chequea si toca parpadear
  if (BlinkState.phase === 'idle') {
    if (now >= BlinkState.next) startBlink(now);
    BlinkState.value = 0.0;
    return BlinkState.value;
  }

  // timings súper rápidos (casi imperceptible)
  const CLOSE_S = 0.045;
  const HOLD_S = 0.018;
  const OPEN_S = 0.075;
  const GAP_S = 0.10; // si hay doble blink

  if (BlinkState.phase === 'closing') {
    const u = (now - BlinkState.t0) / CLOSE_S;
    BlinkState.value = Math.max(0, Math.min(1, u));
    if (u >= 1) {
      BlinkState.phase = 'hold';
      BlinkState.t0 = now;
      BlinkState.value = 1.0;
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'hold') {
    BlinkState.value = 1.0;
    if ((now - BlinkState.t0) >= HOLD_S) {
      BlinkState.phase = 'opening';
      BlinkState.t0 = now;
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'opening') {
    const u = (now - BlinkState.t0) / OPEN_S;
    BlinkState.value = 1.0 - Math.max(0, Math.min(1, u));
    if (u >= 1) {
      BlinkState.value = 0.0;
      if (BlinkState.doDouble && !BlinkState.doubleDone) {
        BlinkState.doubleDone = true;
        BlinkState.phase = 'gap';
        BlinkState.t0 = now;
      } else {
        BlinkState.phase = 'idle';
        scheduleNextBlink(now);
      }
    }
    return BlinkState.value;
  }

  if (BlinkState.phase === 'gap') {
    BlinkState.value = 0.0;
    if ((now - BlinkState.t0) >= GAP_S) {
      BlinkState.phase = 'closing';
      BlinkState.t0 = now;
    }
    return BlinkState.value;
  }

  BlinkState.phase = 'idle';
  BlinkState.value = 0.0;
  scheduleNextBlink(now);
  return BlinkState.value;
}

// =========================
// Movimiento humano "espontáneo" (targets + pausas)
// =========================
export const MotionConfig = {
  head: { ampYaw: 0.055, ampPitch: 0.050, ampRoll: 0.030, holdMin: 1.0, holdMax: 3.2, smooth: 10.0 },
  body: { ampYaw: 0.012, ampPitch: 0.010, ampRoll: 0.010, holdMin: 1.2, holdMax: 4.0, smooth: 6.0 },
  micro: { yaw: 0.006, pitch: 0.004, roll: 0.004 },
};

export const MotionState = {
  seed: Math.random() * 1000.0,
  head: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  body: { current: new THREE.Vector3(0, 0, 0), target: new THREE.Vector3(0, 0, 0), nextSwitch: 0 },
  nod: { active: false, t0: 0, dur: 0.32, amp: 0.012, count: 1 },
};

// === NUEVO: Focus al empezar a hablar (recoloca + hold) y speaking “más suave”
export const SpeakFocus = {
  wasSpeaking: false,
  holdUntil: 0,
  speakingBlend: 0,     // 0..1 (smooth)
  leanZ: 0,
  centerBias: 0,        // 0..1 (smooth) ✅ nuevo: para mirar al centro de forma orgánica
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

export function updateChannel(ch, cfg, t, dt) {
  if (t >= ch.nextSwitch) {
    ch.target.copy(pickTarget(cfg));
    ch.nextSwitch = t + randRange(cfg.holdMin, cfg.holdMax);
  }
  const k = 1.0 - Math.exp(-dt * cfg.smooth);
  ch.current.lerp(ch.target, k);
}

export function updateNod(t, dt) {
  // ✅ Solo inicia nods aleatorios cuando está escuchando, pero si ya empezó NO se corta aunque cambie el modo
  if (!MotionState.nod.active && AvatarState.mode === 'LISTENING') {
    const p = 0.12; // probabilidad por segundo aprox. (sutil)
    if (Math.random() < p * dt) {
      MotionState.nod.active = true;
      MotionState.nod.t0 = t;
      MotionState.nod.count = (Math.random() < 0.42) ? 2 : 1; // 1 o 2 “aja”
      MotionState.nod.dur = (MotionState.nod.count === 1)
        ? randRange(0.32, 0.48)
        : randRange(0.62, 0.92);
      MotionState.nod.amp = randRange(0.010, 0.014);
    }
  }

  if (!MotionState.nod.active) return 0.0;

  const u = (t - MotionState.nod.t0) / MotionState.nod.dur;
  if (u >= 1.0) {
    MotionState.nod.active = false;
    return 0.0;
  }

  // 1 o 2 nods: pulsos de media-seno, con el segundo más suave y con fade-out final
  const n = Math.max(1, MotionState.nod.count | 0);
  const segU = u * n;
  const idx = Math.min(n - 1, Math.floor(segU));
  const localU = segU - idx;

  const ampSeg = MotionState.nod.amp * (idx === 0 ? 1.0 : 0.65); // segundo nod más pequeño
  const pulse = -ampSeg * Math.sin(localU * Math.PI);

  // envelope suave (entra y sale imperceptible)
  const envIn = smoothstepJS(0.0, 0.14, u);
  const envOut = 1.0 - smoothstepJS(0.72, 1.0, u);

  return pulse * envIn * envOut;
}

export function onSpeakStart(now) {
  // ✅ Recolocar mirando al centro, pero ORGÁNICO: no forzamos target=0 (solo marcamos el hold)
  const hold = randRange(2.0, 3.0);
  SpeakFocus.holdUntil = now + hold;

  console.info('[speak-focus] start', { holdSec: hold.toFixed(2) });
}

export function onSpeakEnd() {
  console.info('[speak-focus] end');
}
