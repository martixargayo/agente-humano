from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PresentationThemeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shell_theme: str = "realistic"


class PresentationBackgroundConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "none"
    url: str | None = None
    size: str = "contain"
    position: str = "center center"


class PresentationAvatarModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class PresentationAvatarCameraConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fov: float
    near: float
    far: float
    position: list[float] = Field(default_factory=list, min_length=3, max_length=3)
    target: list[float] = Field(default_factory=list, min_length=3, max_length=3)


class PresentationAvatarTransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: list[float] = Field(default_factory=list, min_length=3, max_length=3)
    scale: float


class PresentationAvatarCalibrationMouthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_x: float
    center_y: float
    width: float
    height: float
    curve: float


class PresentationAvatarCalibrationNeckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_x: float
    width: float
    top_y: float
    bottom_y: float
    curve: float
    neck_pivot_y: float
    body_pivot_y: float


class PresentationAvatarCalibrationEyeLidCurveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: float
    curve: float


class PresentationAvatarCalibrationEyeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_x: float
    center_y: float
    half_width: float
    rotation: float
    upper: PresentationAvatarCalibrationEyeLidCurveConfig
    lower: PresentationAvatarCalibrationEyeLidCurveConfig


class PresentationAvatarCalibrationEyesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_eye: PresentationAvatarCalibrationEyeConfig
    right_eye: PresentationAvatarCalibrationEyeConfig


class PresentationAvatarCalibrationMouthRenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rim_a: float
    rim_b: float
    rim_c: float
    rim_d: float
    inner_a: float
    inner_b: float
    inner_gain: float
    inner_core_a: float
    inner_core_b: float
    inner_core_gain: float
    mask_min: float
    upsample_min_points: int
    upsample_amp_min: float
    upsample_amp_max: float
    rim_resample_factor: int
    points_alpha: float
    points_alpha_clip: float
    points_size_near: float
    points_size_far: float
    points_color_mul: float
    points_luma_floor: float
    points_luma_strength: float
    points_luma_preserve_hue: float
    points_luma_debug: bool
    points_cull_back: bool
    points_debug_back_only: bool
    mesh_fade: float
    mesh_feather: float
    mesh_alpha_min: float
    mesh_fade_gamma: float
    mesh_fade_gain: float
    use_diamond_fade: bool
    fade_diamond_cx: float
    fade_diamond_cy: float
    fade_diamond_rx: float
    fade_diamond_ry: float
    fade_diamond_rot: float
    always_points_mode: bool
    points_on: float
    points_off: float


class PresentationAvatarCalibrationLipsyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    talk_amp_top: float
    talk_amp_bottom: float
    talk_freq: float
    lip_depth_amp: float
    rest_open: float
    attack: float
    release: float


class PresentationAvatarCalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mouth: PresentationAvatarCalibrationMouthConfig
    neck: PresentationAvatarCalibrationNeckConfig
    eyes: PresentationAvatarCalibrationEyesConfig
    mouth_render: PresentationAvatarCalibrationMouthRenderConfig
    lipsync: PresentationAvatarCalibrationLipsyncConfig


class PresentationAvatarMotionChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amp_yaw: float
    amp_pitch: float
    amp_roll: float
    hold_min: float
    hold_max: float
    smooth: float
    ramp_dur: float


class PresentationAvatarMotionMicroConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaw: float
    pitch: float
    roll: float


class PresentationAvatarMotionNodConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listen_probability: float
    dur_min: float
    dur_max: float
    amp_min: float
    amp_max: float


class PresentationAvatarMotionBodyBobConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amp_primary: float
    freq_primary: float
    amp_secondary: float
    freq_secondary: float


class PresentationAvatarMotionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    head: PresentationAvatarMotionChannelConfig
    body: PresentationAvatarMotionChannelConfig
    micro: PresentationAvatarMotionMicroConfig
    nod: PresentationAvatarMotionNodConfig
    body_bob: PresentationAvatarMotionBodyBobConfig


class PresentationAvatarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: PresentationAvatarModelConfig
    camera: PresentationAvatarCameraConfig
    transform: PresentationAvatarTransformConfig
    calibration: PresentationAvatarCalibrationConfig
    motion: PresentationAvatarMotionConfig


class PresentationVoiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str
    speaking_rate: float


class PresentationCaseInfoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = "Información del caso"
    description: str = ""


class PresentationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    theme: PresentationThemeConfig
    background: PresentationBackgroundConfig
    avatar: PresentationAvatarConfig
    voice: PresentationVoiceConfig
    case_info: PresentationCaseInfoConfig | None = None
