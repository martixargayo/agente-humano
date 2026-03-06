from __future__ import annotations

from enum import Enum


class ThreadMode(str, Enum):
    conversation = "conversation"
    previous_response_id = "previous_response_id"


class NodeName(str, Enum):
    memory = "memory"
    planner = "planner"
    executor = "executor"


class PlannerStatus(str, Enum):
    plan = "plan"
    clarify = "clarify"
    refuse = "refuse"


class ExecutorStatus(str, Enum):
    deliver = "deliver"
    clarify = "clarify"
    refuse = "refuse"


class ConversationAct(str, Enum):
    acknowledge = "acknowledge"
    answer = "answer"
    ask_clarification = "ask_clarification"
    ask_followup = "ask_followup"
    propose = "propose"
    refuse = "refuse"


class SafetyPolicyAction(str, Enum):
    allow = "allow"
    clarify = "clarify"
    refuse = "refuse"
    block = "block"


class SafetyDomain(str, Enum):
    none = "none"
    medical = "medical"
    legal = "legal"
    financial = "financial"
    pii = "pii"
    dangerous_instruction = "dangerous_instruction"
    overclaim = "overclaim"


class StyleTone(str, Enum):
    neutral = "neutral"
    warm = "warm"
    firm = "firm"


class LengthBand(str, Enum):
    short = "short"
    medium = "medium"


class DirectnessLevel(str, Enum):
    soft = "soft"
    balanced = "balanced"
    direct = "direct"


class InitiativeLevel(str, Enum):
    reactive = "reactive"
    balanced = "balanced"
    proactive = "proactive"


class EmotionalIntensity(str, Enum):
    low = "low"
    medium = "medium"


class SafetyRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class StructuredCallSource(str, Enum):
    model = "model"
    refusal = "refusal"
    fallback = "fallback"
    parse_error = "parse_error"
    exception = "exception"


class SDKCompatibilityStatus(str, Enum):
    compatible = "compatible"
    below_minimum = "below_minimum"
    unknown = "unknown"
