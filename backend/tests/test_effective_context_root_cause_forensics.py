from __future__ import annotations

from interfaz_usuario import services as interfaz_services
from negociacion.optimizador import services as optimizer_services
from scripts.forensics_effective_context_root_cause import build_report


def test_root_cause_report_finds_pre_memory_divergence_when_residual_exists():
    report = build_report()
    residual = report["scenarios"]["residual_interfaz"]

    assert residual["first_node_divergence"] == {"node": "memory", "path": "recent_dialogue_short.length"}
    assert residual["memory_input_build_first_diff"] == "recent_dialogue_len"


def test_new_conversation_session_ids_are_unique_across_surfaces():
    user_id = "u_collision"
    base_session = "s_collision"

    interfaz_session = interfaz_services.create_new_conversation(user_id=user_id, base_session_id=base_session)["session_id"]
    optimizer_session = optimizer_services.new_conversation_session(
        optimizer_session_id="forensics",
        user_id=user_id,
        session_id=base_session,
    )["session_id"]

    assert interfaz_session != optimizer_session
    assert "__newconv__" in interfaz_session
    assert "__newconv__" in optimizer_session
