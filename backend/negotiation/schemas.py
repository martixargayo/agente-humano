# backend/negotiation/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Set, TypedDict
InteractionHealth = Literal["stable", "tense", "stalled"]
RiskPosture = Literal["low", "mid", "high"]
PolicyOutcome = Literal["good", "neutral", "bad", ""]
ToneSignal = Literal["neutral", "friendly", "tense"]
ToneUsed = Literal["friendly", "neutral", "tense"]
ConversationMode = Literal["general", "negotiation"]
StyleLength = Literal["very_short", "short", "medium", "long"]
StyleFormat = Literal["plain", "bullets", "qa"]
EmojiPolicy = Literal["none", "never", "rare", "allowed"]
InteractionEscalation = Literal["up", "down", "none"]
RequiredInputOp = Literal["exists", "true", "non_empty"]
RequiredBeliefOp = Literal["eq", "neq", "gte", "lte", "in"]
EvidenceType = Literal[
    "PRICE",
    "DEADLINE",
    "URGENCY",
    "OTHER_BUYER",
    "CONCESSION",
    "DOCS",
    "MIN_PRICE",
    "FIRMNESS",
    "EVIDENCE_DOC",
    "BATNA",
    "TONE",
]
EvidenceSource = Literal["regex", "llm", "manual"]
EvidencePolarity = Literal["affirm", "deny"]
IntentStatus = Literal["inactive", "active", "succeeded", "abandoned", "paused"]
IntentType = Literal[
    "info_extract",
    "relationship",
    "concession",
    "closing",
    "credibility_check",
]
CommitmentLevel = Literal["hard", "soft"]
StepKind = Literal[
    "probe_open",
    "probe_narrow",
    "request_evidence",
    "trade_incentive",
    "pressure_soft",
    "close_next",
]
NegotiationPhase = Literal["climate", "interests", "options", "adjust", "formalize"]
LegacyNegotiationPhase = Literal["opening", "discovery", "bargaining", "closing", "recovery"]


class IntentSlot(TypedDict):
    value: object
    evidence: str
    confidence: float
    source: str


class IntentSlots(TypedDict):
    slots_required: List[str]
    slots_optional: List[str]
    slots_filled: Dict[str, IntentSlot]


class IntentStep(TypedDict):
    kind: StepKind
    target_slot: str
    success_if_filled: List[str]


class IntentState(TypedDict):
    status: IntentStatus
    intent_goal: str
    intent_type: IntentType
    steps: List[IntentStep]
    step_idx: int
    step_attempts: int
    max_attempts_per_step: int
    success_criteria: List[str]
    slots: IntentSlots
    confidence: float
    no_progress_turns: int
    slot_fill_count: int
    slot_fill_count_recent: int
    created_turn: int
    last_turn: int
    continue_until: str
    abandon_reasons: List[str]
    last_observation: str
    next_action_hint: str


class SlotValue(TypedDict, total=False):
    value: object
    source: Literal["world", "belief"]
    updated_turn: int


class PolicyState(TypedDict):
    status: Literal["inactive", "active", "succeeded", "abandoned", "paused"]
    policy_id: str
    step_idx: int
    step_attempts: int
    max_attempts_per_step: int
    started_turn: int
    last_turn: int
    no_progress_turns: int
    planner_request: Literal["choose_policy", "continue_policy", "replan_policy"]
    slots_required: List[str]
    slots_filled: Dict[str, SlotValue]


class PolicyHint(TypedDict):
    policy_active: bool
    policy_id: str
    step_kind: str
    target_slot: str
    next_action_hint: str
    attempts_left: int
    slots_missing: List[str]


class PolicyMeta(TypedDict):
    transition: Literal["advance", "retry", "succeed", "abandon", "force_planner"]
    reasons: List[str]
    deltas: dict
    thresholds: dict


# ---------- UniversalState v1 (universal) ----------
ConstraintKind = Literal["time", "money", "availability", "logistics", "capability", "rule", "safety", "other"]
ConstraintPolarity = Literal["must", "must_not", "prefer", "avoid"]
PreferenceStrength = Literal["low", "medium", "high"]
CommitmentWho = Literal["user", "agent", "other"]
CommitmentStatus = Literal["proposed", "agreed", "cancelled", "done"]
EntityType = Literal["person", "place", "product", "org", "event", "document", "other"]
SpeechActType = Literal[
    "ask",
    "inform",
    "refuse",
    "accept",
    "offer",
    "counter",
    "stall",
    "repair",
    "threaten",
    "confirm",
]


class UniversalGoal(TypedDict, total=False):
    summary: str  # <= 120 chars
    confidence: float  # 0..1
    evidence_text: str  # <= 180 chars


class UniversalConstraint(TypedDict, total=False):
    kind: ConstraintKind
    key: str  # <= 48 chars (id lógico tipo "availability")
    value: str  # <= 120 chars
    polarity: ConstraintPolarity
    confidence: float  # 0..1
    evidence_text: str  # <= 180 chars


class UniversalPreference(TypedDict, total=False):
    topic: str  # <= 48 chars
    value: str  # <= 120 chars
    strength: PreferenceStrength
    confidence: float
    evidence_text: str


class UniversalCommitment(TypedDict, total=False):
    who: CommitmentWho
    action: str  # <= 120 chars
    due: str  # <= 60 chars (string simple por ahora)
    status: CommitmentStatus
    confidence: float
    evidence_text: str


class UniversalEntity(TypedDict, total=False):
    name: str  # <= 120 chars
    type: EntityType
    role: str  # <= 48 chars
    confidence: float
    evidence_text: str


class UniversalSpeechAct(TypedDict, total=False):
    act: SpeechActType
    target: str  # <= 48 chars (p.ej. "price" / "planning")
    strength: PreferenceStrength
    confidence: float
    evidence_text: str


class UniversalState(TypedDict, total=False):
    goal: UniversalGoal
    constraints: List[UniversalConstraint]  # max 10
    preferences: List[UniversalPreference]  # max 10
    commitments: List[UniversalCommitment]  # max 10
    entities: List[UniversalEntity]  # max 12
    speech_acts: List[UniversalSpeechAct]  # max 6


# ---------- OpenClaim (open-world, cerrado) ----------
OpenClaimScope = Literal["universal", "negotiation", "other_domain"]
OpenClaimCategory = Literal[
    "emotion",
    "social_dynamics",
    "tactic",
    "risk",
    "identity",
    "preference",
    "constraint",
    "context",
    "quality",
    "other",
]


class OpenClaim(TypedDict, total=False):
    scope: OpenClaimScope
    category: OpenClaimCategory
    label: str  # snake_case ASCII, 1-32, regex ^[a-z][a-z0-9_]{0,31}$
    value: str  # <= 160 chars (string only v1)
    confidence: float  # 0..1
    evidence_text: str  # <= 180 chars
    turn_idx: int
    source: Literal["llm", "regex", "manual"]
    dedupe_key: str  # computed backend preferred (llm can send, but ignore)


class WorldState(TypedDict):
    schema_version: str
    world_buckets: Dict[str, List[Dict[str, Any]]]
    world_state_meta: "WorldStateMeta"


class WorldObservations(TypedDict):
    raw_fields: Dict[str, Any]


class EvidenceV2Claim(TypedDict):
    path: str
    value: Any | None
    polarity: EvidencePolarity
    unit: str | None
    qualifiers: Dict[str, Any]


class EvidenceV2Provenance(TypedDict):
    text: str
    span: tuple[int, int] | None
    source: EvidenceSource
    turn_idx: int
    raw: Dict[str, Any] | None


class EvidenceV2Record(TypedDict):
    claim: EvidenceV2Claim
    confidence: float
    dedupe_key: str
    provenance: EvidenceV2Provenance


class EvidenceV2Index(TypedDict):
    latest_by_path: Dict[str, EvidenceV2Record]
    best_by_path: Dict[str, EvidenceV2Record]
    recent_by_path: Dict[str, List[EvidenceV2Record]]


class WorldObservationsV2(TypedDict):
    claims: List[EvidenceV2Record]
    index: EvidenceV2Index


class WorldDerived(TypedDict):
    fields: Dict[str, Any]


class RequiredInput(TypedDict):
    key: str
    op: RequiredInputOp


class WorldStateMeta(TypedDict):
    last_update_source: Literal["regex", "llm", "mixed"]
    evidence_confidence_min: float
    updated_fields: List[str]
    turn_idx: int | None
    unknown_claims: List[Dict[str, Any]]
    error: str
    extractor_failed: bool


# ============ UNIVERSAL (para cualquier conversación) ============
EscalationSignal = Literal["up", "down", "none"]
CommitmentSignal = Literal["hard", "soft", "none"]


class BeliefUniversalMetrics(TypedDict, total=False):
    trust: float
    cooperation: float
    clarity: float
    engagement: float


class BeliefUniversalDynamics(TypedDict, total=False):
    interaction_health: InteractionHealth
    escalation: EscalationSignal
    looping: bool
    evasion: bool
    commitment: CommitmentSignal


class BeliefUniversalToM(TypedDict, total=False):
    other_goals: List[str]  # <= 6, each <= 80
    other_tactics: List[str]  # <= 6, each <= 80
    other_belief_about_me: List[str]  # <= 6, each <= 80
    confidence: float  # 0..1


class BeliefReasonItem(TypedDict, total=False):
    weight: float  # 0..1
    confidence: float  # 0..1
    evidence: str  # <= 180


class BehaviorGuidance(TypedDict, total=False):
    assertiveness: float
    verification_need: float
    trust_estimate: float
    conflict_risk: float
    pace_preference: float
    recommended_move: str
    epistemic_style: str


class BeliefUniversalState(TypedDict, total=False):
    metrics: BeliefUniversalMetrics
    dynamics: BeliefUniversalDynamics
    tom: BeliefUniversalToM
    reasons: Dict[str, BeliefReasonItem]  # validado por allowlist
    behavior_guidance: BehaviorGuidance


# ============ NEGOTIATION (plugin mental) ============
class BeliefNegotiationState(TypedDict, total=False):
    stance: Dict[str, Any]
    reasons: Dict[str, Any]
    hypotheses: List[str]
    hypotheses_structural: List[str]
    hypotheses_observational: List[str]
    evaluations: Dict[str, Any]
    tom: Dict[str, Any]


# ============ BeliefState principal v2 ============
class BeliefState(TypedDict, total=False):
    schema_version: str
    belief_buckets: Dict[str, List[Dict[str, Any]]]
    planner_signals: Dict[str, Any]


class RequiredBelief(TypedDict):
    key: str
    op: RequiredBeliefOp
    value: object


class PolicyDecision(TypedDict):
    policy_id: str
    reason: str
    micro_goal: str
    risk_posture: RiskPosture
    capabilities: Set[str] | None
    why_short: str
    inputs_used: List[str]


class PersonaProfile(TypedDict, total=False):
    persona_id: str
    role: str
    voice_register: Literal["formal", "neutral", "friendly", "technical", "natural"]
    values: List[str]
    hard_limits: List[str]
    do: List[str]
    dont: List[str]
    role_card: Dict[str, Any]
    experience: str
    big_five: Dict[str, str]
    trait_markers: List[str]
    persona_anchors: List[str]
    signature_line: str


class SceneProfile(TypedDict, total=False):
    scene_id: str
    setting: str
    macro_goal: str
    operational_context: List[str]
    disclaimers: List[str]
    scenario_card: Dict[str, Any]
    partner_name: str
    turn_topic: str


class StyleContract(TypedDict, total=False):
    style_id: str
    target_length: StyleLength
    format: StyleFormat
    max_words: int
    max_questions: int
    emoji_policy: EmojiPolicy
    markdown_allowed: bool
    bullets_max: int


class RenderState(TypedDict, total=False):
    persona_id: str
    scene_id: str
    style_id: str
    language: str
    persona_profile: Dict[str, Any]
    scene_profile: Dict[str, Any]
    style_contract: Dict[str, Any]


class RenderConstraints(TypedDict, total=False):
    forbid_claims: List[str]
    forbid_formats: List[str]
    forbid_behaviors: List[str]
    dialogue_dynamics: List[str]
    end_rule: Dict[str, Any]
    disallow_numbers: bool
    require_ask_if_missing: List[str]
    max_questions: Optional[int]
    epistemic_style: str
    must_hedge: bool
    verify_first: bool


class ExecutorOutput(TypedDict, total=False):
    response_text: str
    asked_question: bool
    requested_info_slots: List[str]
    tone_used: ToneUsed
    followup_intent: Optional[str]
    render_meta: Dict[str, Any]


class IntentHint(TypedDict):
    intent_active: bool
    intent_goal: str
    intent_type: str
    step_kind: str
    target_slot: str
    next_action_hint: str
    slots_missing: List[str]
    slots_filled_summary: str
    commitment_level: CommitmentLevel


class PhaseState(TypedDict):
    phase: NegotiationPhase
    phase_proposed: NegotiationPhase | LegacyNegotiationPhase | Literal[""]
    phase_effective: NegotiationPhase
    recovery_mode: bool
    recovery_stable_turns: int
    confidence: float
    reasons: List[str]
    last_updated_turn: int


ReasonKey = Literal[
    "price_signal",
    "deadline_signal",
    "other_buyer_signal",
    "concession_signal",
    "docs_signal",
    "tone_signal",
]




class PlanLedgerResolvedIntent(TypedDict):
    intent_id: str
    evidence: str
    turn_idx: int


class PlanLedgerOpenIntent(TypedDict):
    intent_id: str
    need: str


class PlanLedgerFailedIntent(TypedDict):
    intent_id: str
    reason: str
    attempts: int
    turn_idx: int


class PlanLedger(TypedDict):
    resolved_intents: List[PlanLedgerResolvedIntent]
    open_intents: List[PlanLedgerOpenIntent]
    failed_intents: List[PlanLedgerFailedIntent]
    asked_questions_recent: List[str]
    attempt_counters: Dict[str, int]


class ProgressState(TypedDict):
    conversation_mode: ConversationMode
    mode_confidence: float
    mode_last_switch_turn: int
    policy_pack_active: str
    render_state: RenderState
    render_constraints_struct: RenderConstraints
    last_executed_policy_id: str
    last_executed_policy_outcome: PolicyOutcome
    last_chosen_policy_id: str
    policy_last_outcome: Dict[str, PolicyOutcome]
    policy_attempts: Dict[str, int]
    loop_flags: List[str]
    turns_in_same_mode: int
    policy_state: PolicyState
    phase_state: PhaseState
    gate_state: "GateState"
    active_plan_status: Literal["none", "active", "completed", "interrupted"]
    active_plan: Dict[str, Any] | None
    advance_step: bool
    judgement_missing_streak: int
    last_judgement_status: str
    no_progress_same_step_turns: int
    last_plan_id: str
    plan_id_changes_window: int
    last_progress_update_turn: int
    plan_ledger: PlanLedger


class GateState(TypedDict):
    last_world_refresh_turn: int
    last_belief_refresh_turn: int
    last_planner_refresh_turn: int
    world_buckets_fingerprint_prev: str
    world_skip_count: int
    belief_skip_count: int
    planner_skip_count: int
    allowed_ids_hash_prev: str
    allowed_ids_hash_stable_count: int
    loop_flags_prev: List[str]
    input_shape_prev: Dict[str, object]
    last_interaction_signals: Dict[str, object]
    interaction_fingerprint_prev: Dict[str, object]
    interaction_fingerprint_version: int
    prev_user_message: str
    world_meta_fingerprint_prev: str


def default_world_state() -> WorldState:
    return {
        "schema_version": "v3",
        "world_buckets": {
            "offers": [],
            "concessions": [],
            "constraints": [],
            "interests": [],
            "claims": [],
            "requests": [],
            "context": [],
        },
        "world_state_meta": {
            "last_update_source": "llm",
            "evidence_confidence_min": 0.6,
            "updated_fields": [],
            "turn_idx": None,
            "unknown_claims": [],
            "error": "",
            "extractor_failed": False,
        },
    }


def default_belief_state() -> BeliefState:
    return {
        "schema_version": "v3",
        "belief_buckets": {
            "hypotheses": [],
            "strategy_notes": [],
            "risk_flags": [],
            "watch_items": [],
        },
        "planner_signals": {
            "interaction_health": "stable",
            "conflict_risk": 0.0,
            "recommended_move": "hold",
            "recovery_mode": False,
        },
    }


def default_persona_profile() -> PersonaProfile:
    return {
        "persona_id": "default",
        "role": "virtual assistant",
        "voice_register": "neutral",
        "values": ["clarity", "precision"],
        "hard_limits": ["no_internal_access", "no_physical_actions"],
        "do": ["be concise", "ask for missing context"],
        "dont": ["claim internal access", "pretend to act in the world"],
        "signature_line": "",
    }


def default_scene_profile() -> SceneProfile:
    return {
        "scene_id": "default_chat",
        "setting": "chat app",
        "macro_goal": "help the user with their objective",
        "operational_context": ["chat_only", "no_internal_systems"],
        "disclaimers": ["chat_only", "no_internal_systems"],
    }


def default_style_contract() -> StyleContract:
    return {
        "style_id": "default",
        "target_length": "short",
        "format": "plain",
        "max_questions": 2,
        "emoji_policy": "rare",
        "markdown_allowed": False,
        "bullets_max": 4,
    }


def default_render_state() -> RenderState:
    return {
        "persona_id": "default",
        "scene_id": "default_chat",
        "style_id": "default",
        "language": "es",
    }


def default_constraints_struct() -> RenderConstraints:
    return {
        "forbid_claims": ["access_internal_systems", "physical_actions_done"],
        "forbid_formats": ["markdown"],
        "forbid_behaviors": [],
        "dialogue_dynamics": [],
        "end_rule": {"when_stalled": False, "marker": ""},
        "disallow_numbers": False,
        "require_ask_if_missing": [],
        "max_questions": 2,
        "epistemic_style": "neutral",
        "must_hedge": False,
        "verify_first": False,
    }


def default_policy_state() -> PolicyState:
    return {
        "status": "inactive",
        "policy_id": "",
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "started_turn": 0,
        "last_turn": 0,
        "no_progress_turns": 0,
        "planner_request": "choose_policy",
        "slots_required": [],
        "slots_filled": {},
    }


def default_plan_ledger() -> PlanLedger:
    return {
        "resolved_intents": [],
        "open_intents": [],
        "failed_intents": [],
        "asked_questions_recent": [],
        "attempt_counters": {},
    }



def default_progress_state() -> ProgressState:
    return {
        "conversation_mode": "general",
        "mode_confidence": 0.0,
        "mode_last_switch_turn": 0,
        "policy_pack_active": "universal",
        "render_state": default_render_state(),
        "render_constraints_struct": default_constraints_struct(),
        "last_executed_policy_id": "",
        "last_executed_policy_outcome": "",
        "last_chosen_policy_id": "",
        "policy_last_outcome": {},
        "policy_attempts": {},
        "loop_flags": [],
        "turns_in_same_mode": 0,
        "policy_state": default_policy_state(),
        "active_plan_status": "none",
        "active_plan": None,
        "advance_step": False,
        "judgement_missing_streak": 0,
        "last_judgement_status": "",
        "no_progress_same_step_turns": 0,
        "last_plan_id": "",
        "plan_id_changes_window": 0,
        "last_progress_update_turn": 0,
        "plan_ledger": default_plan_ledger(),
        "phase_state": {
            "phase": "climate",
            "phase_proposed": "",
            "phase_effective": "climate",
            "recovery_mode": False,
            "recovery_stable_turns": 0,
            "confidence": 0.6,
            "reasons": [],
            "last_updated_turn": 0,
        },
        "gate_state": {
            "last_world_refresh_turn": 0,
            "last_belief_refresh_turn": 0,
            "last_planner_refresh_turn": 0,
            "world_buckets_fingerprint_prev": "",
            "world_skip_count": 0,
            "belief_skip_count": 0,
            "planner_skip_count": 0,
            "allowed_ids_hash_prev": "",
            "allowed_ids_hash_stable_count": 0,
            "loop_flags_prev": [],
            "input_shape_prev": {},
            "last_interaction_signals": {},
            "interaction_fingerprint_prev": {},
            "interaction_fingerprint_version": 1,
            "prev_user_message": "",
            "world_meta_fingerprint_prev": "",
        },
    }




def default_intent_state() -> dict:
    return {
        "status": "inactive",
        "steps": [],
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 0,
        "slots": {"slots_required": [], "slots_optional": [], "slots_filled": {}},
    }

def default_policy_decision() -> PolicyDecision:
    return {
        "policy_id": "rapport_build",
        "reason": "Fallback seguro para mantener buen clima.",
        "micro_goal": "Mantener tono cordial y abrir espacio para información útil.",
        "risk_posture": "low",
        "capabilities": None,
        "why_short": "",
        "inputs_used": [],
    }
