from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app


client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPO_ROOT / "backend" / "avatar_app" / "shared" / "chat_runtime.js"
OPTIMIZER_APP_PATH = REPO_ROOT / "backend" / "avatar_app" / "optimizador" / "app.js"
INTERFAZ_APP_PATH = REPO_ROOT / "backend" / "avatar_app" / "interfaz_usuario" / "app.js"


def test_interfaz_usuario_route_serves_index() -> None:
    response = client.get("/interfaz_usuario/")
    assert response.status_code == 200
    assert "<title>Interfaz Usuario</title>" in response.text


def test_shared_runtime_is_served_from_avatar_mount() -> None:
    response = client.get("/avatar/shared/chat_runtime.js")
    assert response.status_code == 200
    assert "createOptimizadorChatRuntime" in response.text


def test_optimizer_and_interfaz_both_load_the_same_shared_runtime() -> None:
    optimizer_html = client.get("/optimizador/").text
    interfaz_html = client.get("/interfaz_usuario/").text
    assert "/avatar/shared/chat_runtime.js" in optimizer_html
    assert "/avatar/shared/chat_runtime.js" in interfaz_html


def test_chat_runtime_centralizes_canonical_chat_endpoints() -> None:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8")
    assert 'api("/sessions")' in runtime
    assert 'api("/sessions/bootstrap"' in runtime
    assert 'api("/sandbox/turn"' in runtime
    assert "`/sessions/${encodeURIComponent(session.user_id)}/${encodeURIComponent(session.session_id)}`" in runtime
    assert 'api("/chat"' not in runtime


def test_chat_entrypoints_use_shared_runtime_and_do_not_embed_endpoint_flow() -> None:
    optimizer_app = OPTIMIZER_APP_PATH.read_text(encoding="utf-8")
    interfaz_app = INTERFAZ_APP_PATH.read_text(encoding="utf-8")

    # Ambos entrypoints deben usar el runtime compartido.
    assert "createOptimizadorChatRuntime(state" in optimizer_app
    assert "createOptimizadorChatRuntime(state" in interfaz_app

    # La lógica útil de chat (refresh/send/poll) y endpoints vive en el runtime compartido.
    for app_js in (optimizer_app, interfaz_app):
        assert 'fetch(`/api/optimizador${path}`' not in app_js
        assert 'api("/sessions")' not in app_js
        assert 'api("/sessions/bootstrap"' not in app_js
        assert 'api("/sandbox/turn"' not in app_js
        assert 'api("/chat"' not in app_js

    # Ambos usan las mismas primitivas de runtime para flujo de chat.
    assert "chatRuntime.refresh(" in optimizer_app
    assert "chatRuntime.sendChat(" in optimizer_app
    assert "chatRuntime.startPolling(" in optimizer_app
    assert "chatRuntime.renderChatHistoryHtml(" in optimizer_app

    assert "chatRuntime.refresh(" in interfaz_app
    assert "chatRuntime.sendChat(" in interfaz_app
    assert "chatRuntime.startPolling(" in interfaz_app
    assert "chatRuntime.renderChatHistoryHtml(" in interfaz_app


def test_interfaz_usuario_keeps_optimizer_live_follow_semantics() -> None:
    interfaz_app = INTERFAZ_APP_PATH.read_text(encoding="utf-8")
    assert "liveFollow: true" in interfaz_app
    assert "chatRuntime.refresh({ autoSelect: true, followLive: state.liveFollow })" in interfaz_app
    assert "chatRuntime.refresh({ followLive: state.liveFollow })" in interfaz_app
    assert "chatRuntime.sendChat(message" in interfaz_app


def test_backend_canonical_path_for_chat_turn_is_single_and_shared() -> None:
    router_src = (REPO_ROOT / "backend" / "negociacion" / "optimizador" / "__init__.py").read_text(encoding="utf-8")
    services_src = (REPO_ROOT / "backend" / "negociacion" / "optimizador" / "services.py").read_text(encoding="utf-8")

    assert '@router.post("/sandbox/turn")' in router_src
    assert "return services.run_sandbox_turn(" in router_src
    assert "run_negotiation_cognitive_turn(state, message, config)" in services_src
