import { AVATAR_RUNTIME_CONFIG } from './config.js';
import { createAvatarRuntime } from './runtime.js';

function initAvatarRuntime() {
  const stageEl = document.getElementById('stage');
  if (!stageEl) {
    console.warn('[avatar-runtime] No se encontró #stage para montar el avatar.');
    return null;
  }

  const runtime = createAvatarRuntime({
    stageEl,
    config: AVATAR_RUNTIME_CONFIG,
  });

  window.__avatarRuntime = runtime;
  return runtime;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAvatarRuntime, { once: true });
} else {
  initAvatarRuntime();
}
