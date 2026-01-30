import { DEBUG_EDIT_ENABLED, NeckEditor, AvatarState, DebugView, MotionConfig, MotionState, SpeakFocus, updateBlink, updateChannel, updateNod, onSpeakStart, onSpeakEnd, DebugEdit, FreezePose } from './state.js';
import { scene, camera, renderer, controls, clock } from './scene.js';
import { initAvatarParticles, getParticleMaterial, getParticlePoints } from './avatarParticles.js';
import { initAgentUI, getTalkLevelFromAudio, isLipHoldActive } from './audioAgent.js';
import { drawNeckEditorOverlay } from './editorOverlay.js';

// =========================
// Init: partículas + UI
// =========================
initAvatarParticles({ scene, controls });
initAgentUI();

function animate() {
  requestAnimationFrame(animate);

  const elapsed = clock.getElapsedTime();
  const delta = clock.getDelta();

  const freezeActive = DebugEdit.enabled && DebugEdit.freezeMotion;

  // speakingNow SOLO si no estamos congelados
  const speakingNow = !freezeActive && ((AvatarState.mode === 'SPEAKING') || isLipHoldActive());

  // detectar transición speaking start/end (solo si no freeze)
  if (!freezeActive) {
    if (speakingNow && !SpeakFocus.wasSpeaking) onSpeakStart(elapsed);
    if (!speakingNow && SpeakFocus.wasSpeaking) onSpeakEnd(elapsed);
    SpeakFocus.wasSpeaking = speakingNow;

    // speaking blend suave
    const targetBlend = speakingNow ? 1.0 : 0.0;
    SpeakFocus.speakingBlend += (targetBlend - SpeakFocus.speakingBlend) * (1.0 - Math.exp(-delta * 6.5));

    // lean in/out
    const targetLean = speakingNow ? 0.028 : 0.0;
    SpeakFocus.leanZ += (targetLean - SpeakFocus.leanZ) * (1.0 - Math.exp(-delta * 7.0));
  }

  // blink value: en freeze lo paramos
  const blink = freezeActive ? 0.0 : updateBlink(elapsed);

  const particleMaterial = getParticleMaterial();
  const particlePoints = getParticlePoints();

  if (particleMaterial) {
    if (freezeActive) {
      // Captura 1 vez al entrar en freeze (pose actual)
      if (!FreezePose.captured) {
        FreezePose.captured = true;
        FreezePose.uTime = elapsed;

        FreezePose.talk = particleMaterial.uniforms.uTalk?.value ?? 0.0;
        FreezePose.blink = particleMaterial.uniforms.uBlink?.value ?? 0.0;
        FreezePose.headRot.copy(particleMaterial.uniforms.uHeadRot.value);
        FreezePose.bodyRot.copy(particleMaterial.uniforms.uBodyRot.value);
        FreezePose.bodyOffset.copy(particleMaterial.uniforms.uBodyOffset.value);

        console.info('[debugEdit] FREEZE ON', { uTime: FreezePose.uTime });
      }

      // Congela uTime => se para sway/ruido/respiración shader
      particleMaterial.uniforms.uTime.value = FreezePose.uTime;

      // Mantener talk congelado
      AvatarState.talkLevel = FreezePose.talk;
      particleMaterial.uniforms.uTalk.value = FreezePose.talk;
      particleMaterial.uniforms.uRestOpen.value = 0.03;

      particleMaterial.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;

      // Blink congelado, pero en modo eyes forzamos “cierre estático”
      let blinkVal = FreezePose.blink;
      if (DEBUG_EDIT_ENABLED && NeckEditor?.visible && NeckEditor?.mode === 'eyes') {
        blinkVal = NeckEditor.dragging ? 1.0 : 0.65;
      }
      particleMaterial.uniforms.uBlink.value = blinkVal;
      particleMaterial.uniforms.uBlinkAlpha.value = window.EyeTuning.alpha ?? 0.7;

      // Pose congelada
      particleMaterial.uniforms.uHeadRot.value.copy(FreezePose.headRot);
      particleMaterial.uniforms.uBodyRot.value.copy(FreezePose.bodyRot);
      particleMaterial.uniforms.uBodyOffset.value.copy(FreezePose.bodyOffset);

    } else {
      // fuera de freeze, permitir recaptura futura
      FreezePose.captured = false;

      particleMaterial.uniforms.uTime.value = elapsed;

      let targetTalk = 0.0;
      if (isLipHoldActive()) targetTalk = 1.0;
      else targetTalk = getTalkLevelFromAudio();

      AvatarState.talkLevel = targetTalk;
      particleMaterial.uniforms.uTalk.value = AvatarState.talkLevel;

      particleMaterial.uniforms.uRestOpen.value = 0.03;
      particleMaterial.uniforms.uDebugHeadWeight.value = DebugView.headWeight ? 1.0 : 0.0;

      // preview blink en editor eyes
      let blinkVal = blink;
      if (DEBUG_EDIT_ENABLED && NeckEditor?.visible && NeckEditor?.mode === 'eyes') {
        blinkVal = Math.max(blinkVal, NeckEditor.dragging ? 1.0 : 0.65);
      }

      particleMaterial.uniforms.uBlink.value = blinkVal;
      particleMaterial.uniforms.uBlinkAlpha.value = window.EyeTuning.alpha ?? 0.7;

      // motion normal
      const sB = SpeakFocus.speakingBlend;

      const headCfg = {
        ...MotionConfig.head,
        ampYaw: MotionConfig.head.ampYaw * (1.0 - 0.45 * sB),
        ampPitch: MotionConfig.head.ampPitch * (1.0 - 0.45 * sB),
        ampRoll: MotionConfig.head.ampRoll * (1.0 - 0.55 * sB),
        smooth: MotionConfig.head.smooth * (1.0 + 0.35 * sB),
        holdMin: MotionConfig.head.holdMin * (1.0 + 0.15 * sB),
        holdMax: MotionConfig.head.holdMax * (1.0 + 0.25 * sB),
      };

      const bodyCfg = {
        ...MotionConfig.body,
        ampYaw: MotionConfig.body.ampYaw * (1.0 - 0.35 * sB),
        ampPitch: MotionConfig.body.ampPitch * (1.0 - 0.35 * sB),
        ampRoll: MotionConfig.body.ampRoll * (1.0 - 0.40 * sB),
        smooth: MotionConfig.body.smooth * (1.0 + 0.25 * sB),
      };

      updateChannel(MotionState.head, headCfg, elapsed, delta);
      updateChannel(MotionState.body, bodyCfg, elapsed, delta);

      const microMul = 1.0 - 0.55 * sB;

      const microYaw =
        ((Math.sin(elapsed * 2.1 + MotionState.seed) * MotionConfig.micro.yaw) +
        (Math.sin(elapsed * 3.7 + MotionState.seed * 0.3) * MotionConfig.micro.yaw * 0.45)) * microMul;

      const microPitch =
        ((Math.sin(elapsed * 1.8 + MotionState.seed * 0.7) * MotionConfig.micro.pitch) +
        (Math.sin(elapsed * 3.2 + MotionState.seed * 0.2) * MotionConfig.micro.pitch * 0.45)) * microMul;

      const microRoll =
        ((Math.sin(elapsed * 1.5 + MotionState.seed * 1.3) * MotionConfig.micro.roll) +
        (Math.sin(elapsed * 2.9 + MotionState.seed * 0.4) * MotionConfig.micro.roll * 0.45)) * microMul;

      const nodPitch = updateNod(elapsed, delta);

      const holdActive = speakingNow && (elapsed < SpeakFocus.holdUntil);
      const targetCenterBias = holdActive ? 0.92 : (0.22 * sB);

      const centerSpeed = (targetCenterBias > SpeakFocus.centerBias) ? 4.8 : 2.2;
      SpeakFocus.centerBias += (targetCenterBias - SpeakFocus.centerBias) * (1.0 - Math.exp(-delta * centerSpeed));

      const centerBias = SpeakFocus.centerBias;

      const head = MotionState.head.current;
      let hx = head.x + microPitch + nodPitch;
      let hy = head.y + microYaw;
      let hz = head.z + microRoll;

      hx *= (1.0 - centerBias);
      hy *= (1.0 - centerBias);
      hz *= (1.0 - centerBias);

      particleMaterial.uniforms.uHeadRot.value.set(hx, hy, hz);

      const body = MotionState.body.current;
      particleMaterial.uniforms.uBodyRot.value.set(
        body.x + microPitch * 0.25,
        body.y + microYaw * 0.25,
        body.z + microRoll * 0.25
      );

      let offY = 0.0;
      if (AvatarState.idleMotionEnabled) {
        offY = 0.01 * Math.sin(elapsed * 0.9) + 0.005 * Math.sin(elapsed * 0.37);
      }

      particleMaterial.uniforms.uBodyOffset.value.set(0.0, offY, SpeakFocus.leanZ);
    }

    // pivotes live en editor siempre (freeze o no)
    if (DEBUG_EDIT_ENABLED) {
      const t = window.NeckTuning;
      particleMaterial.uniforms.uNeckPivot.value.set(0.0, t.neckPivotY, 0.0);
      particleMaterial.uniforms.uBodyPivot.value.set(0.0, t.bodyPivotY, 0.0);
    }
  }

  if (particlePoints) {
    particlePoints.rotation.set(0, 0, 0);
    particlePoints.position.set(0, 0, 0);
  }

  controls.update();
  renderer.render(scene, camera);

  if (NeckEditor && NeckEditor.visible) drawNeckEditorOverlay();
}

animate();
