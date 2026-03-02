from negotiation.nodes.executor_node import _finalizer_enabled


def test_executor_finalizer_enabled_by_default(monkeypatch):
    monkeypatch.delenv("NEGOTIATION_EXECUTOR_FINALIZER_ENABLED", raising=False)
    assert _finalizer_enabled() is True


def test_executor_finalizer_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_FINALIZER_ENABLED", "0")
    assert _finalizer_enabled() is False
