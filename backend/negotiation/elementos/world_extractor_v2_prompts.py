WORLD_EXTRACTOR_V2_SYSTEM_PROMPT = """
You are a strict JSON extractor for a conversation agent.
Return ONLY valid JSON. No markdown. No extra keys.
You MUST respect the output schema exactly.
"""

# UNIVERSAL (always fill when confident; safe to be empty)
UNIVERSAL_SPEC = """
universal_patch: object with keys:
- goal: {summary<=120, confidence 0..1, evidence_text<=180} or {}
- constraints: list<=10 of {kind, key<=48, value<=120, polarity, confidence, evidence_text<=180}
- preferences: list<=10 of {topic<=48, value<=120, strength, confidence, evidence_text<=180}
- commitments: list<=10 of {who, action<=120, due<=60, status, confidence, evidence_text<=180}
- entities: list<=12 of {name<=120, type, role<=48, confidence, evidence_text<=180}
- speech_acts: list<=6 of {act, target<=48, strength, confidence, evidence_text<=180}
If unsure, use empty lists and {}.
"""

OPEN_CLAIMS_SPEC = """
open_claims: list<=8 of:
{scope, category, label snake_case ASCII 1..32, value<=160, confidence 0..1, evidence_text<=180}
label must match ^[a-z][a-z0-9_]{0,31}$.
If none, return [].
"""

# NEGOTIATION (domain_patch only when conversation_mode == "negotiation")
ALLOWED_DOMAIN_WORLD_KEYS = [
    "price_mentioned",
    "price_value",
    "price_firm",
    "price_firm_text",
    "deadline_claimed",
    "deadline_text",
    "deadline_days",
    "deadline_kind",
    "urgency_claimed",
    "urgency_text",
    "urgency_reason",
    "other_buyer_claimed",
    "other_buyer_text",
    "other_buyer_offer_price",
    "other_buyer_timing_text",
    "concession_made",
    "concession_text",
    "batna_claimed",
    "batna_text",
    "min_price_claimed",
    "min_price_text",
    "docs_claimed",
    "docs_types",
    "evidence_offered",
    "evidence_text",
    "message_is_vague",
    "tone_signal",
    "tone_confidence",
]

NEGOTIATION_SPEC = """
domain_patch: object with ONLY keys in ALLOWED_DOMAIN_WORLD_KEYS.
If conversation_mode != "negotiation", domain_patch MUST be {}.
Do NOT invent keys.
"""

OUTPUT_SCHEMA = """
Output JSON schema:
{
  "schema_version": "world_extractor_v2",
  "domain_patch": { ... },
  "universal_patch": { ... },
  "open_claims": [ ... ]
}
"""

WORLD_EXTRACTOR_V2_USER_PROMPT = """
Extract structured updates for world_state.

conversation_mode: {conversation_mode}

CURRENT user_message:
{user_message}

PREVIOUS world_state (json):
{prev_world_state_json}

CURRENT belief_state (json):
{belief_state_json}

RULES:
- {output_schema}
- {universal_spec}
- {open_claims_spec}
- {negotiation_spec}
Return ONLY JSON.
"""
