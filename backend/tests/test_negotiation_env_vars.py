import importlib
import os
import sys


def _reload(module_name: str):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_negotiation_graph_prefers_new_env_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_MODEL", "gpt-new-executor")
    monkeypatch.setenv("EXECUTOR_MODEL_NAME", "gpt-legacy-executor")
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_TEMPERATURE", "0.12")
    monkeypatch.setenv("EXECUTOR_TEMPERATURE", "0.99")
    monkeypatch.setenv("NEGOTIATION_SUMMARY_MODEL", "gpt-new-summary")
    monkeypatch.setenv("SUMMARY_MODEL_NAME", "gpt-legacy-summary")
    monkeypatch.setenv("NEGOTIATION_SUMMARY_TEMPERATURE", "0.34")
    monkeypatch.setenv("SUMMARY_TEMPERATURE", "0.88")
    monkeypatch.setenv("NEGOTIATION_EMBEDDINGS_MODEL", "text-embedding-new")
    monkeypatch.setenv("EMBEDDINGS_MODEL_NAME", "text-embedding-legacy")
    monkeypatch.setenv("NEGOTIATION_RAG_DIR", "/tmp/new-rag")
    monkeypatch.setenv("NEGOCIATION_RAG_DIR", "/tmp/legacy-rag")

    module = _reload("negotiation.negotiation_graph")

    assert module.EXECUTOR_MODEL == "gpt-new-executor"
    assert module.EXECUTOR_TEMPERATURE == 0.12
    assert module.SUMMARY_MODEL == "gpt-new-summary"
    assert module.SUMMARY_TEMPERATURE == 0.34
    assert module.EMBEDDINGS_MODEL == "text-embedding-new"
    assert module.RAG_DIR == "/tmp/new-rag"


def test_negotiation_graph_supports_legacy_rag_typo(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("NEGOTIATION_RAG_DIR", raising=False)
    monkeypatch.setenv("NEGOCIATION_RAG_DIR", "/tmp/legacy-rag")

    module = _reload("negotiation.negotiation_graph")

    assert module.RAG_DIR == "/tmp/legacy-rag"


def test_planner_and_belief_use_negotiation_env_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("NEGOTIATION_PLANNER_MODEL", "planner-new")
    monkeypatch.setenv("PLANNER_MODEL_NAME", "planner-legacy")
    monkeypatch.setenv("NEGOTIATION_PLANNER_TEMPERATURE", "0.21")
    monkeypatch.setenv("PLANNER_TEMPERATURE", "0.77")
    monkeypatch.setenv("NEGOTIATION_BELIEF_MODEL", "belief-new")
    monkeypatch.setenv("BELIEF_MODEL_NAME", "belief-legacy")
    monkeypatch.setenv("NEGOTIATION_BELIEF_TEMPERATURE", "0.11")
    monkeypatch.setenv("BELIEF_TEMPERATURE", "0.66")

    planner = _reload("negotiation.phase_policy_planner")
    belief = _reload("negotiation.belief_state_updater")

    assert planner.PLANNER_MODEL == "planner-new"
    assert planner.PLANNER_TEMPERATURE == 0.21
    assert belief.BELIEF_MODEL == "belief-new"
    assert belief.BELIEF_TEMPERATURE == 0.11


def test_normalizer_falls_back_to_negotiation_summary(monkeypatch):
    monkeypatch.setenv("NEGOTIATION_SUMMARY_MODEL", "negotiation-summary")
    monkeypatch.delenv("NORMALIZER_MODEL_NAME", raising=False)
    monkeypatch.delenv("SUMMARY_MODEL_NAME", raising=False)

    normalizer = _reload("normalizer")

    assert normalizer.NORMALIZER_MODEL == "negotiation-summary"
