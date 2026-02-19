from __future__ import annotations

from ..specs.world_keys import (
    ALLOWED_UNIVERSAL_DOMAIN_KEYS,
    ALLOWED_NEGOTIATION_DOMAIN_KEYS,
)

WORLD_EXTRACTOR_V3_SYSTEM_PROMPT = """
You are a strict JSON extractor.
Return ONLY valid JSON. No markdown. No extra text.
Do not invent keys. Follow the schema exactly.
""".strip()

UNIVERSAL_DOMAIN_SPEC = """
universal_domain_patch: object with ONLY keys in ALLOWED_UNIVERSAL_DOMAIN_KEYS.
If unsure, use {}.
""".strip()

NEGOTIATION_DOMAIN_SPEC = """
negotiation_domain_patch: object with ONLY keys in ALLOWED_NEGOTIATION_DOMAIN_KEYS.
If conversation_mode == "negotiation", extract all supported negotiation signals.
If conversation_mode != "negotiation", you MAY still emit clear high-precision negotiation signals
(e.g., urgency/deadline/constraints/evidence) with conservative confidence and literal evidence.
Do not hallucinate values; prefer {} over guesses.
If unsure, use {}.
""".strip()

UNIVERSAL_SPEC = """
universal_patch: object with keys:
- goal: {summary<=120, confidence 0..1, evidence_text<=180} or {}
- constraints: list<=10 of {kind, key<=48, value<=120, polarity, confidence, evidence_text<=180}
- preferences: list<=10 of {topic<=48, value<=120, strength, confidence, evidence_text<=180}
- commitments: list<=10 of {who, action<=120, due<=60, status, confidence, evidence_text<=180}
- entities: list<=12 of {name<=120, type, role<=48, confidence, evidence_text<=180}
- speech_acts: list<=6 of {act, target<=48, strength, confidence, evidence_text<=180}
If unsure, use empty lists and {}.
""".strip()

OPEN_CLAIMS_SPEC = """
open_claims: list<=8 of:
{scope, category, label snake_case ASCII 1..32, value<=160, confidence 0..1, evidence_text<=180}
label must match ^[a-z][a-z0-9_]{0,31}$.
If none, return [].
""".strip()

OUTPUT_SCHEMA = """
Output JSON schema:
{
  "schema_version": "world_extractor_v3",
  "universal_domain_patch": { ... },
  "negotiation_domain_patch": { ... },
  "universal_patch": { ... },
  "open_claims": [ ... ]
}
""".strip()

WORLD_EXTRACTOR_V3_USER_PROMPT = f"""
Extract structured updates for world_state.

conversation_mode: {{conversation_mode}}

CURRENT user_message:
{{user_message}}

PREVIOUS world_state (json):
{{prev_world_state_json}}

CURRENT belief_state (json):
{{belief_state_json}}

RULES:
- {OUTPUT_SCHEMA}
- {UNIVERSAL_DOMAIN_SPEC}
- {NEGOTIATION_DOMAIN_SPEC}
- {UNIVERSAL_SPEC}
- {OPEN_CLAIMS_SPEC}

ALLOWED_UNIVERSAL_DOMAIN_KEYS:
{ALLOWED_UNIVERSAL_DOMAIN_KEYS}

ALLOWED_NEGOTIATION_DOMAIN_KEYS:
{ALLOWED_NEGOTIATION_DOMAIN_KEYS}

Return ONLY JSON.
""".strip()
