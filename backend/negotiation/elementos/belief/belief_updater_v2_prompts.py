BELIEF_UPDATER_V2_SYSTEM_PROMPT = """
You are a strict JSON belief updater.
Return ONLY valid JSON. No markdown. No extra keys.
Your job is to update beliefs conservatively.
"""

UNIVERSAL_SPEC = """
universal_patch must contain:
- metrics: {trust, cooperation, clarity, engagement} each 0..1
- dynamics: {interaction_health stable|tense|stalled, escalation up|down|none, looping bool, evasion bool, commitment hard|soft|none}
- tom: {other_goals[], other_tactics[], other_belief_about_me[], confidence 0..1}
- reasons: object with ONLY keys from allowlist:
  tone_shift, evasion_signal, boundary_signal, loop_signal, commitment_signal, cooperation_signal, clarity_signal
Each reason item: {weight 0..1, confidence 0..1, evidence_text<=180}
Be conservative: do not swing metrics wildly.
"""

NEGOTIATION_SPEC = """
negotiation_patch:
- Only fill if conversation_mode == "negotiation" OR world contains negotiation signals (price/deadline/other_buyer/etc.)
- Otherwise negotiation_patch must be {}.
Do not invent new negotiation schema keys; follow existing repo structure.
"""

OUTPUT_SCHEMA = """
Output JSON schema:
{
 "schema_version":"belief_updater_v2",
 "universal_patch": { ... },
 "negotiation_patch": { ... },
 "meta": { ... }
}
"""

BELIEF_UPDATER_V2_USER_PROMPT = """
Update belief_state using current world_state, world_diff, and previous belief_state.

conversation_mode: {conversation_mode}

CURRENT user_message:
{user_message}

WORLD_STATE (json):
{world_state_json}

WORLD_DIFF (json):
{world_diff_json}

PREVIOUS BELIEF_STATE (json):
{prev_belief_json}

RULES:
- {output_schema}
- {universal_spec}
- {negotiation_spec}

Return ONLY JSON.
"""
