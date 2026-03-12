(function initChatRuntime(globalScope) {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function renderChatHistoryHtml(dialogue, waitingReply) {
    const rows = (dialogue || [])
      .map(
        (entry) =>
          `<div class='msg ${entry.role}'>${entry.role === "user" ? "Usuario" : "IA"}: ${escapeHtml(entry.text || "")}</div>`,
      )
      .join("");
    return `${rows}${waitingReply ? "<div class='msg assistant pending'>IA: pensando...</div>" : ""}`;
  }

  function createOptimizadorChatRuntime(state, hooks = {}) {
    async function api(path, opts = {}) {
      const response = await fetch(`/api/optimizador${path}`, {
        headers: { "Content-Type": "application/json" },
        ...opts,
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    function selectedSession() {
      return state.sessions.find((session) => session.session_key === state.selectedSessionKey) || null;
    }

    async function refresh({ autoSelect = false, followLive = Boolean(state.liveFollow) } = {}) {
      const prevSelectedTurnId = state.selectedTurnId;
      const prevLastKnownTurnId = state.lastKnownTurnId || "";

      state.sessions = (await api("/sessions")).items;
      if (!state.sessions.length) {
        await api("/sessions/bootstrap", {
          method: "POST",
          body: JSON.stringify({ user_id: state.defaultUserId, session_id: state.defaultSessionId }),
        });
        state.sessions = (await api("/sessions")).items;
      }

      if (!state.selectedSessionKey && state.sessions[0]) {
        state.selectedSessionKey = state.sessions[0].session_key;
      }

      const session = selectedSession();
      if (!session) return;

      const base = `/sessions/${encodeURIComponent(session.user_id)}/${encodeURIComponent(session.session_id)}`;
      state.turns = (
        await api(
          `${base}/turns${state.selectedConversation ? `?conversation_id=${encodeURIComponent(state.selectedConversation)}` : ""}`,
        )
      ).items;

      const nextLastTurnId = state.turns[state.turns.length - 1]?.turn_id || "";
      if (followLive || autoSelect || !state.selectedTurnId) {
        state.selectedTurnId = nextLastTurnId;
      } else if (prevSelectedTurnId && state.turns.some((turn) => turn.turn_id === prevSelectedTurnId)) {
        state.selectedTurnId = prevSelectedTurnId;
      } else {
        state.selectedTurnId = nextLastTurnId;
      }

      state.dialogue = (await api(`${base}/dialogue`)).items;

      if (typeof hooks.fetchExtraData === "function") {
        await hooks.fetchExtraData({ state, api, base });
      }

      const hasNewTurn = Boolean(prevLastKnownTurnId && nextLastTurnId && nextLastTurnId !== prevLastKnownTurnId);
      if (hasNewTurn && !followLive && typeof hooks.onNewTurnAvailable === "function") {
        hooks.onNewTurnAvailable({ state, latestTurnId: nextLastTurnId, previousTurnId: prevLastKnownTurnId });
      }
      state.lastKnownTurnId = nextLastTurnId;

      if (state.waitingReply && nextLastTurnId && nextLastTurnId !== prevSelectedTurnId) {
        state.waitingReply = false;
        if (typeof hooks.onReplyReady === "function") {
          hooks.onReplyReady({ state, latestTurnId: nextLastTurnId, previousSelectedTurnId: prevSelectedTurnId });
        }
      }
    }

    async function sendChat(message, { repeatFrom = null, onBeforeSend, onAfterSend, onError, autoSelect = true, followLive = Boolean(state.liveFollow) } = {}) {
      const session = selectedSession();
      if (!session) throw new Error("No hay sesión activa en optimizador");

      state.waitingReply = true;
      if (typeof onBeforeSend === "function") onBeforeSend();

      try {
        const result = await api("/sandbox/turn", {
          method: "POST",
          body: JSON.stringify({
            optimizer_session_id: state.optimizerSessionId,
            user_id: session.user_id,
            session_id: session.session_id,
            message,
            conversation_id: state.selectedConversation || null,
            scope_turn_id: state.selectedTurnId || null,
            repeat_from_turn_id: repeatFrom,
          }),
        });

        await refresh({ autoSelect, followLive });

        if (result?.reply && !state.dialogue.some((d) => d.role === "assistant" && d.text === result.reply)) {
          state.dialogue.push({ role: "assistant", text: result.reply });
        }

        if (typeof onAfterSend === "function") onAfterSend(result);
        return result;
      } catch (error) {
        state.waitingReply = false;
        if (typeof onError === "function") onError(error);
        throw error;
      }
    }

    function startPolling({ intervalMs, onTick, onError }) {
      if (state.pollTimer) clearInterval(state.pollTimer);
      state.pollTimer = setInterval(async () => {
        try {
          await onTick();
        } catch (error) {
          if (typeof onError === "function") onError(error);
        }
      }, intervalMs);
    }

    return {
      api,
      escapeHtml,
      renderChatHistoryHtml,
      selectedSession,
      refresh,
      sendChat,
      startPolling,
    };
  }

  globalScope.createOptimizadorChatRuntime = createOptimizadorChatRuntime;
  globalScope.escapeChatHtml = escapeHtml;
})(window);
