from __future__ import annotations

from fastapi import HTTPException

from interfaz_usuario import services
from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY
from sessions.state import SESSIONS, get_session_state


def _context_block(user_id: str, session_id: str) -> dict:
    state = get_session_state(user_id=user_id, session_id=session_id)
    return state.world_state.get(NEGOTIATION_CONTEXT_WORLD_STATE_KEY, {})


def main() -> None:
    SESSIONS.clear()

    default_payload = services.ensure_session(user_id="u_phase3_default", session_id="s_phase3_default")
    print("[default_baseline_session]")
    print(f"bootstrap_payload={default_payload}")
    print(f"context_storage_key=world_state['{NEGOTIATION_CONTEXT_WORLD_STATE_KEY}']")
    print(f"stored_context={_context_block('u_phase3_default', 's_phase3_default')}")

    explicit_payload = services.ensure_session(
        user_id="u_phase3_explicit",
        session_id="s_phase3_explicit",
        context_id="baseline_current",
    )
    print("\n[explicit_context_session]")
    print(f"bootstrap_payload={explicit_payload}")
    print(f"stored_context={_context_block('u_phase3_explicit', 's_phase3_explicit')}")

    inherited_payload = services.create_new_conversation(user_id="u_phase3_explicit", base_session_id="s_phase3_explicit")
    print("\n[new_conversation_inheritance]")
    print(f"new_session_id={inherited_payload['session_id']}")
    print(f"stored_context={_context_block('u_phase3_explicit', inherited_payload['session_id'])}")

    print("\n[conflict_policy]")
    try:
        services.ensure_session(
            user_id="u_phase3_explicit",
            session_id="s_phase3_explicit",
            context_id="otro_contexto",
        )
    except HTTPException as exc:
        print(f"status_code={exc.status_code}")
        print(f"detail={exc.detail}")
        print(f"stored_context_after_conflict={_context_block('u_phase3_explicit', 's_phase3_explicit')}")
    else:
        print("unexpected=no_conflict_raised")

    print("\nresultado=ok")


if __name__ == "__main__":
    main()
