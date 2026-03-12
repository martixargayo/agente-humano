from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPO_ROOT / "backend" / "avatar_app" / "shared" / "chat_runtime.js"
OPTIMIZER_APP_PATH = REPO_ROOT / "backend" / "avatar_app" / "optimizador" / "app.js"
INTERFAZ_APP_PATH = REPO_ROOT / "backend" / "avatar_app" / "interfaz_usuario" / "app.js"


def _run_node_json(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script, str(RUNTIME_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"Node script failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return json.loads(result.stdout)


def test_entrypoint_state_controls_differ_and_can_change_scope_context() -> None:
    optimizer_app = OPTIMIZER_APP_PATH.read_text(encoding="utf-8")
    interfaz_app = INTERFAZ_APP_PATH.read_text(encoding="utf-8")

    # Optimizador: permite mover el turno seleccionado y cortar live follow.
    assert "turnSelector" in optimizer_app
    assert "state.liveFollow = false;" in optimizer_app
    assert "toggleFollow" in optimizer_app

    # Interfaz usuario: no expone esos controles de selección/seguimiento.
    assert "turnSelector" not in interfaz_app
    assert "toggleFollow" not in interfaz_app


def test_runtime_shows_live_follow_changes_effective_scope_turn_before_send() -> None:
    node_script = r"""
const fs = require('fs');
const vm = require('vm');

const runtimePath = process.argv[1];
const runtimeCode = fs.readFileSync(runtimePath, 'utf8');

function buildHarness() {
  const fetchCalls = [];
  const queuedResponses = [];

  const context = {
    window: {},
    fetch: async (url, opts = {}) => {
      fetchCalls.push({ url, opts });
      if (!queuedResponses.length) throw new Error('No mock response for ' + url);
      const payload = queuedResponses.shift();
      return {
        ok: true,
        async text() { return JSON.stringify(payload); },
        async json() { return payload; },
      };
    },
    setInterval: () => ({ id: 'interval' }),
    clearInterval: () => {},
    console,
  };

  vm.createContext(context);
  vm.runInContext(runtimeCode, context);

  return {
    enqueue(payload) { queuedResponses.push(payload); },
    fetchCalls,
    createRuntime(state) { return context.window.createOptimizadorChatRuntime(state); },
  };
}

async function runScenario({ followLive }) {
  const harness = buildHarness();
  const state = {
    optimizerSessionId: 'default',
    defaultUserId: 'u_optimizador',
    defaultSessionId: 'optimizador-main',
    sessions: [{ session_key: 'k1', user_id: 'u1', session_id: 's1' }],
    selectedSessionKey: 'k1',
    selectedConversation: 'conv-A',
    selectedTurnId: 't1',
    turns: [],
    dialogue: [],
    waitingReply: false,
    lastKnownTurnId: '',
    pollTimer: null,
    liveFollow: followLive,
  };

  const runtime = harness.createRuntime(state);

  // refresh previo al envío (simula polling/refresh normal con 2 turns existentes)
  harness.enqueue({ items: [{ session_key: 'k1', user_id: 'u1', session_id: 's1' }] });
  harness.enqueue({ items: [{ turn_id: 't1' }, { turn_id: 't2' }] });
  harness.enqueue({ items: [{ role: 'assistant', text: 'prev' }] });
  await runtime.refresh({ followLive });

  // envío
  harness.enqueue({ reply: 'ok' });
  harness.enqueue({ items: [{ session_key: 'k1', user_id: 'u1', session_id: 's1' }] });
  harness.enqueue({ items: [{ turn_id: 't1' }, { turn_id: 't2' }, { turn_id: 't3' }] });
  harness.enqueue({ items: [{ role: 'user', text: 'hola' }, { role: 'assistant', text: 'ok' }] });
  await runtime.sendChat('hola', { followLive });

  const sandboxCall = harness.fetchCalls.find((call) => call.url === '/api/optimizador/sandbox/turn');
  const payload = JSON.parse(sandboxCall.opts.body);
  return {
    followLive,
    selectedTurnIdBeforeSendResolvedByRefresh: followLive ? 't2' : 't1',
    selectedTurnIdAfterSend: state.selectedTurnId,
    payload,
  };
}

(async () => {
  const off = await runScenario({ followLive: false });
  const on = await runScenario({ followLive: true });
  console.log(JSON.stringify({ off, on }));
})();
"""
    result = _run_node_json(node_script)

    # Mismo endpoint/payload base.
    assert result["off"]["payload"]["message"] == result["on"]["payload"]["message"] == "hola"
    assert result["off"]["payload"]["conversation_id"] == result["on"]["payload"]["conversation_id"] == "conv-A"

    # Diferencia crítica de contexto: scope_turn_id cambia por followLive.
    assert result["off"]["payload"]["scope_turn_id"] == "t1"
    assert result["on"]["payload"]["scope_turn_id"] == "t2"


def test_optimizer_has_repeat_from_path_but_interfaz_usuario_not() -> None:
    optimizer_app = OPTIMIZER_APP_PATH.read_text(encoding="utf-8")
    interfaz_app = INTERFAZ_APP_PATH.read_text(encoding="utf-8")

    # Optimizador sí puede enviar repeat_from_turn_id (acción Repetir).
    assert "sendChat(text, state.selectedTurnId)" in optimizer_app
    assert "repeatFrom," in optimizer_app

    # Interfaz usuario siempre usa mensaje normal (sin repeatFrom expuesto por UI).
    assert "repeatFrom" not in interfaz_app
