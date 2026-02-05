import negotiation.intent_manager as intent_manager
from negotiation.intent_manager import update_intent_state
from negotiation.policy_planner import apply_intent_constraints
from negotiation.schemas import default_belief_state, default_intent_state, default_progress_state
from negotiation.schemas import default_world_state


def test_intent_starts_when_requires_multi_turn():
    world = default_world_state()
    world["universal_domain"]["message_is_vague"] = True
    belief = default_belief_state()
    progress = default_progress_state()
    intent, meta, hint = update_intent_state(
        prev_intent=default_intent_state(),
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende, ya veremos",
        turn_count=1,
        precedence=None,
    )

    assert intent["status"] == "active"
    assert intent["steps"]
    assert hint["intent_active"] is True
    assert hint["step_kind"]
    assert meta["intent_decision"] == "commit"


def test_intent_does_not_start_when_one_turn_sufficient(monkeypatch):
    monkeypatch.setenv("INTENT_START_UTILITY_THRESHOLD", "2.5")
    world = default_world_state()
    world["negotiation"]["price_mentioned"] = True
    world["negotiation"]["price_value"] = 9000
    belief = default_belief_state()
    progress = default_progress_state()

    updated, meta, _hint = update_intent_state(
        prev_intent=default_intent_state(),
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio 9000",
        turn_count=2,
        precedence=None,
    )

    assert updated["status"] == "inactive"
    assert meta["intent_decision"] == "inactive"


def test_build_steps_missing_empty_returns_close_next():
    steps = intent_manager.build_steps("info_extract", [])
    assert steps
    assert steps[0]["kind"] == "close_next"
    assert steps[0]["target_slot"] == ""
    assert steps[0]["success_if_filled"] == []


def test_step_advances_only_when_target_slot_progresses():
    world = default_world_state()
    world["negotiation"]["evidence_offered"] = True
    world["evidence_text"] = "tengo factura"
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
                {
                    "kind": "probe_narrow",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="tengo factura",
        turn_count=2,
        precedence=None,
    )

    assert updated["status"] == "active"
    assert updated["step_idx"] == 0
    assert meta["intent_decision"] == "continue"


def test_intent_succeeds_when_slots_complete():
    world = default_world_state()
    world["negotiation"]["price_mentioned"] = True
    world["negotiation"]["price_value"] = 9500
    world["negotiation"]["price_firm"] = True
    world["negotiation"]["price_firm_text"] = "precio fijo"
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar precio",
            "intent_type": "closing",
            "steps": [
                {"kind": "close_next", "target_slot": "price_firm", "success_if_filled": ["price_firm"]}
            ],
            "step_idx": 0,
            "slots": {
                "slots_required": ["price", "price_firm"],
                "slots_optional": [],
                "slots_filled": {},
            },
            "success_criteria": ["slots_required_complete", "firm_price_detected"],
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio fijo 9500",
        turn_count=3,
        precedence=None,
    )

    assert updated["status"] == "succeeded"
    assert meta["intent_decision"] == "succeed"
    assert hint["intent_active"] is False


def test_intent_progress_requires_new_evidence_key():
    prev_world = default_world_state()
    prev_world["evidence_items"] = [
        {
            "type": "PRICE",
            "field": "price_mentioned",
            "polarity": "affirm",
            "text": "precio 9000",
            "value": None,
            "source": "regex",
            "confidence": 0.7,
            "turn_idx": 1,
            "raw": None,
        }
    ]
    world = default_world_state()
    world["negotiation"]["price_mentioned"] = True
    world["evidence_items"] = list(prev_world["evidence_items"])

    assert intent_manager._evidence_delta_for_slot(prev_world, world, "price") is False

    world["evidence_items"].append(
        {
            "type": "PRICE",
            "field": "price_mentioned",
            "polarity": "affirm",
            "text": "precio 9200",
            "value": None,
            "source": "regex",
            "confidence": 0.7,
            "turn_idx": 2,
            "raw": None,
        }
    )

    assert intent_manager._evidence_delta_for_slot(prev_world, world, "price") is True


def test_intent_abandons_on_hard_trigger():
    world = default_world_state()
    belief = default_belief_state()
    belief["universal"]["dynamics"]["interaction_health"] = "tense"
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Extraer información",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["price"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="",
        turn_count=4,
        precedence=None,
    )

    assert updated["status"] == "abandoned"
    assert "interaction_tense" in updated["abandon_reasons"]
    assert meta["intent_decision"] == "abandon"


def test_planner_respects_intent_hard_preferences():
    allowed = ["info_extract_critical", "rapport_build", "deescalate_tension"]
    intent_hint = {
        "step_kind": "pressure_soft",
        "commitment_level": "hard",
    }

    constrained, preferred, meta = apply_intent_constraints(allowed, intent_hint)

    assert "deescalate_tension" in preferred
    assert constrained == ["deescalate_tension"]
    assert meta["planner_mode"] == "intent_forced"


def test_planner_soft_ranks_when_intersection_exists():
    allowed = ["rapport_build", "deescalate_tension", "info_extract_critical"]
    intent_hint = {
        "step_kind": "probe_open",
        "commitment_level": "soft",
    }

    constrained, preferred, meta = apply_intent_constraints(allowed, intent_hint)

    intersection = [pid for pid in preferred if pid in allowed]
    assert constrained[: len(intersection)] == intersection
    assert meta["planner_mode"] == "intent_soft_ranked"


def test_planner_soft_ranking_no_intersection_keeps_order():
    allowed = ["rapport_build", "deescalate_tension"]
    intent_hint = {
        "step_kind": "request_evidence",
        "commitment_level": "soft",
    }

    constrained, _preferred, meta = apply_intent_constraints(allowed, intent_hint)

    assert constrained == allowed
    assert meta["planner_mode"] == "intent_preferred_no_intersection"


def test_planner_hard_no_forced_sets_fallback():
    allowed = ["rapport_build", "info_extract_critical"]
    intent_hint = {
        "step_kind": "pressure_soft",
        "commitment_level": "hard",
    }

    constrained, _preferred, meta = apply_intent_constraints(allowed, intent_hint)

    assert constrained == []
    assert meta["planner_error"] == "intent_policy_unavailable"
    assert meta["planner_fallback_used"] is True


def test_vague_response_triggers_pivot_sequence():
    world = default_world_state()
    world["universal_domain"]["message_is_vague"] = True
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
                {
                    "kind": "probe_narrow",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
                {
                    "kind": "trade_incentive",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="no sé",
        turn_count=2,
        precedence=None,
    )

    assert updated["step_idx"] == 0
    assert meta["intent_decision"] == "continue"

    updated, meta, hint = update_intent_state(
        prev_intent=updated,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=3,
        precedence=None,
    )

    assert updated["step_idx"] == 0
    assert hint["step_kind"] == "probe_narrow"
    assert meta["intent_decision"] == "pivot"
    assert meta["pivot_reason"] == "vague"


def test_multi_turn_scoring_single_impl():
    assert hasattr(intent_manager, "score_multi_turn_start")
    assert not hasattr(intent_manager, "_should_require_multi_turn")
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()

    _, meta, _ = update_intent_state(
        prev_intent=default_intent_state(),
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=1,
        precedence=None,
    )

    assert any(reason.startswith("multi_turn_score:") for reason in meta["reasons"])


def test_slot_switch_retargets_next_missing():
    world = default_world_state()
    world["negotiation"]["batna_claimed"] = True
    world["negotiation"]["batna_text"] = "Tengo a mi primo interesado."
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "step_attempts": 1,
            "max_attempts_per_step": 2,
            "slots": {
                "slots_required": ["seller_batna", "seller_urgency_reason"],
                "slots_optional": [],
                "slots_filled": {
                    "seller_batna": {
                        "value": "ok",
                        "evidence": "Tengo a mi primo interesado.",
                        "confidence": 0.6,
                        "source": "world_state",
                    }
                },
            },
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="Mi primo ya lo quiere.",
        turn_count=2,
        precedence=None,
    )

    assert meta["intent_transition"] == "retarget"
    assert meta["retarget_slot"] == "seller_urgency_reason"
    assert updated["step_idx"] == 0
    assert updated["step_attempts"] == 0
    assert hint["target_slot"] == "seller_urgency_reason"


def test_retarget_guardrail_forces_step0_target(monkeypatch):
    def fake_build_steps(intent_type, missing):
        return [
            {
                "kind": "probe_open",
                "target_slot": "WRONG",
                "success_if_filled": [missing[0]],
            }
        ]

    monkeypatch.setattr(intent_manager, "build_steps", fake_build_steps)

    world = default_world_state()
    world["negotiation"]["batna_claimed"] = True
    world["negotiation"]["batna_text"] = "Tengo otra opción."
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 2,
            "slots": {
                "slots_required": ["seller_batna", "seller_urgency_reason"],
                "slots_optional": [],
                "slots_filled": {
                    "seller_batna": {
                        "value": "ok",
                        "evidence": "Tengo otra opción.",
                        "confidence": 0.6,
                        "source": "world_state",
                    }
                },
            },
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="Tengo otra opción.",
        turn_count=2,
        precedence=None,
    )

    assert meta["intent_transition"] == "retarget"
    assert meta["retarget_slot"] == "seller_urgency_reason"
    assert updated["steps"][0]["target_slot"] == "seller_urgency_reason"
    assert hint["target_slot"] == "seller_urgency_reason"


def test_other_buyer_details_has_text():
    world = default_world_state()
    world["negotiation"]["other_buyer_claimed"] = True
    world["negotiation"]["other_buyer_text"] = "Tengo otro comprador que ofrece 9.500€ esta semana."
    world["universal_domain"]["message_is_vague"] = True
    belief = default_belief_state()
    progress = default_progress_state()

    intent, _meta, _hint = update_intent_state(
        prev_intent=default_intent_state(),
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=1,
        precedence=None,
    )

    details = intent["slots"]["slots_filled"]["other_buyer_details"]["value"]
    assert isinstance(details, dict)
    assert set(details.keys()) >= {
        "claim_text",
        "offer_price",
        "timing",
        "claim_confidence",
    }
    assert "otro comprador" in details.get("claim_text", "")


def test_pivot_kind_progression():
    world = default_world_state()
    world["universal_domain"]["message_is_vague"] = True
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 1,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="no sé",
        turn_count=2,
        precedence=None,
    )

    assert meta["intent_decision"] == "pivot"
    assert hint["step_kind"] == "probe_narrow"

    updated, meta, hint = update_intent_state(
        prev_intent=updated,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=3,
        precedence=None,
    )

    assert meta["intent_decision"] == "pivot"
    assert hint["step_kind"] == "request_evidence"


def test_replan_transition_when_price_firm_detected():
    world = default_world_state()
    world["negotiation"]["price_firm_text"] = "precio fijo"
    world["negotiation"]["price_mentioned"] = True
    world["negotiation"]["price_value"] = 9000
    world["evidence_items"] = [
        {
            "type": "FIRMNESS",
            "text": "precio fijo",
            "value": None,
            "source": "regex",
            "confidence": 0.8,
            "turn_idx": 1,
            "raw": None,
        }
    ]
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Extraer información",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio fijo",
        turn_count=5,
        precedence=None,
    )

    assert updated["status"] == "active"
    assert updated["intent_type"] == "closing"
    assert meta["intent_decision"] == "replan"
    assert meta["intent_transition"] == "replan"
    assert meta["replan_to"] == "closing"


def test_unknown_success_criterion_fails():
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Test criterio",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
            "success_criteria": ["unknown_criterion"],
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=2,
        precedence=None,
    )

    assert updated["status"] == "active"
    assert "unknown_success_criterion:unknown_criterion" in meta["reasons"]


def test_hydrates_legacy_steps_with_unknown_targets():
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": ["ask_open"],
            "step_idx": 0,
            "step_attempts": 1,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=2,
        precedence=None,
    )

    assert updated["status"] == "active"
    assert hint["target_slot"] != "unknown"
    assert meta["reasons"] and "steps_hydrated" in meta["reasons"]


def test_hydration_missing_empty_does_not_break_hint():
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar",
            "intent_type": "info_extract",
            "steps": [],
            "step_idx": 0,
            "slots": {"slots_required": [], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="ok",
        turn_count=2,
        precedence=None,
    )

    assert updated["status"] == "active"
    assert "steps_hydrated" in meta["reasons"]
    assert "step_kind" in hint


def test_intent_abandons_after_no_progress(monkeypatch):
    monkeypatch.setenv("INTENT_NO_PROGRESS_ABORT_TURNS", "2")
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, _meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="",
        turn_count=2,
        precedence=None,
    )
    updated, meta, _hint = update_intent_state(
        prev_intent=updated,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="",
        turn_count=3,
        precedence=None,
    )

    assert updated["status"] == "abandoned"
    assert "no_progress" in updated["abandon_reasons"]
    assert meta["intent_decision"] == "abandon"


def test_firmness_requires_confident_evidence_for_replan(monkeypatch):
    monkeypatch.setenv("INTENT_FIRMNESS_REPLAN_THRESHOLD", "0.7")
    world = default_world_state()
    world["negotiation"]["price_firm_text"] = "no negocio"
    world["negotiation"]["price_mentioned"] = False
    world["evidence_items"] = [
        {
            "type": "FIRMNESS",
            "text": "no negocio",
            "value": None,
            "source": "regex",
            "confidence": 0.4,
            "turn_idx": 1,
            "raw": None,
        }
    ]
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="no negocio",
        turn_count=2,
        precedence=None,
    )

    assert updated["intent_type"] == "info_extract"
    assert meta["intent_decision"] != "replan"
