const GLOBAL_RUNTIME_FLAGS = Object.freeze({
  controlsLocked: true,
});

function arrayOrThrow(value, expectedLength, fieldName) {
  if (!Array.isArray(value) || value.length !== expectedLength) {
    throw new Error(`avatar_runtime_config_invalid_${fieldName}`);
  }
  return [...value];
}

function finiteNumberOrThrow(value, fieldName) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    throw new Error(`avatar_runtime_config_invalid_${fieldName}`);
  }
  return numeric;
}

function nonEmptyStringOrThrow(value, fieldName) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`avatar_runtime_config_invalid_${fieldName}`);
  }
  return value.trim();
}

export function buildAvatarRuntimeConfigFromPresentation(presentationConfig) {
  const avatar = presentationConfig?.avatar;
  const camera = avatar?.camera;
  const transform = avatar?.transform;
  const calibration = avatar?.calibration;
  const motion = avatar?.motion;
  const model = avatar?.model;
  const theme = presentationConfig?.theme;

  return {
    theme: nonEmptyStringOrThrow(theme?.shell_theme, 'theme_shell_theme'),
    modelUrl: nonEmptyStringOrThrow(model?.url, 'avatar_model_url'),
    camera: {
      fov: finiteNumberOrThrow(camera?.fov, 'avatar_camera_fov'),
      near: finiteNumberOrThrow(camera?.near, 'avatar_camera_near'),
      far: finiteNumberOrThrow(camera?.far, 'avatar_camera_far'),
      position: arrayOrThrow(camera?.position, 3, 'avatar_camera_position'),
    },
    controlsTarget: arrayOrThrow(camera?.target, 3, 'avatar_camera_target'),
    controlsLocked: GLOBAL_RUNTIME_FLAGS.controlsLocked,
    transform: {
      offset: arrayOrThrow(transform?.offset, 3, 'avatar_transform_offset'),
      scale: finiteNumberOrThrow(transform?.scale, 'avatar_transform_scale'),
    },
    calibration: calibration && typeof calibration === 'object' ? calibration : {},
    motion: motion && typeof motion === 'object' ? motion : {},
  };
}

export const AVATAR_RUNTIME_SHIM = Object.freeze({ GLOBAL_RUNTIME_FLAGS });
