from __future__ import annotations

from fastapi import HTTPException

from interfaz_usuario import services
from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY, resolve_public_context_selection
from sessions.state import SESSIONS, get_session_state


def _stored_context(user_id: str, session_id: str) -> dict:
    return get_session_state(user_id=user_id, session_id=session_id).world_state.get(NEGOTIATION_CONTEXT_WORLD_STATE_KEY, {})


def main() -> None:
    SESSIONS.clear()

    print('[baseline_default]')
    print(services.ensure_session(user_id='u_phase4_default', session_id='s_phase4_default'))
    print(_stored_context('u_phase4_default', 's_phase4_default'))

    print('\n[by_context_id]')
    print(services.ensure_session(user_id='u_phase4_context', session_id='s_phase4_context', context_id='baseline_current'))
    print(_stored_context('u_phase4_context', 's_phase4_context'))

    print('\n[by_public_slug]')
    print(resolve_public_context_selection(public_slug='negociacion').model_dump(mode='json'))
    print(services.ensure_session(user_id='u_phase4_slug', session_id='s_phase4_slug', public_slug='negociacion'))
    print(_stored_context('u_phase4_slug', 's_phase4_slug'))

    print('\n[input_conflict]')
    try:
        services.ensure_session(
            user_id='u_phase4_conflict',
            session_id='s_phase4_conflict',
            context_id='otro_contexto',
            public_slug='negociacion',
        )
    except HTTPException as exc:
        print({'status_code': exc.status_code, 'detail': exc.detail})

    print('\n[fixed_session_conflict]')
    services.ensure_session(user_id='u_phase4_fixed', session_id='s_phase4_fixed', public_slug='negociacion')
    try:
        services.ensure_session(user_id='u_phase4_fixed', session_id='s_phase4_fixed', context_id='otro_contexto')
    except HTTPException as exc:
        print({'status_code': exc.status_code, 'detail': exc.detail})
        print(_stored_context('u_phase4_fixed', 's_phase4_fixed'))

    print('\nresultado=ok')


if __name__ == '__main__':
    main()
