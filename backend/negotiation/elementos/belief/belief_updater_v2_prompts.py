BELIEF_UPDATER_V2_SYSTEM_PROMPT = """
You are a strict JSON belief updater.
Return ONLY valid JSON. No markdown. No extra keys.
"""

OUTPUT_SCHEMA = """
Output JSON schema:
{
  "schema_version":"belief_updater_v2",
  "universal_patch": { ... },
  "negotiation_patch": { ... },
  "belief_buckets_patch": {
    "hypotheses": [
      {"text":"... (0.86)", "confidence":0.86, "status":"active|weakening|new"}
    ],
    "strategy_notes": [{"text":"...", "confidence":0.70, "status":"active"}],
    "risk_flags": [{"text":"...", "confidence":0.55, "status":"active"}],
    "watch_items": [{"text":"...", "confidence":0.60, "status":"active"}]
  },
  "meta": { ... }
}
"""

UNIVERSAL_SPEC = """
universal_patch can be conservative and minimal. Keep existing schema compatibility.
"""

NEGOTIATION_SPEC = """
negotiation_patch can be {} when not needed.
"""

BELIEF_BUCKET_RULES = """
belief_buckets_patch rules:
- Update-not-rewrite: prefer adjusting confidence of existing hypotheses.
- Keep hypotheses stable; avoid creating many new ones.
- Max active hypotheses target: 6.
- Hypothesis text MUST end with confidence in parentheses, e.g. "Alta urgencia por liquidez hoy. (0.86)".
- If world shows repeated pattern (more money today <-> future/service concession), increase confidence of existing related hypotheses.
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
- {belief_bucket_rules}

Return ONLY JSON.
"""
