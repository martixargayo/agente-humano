from negotiation.gate_utils import input_shape_features, gate_world


def test_voice_question_direct_without_qmark():
    feats = input_shape_features("cuanto pides por el coche", modality="voice")
    assert feats["has_question_words"] is True
    assert feats["question_strength"] == "direct"


def test_voice_question_soft():
    feats = input_shape_features("me puedes decir cuanto cuesta", modality="voice")
    assert feats["question_strength"] == "soft"


def test_voice_short_ack():
    feats = input_shape_features("vale perfecto", modality="voice")
    assert feats["is_short_ack"] is True


def test_voice_negation_refusal():
    feats = input_shape_features("no me interesa", modality="voice")
    assert feats["has_negation"] is True
    assert feats["has_refusal_phrase"] is True


def test_voice_amount_mention_without_digits():
    feats = input_shape_features(
        "diez mil euros",
        modality="voice",
        conversation_mode="negotiation",
    )
    assert feats["has_amount_mention"] is True


def test_repeat_ratio_bucket_high():
    feats = input_shape_features(
        "vale perfecto",
        modality="voice",
        prev_text="vale perfecto",
    )
    assert feats["repeat_ratio_bucket"] == "high"


def test_gate_world_opens_on_interaction_changed():
    prev_features = input_shape_features("ok", modality="voice")
    curr_features = input_shape_features("ok", modality="voice")
    prev_fp = {
        "implicit_acceptance": False,
        "escalation_signal": "none",
        "loop_hint": False,
        "evasion_detected": False,
        "soft_commitment": False,
    }
    curr_fp = {
        "implicit_acceptance": True,
        "escalation_signal": "none",
        "loop_hint": False,
        "evasion_detected": False,
        "soft_commitment": False,
    }
    skip, reason, _meta = gate_world(
        user_message="ok",
        turn_count=2,
        last_refresh_turn=1,
        prev_features=prev_features,
        current_features=curr_features,
        interaction_fingerprint_prev=prev_fp,
        interaction_fingerprint_current=curr_fp,
        interval=3,
        modality="voice",
    )
    assert skip is False
    assert reason == "always_refresh_user_turn"
