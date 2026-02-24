from negotiation.schemas import default_world_state
from negotiation.world_state_updater import update_world_state


class _QueueDeps:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def execute(self, messages):
        self.messages.append(messages)
        if not self.payloads:
            raise AssertionError("no payload available")
        return self.payloads.pop(0)


def test_multi_item_single_turn_keeps_claims_and_offers():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{' \
        '"offers":[{"text":"Ofrece cubrir una reparación","confidence":0.8,"raw_text":"yo cubro la reparación","source_turn":1}],'
        '"concessions":[],"constraints":[],"interests":[],'
        '"claims":[{"text":"Mantenimiento anual realizado","confidence":0.82,"raw_text":"el mantenimiento fue anual","source_turn":1}],'
        '"requests":[],"context":[]},"meta":{"negotiation_signal_detected":true}}'
    ])
    world, _ = update_world_state(default_world_state(), "mantenimiento anual y cubro reparación", turn_count=1, deps=deps)
    assert len(world["world_buckets"]["claims"]) == 1
    assert len(world["world_buckets"]["offers"]) == 1


def test_multi_item_caps_global_max_items_per_turn():
    make_items = lambda prefix, n: ",".join(
        f'{{"text":"{prefix} {i}","confidence":0.8,"raw_text":"{prefix} {i}","source_turn":1}}' for i in range(1, n + 1)
    )
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{' \
        f'"claims":[{make_items("claim", 5)}],"offers":[{make_items("offer", 2)}],"requests":[{make_items("request", 2)}],'
        f'"concessions":[{make_items("concession", 2)}],"constraints":[],"interests":[],"context":[]'
        '},"meta":{}}'
    ])
    world, meta = update_world_state(default_world_state(), "mensaje", turn_count=1, deps=deps)
    total_kept = sum(len(v) for v in world["world_buckets"].values() if isinstance(v, list))
    assert total_kept == 8
    assert meta["postprocess_global_trimmed"] is True


def test_context_short_answer_uses_last_question_to_extract_two_claims():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{' \
        '"claims":[{"text":"Mantenimiento anual","confidence":0.85,"raw_text":"Se hicieron anualmente","source_turn":3},'
        '{"text":"Tiene documentación","confidence":0.86,"raw_text":"sí tengo documentación","source_turn":3}],'
        '"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}'
    ])
    world, _ = update_world_state(
        default_world_state(),
        "Se hicieron anualmente y sí tengo documentación.",
        turn_count=3,
        deps=deps,
        last_assistant_question="¿Cuándo se hicieron los mantenimientos y tienes documentación?",
        current_step_micro_goal="confirmar mantenimiento",
        success_criteria=["mantenimiento", "documentacion"],
        missing_signals=["mantenimiento"],
        expected_slots=["world_buckets.claims"],
    )
    assert len(world["world_buckets"]["claims"]) == 2


def test_context_always_on_long_answer_keeps_extra_signal():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{' \
        '"claims":[{"text":"Mantenimiento anual","confidence":0.8,"raw_text":"anualmente","source_turn":2}],'
        '"offers":[{"text":"Compromiso de compartir facturas","confidence":0.8,"raw_text":"te comparto facturas","source_turn":2}],'
        '"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}'
    ])
    world, _ = update_world_state(
        default_world_state(),
        "Anualmente y te comparto facturas hoy.",
        turn_count=2,
        deps=deps,
        last_assistant_question="¿Frecuencia y pruebas?",
        current_step_micro_goal="cerrar evidencia",
    )
    assert world["world_buckets"]["claims"]
    assert world["world_buckets"]["offers"]


def test_short_answer_owner_question_without_numbers_still_extracts_claim():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{' \
        '"claims":[{"text":"Comprado nuevo / único propietario","confidence":0.81,"raw_text":"Lo compré nuevo","source_turn":4}],'
        '"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}'
    ])
    world, meta = update_world_state(
        default_world_state(),
        "Lo compré nuevo",
        turn_count=4,
        deps=deps,
        last_assistant_question="¿Cuántos propietarios ha tenido?",
        current_step_micro_goal="confirmar historial de propietarios",
        success_criteria=["propietarios"],
        missing_signals=["numero_propietarios"],
    )
    assert world["world_buckets"]["claims"]
    assert world["world_buckets"]["claims"][0]["text"].lower().startswith("comprado nuevo")
    assert meta.get("extractor_used") is True


def test_contradiction_keeps_both_claims_and_sets_meta():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"No lo compró nuevo","confidence":0.8,"raw_text":"No lo compré nuevo","source_turn":1}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}',
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Lo compró nuevo","confidence":0.8,"raw_text":"Lo compré nuevo","source_turn":2}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{"contradictions_detected":true,"contradictions":[{"topic":"propiedad","previous_quote":"No lo compré nuevo","current_quote":"Lo compré nuevo","note":"Antes dijo que no lo compró nuevo, ahora dice que sí."}]}}'
    ])
    world1, _ = update_world_state(default_world_state(), "No lo compré nuevo", turn_count=1, deps=deps)
    world2, meta2 = update_world_state(world1, "Lo compré nuevo", turn_count=2, deps=deps)
    assert len(world2["world_buckets"]["claims"]) == 2
    assert meta2["contradictions_detected"] is True
    assert "Antes" in meta2["contradictions"][0]["note"]


def test_contradiction_without_raw_text_previous_quote_from_text_fragment():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Cambio de versión","confidence":0.8,"raw_text":"Lo compré nuevo","source_turn":2}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{"contradictions_detected":true,"contradictions":[{"topic":"propiedad","previous_quote":"No lo compré nuevo en 2020","current_quote":"Lo compré nuevo","note":"Antes dijo que no lo compró nuevo, ahora dice que sí."}]}}'
    ])
    prev = default_world_state()
    prev["world_buckets"]["claims"] = [{"text": "No lo compré nuevo en 2020", "confidence": 0.7, "raw_text": "", "source_turn": 1}]
    world, meta = update_world_state(prev, "Lo compré nuevo", turn_count=2, deps=deps)
    prompt = deps.messages[0][1]["content"]
    assert "No lo compré nuevo en 2020" in prompt
    assert meta["contradictions"][0]["previous_quote"] == "No lo compré nuevo en 2020"
    assert world["world_state_meta"]["last_conflict_turn"] == 2


def test_dedupe_exact_match_normalized_keeps_single_item():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Tiene documentación","confidence":0.8,"raw_text":"Sí tengo documentación","source_turn":1},{"text":"Tiene documentación","confidence":0.7,"raw_text":"  sí   tengo documentación ","source_turn":1}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}'
    ])
    world, meta = update_world_state(default_world_state(), "sí tengo documentación", turn_count=1, deps=deps)
    assert len(world["world_buckets"]["claims"]) == 1
    assert meta["postprocess_exact_deduped"] == 1


def test_integration_four_turns_accumulates_caps_and_contradictions():
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Mantenimiento anual","confidence":0.8,"raw_text":"anual","source_turn":1}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}',
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"offers":[{"text":"Incluye traslado","confidence":0.8,"raw_text":"incluyo traslado","source_turn":2}],"claims":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}',
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"No lo compró nuevo","confidence":0.8,"raw_text":"No lo compré nuevo","source_turn":3}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}',
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Lo compró nuevo","confidence":0.8,"raw_text":"Lo compré nuevo","source_turn":4}],"offers":[],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{"contradictions_detected":true,"contradictions":[{"topic":"propiedad","previous_quote":"No lo compré nuevo","current_quote":"Lo compré nuevo","note":"Antes dijo no nuevo, ahora nuevo."}]}}'
    ])
    world = default_world_state()
    meta_last = {}
    for turn, msg in enumerate(["anual", "incluyo traslado", "No lo compré nuevo", "Lo compré nuevo"], start=1):
        world, meta_last = update_world_state(world, msg, turn_count=turn, deps=deps)
    assert world["world_buckets"]["claims"]
    assert world["world_buckets"]["offers"]
    assert meta_last["contradictions_detected"] is True
    assert world["world_state_meta"]["conflicts_count"] == 1
