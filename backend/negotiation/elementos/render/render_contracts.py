# ============ UNIVERSAL FIRST ============
RENDER_LIMITS = {
    "response_text_max_len": 900,
    "requested_slots_max": 6,
    "why_short_max_len": 220,
}

CRITICAL_VIOLATION_CODES = {
    "claims_internal_access",
    "claims_physical_action_done",
    "dangerous_instruction",
    "privacy_leak",
}

PERSONA_VOICE_REGISTERS = {"formal", "neutral", "friendly", "technical", "natural"}
STYLE_LENGTHS = {"very_short", "short", "medium", "long"}
STYLE_FORMATS = {"plain", "bullets", "qa"}
STYLE_EMOJI_POLICIES = {"none", "never", "rare", "allowed"}

# ============ NEGOTIATION SECOND ============
NEGOTIATION_RENDER_DEFAULTS = {
    "disallow_numbers_when_guarded": True,
}
