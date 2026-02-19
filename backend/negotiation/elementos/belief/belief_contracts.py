# ============ UNIVERSAL (FIRST) ============
UNIVERSAL_REASON_KEYS = {
    "tone_shift",
    "evasion_signal",
    "boundary_signal",
    "loop_signal",
    "commitment_signal",
    "cooperation_signal",
    "clarity_signal",
    "constraint_signal",
    "urgency_signal",
    "preference_signal",
    "market_demand_uncertainty",
}

UNIVERSAL_LIMITS = {
    "tom_list_max": 6,
    "tom_item_max_len": 80,
    "reason_evidence_max_len": 180,
    "max_step_metrics": 0.10,
}

# ============ NEGOTIATION (SECOND) ============
# (En PR3 no añadimos nuevas reason keys de negociación; usamos las existentes del repo.)
NEGOTIATION_LIMITS = {
    "max_step_stance": 0.10,
}
