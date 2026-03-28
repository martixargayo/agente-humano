from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evaluacion.contracts.models import SessionRef

CommunicationJobStatus = Literal['queued', 'running', 'completed', 'failed']
CommunicationJobStage = Literal[
    'queued',
    'extracting',
    'extracting_media',
    'transcription_started',
    'transcript_ready',
    'content_analysis_started',
    'content_analysis_ready',
    'delivery_analysis_started',
    'audio_metrics_started',
    'audio_features_ready',
    'delivery_analysis_ready',
    'frame_extraction_started',
    'frames_ready',
    'visual_analysis_started',
    'visual_analysis_ready',
    'synthesis_started',
    'synthesis_ready',
    'assembling_report',
    'completed',
    'failed',
]
CommunicationBlockStatus = Literal['correcto', 'mejorable', 'placeholder']
CommunicationVisualMode = Literal['metadata', 'llm_v1']
CommunicationSpecializedEvalLabel = Literal['bajo', 'medio-bajo', 'medio', 'medio-alto', 'alto']
CommunicationContentAidaLabel = Literal['mal', 'mejorable', 'correcto']


class CommunicationDomainContext(BaseModel):
    model_config = ConfigDict(extra='forbid')

    domain: Literal['comunicacion'] = 'comunicacion'
    flow_id: Literal['comunicacion'] = 'comunicacion'
    context_id: str
    context_version: str


class CommunicationAttemptRef(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attempt_id: str
    recording_id: str


class CommunicationRecordingMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    duration_ms: int
    mime_type: str
    video_ref: str
    playback_url: str | None = None
    poster_frame_ref: str | None = None
    capture_meta: dict[str, object] = Field(default_factory=dict)


class CommunicationTranscriptSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    segment_index: int
    start_ms: int
    end_ms: int
    text: str


class CommunicationTranscriptPlaceholder(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: Literal['placeholder'] = 'placeholder'
    language: str = 'es'
    full_text: str = ''
    explanation: str
    segments: list[CommunicationTranscriptSegment] = Field(default_factory=list)


class CommunicationTranscriptRealV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_transcript_real.v1'] = 'communication_transcript_real.v1'
    status: Literal['ready'] = 'ready'
    provider: str
    language: str
    full_text: str
    segments: list[CommunicationTranscriptSegment] = Field(default_factory=list)
    confidence_global: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    explanation: str | None = None


class CommunicationPauseSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    start_ms: int
    end_ms: int
    duration_ms: int
    kind: Literal['synthetic_pause'] = 'synthetic_pause'


class CommunicationAudioFeaturesPlaceholder(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: Literal['placeholder'] = 'placeholder'
    speech_rate_wpm: float | None = None
    filler_count: int | None = None
    pause_segments: list[CommunicationPauseSegment] = Field(default_factory=list)
    explanation: str
    metrics: dict[str, object] = Field(default_factory=dict)


class CommunicationAudioPauseEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    start_ms: int
    end_ms: int
    duration_ms: int


class CommunicationAudioPitchStats(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mean_hz: float | None = None
    median_hz: float | None = None
    std_hz: float | None = None
    min_hz: float | None = None
    max_hz: float | None = None
    range_hz: float | None = None


class CommunicationAudioEnergyStats(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rms_mean: float
    rms_std: float
    rms_min: float
    rms_max: float


class CommunicationAudioRawMetricsV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    pause_events: list[CommunicationAudioPauseEvent] = Field(default_factory=list)
    speech_rate_wpm: float | None = None
    speaking_time_ms: int
    pause_time_ms: int
    pause_ratio: float
    pause_mean_ms: float | None = None
    pause_max_ms: int | None = None
    long_pauses_count: int = 0
    pitch_stats: CommunicationAudioPitchStats
    energy_stats: CommunicationAudioEnergyStats
    voiced_ratio: float | None = None


class CommunicationAudioInterpretedMetricsV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    fluency_1_5: int | None = None
    pause_control_1_5: int | None = None
    expressiveness_1_5: int | None = None
    stability_1_5: int | None = None


class CommunicationSpecializedDimensionEvalV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    score_1_5: int = Field(ge=1, le=5)
    label: CommunicationSpecializedEvalLabel
    reason_short: str = Field(min_length=1)


class CommunicationContentAidaBlockEvalV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    score_1_3: int = Field(ge=1, le=3)
    label: CommunicationContentAidaLabel
    reason_short: str = Field(min_length=1)

    @model_validator(mode='after')
    def _validate_label_matches_score(self) -> 'CommunicationContentAidaBlockEvalV1':
        expected = {1: 'mal', 2: 'mejorable', 3: 'correcto'}[self.score_1_3]
        if self.label != expected:
            raise ValueError(f'label_mismatch_for_score:{self.score_1_3}->{expected}')
        return self


class CommunicationContentAidaEvalV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attention: CommunicationContentAidaBlockEvalV1
    interest: CommunicationContentAidaBlockEvalV1
    development: CommunicationContentAidaBlockEvalV1
    action: CommunicationContentAidaBlockEvalV1


class CommunicationAudioFeaturesRealV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_audio_features_real.v1'] = 'communication_audio_features_real.v1'
    status: Literal['ready', 'unavailable'] = 'ready'
    raw_metrics: CommunicationAudioRawMetricsV1
    interpreted_metrics: CommunicationAudioInterpretedMetricsV1 = Field(default_factory=CommunicationAudioInterpretedMetricsV1)
    quality_flags: list[str] = Field(default_factory=list)
    provider_meta: dict[str, object] = Field(default_factory=dict)
    explanation: str | None = None


class CommunicationVisualFeaturesPlaceholder(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: Literal['placeholder'] = 'placeholder'
    score_visual_0_100: int | None = None
    summary: str
    explanation: str
    notable_windows: list[dict[str, object]] = Field(default_factory=list)


class CommunicationFrameSample(BaseModel):
    model_config = ConfigDict(extra='forbid')

    frame_id: str
    timestamp_ms: int
    frame_ref: str
    width: int | None = None
    height: int | None = None
    byte_size: int | None = None
    quality: Literal['ok', 'low_detail', 'unknown'] = 'unknown'


class CommunicationFrameWindow(BaseModel):
    model_config = ConfigDict(extra='forbid')

    window_id: str
    start_ms: int
    end_ms: int
    frame_ids: list[str] = Field(default_factory=list)


class CommunicationFrameManifestV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_frame_manifest.v1'] = 'communication_frame_manifest.v1'
    source_ref: str
    sampling_policy: dict[str, object] = Field(default_factory=dict)
    frames: list[CommunicationFrameSample] = Field(default_factory=list)
    windows: list[CommunicationFrameWindow] = Field(default_factory=list)


class CommunicationVisualFeaturesRealV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_features_real.v1'] = 'communication_visual_features_real.v1'
    status: Literal['ready', 'unavailable'] = 'ready'
    frame_manifest: CommunicationFrameManifestV1
    coverage_stats: dict[str, float | int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    explanation: str | None = None


class CommunicationVisualSamplingStrategyV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mode: Literal['uniform_1fps_capped_90'] = 'uniform_1fps_capped_90'
    candidate_fps: Literal[1] = 1
    max_frames: int = Field(default=90, ge=1, le=90)
    selection: Literal['uniform_full_duration'] = 'uniform_full_duration'
    batch_target: int = Field(default=30, ge=1, le=90)
    tail_merge_threshold: int = Field(default=6, ge=1, le=30)


class CommunicationVisualBatchFrameRefV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    frame_id: str
    timestamp_ms: int = Field(ge=0)
    frame_ref: str
    detail: Literal['low'] = 'low'


class CommunicationVisualBatchEvalInputV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_batch_eval_input.v1'] = 'communication_visual_batch_eval_input.v1'
    evaluation_id: str
    recording_id: str
    batch_index: int = Field(ge=1)
    total_batches: int = Field(ge=1)
    video_duration_ms: int = Field(ge=0)
    sampling_strategy: CommunicationVisualSamplingStrategyV1 = Field(default_factory=CommunicationVisualSamplingStrategyV1)
    frames: list[CommunicationVisualBatchFrameRefV1] = Field(default_factory=list)
    rubric: dict[str, str] = Field(default_factory=dict)


class CommunicationVisualObservabilityFlagsV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    hands_not_visible: bool
    face_partially_visible: bool
    upper_body_not_visible: bool
    blur_detected: bool
    low_light_detected: bool
    camera_far_distance: bool


class CommunicationVisualFrameCoverageSummaryV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    frames_total: int = Field(ge=0)
    frames_usable: int = Field(ge=0)
    frames_with_face_visible: int = Field(ge=0)
    frames_with_hands_visible: int = Field(ge=0)
    frames_with_upper_body_visible: int = Field(ge=0)
    frames_blurry: int = Field(ge=0)
    frames_low_light: int = Field(ge=0)


class CommunicationVisualBatchEvalV2(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_batch_eval.v2'] = 'communication_visual_batch_eval.v2'
    batch_index: int = Field(ge=1)
    total_batches: int = Field(ge=1)
    batch_score_1_5: int = Field(ge=1, le=5)
    evidence_sufficiency: Literal['low', 'medium', 'high']
    confidence: float = Field(ge=0.0, le=1.0)
    hand_use_assessment: str
    facial_expression_assessment: str
    posture_assessment: str
    visual_support_assessment: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    cited_frame_ids: list[str] = Field(default_factory=list)
    observability_flags: CommunicationVisualObservabilityFlagsV1
    frame_coverage_summary: CommunicationVisualFrameCoverageSummaryV1
    confidence_reasoning: list[str] = Field(default_factory=list)


class CommunicationVisualFinalEvalV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_final_eval.v1'] = 'communication_visual_final_eval.v1'
    global_score_1_5: int = Field(ge=1, le=5)
    label: str
    diagnosis: str
    temporal_consistency: Literal['low', 'medium', 'high']
    top_strengths: list[str] = Field(default_factory=list)
    top_weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_frame_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    batch_summaries: list[CommunicationVisualBatchEvalV2] = Field(default_factory=list)


class CommunicationFeedbackInputBundleV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_feedback_input_bundle.v1'] = 'communication_feedback_input_bundle.v1'
    evaluation_id: str
    session_ref: SessionRef
    attempt_ref: CommunicationAttemptRef
    domain_context: CommunicationDomainContext
    recording: CommunicationRecordingMetadata
    transcript: CommunicationTranscriptPlaceholder | CommunicationTranscriptRealV1
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1
    visual_features: CommunicationVisualFeaturesPlaceholder | CommunicationVisualFeaturesRealV1


class CommunicationCoreEvaluatorInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_core_evaluator_input.v1'] = 'communication_core_evaluator_input.v1'
    evaluation_id: str
    domain_context: CommunicationDomainContext
    transcript: CommunicationTranscriptPlaceholder
    recording_meta: CommunicationRecordingMetadata


class CommunicationDeliveryEvaluatorInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_delivery_evaluator_input.v1'] = 'communication_delivery_evaluator_input.v1'
    evaluation_id: str
    audio_features: CommunicationAudioFeaturesPlaceholder | CommunicationAudioFeaturesRealV1
    transcript_segments: list[CommunicationTranscriptSegment] = Field(default_factory=list)


class CommunicationDeliveryEvaluationV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_delivery_evaluation.v1'] = 'communication_delivery_evaluation.v1'
    score_0_100: int
    subscores: dict[str, int] = Field(default_factory=dict)
    evidence_metrics: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CommunicationVisualEvaluatorInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_evaluator_input.v1'] = 'communication_visual_evaluator_input.v1'
    evaluation_id: str
    visual_features: CommunicationVisualFeaturesPlaceholder | CommunicationVisualFeaturesRealV1
    recording_meta: CommunicationRecordingMetadata


class CommunicationVisualTemporalFinding(BaseModel):
    model_config = ConfigDict(extra='forbid')

    window_id: str
    start_ms: int
    end_ms: int
    finding: str
    evidence_frame_ids: list[str] = Field(default_factory=list)


class CommunicationVisualEvaluationV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_visual_evaluation.v1'] = 'communication_visual_evaluation.v1'
    score_0_100: int
    subscores: dict[str, int] = Field(default_factory=dict)
    temporal_findings: list[CommunicationVisualTemporalFinding] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_frames: list[str] = Field(default_factory=list)


class CommunicationGlobalSynthesisInputV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_global_synthesis_input.v1'] = 'communication_global_synthesis_input.v1'
    evaluation_id: str
    content_evaluation: dict[str, object] = Field(default_factory=dict)
    delivery_evaluation: dict[str, object] = Field(default_factory=dict)
    visual_evaluation: dict[str, object] = Field(default_factory=dict)
    evidence_summary: list[str] = Field(default_factory=list)


class CommunicationGlobalSynthesisRecommendationV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CommunicationGlobalSynthesisLlmOutputV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    score_global_100: int = Field(ge=0, le=100)
    summary_short_2_3_lines: str = Field(min_length=1)
    recommendations: list[CommunicationGlobalSynthesisRecommendationV1] = Field(max_length=4)


class CommunicationGlobalSynthesisMetaV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mode: Literal['llm', 'fallback']
    fallback_reason: Literal['disabled_policy', 'missing_openai_api_key', 'openai_error', 'schema_validation_error', 'unexpected_error'] | None = None
    detail: str | None = None


class CommunicationBranchRuntimeMetaV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    branch_id: Literal['contenido', 'delivery', 'visual', 'global_synthesis']
    mode: Literal['llm', 'fallback', 'placeholder', 'metadata', 'real', 'rule_based']
    reason: str | None = None
    detail: str | None = None


class CommunicationGlobalSynthesisOutputV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['communication_global_synthesis_output.v1'] = 'communication_global_synthesis_output.v1'
    global_score_0_100: int
    global_diagnosis: str
    top_strengths: list[str] = Field(default_factory=list)
    priority_improvements: list[str] = Field(default_factory=list)
    action_plan: list[str] = Field(default_factory=list)
    friendly_summary: str
    consistency_notes: list[str] = Field(default_factory=list)


class CommunicationReportCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')

    polarity: Literal['check', 'note', 'placeholder']
    micro_explanation: str
    evidence_segment_ids: list[str] = Field(default_factory=list)


class CommunicationReportBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')

    block_id: Literal['contenido', 'delivery', 'visual']
    title: str
    status_visual: CommunicationBlockStatus
    score_0_100: int | None = None
    checks: list[CommunicationReportCheck] = Field(default_factory=list)
    block_verdict: str
    summary: str
    details: list[str] = Field(default_factory=list)


class CommunicationReportHeader(BaseModel):
    model_config = ConfigDict(extra='forbid')

    report_title: str
    activity_name: str
    score_global_100: int
    stars_0_5: float
    summary_2_3_lines: str


class CommunicationVideoPlayerHint(BaseModel):
    model_config = ConfigDict(extra='forbid')

    placement: Literal['top_right'] = 'top_right'
    size: Literal['small'] = 'small'
    sticky_within_report: bool = True


class CommunicationReportMediaBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')

    recording_id: str
    video_ref: str
    playback_url: str | None = None
    poster_frame_ref: str | None = None
    duration_ms: int
    mime_type: str
    player_hint: CommunicationVideoPlayerHint = Field(default_factory=CommunicationVideoPlayerHint)


class CommunicationVideoPanel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str
    help_text: str
    default_mode: Literal['embedded_small_player'] = 'embedded_small_player'


class CommunicationTimelineSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    segment_id: str
    label: str
    start_ms: int
    end_ms: int
    score_0_100: int | None = None
    summary: str
    signals: list[str] = Field(default_factory=list)


class CommunicationTimeline(BaseModel):
    model_config = ConfigDict(extra='forbid')

    segments: list[CommunicationTimelineSegment] = Field(default_factory=list)


class CommunicationKeyMoment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    segment_id: str
    label: str
    why: str
    impact: str


class CommunicationKeyMoments(BaseModel):
    model_config = ConfigDict(extra='forbid')

    best_moment: CommunicationKeyMoment
    most_delicate_moment: CommunicationKeyMoment
    turning_point: CommunicationKeyMoment


class CommunicationRecommendationExample(BaseModel):
    model_config = ConfigDict(extra='forbid')

    original_excerpt: str
    better_rephrase: str


class CommunicationRecommendationItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str
    description: str
    example: CommunicationRecommendationExample | None = None


class CommunicationRecommendations(BaseModel):
    model_config = ConfigDict(extra='forbid')

    items: list[CommunicationRecommendationItem] = Field(default_factory=list)


class CommunicationReportProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid')

    evaluation_id: str
    recording_id: str
    flow_id: str
    context_id: str
    context_version: str
    bundle_hash: str
    content_output_hash: str
    delivery_output_hash: str
    visual_output_hash: str
    global_synthesis_mode: Literal['llm', 'fallback'] | None = None
    global_synthesis_fallback_reason: str | None = None


class CommunicationReportExports(BaseModel):
    model_config = ConfigDict(extra='forbid')

    report_json: dict[str, object]
    summary_html: str
    report_snapshot_png_data_url: str


class UiCommunicationReportV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['ui_communication_report.v1'] = 'ui_communication_report.v1'
    evaluation_id: str
    attempt_id: str
    recording_id: str
    status: Literal['completed'] = 'completed'
    header: CommunicationReportHeader
    media: CommunicationReportMediaBlock
    video_panel: CommunicationVideoPanel
    block_cards: list[CommunicationReportBlock] = Field(default_factory=list)
    timeline: CommunicationTimeline
    key_moments: CommunicationKeyMoments
    recommendations: CommunicationRecommendations
    global_synthesis: CommunicationGlobalSynthesisLlmOutputV1 | None = None
    global_synthesis_meta: CommunicationGlobalSynthesisMetaV1 | None = None
    branch_runtime_meta: dict[str, CommunicationBranchRuntimeMetaV1] = Field(default_factory=dict)
    provenance: CommunicationReportProvenance
    exports: CommunicationReportExports
    placeholders: dict[str, str] = Field(default_factory=dict)


class CommunicationEvaluationStatusResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    evaluation_id: str
    attempt_id: str
    status: CommunicationJobStatus
    stage: CommunicationJobStage
    report_available: bool
    error: str | None = None
