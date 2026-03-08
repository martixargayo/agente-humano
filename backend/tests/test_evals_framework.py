from __future__ import annotations

from pathlib import Path

from negociacion.evals.cases import load_jsonl_cases
from negociacion.evals.graders.end_to_end import grade_end_to_end_case
from negociacion.evals.graders.executor import grade_executor_case
from negociacion.evals.graders.memory import grade_memory_case
from negociacion.evals.graders.phase import grade_phase_case
from negociacion.evals.graders.planner import grade_planner_case
from negociacion.evals.runners.run_all_evals import run as run_all_fixture_evals
from negociacion.evals.runners.run_all_live_evals import run as run_all_live_evals
from negociacion.evals.runners.run_end_to_end_live_evals import run as run_end_to_end_live_evals
from negociacion.evals.runners.run_end_to_end_mock_evals import run as run_end_to_end_mock_evals
from negociacion.evals.runners.run_phase_live_evals import run as run_phase_live_evals
from negociacion.evals.runners import live_utils
from negociacion.orchestration import flow_config as fc
from negociacion.orchestration.flow_config import StructuredCallResult
from negociacion.state.shared_types import StructuredCallSource


def test_fixture_and_live_datasets_coexist_and_load():
    datasets = [
        "memory_fixture_cases.jsonl",
        "phase_fixture_cases.jsonl",
        "planner_fixture_cases.jsonl",
        "executor_fixture_cases.jsonl",
        "end_to_end_mock_cases.jsonl",
        "memory_live_cases.jsonl",
        "phase_live_cases.jsonl",
        "planner_live_cases.jsonl",
        "executor_live_cases.jsonl",
        "end_to_end_live_cases.jsonl",
    ]
    for dataset in datasets:
        cases = load_jsonl_cases(dataset)
        assert cases, dataset
        assert all("case_id" in c for c in cases)


def test_graders_return_homogeneous_shape_with_input_output_context():
    mem = load_jsonl_cases("memory_fixture_cases.jsonl")[0]
    phase = load_jsonl_cases("phase_fixture_cases.jsonl")[0]
    plan = load_jsonl_cases("planner_fixture_cases.jsonl")[0]
    exe = load_jsonl_cases("executor_fixture_cases.jsonl")[0]

    results = [
        grade_memory_case(mem["case_id"], mem["candidate_output"], mem["expected_checks"], mem["input"]),
        grade_phase_case(phase["case_id"], phase["candidate_output"], phase["expected_phase"]),
        grade_planner_case(plan["case_id"], plan["candidate_output"], plan["expected_checks"], plan["allowed_decisions"], plan["forbidden_decisions"], plan["input"]),
        grade_executor_case(exe["case_id"], exe["candidate_output"], exe["planner_output_status"], exe["expected_checks"], exe["input"]),
    ]

    for result in results:
        assert result.case_id
        assert result.grader_name
        assert isinstance(result.passed, bool)
        assert isinstance(result.score, float)
        assert isinstance(result.checks, list)


def test_fixture_runners_execute_without_breaking():
    assert run_end_to_end_mock_evals() == 0
    assert run_all_fixture_evals() == 0


def test_phase_live_eval_runs_real_live_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class _FakeClient:
        pass

    def _fake_build_client():
        return _FakeClient()

    def _fake_refresh_request_context(client, canonical_state, mode_default):
        _ = (client, canonical_state, mode_default)
        return {}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, response_model, reasoning_effort, request_context, store)
        payload_text = messages[1]["content"]
        assert "phase_classifier_input_json" in payload_text
        return StructuredCallResult(
            parsed_json={"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"},
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
        )

    monkeypatch.setattr(fc, "_build_client", _fake_build_client)
    monkeypatch.setattr(fc, "refresh_request_context", _fake_refresh_request_context)
    monkeypatch.setattr(live_utils, "_call_structured", _fake_call_structured)

    assert run_phase_live_evals() in {0, 1}


def test_end_to_end_mock_and_live_runners_both_exist():
    assert callable(run_end_to_end_mock_evals)
    assert callable(run_end_to_end_live_evals)


def test_end_to_end_grader_checks_trace_and_compact_trace():
    world_state = {
        "negotiation_canonical": {"trace": {"turn_id": "t1"}},
        "negotiation_canonical_traces": [
            {
                "final_status": "deliver",
                "guardrails_triggered": False,
                "nodes": {
                    "memory": {},
                    "phase_classifier": {"output_summary": {"current_phase": "propuesta_creativa"}},
                    "planner": {},
                    "executor": {},
                },
            }
        ],
    }
    result = grade_end_to_end_case(
        case_id="e2e_shape",
        final_reply="ok",
        world_state=world_state,
        memory_key="negotiation_canonical",
        expected_checks={"expected_phase": "propuesta_creativa", "expected_final_status": "deliver", "expected_guardrail": False},
    )
    assert result.passed is True


def test_eval_framework_stays_outside_runtime_flow_config():
    flow_config_text = Path("backend/negociacion/orchestration/flow_config.py").read_text(encoding="utf-8")
    assert "negociacion.evals" not in flow_config_text


def test_live_e2e_runner_declares_real_trace_dependency(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_all_live_evals() == 0
