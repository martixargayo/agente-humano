from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MemoryWorkingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_topic: str | None
    pending_question: str | None
    last_turn_summary_excerpt: str | None


class NegotiationOfferSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str | None
    price_amount: float | None
    currency: str | None
    extras_count: int
    conditions_count: int
    is_currently_active: bool | None
    source_turn_role: str | None


class NegotiationStateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    active_axes: list[str]
    last_offer_self: NegotiationOfferSummary | None
    last_offer_other: NegotiationOfferSummary | None
    tentative_agreement_summary: str | None
    blockers_count: int
    blockers: list[str]
    next_open_loop: str | None


class PlannerLimitsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_sentences: int
    max_questions: int
    allow_topic_shift: bool
    allow_personal_disclosure: bool


class PlannerStateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: str | None
    previous_phase: str | None
    current_turn_goal: str | None
    topics_touched_current_phase_count: int
    topics_touched_previous_phases_count: int


class MemoryInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_text_excerpt: str
    recent_dialogue_count: int
    memory_working_current: MemoryWorkingSummary
    recent_memory_episodic_count: int
    recent_memory_event_types: list[str]


class MemoryOutputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episodic_append_count: int
    episodic_append_event_types: list[str]
    working_memory_new: MemoryWorkingSummary
    negotiation_state: NegotiationStateSummary


class PhaseInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous_phase: str | None
    recent_phase_history: list[str]
    phase_classifier_card_source: str
    recent_turn_count: int
    user_text_excerpt: str


class PhaseOutputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: str


class PlannerInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: str
    phase_card_phase: str
    user_text_excerpt: str
    recent_dialogue_count: int
    memory_working: MemoryWorkingSummary
    negotiation_state: NegotiationStateSummary
    planner_state: PlannerStateSummary
    selected_memory_count: int
    selected_memory_ids: list[str]


class PlannerOutputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    decision: str
    turn_goal: str
    must_include: list[str]
    must_avoid: list[str]
    limits: PlannerLimitsSummary
    memory_targets: list[str]
    done_criteria: list[str]


class ExecutorInputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: str
    phase_card_phase: str
    user_text_excerpt: str
    recent_dialogue_count: int
    planner_status: str
    planner_decision: str
    planner_turn_goal: str
    selected_memory_count: int
    selected_memory_ids: list[str]
    response_limits: PlannerLimitsSummary


class ExecutorOutputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    spoken_text_excerpt: str
    spoken_text_length: int
    memory_used: list[str]
    refusal_reason: str | None
