const POLL_MS = 2000;

const state = {
  optimizerSessionId: "default",
  defaultUserId: "u_optimizador",
  defaultSessionId: "optimizador-main",
  sessions: [],
  selectedSessionKey: "",
  selectedConversation: "",
  selectedTurnId: "",
  turns: [],
  dialogue: [],
  waitingReply: false,
  lastKnownTurnId: "",
  pollTimer: null,
  liveFollow: true,
};

const byId = (id) => document.getElementById(id);

const chatRuntime = window.createOptimizadorChatRuntime(state);

function render() {
  const history = byId("chatHistory");
  if (!history) return;
  history.innerHTML = chatRuntime.renderChatHistoryHtml(state.dialogue, state.waitingReply);
  history.scrollTop = history.scrollHeight;
  byId("sendBtn").disabled = state.waitingReply;
}

function bind() {
  byId("chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = byId("chatInput");
    const message = input.value.trim();
    if (!message || state.waitingReply) return;
    input.value = "";

    try {
      await chatRuntime.sendChat(message, {
        followLive: state.liveFollow,
        onBeforeSend: render,
      });
    } catch (error) {
      input.value = message;
      // eslint-disable-next-line no-alert
      alert(`Chat falló: ${error.message || error}`);
    }

    render();
  });
}

async function boot() {
  await chatRuntime.refresh({ autoSelect: true, followLive: state.liveFollow });
  render();
  bind();

  chatRuntime.startPolling({
    intervalMs: POLL_MS,
    onTick: async () => {
      await chatRuntime.refresh({ followLive: state.liveFollow });
      render();
    },
  });
}

boot().catch((error) => {
  document.body.innerHTML = `<pre>${chatRuntime.escapeHtml(error.message || String(error))}</pre>`;
});
