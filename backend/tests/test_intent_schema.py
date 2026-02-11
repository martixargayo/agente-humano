from negotiation.validation import normalize_intent_state


def test_schema_steps_typed_only():
    raw = {
        "status": "active",
        "intent_type": "info_extract",
        "intent_goal": "Recoger datos",
        "steps": ["probe_open", "probe_narrow"],
        "step_idx": 0,
        "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
    }

    intent, issues = normalize_intent_state(raw)

    assert issues
    assert intent["steps"]
    assert all(isinstance(step, dict) for step in intent["steps"])
    assert all("kind" in step and "target_slot" in step and "success_if_filled" in step
               for step in intent["steps"])
