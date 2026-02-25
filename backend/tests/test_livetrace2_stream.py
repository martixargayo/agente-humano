from negotiation.telemetry.live_trace2 import (
    append_livetrace2_event,
    build_livetrace2_event,
    list_recent_livetrace2_events,
)


def test_livetrace2_buffer_roundtrip():
    event = build_livetrace2_event(
        user_id="u1",
        session_id="s1",
        session=None,
        trace_index=0,
        trace_item={"kind": "trace", "message": "hola"},
    )
    append_livetrace2_event(event)
    recent = list_recent_livetrace2_events(limit=1)
    assert recent
    assert recent[-1]["user_id"] == "u1"
    assert recent[-1]["session_id"] == "s1"


def test_livetrace2_generator_starts_with_connected_chunk():
    from app import _livetrace2_sse_generator

    gen = _livetrace2_sse_generator()
    first = next(gen)
    assert first == ": connected\n\n"
