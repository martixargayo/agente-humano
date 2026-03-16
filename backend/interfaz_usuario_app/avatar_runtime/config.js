export const AVATAR_RUNTIME_CONFIG = {
  // ⚠️ Debes colocar manualmente el GLB en esta ruta (no se incluye en repo en esta fase).
  modelUrl: './avatar_runtime/assets/FaceVolumen.glb',
  // ⚠️ Opcional: fondo dark externo. Mantener null para tema realistic.
  backgroundImageUrl: null,
  theme: 'realistic',
  camera: {
    fov: 40,
    near: 0.01,
    far: 100,
    position: [0, 0.25, 1.9],
  },
  controlsTarget: [0, 0.15, 0],
  // true = fija completamente cámara/encuadre (sin orbit/pan/zoom manual).
  controlsLocked: true,
  transform: {
    offset: [0, 0, 0],
    scale: 1.0,
  },
};
