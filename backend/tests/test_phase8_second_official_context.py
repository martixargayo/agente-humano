from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.domains.negotiation.assets_loader import resolve_negotiation_evaluation_assets
from evaluacion.domains.negotiation.extractor import build_feedback_input_bundle_v1
from evaluacion.domains.negotiation.rubric_loader import load_negotiation_rubric_v1
from evaluacion.engine.service import _run_pipeline_from_bundle
from evaluacion.storage import REPOSITORY
from interfaz_usuario import services as ui_services
from negociacion.contexts import (
    NEGOTIATION_CONTEXT_WORLD_STATE_KEY,
    list_official_negotiation_contexts,
    resolve_negotiation_context,
    resolve_public_context_selection,
    resolve_public_slug_to_context_id,
)
from negociacion.optimizador import services as optimizer_services
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from sessions.state import SESSIONS, get_session_state

NEW_CONTEXT_ID = 'validacion_multicontexto'
NEW_PUBLIC_SLUG = 'negociacion-validacion'


class Phase8SecondOfficialContextTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._jobs.clear()
        REPOSITORY._reports.clear()
        self.client = TestClient(app)

    def _seed_history(self, state) -> None:
        state.history = [
            {'role': 'user', 'content': 'hola'},
            {'role': 'assistant', 'content': 'buenas, dime'},
            {'role': 'user', 'content': 'te ofrezco 7000 euros'},
            {'role': 'assistant', 'content': 'necesito algo más de margen'},
        ]

    def test_baseline_remains_intact_while_second_context_is_registered(self) -> None:
        payload = ui_services.ensure_session(user_id='u_base', session_id='s_base')
        state = get_session_state(user_id='u_base', session_id='s_base')
        selection = resolve_public_context_selection(public_slug='negociacion')
        contexts = {context.context_id for context in list_official_negotiation_contexts()}

        self.assertEqual(payload['session_id'], 's_base')
        self.assertEqual(selection.context_id, 'baseline_current')
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], 'baseline_current')
        self.assertIn('baseline_current', contexts)
        self.assertIn(NEW_CONTEXT_ID, contexts)

    def test_new_context_resolves_publicly_and_slugged_ui_entry_returns_200(self) -> None:
        self.assertEqual(resolve_public_slug_to_context_id(NEW_PUBLIC_SLUG), NEW_CONTEXT_ID)
        selection = resolve_public_context_selection(public_slug=NEW_PUBLIC_SLUG)
        response = self.client.get(f'/interfaz_usuario/{NEW_PUBLIC_SLUG}')
        response_slash = self.client.get(f'/interfaz_usuario/{NEW_PUBLIC_SLUG}/')

        self.assertEqual(selection.context_id, NEW_CONTEXT_ID)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_slash.status_code, 200)
        self.assertIn('Interfaz Usuario', response.text)

    def test_session_binding_supports_new_context_by_context_id_and_public_slug(self) -> None:
        by_context = ui_services.ensure_session(user_id='u_ctx', session_id='s_ctx', context_id=NEW_CONTEXT_ID)
        by_slug = ui_services.ensure_session(user_id='u_slug', session_id='s_slug', public_slug=NEW_PUBLIC_SLUG)
        state_context = get_session_state(user_id='u_ctx', session_id='s_ctx')
        state_slug = get_session_state(user_id='u_slug', session_id='s_slug')

        self.assertEqual(by_context['session_id'], 's_ctx')
        self.assertEqual(by_slug['session_id'], 's_slug')
        self.assertEqual(state_context.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], NEW_CONTEXT_ID)
        self.assertEqual(state_slug.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], NEW_CONTEXT_ID)

    def test_conflicting_session_reuse_rejects_baseline_and_second_context_mix_both_directions(self) -> None:
        ui_services.ensure_session(user_id='u_conflict_a', session_id='s_conflict_a', context_id='baseline_current')
        ui_services.ensure_session(user_id='u_conflict_b', session_id='s_conflict_b', context_id=NEW_CONTEXT_ID)

        with self.assertRaises(Exception) as ctx_a:
            ui_services.ensure_session(user_id='u_conflict_a', session_id='s_conflict_a', context_id=NEW_CONTEXT_ID)
        with self.assertRaises(Exception) as ctx_b:
            ui_services.ensure_session(user_id='u_conflict_b', session_id='s_conflict_b', context_id='baseline_current')

        self.assertEqual(ctx_a.exception.status_code, 409)
        self.assertEqual(ctx_b.exception.status_code, 409)
        self.assertEqual(ctx_a.exception.detail['error'], 'session_context_conflict')
        self.assertEqual(ctx_b.exception.detail['error'], 'session_context_conflict')

    def test_runtime_uses_new_context_and_traces_keep_new_context_id(self) -> None:
        ui_services.ensure_session(user_id='u_runtime', session_id='s_runtime', context_id=NEW_CONTEXT_ID)
        state = get_session_state(user_id='u_runtime', session_id='s_runtime')
        resolved = resolve_negotiation_context(NEW_CONTEXT_ID)

        captured = {}

        def fake_execute_turn_with_contract(*, state, user_message, config, contract):
            captured['prompts_dir'] = config.prompts_dir
            return (
                'reply-runtime',
                state,
                {
                    'trace_count': 0,
                    'conversation_id_before': None,
                    'conversation_id_after': None,
                    'previous_response_id_before': None,
                    'previous_response_id_after': None,
                    'latest_turn_id': 'turn-runtime',
                    'entry_contract': {'entry_surface': 'interfaz_usuario'},
                },
            )

        with patch('interfaz_usuario.services.execute_turn_with_contract', side_effect=fake_execute_turn_with_contract):
            result = ui_services.run_turn(user_id='u_runtime', session_id='s_runtime', message='hola')

        config = build_negotiation_pipeline_config(context_id=NEW_CONTEXT_ID)

        def fake_turn(current_state, user_message, current_config):
            current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-new'}]
            current_state.world_state[current_config.memory_key] = {'openai_thread': {}}
            return 'ok', current_state

        with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
            _, updated_state, _ = execute_turn_with_contract(
                state=state,
                user_message='hola',
                config=config,
                contract=TurnEntryContract(
                    entry_surface='interfaz_usuario',
                    entrypoint='/api/interfaz_usuario/negociacion/turn',
                    overrides_applied=False,
                    optimizer_wrapper_used=False,
                ),
            )

        trace = updated_state.world_state['negotiation_canonical_traces'][-1]
        self.assertEqual(result['reply'], 'reply-runtime')
        self.assertEqual(Path(captured['prompts_dir']), resolved.prompts_dir)
        self.assertEqual(Path(config.prompts_dir), resolved.prompts_dir)
        self.assertEqual(trace['context_meta']['context_id'], NEW_CONTEXT_ID)

    def test_evaluation_uses_new_context_assets_and_provenance(self) -> None:
        ui_services.ensure_session(user_id='u_eval_new', session_id='s_eval_new', context_id=NEW_CONTEXT_ID)
        state = get_session_state(user_id='u_eval_new', session_id='s_eval_new')
        self._seed_history(state)

        bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-new')
        assets = resolve_negotiation_evaluation_assets(bundle.domain_context)
        rubric = load_negotiation_rubric_v1(bundle.domain_context)

        core_output = FeedbackReportCoreV1.model_validate({
            'schema_version': 'feedback_report_core.v1',
            'score_global_100': 70,
            'interaction_outcome': 'partial_progress',
            'summary_2_3_lines': 'Resumen contexto alternativo.',
            'evaluation_blocks': [
                {'block_id': 'valores', 'title': 'Valores', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'vision', 'title': 'Visión', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'relacion', 'title': 'Relación', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'proceso', 'title': 'Proceso', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            ],
            'best_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'most_delicate_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'turning_point': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'recommendations': [{'title': 't', 'description': 'd', 'example': {'original_excerpt': 'x', 'better_rephrase': 'y'}}],
        })
        trajectory_output = TurnTrajectoryV1(schema_version='turn_trajectory.v1', trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=60, user_excerpt='u', counterpart_excerpt='a', impact_reason='i', counterpart_thought_effect='c', better_rephrase='b')
        ])

        REPOSITORY.create_job(evaluation_id='eval-new', user_id='u_eval_new', session_id='s_eval_new', created_at='2026-03-19T00:00:00+00:00')
        with patch('evaluacion.engine.service.run_core_evaluator', return_value=(core_output, 'model')), patch(
            'evaluacion.engine.service.run_trajectory_evaluator', return_value=(trajectory_output, 'model')
        ):
            _run_pipeline_from_bundle(evaluation_id='eval-new', bundle=bundle)

        report = REPOSITORY.get_report(evaluation_id='eval-new')
        resolved_context = resolve_negotiation_context(NEW_CONTEXT_ID)
        self.assertEqual(bundle.domain_context.context_id, NEW_CONTEXT_ID)
        self.assertIn(NEW_CONTEXT_ID, str(assets.core_prompt_path))
        self.assertIn(NEW_CONTEXT_ID, str(assets.trajectory_prompt_path))
        self.assertEqual(rubric.metadata.case_title, 'Negociación guiada por acuerdos sostenibles')
        self.assertEqual(resolved_context.public_slug, NEW_PUBLIC_SLUG)
        self.assertEqual(report.provenance.context_id, NEW_CONTEXT_ID)
        self.assertEqual(report.provenance.flow_id, 'negociacion')

    def test_optimizer_supports_new_context_end_to_end(self) -> None:
        boot = optimizer_services.ensure_session(user_id='u_opt_new', session_id='s_opt_new', context_id=NEW_CONTEXT_ID)
        cloned = optimizer_services.duplicate_sandbox_session(
            optimizer_session_id='opt-new',
            source_user_id='u_opt_new',
            source_session_id='s_opt_new',
            source_conversation_id='conv-new',
        )
        new_conv = optimizer_services.new_conversation_session(
            optimizer_session_id='opt-new',
            user_id='u_opt_new',
            session_id='s_opt_new',
        )
        state = get_session_state(user_id='u_opt_new', session_id='s_opt_new')
        state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'full_session_with_preferred_conversation'}
        state.world_state['negotiation_canonical_traces'] = [
            {'turn_id': 'turn-opt-new', 'context_meta': {'flow_id': 'negociacion', 'context_id': NEW_CONTEXT_ID, 'context_version': '1.0.0'}}
        ]
        resolved = resolve_negotiation_context(NEW_CONTEXT_ID)
        captured = {}

        def fake_execute_turn_with_contract(*, state, user_message, config, contract):
            captured['prompts_dir'] = config.prompts_dir
            captured['phase_cards'] = Path(config.prompts_dir, 'phase_cards.json').read_text(encoding='utf-8')
            captured['persona'] = Path(config.prompts_dir, 'persona.json').read_text(encoding='utf-8')
            return ('reply-opt-new', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1})

        with patch(
            'negociacion.optimizador.services.experiments_bridge.resolve_entries',
            return_value=[{'scope': 'this_optimizer_session', 'category': 'prompt', 'key': 'planner_prompt', 'value': 'override'}],
        ), patch(
            'negociacion.optimizador.services.execute_turn_with_contract',
            side_effect=fake_execute_turn_with_contract,
        ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {'planner_prompt': 'override'}, 'config': {}, 'contextual': {}}), patch(
            'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'sandbox', 'workspace_version': 2}
        ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-opt-new'}]), patch(
            'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
        ):
            result = optimizer_services.run_sandbox_turn(
                optimizer_session_id='opt-new',
                user_id='u_opt_new',
                session_id='s_opt_new',
                message='hola',
                conversation_id='conv-new',
                scope_turn_id=None,
                repeat_from_turn_id=None,
            )

        optimizer_meta = state.world_state['negotiation_canonical_traces'][-1]['_optimizador']
        self.assertEqual(boot['base_context']['context_id'], NEW_CONTEXT_ID)
        self.assertEqual(cloned['base_context']['context_id'], NEW_CONTEXT_ID)
        self.assertEqual(new_conv['base_context']['context_id'], NEW_CONTEXT_ID)
        self.assertEqual(result['reply'], 'reply-opt-new')
        self.assertEqual(optimizer_meta['base_context']['context_id'], NEW_CONTEXT_ID)
        self.assertEqual(optimizer_meta['base_context']['context_scope'], 'official_with_overrides')
        self.assertEqual(captured['phase_cards'], resolved.phase_cards_path.read_text(encoding='utf-8'))
        self.assertEqual(captured['persona'], resolved.persona_path.read_text(encoding='utf-8'))

    def test_baseline_and_second_context_coexist_without_breaking_legacy_surfaces(self) -> None:
        baseline = resolve_negotiation_context('baseline_current')
        alternate = resolve_negotiation_context(NEW_CONTEXT_ID)

        self.assertNotEqual(baseline.context_id, alternate.context_id)
        self.assertNotEqual(baseline.public_slug, alternate.public_slug)
        self.assertEqual(baseline.flow_id, alternate.flow_id)
        self.assertTrue(baseline.prompts_dir.exists())
        self.assertTrue(alternate.prompts_dir.exists())


if __name__ == '__main__':
    unittest.main()
