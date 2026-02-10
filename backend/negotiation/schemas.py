# backend/negotiation/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Set, TypedDict
InteractionHealth = Literal["stable", "tense", "stalled"]
RiskPosture = Literal["low", "mid", "high"]
PolicyOutcome = Literal["good", "neutral", "bad", ""]
ToneSignal = Literal["neutral", "friendly", "tense"]
ToneUsed = Literal["friendly", "neutral", "tense"]
ConversationMode = Literal["general", "negotiation"]
StyleLength = Literal["short", "medium", "long"]
StyleFormat = Literal["plain", "bullets", "qa"]
EmojiPolicy = Literal["never", "rare", "allowed"]
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
NegotiationPhase = Literal["opening", "discovery", "bargaining", "closing", "recovery"]


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
    universal_domain: Dict[str, Any]
    negotiation: Dict[str, Any]
    universal_state: "UniversalState"
    open_claims: List["OpenClaim"]
    evidence_items: List["EvidenceItem"]
    world_observations: "WorldObservations"
    world_observations_v2: "WorldObservationsV2"
    world_derived: "WorldDerived"
    world_state_meta: "WorldStateMeta"


class EvidenceItem(TypedDict):
    type: EvidenceType
    field: str
    polarity: EvidencePolarity
    text: str
    value: Any | None
    source: EvidenceSource
    confidence: float
    turn_idx: int | None
    span: tuple[int, int] | None
    raw: Dict[str, Any] | None


class WorldObservations(TypedDict):
    raw_fields: Dict[str, Any]
    evidence_items: List["EvidenceItem"]


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
    # v2
    universal: BeliefUniversalState
    negotiation: BeliefNegotiationState

    # mirrors legacy (compat)
    dynamics: BeliefUniversalDynamics
    tom: BeliefUniversalToM
    stance: Dict[str, Any]
    reasons: Dict[str, Any]
    hypotheses: List[str]
    hypotheses_structural: List[str]
    hypotheses_observational: List[str]
    evaluations: Dict[str, Any]


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
    voice_register: Literal["formal", "neutral", "friendly", "technical"]
    values: List[str]
    hard_limits: List[str]
    do: List[str]
    dont: List[str]
    signature_line: str


class SceneProfile(TypedDict, total=False):
    scene_id: str
    setting: str
    macro_goal: str
    operational_context: List[str]
    disclaimers: List[str]


class StyleContract(TypedDict, total=False):
    style_id: str
    target_length: StyleLength
    format: StyleFormat
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
    intent_state: IntentState
    policy_state: PolicyState
    phase_state: PhaseState
    gate_state: "GateState"


class GateState(TypedDict):
    last_world_refresh_turn: int
    last_belief_refresh_turn: int
    last_planner_refresh_turn: int
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
    universal_state_fingerprint_prev: str


def default_universal_state() -> UniversalState:
    return {
        "goal": {},
        "constraints": [],
        "preferences": [],
        "commitments": [],
        "entities": [],
        "speech_acts": [],
    }


def default_world_state() -> WorldState:
    return {
        "schema_version": "v1",
        "universal_domain": {
            "message_is_vague": False,
            "tone_signal": "neutral",
            "tone_confidence": 0.0,
        },
        "negotiation": {
            "price_mentioned": False,
            "price_value": None,
            "price_firm": False,
            "price_firm_text": "",
            "deadline_claimed": False,
            "deadline_text": "",
            "deadline_days": None,
            "deadline_kind": "",
            "urgency_claimed": False,
            "urgency_text": "",
            "urgency_reason": "",
            "other_buyer_claimed": False,
            "other_buyer_text": "",
            "other_buyer_offer_price": None,
            "other_buyer_timing_text": "",
            "concession_made": False,
            "concession_text": "",
            "batna_claimed": False,
            "batna_text": "",
            "min_price_claimed": False,
            "min_price_text": "",
            "docs_claimed": False,
            "docs_types": [],
            "evidence_offered": False,
            "evidence_text": "",
        },
        "universal_v2": {
            "clarity": {"is_vague": False, "missing_info": [], "ambiguity_types": [], "confidence": 0.0},
            "affect": {"tone": "neutral", "confidence": 0.0, "sentiment": "neutral", "arousal": "medium"},
            "interaction": {"cooperation": 0.5, "friction": 0.0, "boundary": False, "loop": False, "commitment_signal": 0.0},
            "intent": {"act": "inform", "confidence": 0.0},
            "commitments": [],
        },
        "negotiation_v2": {
            "subject": {"item": "", "context": "", "attributes": {}},
            "offers": [],
            "constraints": [],
            "interests": [],
            "concessions": [],
            "time_pressure": {"deadline_text": "", "deadline_date": None, "window_days": None, "urgency": 0.0, "reason": "", "status": "unverified", "confidence": 0.0},
            "leverage_claims": [],
            "evidence": [],
            "agreement_state": {"state": "none", "next_step": "", "open_points": [], "confidence": 0.0},
        },
        "universal_state": default_universal_state(),
        "open_claims": [],
        "evidence_items": [],
        "world_observations": {
            "raw_fields": {},
            "evidence_items": [],
        },
        "world_observations_v2": {
            "claims": [],
            "index": {
                "latest_by_path": {},
                "best_by_path": {},
                "recent_by_path": {},
            },
        },
        "world_derived": {"fields": {}},
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
    uni: BeliefUniversalState = {
        "metrics": {"trust": 0.5, "cooperation": 0.5, "clarity": 0.5, "engagement": 0.5},
        "dynamics": {
            "interaction_health": "stable",
            "escalation": "none",
            "looping": False,
            "evasion": False,
            "commitment": "none",
        },
        "tom": {"other_goals": [], "other_tactics": [], "other_belief_about_me": [], "confidence": 0.0},
        "reasons": {},
    }
    neg: BeliefNegotiationState = {
        "stance": {},
        "reasons": {},
        "hypotheses": [],
        "hypotheses_structural": [],
        "hypotheses_observational": [],
        "evaluations": {},
        "tom": {},
    }
    uni["behavior_guidance"] = {
        "assertiveness": 0.5,
        "verification_need": 0.5,
        "trust_estimate": 0.5,
        "conflict_risk": 0.0,
        "pace_preference": 0.5,
        "recommended_move": "hold",
        "epistemic_style": "neutral",
    }
    uni["tom"]["hypotheses"] = []
    return {
        "schema_version": "v2",
        "universal": uni,
        "negotiation": neg,
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
        "intent_state": default_intent_state(),
        "policy_state": default_policy_state(),
        "phase_state": {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": [],
            "last_updated_turn": 0,
        },
        "gate_state": {
            "last_world_refresh_turn": 0,
            "last_belief_refresh_turn": 0,
            "last_planner_refresh_turn": 0,
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
            "universal_state_fingerprint_prev": "",
        },
    }


def default_intent_state() -> IntentState:
    return {
        "status": "inactive",
        "intent_goal": "",
        "intent_type": "info_extract",
        "steps": [],
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "success_criteria": [],
        "slots": {
            "slots_required": [],
            "slots_optional": [],
            "slots_filled": {},
        },
        "confidence": 0.0,
        "no_progress_turns": 0,
        "slot_fill_count": 0,
        "slot_fill_count_recent": 0,
        "created_turn": 0,
        "last_turn": 0,
        "continue_until": "",
        "abandon_reasons": [],
        "last_observation": "",
        "next_action_hint": "",
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
