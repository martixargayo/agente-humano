import * as THREE from 'three';
import { DEBUG_EDIT_ENABLED, NeckEditor, DebugView, DebugEdit, FreezePose } from './state.js';
import { camera, controls, addResizeHandler } from './scene.js';
import { scheduleRecomputeHeadWeights, scheduleRecomputeMouthWeights, scheduleRebuildBlinkCurtain, setDebugHeadWeight } from './avatarParticles.js';

// =========================
// Keybinds (igual que antes)
// =========================
window.addEventListener('keydown', (e) => {
  if (e.key === 'n' || e.key === 'N') {
    DebugView.headWeight = !DebugView.headWeight;
    setDebugHeadWeight(DebugView.headWeight);
    console.info('[debug] Debug cuello/cabeza (aHeadWeight):', DebugView.headWeight ? 'ON' : 'OFF');
  }

  if (DEBUG_EDIT_ENABLED && (e.key === 'e' || e.key === 'E')) {
    NeckEditor.visible = !NeckEditor.visible;
    setNeckEditorVisible(NeckEditor.visible);
    console.info('[neck-editor] Visible:', NeckEditor.visible ? 'ON' : 'OFF');
  }

  if (DEBUG_EDIT_ENABLED && (e.key === '1' || e.key === '2' || e.key === '3')) {
    NeckEditor.mode = (e.key === '1') ? 'neck' : (e.key === '2') ? 'mouth' : 'eyes';
    console.info('[neck-editor] Modo:', NeckEditor.mode.toUpperCase());
    updateNeckEditorInfo();
  }

  // Ajuste rápido de densidad de parpadeo
  if (DEBUG_EDIT_ENABLED && NeckEditor.mode === 'eyes') {
    if (e.key === '[') {
      window.EyeTuning.pointsPerEye = Math.max(40, (window.EyeTuning.pointsPerEye | 0) - 40);
      scheduleRebuildBlinkCurtain('eyes:points--');
    }
    if (e.key === ']') {
      window.EyeTuning.pointsPerEye = Math.min(2000, (window.EyeTuning.pointsPerEye | 0) + 40);
      scheduleRebuildBlinkCurtain('eyes:points++');
    }
  }

  // ⏸ P pausa / ▶ reanuda movimiento (solo debugEdit)
  if (DEBUG_EDIT_ENABLED && (e.key === 'p' || e.key === 'P')) {
    setFreezeMotion(!DebugEdit.freezeMotion);
  }

  // 🎥 V alterna cámara/orbit vs edición
  if (DEBUG_EDIT_ENABLED && (e.key === 'v' || e.key === 'V')) {
    setCameraMode(!DebugEdit.cameraMode);
  }
});

// =========================
// Editor overlay helpers
// =========================
function setFreezeMotion(v) {
  if (!DebugEdit.enabled) return;
  DebugEdit.freezeMotion = !!v;
  FreezePose.captured = false; // recaptura cuando haga falta
  updateNeckEditorInfo();
  console.info('[debugEdit] freezeMotion:', DebugEdit.freezeMotion ? 'ON' : 'OFF');
}

function setCameraMode(v) {
  if (!DebugEdit.enabled) return;
  DebugEdit.cameraMode = !!v;

  // Aplica el cambio al overlay/controls respetando si el editor está visible
  setNeckEditorVisible(NeckEditor.visible);

  updateNeckEditorInfo();
  console.info('[debugEdit] cameraMode:', DebugEdit.cameraMode ? 'ON' : 'OFF');
}

function setNeckEditorVisible(v) {
  if (!NeckEditor.enabled) return;
  if (!NeckEditor.overlay) initNeckEditorOverlay();

  NeckEditor.visible = !!v;

  const overlayVisible = NeckEditor.visible && !DebugEdit.cameraMode;

  NeckEditor.overlay.style.display = overlayVisible ? 'block' : 'none';
  NeckEditor.overlay.style.pointerEvents = overlayVisible ? 'auto' : 'none';

  if (NeckEditor.infoEl) NeckEditor.infoEl.style.display = NeckEditor.visible ? 'block' : 'none';

  // Controls: en debugEdit solo se activan si cameraMode ON o si editor oculto
  if (DebugEdit.enabled) {
    controls.enabled = DebugEdit.cameraMode || !NeckEditor.visible;
  }
}

function updateNeckEditorInfo() {
  if (!NeckEditor.infoEl) return;

  const mode = NeckEditor.mode;
  let handlesLine = '';
  if (mode === 'neck') {
    handlesLine = 'Handles: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>, <b>neckPivot</b>, <b>bodyPivot</b>';
  } else if (mode === 'mouth') {
    handlesLine = 'Handles: <b>center</b>, <b>top</b>, <b>bottom</b>, <b>left</b>, <b>right</b>, <b>curve</b>';
  } else {
    handlesLine = 'Handles: <b>leftCenter</b>, <b>rightCenter</b>, <b>width</b>, <b>height</b>, <b>curve</b>, <b>hide</b>, <b>z</b> &nbsp;(<b>[</b>/<b>]</b> densidad)';
  }

  // ✅ Patch 2: botones clicables
  const freezeLabel = DebugEdit.freezeMotion ? '▶ Reanudar movimiento' : '⏸ Pausar movimiento';
  const cameraLabel = DebugEdit.cameraMode ? '✏️ Editar (bloquear cámara)' : '🎥 Cámara (rotar/zoom)';

    NeckEditor.infoEl.innerHTML = `
    <div style="font-weight:700; margin-bottom:6px;">Editor (${mode.toUpperCase()})</div>

    <div style="margin-bottom:8px;">
      <button data-mode="neck"  style="margin-right:6px; padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Neck</button>
      <button data-mode="mouth" style="margin-right:6px; padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Mouth</button>
      <button data-mode="eyes"  style="padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.08); color:#fff; cursor:pointer;">Eyes</button>
    </div>

    <div style="margin-bottom:8px;">
      <button data-action="toggle-freeze" style="margin-right:6px; padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.12); color:#fff; cursor:pointer;">${freezeLabel}</button>
      <button data-action="toggle-camera" style="padding:4px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.12); color:#fff; cursor:pointer;">${cameraLabel}</button>
    </div>

    <div>Tecla <b>E</b> ocultar/mostrar. (También: <b>1</b>/<b>2</b>/<b>3</b>)</div>
    <div>Atajos: <b>P</b> pausa, <b>V</b> cámara</div>
    <div style="margin-top:6px; opacity:.92">${handlesLine}</div>
    <div style="margin-top:8px; opacity:.85">Cada cambio imprime JSON en consola.</div>
  `;
}

function initNeckEditorOverlay() {
  if (!NeckEditor.enabled || NeckEditor.overlay) return;

  const overlay = document.createElement('canvas');
  overlay.id = 'neck-editor-overlay';
  Object.assign(overlay.style, {
    position: 'fixed',
    top: '0px',
    left: '0px',
    width: '100vw',
    height: '100vh',
    zIndex: '9999',
    pointerEvents: 'auto',
  });

  document.body.appendChild(overlay);
  NeckEditor.overlay = overlay;
  NeckEditor.ctx = overlay.getContext('2d');

  const info = document.createElement('div');
  Object.assign(info.style, {
    position: 'fixed',
    top: '12px',
    left: '12px',
    zIndex: '10000',
    padding: '10px 12px',
    borderRadius: '12px',
    background: 'rgba(0,0,0,0.55)',
    color: '#fff',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    fontSize: '12px',
    lineHeight: '1.35',
    maxWidth: '420px',
    userSelect: 'none',
  });
  NeckEditor.infoEl = info;

  // ✅ Patch 2: listener botones modo
  info.addEventListener('click', (ev) => {
    const actionBtn = ev.target.closest('[data-action]');
    if (actionBtn) {
      const a = actionBtn.dataset.action;
      if (a === 'toggle-freeze') setFreezeMotion(!DebugEdit.freezeMotion);
      if (a === 'toggle-camera') setCameraMode(!DebugEdit.cameraMode);
      return;
    }

    const btn = ev.target.closest('[data-mode]');
    if (!btn) return;
    NeckEditor.mode = btn.dataset.mode;
    console.info('[neck-editor] Modo:', NeckEditor.mode.toUpperCase());
    updateNeckEditorInfo();
  });


  updateNeckEditorInfo();
  document.body.appendChild(info);

  overlay.addEventListener('mousemove', onNeckEditorMove);
  overlay.addEventListener('mousedown', onNeckEditorDown);
  window.addEventListener('mouseup', onNeckEditorUp);

  overlay.addEventListener('touchstart', onNeckEditorTouchStart, { passive: false });
  overlay.addEventListener('touchmove', onNeckEditorTouchMove, { passive: false });
  overlay.addEventListener('touchend', onNeckEditorTouchEnd, { passive: false });

  resizeNeckEditorOverlay();
  setNeckEditorVisible(true);
  // defaults en debugEdit: quieto y en modo edición (sin cámara)
  setFreezeMotion(true);
  setCameraMode(false);
}

function resizeNeckEditorOverlay() {
  if (!NeckEditor.overlay) return;
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  NeckEditor.dpr = dpr;
  NeckEditor.overlay.width = Math.floor(window.innerWidth * dpr);
  NeckEditor.overlay.height = Math.floor(window.innerHeight * dpr);
  NeckEditor.overlay.style.width = '100vw';
  NeckEditor.overlay.style.height = '100vh';
  const ctx = NeckEditor.ctx;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

addResizeHandler(resizeNeckEditorOverlay);

function getMouseNDC(clientX, clientY) {
  return {
    x: (clientX / window.innerWidth) * 2 - 1,
    y: -(clientY / window.innerHeight) * 2 + 1,
  };
}

function screenProject(x, y, z = 0) {
  const v = new THREE.Vector3(x, y, z).project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * window.innerWidth,
    y: (-v.y * 0.5 + 0.5) * window.innerHeight,
  };
}

function rayToPlane(clientX, clientY) {
  const ndc = getMouseNDC(clientX, clientY);
  NeckEditor.raycaster.setFromCamera(ndc, camera);
  const out = new THREE.Vector3();
  const hit = NeckEditor.raycaster.ray.intersectPlane(NeckEditor.plane, out);
  return hit ? out.clone() : null;
}

// -------- Handles Models (neck/mouth/eyes) --------
function getNeckHandlesModel() {
  const t = window.NeckTuning;
  const midY = (t.topY + t.bottomY) * 0.5;
  const wAbs = Math.max(1e-6, Math.abs(t.width));

  const curveX = t.centerX + wAbs;
  const curveY = t.topY - t.curve;

  return {
    center: { x: t.centerX, y: midY },
    top: { x: t.centerX, y: t.topY },
    bottom: { x: t.centerX, y: t.bottomY },
    left: { x: t.centerX - wAbs, y: midY },
    right: { x: t.centerX + wAbs, y: midY },
    curve: { x: curveX, y: curveY },
    neckPivot: { x: t.centerX, y: t.neckPivotY },
    bodyPivot: { x: t.centerX, y: t.bodyPivotY },
  };
}

function getMouthHandlesModel() {
  const m = window.MouthTuning;
  const wAbs = Math.max(1e-6, Math.abs(m.width));
  const hAbs = Math.max(1e-6, Math.abs(m.height));

  // curve handle en borde derecho (nx=1): curveY = centerY - curve
  const curveX = m.centerX + wAbs;
  const curveY = m.centerY - m.curve;

  return {
    center: { x: m.centerX, y: m.centerY },
    top: { x: m.centerX, y: m.centerY + hAbs },
    bottom: { x: m.centerX, y: m.centerY - hAbs },
    left: { x: m.centerX - wAbs, y: m.centerY },
    right: { x: m.centerX + wAbs, y: m.centerY },
    curve: { x: curveX, y: curveY },
  };
}

function getEyeHandlesModel() {
  const t = window.EyeTuning;
  const wAbs = Math.max(1e-6, Math.abs(t.width));
  const hAbs = Math.max(1e-6, Math.abs(t.height));

  // Un handle de “width/height/curve/hide/z” global, y centers por ojo
  return {
    leftCenter: { x: t.leftCenterX, y: t.centerY },
    rightCenter: { x: t.rightCenterX, y: t.centerY },

    width: { x: t.rightCenterX + wAbs, y: t.centerY },
    height: { x: t.rightCenterX, y: t.centerY + hAbs },

    curve: { x: t.rightCenterX + wAbs, y: t.centerY - t.lidCurve },
    hide: { x: t.rightCenterX, y: t.centerY + (t.hideOffsetY || 0.07) },

    z: { x: t.rightCenterX + wAbs * 0.6, y: t.centerY - hAbs * 1.6 },
  };
}

function getHandlesModel() {
  if (NeckEditor.mode === 'mouth') return getMouthHandlesModel();
  if (NeckEditor.mode === 'eyes') return getEyeHandlesModel();
  return getNeckHandlesModel();
}

function pickHandle(clientX, clientY) {
  const handles = getHandlesModel();
  let best = null;
  let bestD = Infinity;
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);
    const dx = s.x - clientX;
    const dy = s.y - clientY;
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < NeckEditor.handlesRadius && d < bestD) {
      bestD = d;
      best = key;
    }
  }
  return best;
}

// -------- Apply drags per mode --------
function applyNeckDrag(key, worldPoint, startPoint, startTuning) {
  const t = window.NeckTuning;
  const minBand = 1e-4;

  if (key === 'center') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;

    t.centerX = startTuning.centerX + dx;
    t.topY = startTuning.topY + dy;
    t.bottomY = startTuning.bottomY + dy;
    t.neckPivotY = startTuning.neckPivotY + dy;
    t.bodyPivotY = startTuning.bodyPivotY + dy;
  }

  if (key === 'top') {
    t.topY = worldPoint.y;
    if (t.topY < t.bottomY + minBand) t.topY = t.bottomY + minBand;
  }

  if (key === 'bottom') {
    t.bottomY = worldPoint.y;
    if (t.bottomY > t.topY - minBand) t.bottomY = t.topY - minBand;

    // auto-follow pivots por defecto
    t.neckPivotY = t.bottomY;
    t.bodyPivotY = t.bottomY - 0.12;
  }

  if (key === 'left') {
    const w = startTuning.centerX - worldPoint.x;
    t.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'right') {
    const w = worldPoint.x - startTuning.centerX;
    t.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'curve') {
    const newCurve = (t.topY - worldPoint.y);
    t.curve = newCurve;
  }

  if (key === 'neckPivot') {
    t.neckPivotY = worldPoint.y;
  }

  if (key === 'bodyPivot') {
    t.bodyPivotY = worldPoint.y;
  }

  scheduleRecomputeHeadWeights(`drag:${key}`);
}

function applyMouthDrag(key, worldPoint, startPoint, startTuning) {
  const m = window.MouthTuning;

  if (key === 'center') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    m.centerX = startTuning.centerX + dx;
    m.centerY = startTuning.centerY + dy;
  }

  if (key === 'left') {
    const w = startTuning.centerX - worldPoint.x;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'right') {
    const w = worldPoint.x - startTuning.centerX;
    m.width = Math.max(1e-6, Math.abs(w));
  }

  if (key === 'top') {
    m.height = Math.max(1e-6, Math.abs(worldPoint.y - m.centerY));
  }

  if (key === 'bottom') {
    m.height = Math.max(1e-6, Math.abs(m.centerY - worldPoint.y));
  }

  if (key === 'curve') {
    // curve = centerY - y_en_borde (nx=1)
    m.curve = (m.centerY - worldPoint.y);
  }

  scheduleRecomputeMouthWeights(`drag:${key}`);
}

function applyEyeDrag(key, worldPoint, startPoint, startTuning) {
  const t = window.EyeTuning;

  if (key === 'leftCenter') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    t.leftCenterX = startTuning.leftCenterX + dx;
    t.centerY = startTuning.centerY + dy;
  }

  if (key === 'rightCenter') {
    const dx = worldPoint.x - startPoint.x;
    const dy = worldPoint.y - startPoint.y;
    t.rightCenterX = startTuning.rightCenterX + dx;
    t.centerY = startTuning.centerY + dy;
  }

  if (key === 'width') {
    t.width = Math.max(1e-6, Math.abs(worldPoint.x - t.rightCenterX));
  }

  if (key === 'height') {
    t.height = Math.max(1e-6, Math.abs(worldPoint.y - t.centerY));
  }

  if (key === 'curve') {
    // lidCurve = centerY - y_at_edge (nx=1)
    t.lidCurve = (t.centerY - worldPoint.y);
  }

  if (key === 'hide') {
    t.hideOffsetY = Math.max(0.001, Math.abs(worldPoint.y - t.centerY));
  }

  if (key === 'z') {
    // z handle: usa Y para mapear z (simple y práctico)
    // cuanto más arriba el handle, más cerca (z mayor)
    const dz = (startPoint.y - worldPoint.y) * 0.05;
    t.z = Math.max(0.0, startTuning.z + dz);
  }

  scheduleRebuildBlinkCurtain(`drag:${key}`);
}

function applyDrag(key, worldPoint, startPoint, startTuning) {
  if (NeckEditor.mode === 'mouth') return applyMouthDrag(key, worldPoint, startPoint, startTuning);
  if (NeckEditor.mode === 'eyes') return applyEyeDrag(key, worldPoint, startPoint, startTuning);
  return applyNeckDrag(key, worldPoint, startPoint, startTuning);
}

function onNeckEditorDown(e) {
  if (!NeckEditor.visible) return;
  const key = pickHandle(e.clientX, e.clientY);
  if (!key) return;

  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  let startTuning = null;
  if (NeckEditor.mode === 'mouth') startTuning = { ...window.MouthTuning };
  else if (NeckEditor.mode === 'eyes') startTuning = { ...window.EyeTuning };
  else startTuning = { ...window.NeckTuning };

  NeckEditor.dragging = {
    key,
    startPoint: p,
    startTuning,
  };

  controls.enabled = true;
  e.preventDefault();
}

function onNeckEditorMove(e) {
  if (!NeckEditor.visible) return;

  if (!NeckEditor.dragging) {
    NeckEditor.hoverKey = pickHandle(e.clientX, e.clientY);
    return;
  }

  const { key, startPoint, startTuning } = NeckEditor.dragging;
  const p = rayToPlane(e.clientX, e.clientY);
  if (!p) return;

  applyDrag(key, p, startPoint, startTuning);
  e.preventDefault();
}

function onNeckEditorUp() {
  if (!NeckEditor.dragging) return;
  NeckEditor.dragging = null;
  controls.enabled = true;
}

function onNeckEditorTouchStart(e) {
  if (!NeckEditor.visible) return;
  if (!e.touches?.length) return;
  const t = e.touches[0];
  onNeckEditorDown({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onNeckEditorTouchMove(e) {
  if (!NeckEditor.visible) return;
  if (!e.touches?.length) return;
  const t = e.touches[0];
  onNeckEditorMove({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => {} });
  e.preventDefault();
}

function onNeckEditorTouchEnd(e) {
  onNeckEditorUp(e);
  e.preventDefault();
}

function drawHandle(ctx, key, color, filled, clientX, clientY) {
  const r = NeckEditor.handlesRadius;
  const isHover = NeckEditor.hoverKey === key;
  const isDrag = NeckEditor.dragging?.key === key;

  ctx.save();
  ctx.beginPath();
  ctx.arc(clientX, clientY, r, 0, Math.PI * 2);

  ctx.lineWidth = isDrag ? 3 : (isHover ? 2 : 1.5);
  ctx.strokeStyle = color;

  if (filled) {
    ctx.fillStyle = 'rgba(255,0,0,0.15)';
    ctx.fill();
  }

  ctx.stroke();
  ctx.restore();
}

export function drawNeckEditorOverlay() {
  if (!NeckEditor.enabled || !NeckEditor.visible) return;
  if (!NeckEditor.overlay) initNeckEditorOverlay();

  const ctx = NeckEditor.ctx;
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

  // ========= Draw per mode =========
  if (NeckEditor.mode === 'neck') {
    const t = window.NeckTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));

    const segments = 64;
    const x0 = t.centerX - wAbs;
    const x1 = t.centerX + wAbs;

    const topPts = [];
    const botPts = [];

    for (let i = 0; i <= segments; i++) {
      const u = i / segments;
      const x = x0 + (x1 - x0) * u;

      const dx = x - t.centerX;
      const nx = dx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const c = t.curve * nxClamped * nxClamped;

      const yTop = t.topY - c;
      const yBot = t.bottomY - c;

      topPts.push(screenProject(x, yTop, 0));
      botPts.push(screenProject(x, yBot, 0));
    }

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    const leftTop = topPts[0], leftBot = botPts[0];
    const rightTop = topPts[topPts.length - 1], rightBot = botPts[botPts.length - 1];

    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(leftTop.x, leftTop.y); ctx.lineTo(leftBot.x, leftBot.y);
    ctx.moveTo(rightTop.x, rightTop.y); ctx.lineTo(rightBot.x, rightBot.y);
    ctx.stroke();

    ctx.restore();
  }

  if (NeckEditor.mode === 'mouth') {
    const m = window.MouthTuning;
    const wAbs = Math.max(1e-6, Math.abs(m.width));
    const hAbs = Math.max(1e-6, Math.abs(m.height));

    const segments = 64;
    const x0 = m.centerX - wAbs;
    const x1 = m.centerX + wAbs;

    const topPts = [];
    const midPts = [];
    const botPts = [];

    for (let i = 0; i <= segments; i++) {
      const u = i / segments;
      const x = x0 + (x1 - x0) * u;

      const dx = x - m.centerX;
      const nx = dx / wAbs;
      const nxClamped = Math.max(-1, Math.min(1, nx));
      const c = m.curve * nxClamped * nxClamped;

      const curveY = m.centerY - c;
      topPts.push(screenProject(x, curveY + hAbs, 0));
      midPts.push(screenProject(x, curveY, 0));
      botPts.push(screenProject(x, curveY - hAbs, 0));
    }

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    // mid
    ctx.beginPath();
    ctx.moveTo(midPts[0].x, midPts[0].y);
    for (let i = 1; i < midPts.length; i++) ctx.lineTo(midPts[i].x, midPts[i].y);
    ctx.stroke();

    // top
    ctx.globalAlpha = 0.65;
    ctx.beginPath();
    ctx.moveTo(topPts[0].x, topPts[0].y);
    for (let i = 1; i < topPts.length; i++) ctx.lineTo(topPts[i].x, topPts[i].y);
    ctx.stroke();

    // bottom
    ctx.beginPath();
    ctx.moveTo(botPts[0].x, botPts[0].y);
    for (let i = 1; i < botPts.length; i++) ctx.lineTo(botPts[i].x, botPts[i].y);
    ctx.stroke();

    ctx.restore();
  }

  if (NeckEditor.mode === 'eyes') {
    const t = window.EyeTuning;
    const wAbs = Math.max(1e-6, Math.abs(t.width));
    const hAbs = Math.max(1e-6, Math.abs(t.height));

    const eyes = [
      { cx: t.leftCenterX, cy: t.centerY },
      { cx: t.rightCenterX, cy: t.centerY },
    ];

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,0,0,0.95)';

    for (const e of eyes) {
      const x0 = e.cx - wAbs, x1 = e.cx + wAbs;
      const y0 = e.cy - hAbs, y1 = e.cy + hAbs;

      const p0 = screenProject(x0, y0, 0);
      const p1 = screenProject(x1, y0, 0);
      const p2 = screenProject(x1, y1, 0);
      const p3 = screenProject(x0, y1, 0);

      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p3.x, p3.y);
      ctx.closePath();
      ctx.stroke();
    }

    // dibuja un arco de lidCurve (visual)
    const segments = 48;
    for (const e of eyes) {
      const pts = [];
      for (let i = 0; i <= segments; i++) {
        const u = i / segments;
        const x = (e.cx - wAbs) + (2.0 * wAbs) * u;
        const dx = x - e.cx;
        const nx = dx / wAbs;
        const nxClamped = Math.max(-1, Math.min(1, nx));
        const c = t.lidCurve * nxClamped * nxClamped;
        const y = e.cy + hAbs - c;
        pts.push(screenProject(x, y, 0));
      }
      ctx.globalAlpha = 0.70;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      ctx.stroke();
      ctx.globalAlpha = 1.0;
    }

    // ✅ Patch 3: cruces grandes en centros (imposible “no verlos”)
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 2;

    const centers = [
      { x: t.leftCenterX, y: t.centerY, label: 'L' },
      { x: t.rightCenterX, y: t.centerY, label: 'R' },
    ];

    for (const c of centers) {
      const s = screenProject(c.x, c.y, 0);
      const size = 18;

      ctx.beginPath();
      ctx.moveTo(s.x - size, s.y);
      ctx.lineTo(s.x + size, s.y);
      ctx.moveTo(s.x, s.y - size);
      ctx.lineTo(s.x, s.y + size);
      ctx.stroke();

      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.font = '14px ui-monospace, monospace';
      ctx.fillText(c.label, s.x + size + 6, s.y + 5);
    }
    ctx.restore();

    ctx.restore();
  }

  // --- Handles ---
  const handles = getHandlesModel();
  for (const key of Object.keys(handles)) {
    const s = screenProject(handles[key].x, handles[key].y, 0);

    const isPivot = (key === 'neckPivot' || key === 'bodyPivot');
    const color = isPivot ? 'rgba(255,0,0,0.75)' : 'rgba(255,0,0,0.95)';

    drawHandle(ctx, key, color, true, s.x, s.y);

    ctx.save();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';
    ctx.fillText(key, s.x + 12, s.y - 10);
    ctx.restore();
  }
}

// init overlay si aplica (igual que antes)
if (DEBUG_EDIT_ENABLED) {
  initNeckEditorOverlay();
}
