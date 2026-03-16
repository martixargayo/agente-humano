from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal[
    "created",
    "queued",
    "building_inputs",
    "running_core",
    "running_trajectory",
    "assembling_report",
    "completed",
    "failed",
]

InteractionOutcome = Literal["agreement_reached", "partial_progress", "no_agreement", "blocked"]
BlockStatus = Literal["correcto", "mejorable", "mal"]


class SessionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    session_id: str


class BundleTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_index: int
    turn_id: str
    user_text: str
    assistant_text: str


class ConversationBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turns: list[BundleTurn] = Field(default_factory=list)


class ConversationStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_count: int
    duration_seconds: int
    user_avg_chars: int
    assistant_avg_chars: int


class DomainContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["negociacion"]
    final_phase: str | None = None
    finish_button_was_armed: bool = False


class DerivedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_turn_indexes: list[int] = Field(default_factory=list)
    close_signals_count: int = 0
    offer_signals_count: int = 0
    blocker_signals_count: int = 0


class TraceDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_count: int = 0
    guardrail_events_count: int = 0


class FeedbackInputBundleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["feedback_input_bundle.v1"]
    evaluation_id: str
    session_ref: SessionRef
    conversation: ConversationBlock
    conversation_stats: ConversationStats
    domain_context: DomainContext
    derived_facts: DerivedFacts
    trace_digest: TraceDigest | None = None


class DomainRubricMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["negociacion"]
    rubric_version: str
    case_title: str


class DomainRubricBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: Literal["valores", "vision", "relacion", "proceso"]
    title: str
    evaluates: str
    positive_signals: list[str]
    negative_signals: list[str]
    common_mistakes: list[str]
    evaluator_focus: str


class DomainRubricGlobalGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principles: list[str]
    transversal_errors: list[str]
    progress_signals: list[str]
    deterioration_signals: list[str]
    tone_and_rhythm_reminders: list[str]


class NegotiationDomainRubricV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["negotiation_domain_rubric.v1"]
    metadata: DomainRubricMetadata
    blocks: list[DomainRubricBlock]
    global_guide: DomainRubricGlobalGuide


class CoreRunnerInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["core_runner_input.v1"]
    evaluation_id: str
    conversation: ConversationBlock
    conversation_stats: ConversationStats
    domain_context: DomainContext
    domain_rubric: NegotiationDomainRubricV1


class TrajectoryRunnerInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["trajectory_runner_input.v1"]
    evaluation_id: str
    turns_for_trajectory: list[BundleTurn]


class EvaluationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polarity: Literal["check", "cross"]
    micro_explanation: str
    evidence_turn_indexes: list[int]


class EvaluationBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: Literal["valores", "vision", "relacion", "proceso"]
    title: str
    status_visual: BlockStatus
    score_0_100: int
    checks: list[EvaluationCheck]
    block_verdict: str


class KeyMoment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_index: int
    why: str
    impact: str


class RecommendationExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_excerpt: str
    better_rephrase: str


class RecommendationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    description: str
    example: RecommendationExample | None


class FeedbackReportCoreV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["feedback_report_core.v1"]
    score_global_100: int
    interaction_outcome: InteractionOutcome
    summary_2_3_lines: str
    evaluation_blocks: list[EvaluationBlock]
    best_moment: KeyMoment
    most_delicate_moment: KeyMoment
    turning_point: KeyMoment
    recommendations: list[RecommendationItem]


class TrajectoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_index: int
    agreement_closeness_score_0_100: int
    user_excerpt: str
    counterpart_excerpt: str
    impact_reason: str
    counterpart_thought_effect: str
    better_rephrase: str | None


class TurnTrajectoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["turn_trajectory.v1"]
    trajectory: list[TrajectoryTurn]


class UiHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_title: str
    activity_name: str
    score_global_100: int
    stars_0_5: float
    interaction_outcome: InteractionOutcome
    summary_2_3_lines: str


class KeyMomentsPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    best_moment: KeyMoment
    most_delicate_moment: KeyMoment
    turning_point: KeyMoment


class RecommendationsPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RecommendationItem]


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    bundle_hash: str
    core_input_hash: str
    trajectory_input_hash: str
    core_output_hash: str
    trajectory_output_hash: str
    core_model: str
    trajectory_model: str
    core_prompt_version: str
    trajectory_prompt_version: str


class UiFeedbackReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ui_feedback_report.v1"]
    evaluation_id: str
    header: UiHeader
    block_cards: list[EvaluationBlock]
    trajectory_chart: list[TrajectoryTurn]
    key_moments: KeyMomentsPanel
    recommendations: RecommendationsPanel
    provenance: Provenance
