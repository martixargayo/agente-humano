from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.storage import REPOSITORY
from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY
from sessions.state import SESSIONS, get_session_state

TARGET_CONTEXT_ID = 'validacion_multicontexto'
TARGET_PUBLIC_SLUG = 'negociacion-validacion'


class Phase8SecondOfficialContextE2EHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._jobs.clear()
        REPOSITORY._reports.clear()
        self.client = TestClient(app)

    @staticmethod
    def _fake_runtime_turn(current_state, user_message: str, current_config):
        traces_key = f'{current_config.memory_key}_traces'
        traces = current_state.world_state.setdefault(traces_key, [])
        turn_index = len(traces) + 1
        canonical = current_state.world_state.setdefault(
            current_config.memory_key,
            {
                'openai_thread': {
                    'thread_mode': current_config.thread_mode_default.value,
                    'conversation_id': None,
                    'previous_response_id': None,
                },
                'planner_state': {'current_phase': 'descubrimiento_y_comprension'},
                'ui_state': {'finish_button_armed': False},
            },
        )
        thread = canonical.setdefault('openai_thread', {})
        if not thread.get('conversation_id'):
            thread['conversation_id'] = f'conv-{current_state.session_id}'
        thread['previous_response_id'] = f'resp-{turn_index}'
        if turn_index >= 3:
            canonical.setdefault('ui_state', {})['finish_button_armed'] = True
        traces.append(
            {
                'turn_id': f'{current_state.session_id}-turn-{turn_index}',
                'turn_started_at': f'2026-03-19T12:40:0{turn_index}+00:00',
                'timestamp_utc': f'2026-03-19T12:40:0{turn_index}+00:00',
                'conversation_id_before': thread['conversation_id'],
                'conversation_id_after': thread['conversation_id'],
                'previous_response_id_before': f'resp-{turn_index-1}' if turn_index > 1 else None,
                'previous_response_id_after': thread['previous_response_id'],
                'final_reply_text': f'[{TARGET_CONTEXT_ID}] turno {turn_index}: respuesta a {user_message}',
                'final_status': 'ok',
                'guardrails_triggered': False,
                'logs': [],
                'nodes': {},
            }
        )
        current_state.world_state[current_config.memory_key] = canonical
        return traces[-1]['final_reply_text'], current_state

    @staticmethod
    def _seed_history(state) -> None:
        state.history = [
            {'role': 'user', 'content': 'Hola, vengo a ver el Mustang.'},
            {'role': 'assistant', 'content': 'Buenas, sí, sigue disponible.'},
            {'role': 'user', 'content': 'Me interesa, pero quiero entender mejor el estado real.'},
            {'role': 'assistant', 'content': 'Te cuento lo que se le ha hecho y lo que falta.'},
            {'role': 'user', 'content': 'Si el coche está fino podríamos hablar de números.'},
            {'role': 'assistant', 'content': 'Perfecto, dime por dónde quieres empezar.'},
        ]

    def _core_output(self) -> FeedbackReportCoreV1:
        return FeedbackReportCoreV1.model_validate({
            'schema_version': 'feedback_report_core.v1',
            'score_global_100': 74,
            'interaction_outcome': 'partial_progress',
            'summary_2_3_lines': 'La conversación avanzó con continuidad y sin mezclar contextos.',
            'evaluation_blocks': [
                {'block_id': 'valores', 'title': 'Valores', 'status_visual': 'correcto', 'score_0_100': 74, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'vision', 'title': 'Visión', 'status_visual': 'correcto', 'score_0_100': 74, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [2]}], 'block_verdict': 'ok'},
                {'block_id': 'relacion', 'title': 'Relación', 'status_visual': 'correcto', 'score_0_100': 74, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [3]}], 'block_verdict': 'ok'},
                {'block_id': 'proceso', 'title': 'Proceso', 'status_visual': 'correcto', 'score_0_100': 74, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [3]}], 'block_verdict': 'ok'},
            ],
            'best_moment': {'turn_index': 2, 'why': 'Hubo foco y continuidad.', 'impact': 'Consolidó claridad útil.'},
            'most_delicate_moment': {'turn_index': 3, 'why': 'Aparece presión negociadora.', 'impact': 'Exige cuidar límites.'},
            'turning_point': {'turn_index': 3, 'why': 'Se abre el terreno de oferta.', 'impact': 'La conversación pasa a ajuste.'},
            'recommendations': [{'title': 'Seguir', 'description': 'Mantener reciprocidad.', 'example': {'original_excerpt': 'x', 'better_rephrase': 'y'}}],
        })

    def _trajectory_output(self) -> TurnTrajectoryV1:
        return TurnTrajectoryV1(schema_version='turn_trajectory.v1', trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=42, user_excerpt='u1', counterpart_excerpt='a1', impact_reason='base', counterpart_thought_effect='ok', better_rephrase='b1'),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=55, user_excerpt='u2', counterpart_excerpt='a2', impact_reason='progreso', counterpart_thought_effect='ok', better_rephrase='b2'),
            TrajectoryTurn(turn_index=3, agreement_closeness_score_0_100=63, user_excerpt='u3', counterpart_excerpt='a3', impact_reason='ajuste', counterpart_thought_effect='ok', better_rephrase='b3'),
        ])

    def test_http_end_to_end_surface_keeps_context_across_runtime_evaluation_and_optimizer(self) -> None:
        with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=self._fake_runtime_turn), patch(
            'evaluacion.engine.service.run_core_evaluator', return_value=(self._core_output(), 'gpt-5.4')
        ), patch('evaluacion.engine.service.run_trajectory_evaluator', return_value=(self._trajectory_output(), 'gpt-5.4')):
            boot = self.client.post(
                '/api/interfaz_usuario/sessions/bootstrap',
                json={'user_id': 'u_http', 'session_id': 's_http', 'public_slug': TARGET_PUBLIC_SLUG},
            )
            self.assertEqual(boot.status_code, 200)

            turns = []
            for message in [
                'Hola, quiero entender bien el Mustang antes de hablar de precio.',
                '¿Qué mantenimiento importante tiene hecho?',
                'Si todo cuadra, podría moverme cerca de mercado pero necesito ver reciprocidad.',
            ]:
                response = self.client.post(
                    '/api/interfaz_usuario/negociacion/turn',
                    json={'user_id': 'u_http', 'session_id': 's_http', 'message': message, 'new_conversation': False},
                )
                self.assertEqual(response.status_code, 200)
                turns.append(response.json())

            state = get_session_state('u_http', 's_http')
            trace = state.world_state['negotiation_canonical_traces'][-1]
            self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], TARGET_CONTEXT_ID)
            self.assertEqual(len(turns), 3)
            self.assertEqual(turns[-1]['trace_count'], 3)
            self.assertTrue(turns[-1]['finish_button_armed'])
            self.assertEqual(turns[0]['conversation_id_after'], turns[-1]['conversation_id_after'])
            self.assertEqual(trace['context_meta']['context_id'], TARGET_CONTEXT_ID)
            self.assertEqual(trace['_entry_contract']['context_meta']['context_id'], TARGET_CONTEXT_ID)

            new_conv = self.client.post(
                '/api/interfaz_usuario/negociacion/new_conversation',
                json={'user_id': 'u_http', 'session_id': 's_http'},
            )
            self.assertEqual(new_conv.status_code, 200)
            new_session_id = new_conv.json()['session_id']
            new_state = get_session_state('u_http', new_session_id)
            self.assertEqual(new_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], TARGET_CONTEXT_ID)

            conflict = self.client.post(
                '/api/interfaz_usuario/sessions/bootstrap',
                json={'user_id': 'u_http', 'session_id': 's_http', 'context_id': 'baseline_current'},
            )
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(conflict.json()['detail']['error'], 'session_context_conflict')

            self._seed_history(state)
            evaluation = self.client.post('/api/interfaz_usuario/feedback/evaluations', json={'user_id': 'u_http', 'session_id': 's_http'})
            self.assertEqual(evaluation.status_code, 200)
            evaluation_id = evaluation.json()['evaluation_id']
            report = None
            for _ in range(20):
                report = self.client.get(f'/api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report')
                if report.status_code == 200:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(report)
            self.assertEqual(report.status_code, 200)
            provenance = report.json()['report']['provenance']
            self.assertEqual(provenance['context_id'], TARGET_CONTEXT_ID)
            self.assertEqual(provenance['flow_id'], 'negociacion')

            opt_boot = self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_opt_http', 'session_id': 's_opt_http', 'context_id': TARGET_CONTEXT_ID})
            self.assertEqual(opt_boot.status_code, 200)
            opt_new = self.client.post('/api/optimizador/sandbox/new_conversation', json={'optimizer_session_id': 'opt-http', 'user_id': 'u_opt_http', 'session_id': 's_opt_http'})
            self.assertEqual(opt_new.status_code, 200)
            sandbox_session_id = opt_new.json()['session_id']
            opt_turn = self.client.post(
                '/api/optimizador/sandbox/turn',
                json={
                    'optimizer_session_id': 'opt-http',
                    'user_id': 'u_opt_http',
                    'session_id': sandbox_session_id,
                    'message': 'Quiero validar el sandbox multi-context.',
                    'conversation_id': None,
                    'scope_turn_id': None,
                    'repeat_from_turn_id': None,
                },
            )
            self.assertEqual(opt_turn.status_code, 200)
            turn_id = opt_turn.json()['turn']['turn_id']
            opt_turn_payload = self.client.get(f'/api/optimizador/turns/{turn_id}')
            opt_turns = self.client.get(f'/api/optimizador/sessions/u_opt_http/{sandbox_session_id}/turns')
            self.assertEqual(opt_turn_payload.status_code, 200)
            self.assertEqual(opt_turns.status_code, 200)
            self.assertEqual(opt_turn_payload.json()['_optimizador']['base_context']['context_id'], TARGET_CONTEXT_ID)
            self.assertEqual(opt_turn_payload.json()['_optimizador']['base_context']['context_scope'], 'official')
            self.assertEqual(opt_turns.json()['items'][0]['base_context']['context_id'], TARGET_CONTEXT_ID)
