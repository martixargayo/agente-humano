import { buildAvatarRuntimeConfigFromPresentation } from './config.js';
import { createAvatarRuntime } from './runtime.js';

export function initAvatarRuntime({ stageEl, presentationConfig } = {}) {
  if (window.__avatarRuntime) return window.__avatarRuntime;

  const resolvedStageEl = stageEl || document.getElementById('stage');
  if (!resolvedStageEl) {
    throw new Error('avatar_runtime_stage_missing');
  }

  const runtime = createAvatarRuntime({
    stageEl: resolvedStageEl,
    config: buildAvatarRuntimeConfigFromPresentation(presentationConfig),
  });

  window.__avatarRuntime = runtime;
  return runtime;
}

window.__initAvatarRuntime = initAvatarRuntime;
