import importlib


def test_migrate_negotiation_env_aliases_promotes_and_cleans(monkeypatch):
    monkeypatch.setenv("PLANNER_MODEL_NAME", "legacy-planner")
    monkeypatch.delenv("NEGOTIATION_PLANNER_MODEL", raising=False)

    app = importlib.import_module("app")
    app._migrate_negotiation_env_aliases()

    assert app.os.getenv("NEGOTIATION_PLANNER_MODEL") == "legacy-planner"
    assert app.os.getenv("PLANNER_MODEL_NAME") is None


def test_migrate_negotiation_env_aliases_does_not_override_new(monkeypatch):
    monkeypatch.setenv("EXECUTOR_MODEL_NAME", "legacy-executor")
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_MODEL", "new-executor")

    app = importlib.import_module("app")
    app._migrate_negotiation_env_aliases()

    assert app.os.getenv("NEGOTIATION_EXECUTOR_MODEL") == "new-executor"
    assert app.os.getenv("EXECUTOR_MODEL_NAME") is None
