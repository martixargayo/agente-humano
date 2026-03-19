from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app
from interfaz_usuario import services
from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY, resolve_public_context_selection
from sessions.state import SESSIONS, get_session_state


class Phase4PublicContextSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        self.client = TestClient(app)

    def test_bootstrap_without_context_id_or_public_slug_uses_default_baseline(self) -> None:
        payload = services.ensure_session(user_id="u_p4_default", session_id="s_p4_default")
        state = get_session_state(user_id="u_p4_default", session_id="s_p4_default")

        self.assertEqual(payload["session_id"], "s_p4_default")
        self.assertEqual(
            state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {"flow_id": "negociacion", "context_id": "baseline_current", "context_version": "1.0.0"},
        )

    def test_bootstrap_with_context_id_baseline_current_works(self) -> None:
        services.ensure_session(user_id="u_p4_context", session_id="s_p4_context", context_id="baseline_current")
        state = get_session_state(user_id="u_p4_context", session_id="s_p4_context")
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"], "baseline_current")

    def test_bootstrap_with_public_slug_resolves_same_context_id(self) -> None:
        selection = resolve_public_context_selection(public_slug="negociacion")
        services.ensure_session(user_id="u_p4_slug", session_id="s_p4_slug", public_slug="negociacion")
        state = get_session_state(user_id="u_p4_slug", session_id="s_p4_slug")

        self.assertEqual(selection.context_id, "baseline_current")
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"], selection.context_id)

    def test_bootstrap_with_matching_context_id_and_public_slug_works(self) -> None:
        services.ensure_session(
            user_id="u_p4_match",
            session_id="s_p4_match",
            context_id="baseline_current",
            public_slug="negociacion",
        )
        state = get_session_state(user_id="u_p4_match", session_id="s_p4_match")
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"], "baseline_current")

    def test_bootstrap_with_context_id_and_public_slug_mismatch_is_rejected_explicitly(self) -> None:
        response = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={
                "user_id": "u_p4_conflict",
                "session_id": "s_p4_conflict",
                "context_id": "otro_contexto",
                "public_slug": "negociacion",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["error"], "bootstrap_context_input_conflict")

    def test_current_baseline_public_entry_still_exists(self) -> None:
        baseline = self.client.get("/interfaz_usuario")
        slugged = self.client.get("/interfaz_usuario/negociacion")

        self.assertEqual(baseline.status_code, 200)
        self.assertEqual(slugged.status_code, 200)
        self.assertIn("Interfaz Usuario", baseline.text)
        self.assertIn("Interfaz Usuario", slugged.text)

    def test_reusing_fixed_session_with_incompatible_slug_or_context_still_avoids_silent_mix(self) -> None:
        services.ensure_session(user_id="u_p4_reuse", session_id="s_p4_reuse", public_slug="negociacion")
        response = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={
                "user_id": "u_p4_reuse",
                "session_id": "s_p4_reuse",
                "context_id": "otro_contexto",
            },
        )

        state = get_session_state(user_id="u_p4_reuse", session_id="s_p4_reuse")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["error"], "session_context_conflict")
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"], "baseline_current")

    def test_session_is_fixed_to_same_context_resolved_by_backend(self) -> None:
        response = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_p4_backend", "session_id": "s_p4_backend", "public_slug": "negociacion"},
        )
        state = get_session_state(user_id="u_p4_backend", session_id="s_p4_backend")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"], "baseline_current")


if __name__ == "__main__":
    unittest.main()
