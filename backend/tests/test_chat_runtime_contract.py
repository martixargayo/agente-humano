from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPO_ROOT / "backend" / "avatar_app" / "shared" / "chat_runtime.js"


NODE_SCRIPT = r"""
const fs = require('fs');
const vm = require('vm');

const runtimeCode = fs.readFileSync(process.argv[1], 'utf8');

const fetchCalls = [];
const responses = [];

function enqueue(payload) {
  responses.push(payload);
}

function jsonResponse(payload) {
  return {
    ok: true,
    async text() { return JSON.stringify(payload); },
    async json() { return payload; },
  };
}

const context = {
  window: {},
  fetch: async (url, opts = {}) => {
    fetchCalls.push({ url, opts });
    if (!responses.length) throw new Error('No mock response queued for ' + url);
    return jsonResponse(responses.shift());
  },
  setInterval: (fn, ms) => ({ fn, ms }),
  clearInterval: () => {},
  console,
};

vm.createContext(context);
vm.runInContext(runtimeCode, context);

const state = {
  optimizerSessionId: 'default',
  defaultUserId: 'u_optimizador',
  defaultSessionId: 'optimizador-main',
  sessions: [],
  selectedSessionKey: '',
  selectedConversation: '',
  selectedTurnId: '',
  turns: [],
  dialogue: [],
  waitingReply: false,
  lastKnownTurnId: '',
  pollTimer: null,
  liveFollow: true,
};

const hookEvents = { newTurn: 0, replyReady: 0 };

const runtime = context.window.createOptimizadorChatRuntime(state, {
  onNewTurnAvailable: () => { hookEvents.newTurn += 1; },
  onReplyReady: () => { hookEvents.replyReady += 1; },
});

(async () => {
  // refresh con bootstrap cuando no hay sesiones.
  enqueue({ items: [] });
  enqueue({ ok: true });
  enqueue({ items: [{ session_key: 'k1', user_id: 'u1', session_id: 's1' }] });
  enqueue({ items: [{ turn_id: 't1' }] });
  enqueue({ items: [{ role: 'assistant', text: 'hola' }] });

  await runtime.refresh({ autoSelect: true });

  if (state.selectedSessionKey !== 'k1') throw new Error('selectedSessionKey no seteado');
  if (state.selectedTurnId !== 't1') throw new Error('selectedTurnId no seteado');
  if (state.dialogue.length !== 1) throw new Error('dialogue no cargado');

  const refreshUrls = fetchCalls.map((call) => call.url);
  const expectedRefresh = [
    '/api/optimizador/sessions',
    '/api/optimizador/sessions/bootstrap',
    '/api/optimizador/sessions',
    '/api/optimizador/sessions/u1/s1/turns',
    '/api/optimizador/sessions/u1/s1/dialogue',
  ];

  for (let i = 0; i < expectedRefresh.length; i += 1) {
    if (refreshUrls[i] !== expectedRefresh[i]) {
      throw new Error(`Orden refresh incorrecto en posicion ${i}: ${refreshUrls[i]} != ${expectedRefresh[i]}`);
    }
  }

  // sendChat usa sandbox/turn con payload canónico y luego refresca.
  enqueue({ reply: 'respuesta final' });
  enqueue({ items: [{ session_key: 'k1', user_id: 'u1', session_id: 's1' }] });
  enqueue({ items: [{ turn_id: 't1' }, { turn_id: 't2' }] });
  enqueue({ items: [{ role: 'user', text: 'hola' }, { role: 'assistant', text: 'respuesta final' }] });

  let waitingOnBeforeSend = false;
  await runtime.sendChat('hola', {
    repeatFrom: 't1',
    onBeforeSend: () => { waitingOnBeforeSend = state.waitingReply; },
  });

  if (!waitingOnBeforeSend) throw new Error('waitingReply no se activa antes de enviar');
  if (state.waitingReply) throw new Error('waitingReply no se desactiva tras nuevo turno');
  if (state.selectedTurnId !== 't2') throw new Error('selectedTurnId no avanzó al último turno');
  if (!state.dialogue.some((item) => item.role === 'assistant' && item.text === 'respuesta final')) {
    throw new Error('dialogue no contiene respuesta final');
  }

  const sandboxCall = fetchCalls.find((call) => call.url === '/api/optimizador/sandbox/turn');
  if (!sandboxCall) throw new Error('No se llamó a sandbox/turn');

  const payload = JSON.parse(sandboxCall.opts.body);
  if (payload.optimizer_session_id !== 'default') throw new Error('optimizer_session_id incorrecto');
  if (payload.user_id !== 'u1' || payload.session_id !== 's1') throw new Error('user/session incorrectos');
  if (payload.message !== 'hola') throw new Error('message incorrecto');
  if (payload.conversation_id !== null) throw new Error('conversation_id incorrecto');
  if (payload.scope_turn_id !== 't1') throw new Error('scope_turn_id incorrecto');
  if (payload.repeat_from_turn_id !== 't1') throw new Error('repeat_from_turn_id incorrecto');

  if (hookEvents.replyReady !== 1) throw new Error('onReplyReady no disparó una vez');

  if (fetchCalls.some((call) => call.url === '/api/optimizador/chat')) {
    throw new Error('Se llamó endpoint legacy /chat');
  }

  process.exit(0);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""


def test_chat_runtime_refresh_and_send_contract() -> None:
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, str(RUNTIME_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node runtime contract test failed\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
