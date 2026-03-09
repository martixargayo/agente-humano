const TABS = ["Chat", "Timeline", "Nodos", "Guardrails", "Trace", "Evals", "Datasets / Casos", "Prompts", "Cambios", "Diálogo"];
const COPYABLE_TABS = ["Chat", "Timeline", "Nodos", "Guardrails", "Trace", "Cambios", "Diálogo", "Datasets / Casos", "Prompts", "Evals"];
const POLL_IDLE_MS = 2000;
const POLL_BUSY_MS = 900;

const EVAL_TOOLTIPS = {
  run_fixture_evals: "Ejecuta pruebas rápidas con casos de ejemplo fijos.",
  run_live_evals: "Ejecuta pruebas reales usando llamadas en vivo.",
  run_e2e_mock: "Prueba el flujo completo con casos simulados.",
  run_e2e_live: "Prueba el flujo completo con ejecución real.",
  run_all: "Ejecuta todas las pruebas no live.",
  run_all_live: "Ejecuta todas las pruebas live.",
};

const state = {
  optimizerSessionId: "default",
  sessions: [], selectedSessionKey: "", selectedConversation: "",
  turns: [], selectedTurnId: "", turn: null,
  dialogue: [], prompts: [], cases: [], overrides: { mode: "mirror", entries: [], workspace_version: 1 },
  copyTabs: new Set(["Chat", "Timeline", "Cambios"]),
  liveFollow: true, editing: false, busy: false, waitingReply: false,
  draftEntries: [], evalOut: "", lastKnownTurnId: "", pollTimer: null,
  chatDraft: "", activeTab: "Chat",
  defaultUserId: "u_optimizador",
  defaultSessionId: "optimizador-main",
  lastUiSnapshot: "",
};

const $ = (q) => document.querySelector(q);
const byId = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(`/api/optimizador${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

const deepEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const escapeHtml = (s) => String(s ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const selectedSession = () => state.sessions.find((s) => s.session_key === state.selectedSessionKey) || null;

function currentTurnOptionLabel() {
  const row = state.turns.find((x) => x.turn_id === state.selectedTurnId);
  return row ? `Turno ${row.index} · v${row.version || 1}` : "Turno - · v1";
}

function pendingChangesCount() {
  return deepEqual(state.draftEntries, state.overrides.entries || []) ? 0 : 1;
}

function showToast(text, type = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1800);
}

async function refresh({ autoSelect = false } = {}) {
  const prevSelected = state.selectedTurnId;
  state.sessions = (await api("/sessions")).items;
  if (!state.sessions.length) {
    await api("/sessions/bootstrap", { method: "POST", body: JSON.stringify({ user_id: state.defaultUserId, session_id: state.defaultSessionId }) });
    state.sessions = (await api("/sessions")).items;
  }
  if (!state.selectedSessionKey && state.sessions[0]) state.selectedSessionKey = state.sessions[0].session_key;
  const s = selectedSession();
  if (!s) return;
  const base = `/sessions/${encodeURIComponent(s.user_id)}/${encodeURIComponent(s.session_id)}`;
  state.turns = (await api(`${base}/turns${state.selectedConversation ? `?conversation_id=${encodeURIComponent(state.selectedConversation)}` : ""}`)).items;
  const nextLast = state.turns[state.turns.length - 1]?.turn_id || "";
  if (state.liveFollow || autoSelect || !state.selectedTurnId) state.selectedTurnId = nextLast;
  else if (prevSelected && state.turns.some((x) => x.turn_id === prevSelected)) state.selectedTurnId = prevSelected;
  else state.selectedTurnId = nextLast;

  state.turn = state.selectedTurnId ? await api(`/turns/${state.selectedTurnId}`) : null;
  state.dialogue = (await api(`${base}/dialogue`)).items;
  state.cases = (await api("/cases")).items;
  state.prompts = (await api("/prompts")).items;
  state.overrides = await api(`/overrides/${state.optimizerSessionId}`);
  if (!state.editing) state.draftEntries = structuredClone(state.overrides.entries || []);

  const latest = state.turns[state.turns.length - 1]?.turn_id || "";
  if (state.lastKnownTurnId && latest && latest !== state.lastKnownTurnId && !state.liveFollow) showToast("Nuevo turno disponible", "warn");
  state.lastKnownTurnId = latest;
  if (state.waitingReply && latest && latest !== prevSelected) {
    state.waitingReply = false;
    showToast("Respuesta lista");
  }
}



function buildUiSnapshot() {
  return JSON.stringify({
    selectedSessionKey: state.selectedSessionKey,
    selectedTurnId: state.selectedTurnId,
    liveFollow: state.liveFollow,
    waitingReply: state.waitingReply,
    editing: state.editing,
    turns: state.turns.map((t) => `${t.turn_id}:${t.version || 1}`).join("|"),
    dialogueLen: state.dialogue.length,
    dialogueLast: state.dialogue[state.dialogue.length - 1]?.turn_id || "",
    promptsHash: state.prompts.map((p) => `${p.node}:${(p.base_text || "").length}`).join("|"),
    draftHash: JSON.stringify(state.draftEntries || []),
    casesLen: state.cases.length,
    workspaceVersion: state.overrides.workspace_version || 1,
    mode: state.overrides.mode || "mirror",
  });
}

function captureInteractionState() {
  const content = byId("content");
  const active = document.activeElement;
  const focusedPrompt = active?.matches?.("textarea.promptTextarea[data-node]")
    ? {
        node: active.dataset.node,
        selectionStart: active.selectionStart,
        selectionEnd: active.selectionEnd,
      }
    : null;
  return {
    scrollTop: content?.scrollTop ?? 0,
    focusedPrompt,
  };
}

function restoreInteractionState(snapshot) {
  const content = byId("content");
  if (content) content.scrollTop = snapshot.scrollTop;
  if (snapshot.focusedPrompt) {
    const target = document.querySelector(`textarea.promptTextarea[data-node='${snapshot.focusedPrompt.node}']`);
    if (target) {
      target.focus();
      if (typeof snapshot.focusedPrompt.selectionStart === "number" && typeof snapshot.focusedPrompt.selectionEnd === "number") {
        target.setSelectionRange(snapshot.focusedPrompt.selectionStart, snapshot.focusedPrompt.selectionEnd);
      }
    }
  }
}

function renderTabs() {
  byId("tabs").innerHTML = TABS.map((t) => `<button data-tab='${t}' class='${state.activeTab === t ? "active" : ""}'>${t}</button>`).join("");
}

function renderTopbar() {
  const disabledCopy = state.busy;
  const ws = state.overrides.workspace_version || 1;
  byId("topbar").innerHTML = `
  <div class='top-left'>
    <select id='turnSelector' title='Elige el turno y versión para revisar las pestañas.'>
      ${state.turns.map((t) => `<option value='${t.turn_id}' ${t.turn_id === state.selectedTurnId ? "selected" : ""}>Turno ${t.index} · v${t.version || 1}</option>`).join("")}
    </select>
  </div>
  <div class='top-mid'>Trabajando en versión v${ws} · selección: ${currentTurnOptionLabel()}</div>
  <div class='top-right'>
    <details class='copyMenu'><summary>Secciones copiar (${state.copyTabs.size})</summary>${COPYABLE_TABS.map((t) => `<label><input type='checkbox' data-copy='${t}' ${state.copyTabs.has(t) ? "checked" : ""}/> ${t}</label>`).join("")}</details>
    <button id='copyBtn' ${disabledCopy ? "disabled" : ""}>Copiar</button>
    <button id='editBtn' class='${state.editing ? "active" : ""}' title='Marca en naranja lo editable para preparar cambios.'>${state.editing ? "Salir edición" : "Editar"}</button>
  </div>`;
}

function toolbarHtml() {
  const s = selectedSession();
  const meta = s?.sandbox_meta || {};
  return `<div class='toolbar'>
    <span class='badge' title='Estás trabajando sobre una copia para hacer cambios sin tocar la conversación original.'>${state.overrides.mode === "sandbox" ? "Probar" : "Ver"}</span>
    <span class='badge' title='Si está activado, el optimizador se mueve solo al último turno nuevo.'>follow:${state.liveFollow ? "on" : "off"}</span>
    ${s?.is_sandbox ? `<span class='badge' title='Esta conversación es una copia creada para probar cambios.'>sandbox clonado · ${meta.source_session_id || "-"}</span>` : ""}
    <button id='toggleFollow' title='Activa o desactiva que el optimizador siga automáticamente los nuevos turnos.'>live follow</button>
    <button id='repeatBtn' title='Vuelve a ejecutar el último mensaje usando la versión actual de trabajo.'>Repetir</button>
    <button id='newConvBtn' title='Empieza una conversación nueva desde cero, sin arrastrar el historial anterior.'>Nueva conversación</button>
    <button id='saveCaseBtn' title='Guarda este turno como caso para revisarlo o usarlo en evals.'>Guardar caso</button>
    <button id='resetOverridesBtn' title='Quita los cambios temporales y vuelve a la versión base.'>Reset overrides</button>
  </div>`;
}

function renderTab() {
  const tab = state.activeTab;
  const t = state.turn || {};
  let html = toolbarHtml();
  if (tab === "Chat") html += `<div class='panel'><div class='card' id='chatHistory'>${state.dialogue.map((d) => `<div class='msg ${d.role}'>${d.role === "user" ? "Usuario" : "IA"}: ${escapeHtml(d.text || "")}</div>`).join("")}${state.waitingReply ? "<div class='msg assistant pending'>IA: pensando...</div>" : ""}</div><div class='card'><textarea id='chatInput' placeholder='Escribe tu mensaje...'>${escapeHtml(state.chatDraft)}</textarea><div class='sendRow'><span class='hint'>El próximo mensaje se envía con versión v${state.overrides.workspace_version || 1}.</span><button id='sendBtn'>Enviar</button></div></div></div>`;
  if (tab === "Timeline") html += `<div class='card'>${(t.logs || []).map((l) => `<div class='timeline-item ${statusClass(l.source, l.status)}'><b>${l.node_name}</b> · ${l.status} · ${l.latency_ms}ms · ${l.source}</div>`).join("") || "Sin datos"}</div>`;
  if (tab === "Nodos") html += `<div class='grid2'>${Object.entries(t.nodes || {}).map(([k, v]) => `<div class='card'><h3>${k}</h3><pre>${escapeHtml(JSON.stringify(v, null, 2))}</pre></div>`).join("")}</div>`;
  if (tab === "Guardrails") html += `<div class='grid2'><div class='card'><h3>Input</h3><pre>${escapeHtml(JSON.stringify({decision:t.input_guardrail_decision,reasons:t.input_guardrail_reasons,triggered:t.input_guardrail_triggered,moderation:t.input_moderation_used},null,2))}</pre></div><div class='card'><h3>Output</h3><pre>${escapeHtml(JSON.stringify({decision:t.output_guardrail_decision,reasons:t.output_guardrail_reasons,triggered:t.output_guardrail_triggered,rewrite:t.output_guardrail_rewrite_applied,moderation:t.output_moderation_used},null,2))}</pre></div></div>`;
  if (tab === "Trace") html += `<div class='card'><pre>${escapeHtml(JSON.stringify(t, null, 2))}</pre></div>`;
  if (tab === "Evals") html += `<div class='card'>${Object.keys(EVAL_TOOLTIPS).map((a)=>`<button class='evalBtn' data-act='${a}' title='${EVAL_TOOLTIPS[a]}'>${a}</button>`).join(" ")}<pre id='evalOut'>${escapeHtml(state.evalOut)}</pre></div>`;
  if (tab === "Datasets / Casos") html += `<div class='card'><pre>${escapeHtml(JSON.stringify(state.cases.slice(-30), null, 2))}</pre></div>`;
  if (tab === "Prompts") html += `<div class='panel'>${state.prompts.map((p) => {
    const found = (state.draftEntries || []).find((e) => e.category === "prompt" && e.key === p.node);
    const val = found ? found.value : p.base_text;
    const changed = (found?.value ?? p.base_text) !== p.base_text;
    return `<div class='card ${state.editing ? "editable" : ""} ${changed ? "changed" : ""}'><h3>${p.node}</h3><textarea class='promptTextarea' data-node='${p.node}' ${state.editing ? "" : "disabled"}>${escapeHtml(val)}</textarea></div>`;
  }).join("")}</div>`;
  if (tab === "Cambios") html += renderChanges();
  if (tab === "Diálogo") html += `<div class='card'>${state.dialogue.map((d) => `<div class='msg ${d.role}'><b>${d.role}:</b> ${escapeHtml(d.text || "")}</div>`).join("")}</div>`;

  html += `<div class='editStatus ${state.editing ? "on" : ""}' id='editStatus'>${state.editing ? `modo edición · ${pendingChangesCount()} cambio${pendingChangesCount() === 1 ? "" : "s"}` : `modo lectura · v${state.overrides.workspace_version || 1}`}</div>`;
  byId("content").innerHTML = html;
  autosizePromptTextareas();
}



function autosizePromptTextareas() {
  document.querySelectorAll("textarea.promptTextarea").forEach((ta) => {
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  });
}

function renderChanges() {
  const base = state.turns.find((x) => (x.version || 1) === 1 && (x.index === (state.turn?.index || x.index)));
  const changedPrompts = (state.draftEntries || []).filter((e) => e.category === "prompt");
  const changedConfig = (state.draftEntries || []).filter((e) => e.category === "config");
  const changedCtx = (state.draftEntries || []).filter((e) => e.category === "contextual");
  return `<div class='panel'>
    <div class='card'>Estás trabajando sobre <b>v${state.overrides.workspace_version || 1}</b>. El próximo mensaje usará esta versión actual.</div>
    <div class='card'><h3>Base</h3><div>${base ? `Turno ${base.index} · v${base.version || 1}` : "Sin base detectada"}</div></div>
    <div class='card'><h3>Cambios de prompts</h3><pre>${escapeHtml(JSON.stringify(changedPrompts, null, 2))}</pre></div>
    <div class='card'><h3>Cambios de config</h3><pre>${escapeHtml(JSON.stringify(changedConfig, null, 2))}</pre></div>
    <div class='card'><h3>Cambios de contexto</h3><pre>${escapeHtml(JSON.stringify(changedCtx, null, 2))}</pre></div>
  </div>`;
}

function statusClass(source, status) {
  if (["exception", "parse_error", "refusal"].includes(source) || ["refuse", "block"].includes(status)) return "err";
  if (source === "fallback" || status === "rewrite") return "warn";
  return "ok";
}

function copyTextForTab(tab) {
  const t = state.turn || {};
  if (tab === "Chat" || tab === "Diálogo") return state.dialogue.map((d) => `${d.role}: ${d.text}`).join("\n");
  if (tab === "Timeline") return (t.logs || []).map((l) => `${l.node_name}: ${l.status} (${l.source}) ${l.latency_ms}ms`).join("\n");
  if (tab === "Nodos") return JSON.stringify(t.nodes || {}, null, 2);
  if (tab === "Guardrails") return JSON.stringify({ input: t.input_guardrail_decision, output: t.output_guardrail_decision }, null, 2);
  if (tab === "Trace") return JSON.stringify(t, null, 2);
  if (tab === "Prompts") return (state.draftEntries || []).filter((e) => e.category === "prompt").map((p) => `# ${p.key}\n${p.value}`).join("\n\n");
  if (tab === "Cambios") return JSON.stringify({ workspace_version: state.overrides.workspace_version, draft_entries: state.draftEntries }, null, 2);
  if (tab === "Datasets / Casos") return JSON.stringify(state.cases.slice(-30), null, 2);
  if (tab === "Evals") return state.evalOut;
  return "";
}

async function copyMulti() {
  const sections = [...state.copyTabs].map((tab) => `=== ${tab} ===\n${copyTextForTab(tab)}`).join("\n\n");
  if (!sections.trim()) throw new Error("Sin secciones seleccionadas");
  await navigator.clipboard.writeText(sections);
}

function bindEvents() {
  byId("tabs").onclick = (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    state.activeTab = b.dataset.tab;
    renderTabs(); renderTopbar(); renderTab(); bindEvents();
  };

  byId("turnSelector")?.addEventListener("change", async (e) => {
    state.selectedTurnId = e.target.value;
    state.liveFollow = false;
    await refresh();
    renderTopbar(); renderTab(); bindEvents();
  });

  document.querySelectorAll("input[data-copy]").forEach((cb) => cb.onchange = () => {
    if (cb.checked) state.copyTabs.add(cb.dataset.copy); else state.copyTabs.delete(cb.dataset.copy);
    renderTopbar(); bindEvents();
  });

  byId("copyBtn")?.addEventListener("click", async () => { try { await copyMulti(); showToast("Copiado"); } catch { showToast("Error al copiar", "err"); } });
  byId("editBtn")?.addEventListener("click", async () => {
    if (state.overrides.mode === "mirror") {
      const s = selectedSession();
      if (!s) return;
      await api("/sandbox/clone", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, source_user_id: s.user_id, source_session_id: s.session_id, source_conversation_id: state.selectedConversation || null }) });
      await api(`/overrides/${state.optimizerSessionId}`, { method: "PUT", body: JSON.stringify({ mode: "sandbox", entries: state.overrides.entries || [] }) });
      state.editing = true;
    } else state.editing = !state.editing;
    await refresh({ autoSelect: true }); renderTopbar(); renderTab(); bindEvents();
  });

  byId("toggleFollow")?.addEventListener("click", async () => { state.liveFollow = !state.liveFollow; await refresh({ autoSelect: state.liveFollow }); renderTopbar(); renderTab(); bindEvents(); });
  byId("repeatBtn")?.addEventListener("click", async () => {
    const text = state.turn?.user_turn?.raw_text; if (!text) return showToast("Sin turno", "warn");
    await sendChat(text, state.selectedTurnId); showToast("Turno repetido");
  });
  byId("newConvBtn")?.addEventListener("click", async () => {
    const s = selectedSession(); if (!s) return;
    await api("/sandbox/new_conversation", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, user_id: s.user_id, session_id: s.session_id }) });
    await refresh({ autoSelect: true }); renderTopbar(); renderTab(); bindEvents();
  });
  byId("saveCaseBtn")?.addEventListener("click", async () => {
    if (!state.selectedTurnId) return; await api("/cases", { method: "POST", body: JSON.stringify({ turn_id: state.selectedTurnId, family: "end_to_end", tags: ["manual"], notes: "guardado desde optimizador" }) }); showToast("Caso guardado");
  });
  byId("resetOverridesBtn")?.addEventListener("click", async () => { await api(`/overrides/${state.optimizerSessionId}`, { method: "DELETE" }); state.editing = false; await refresh(); renderTopbar(); renderTab(); bindEvents(); });

  byId("chatInput")?.addEventListener("input", (e) => { state.chatDraft = e.target.value; });
  byId("sendBtn")?.addEventListener("click", async () => { if (!state.chatDraft.trim()) return; const msg = state.chatDraft; state.chatDraft = ""; try { await sendChat(msg); } catch (_) { state.chatDraft = msg; renderTab(); bindEvents(); } });

  document.querySelectorAll(".evalBtn").forEach((b) => b.addEventListener("click", async () => {
    state.evalOut = JSON.stringify(await api(`/evals/${b.dataset.act}`, { method: "POST" }), null, 2);
    renderTab(); bindEvents();
  }));

  document.querySelectorAll("textarea[data-node]").forEach((ta) => ta.addEventListener("input", (e) => {
    if (!state.editing) return;
    autosizePromptTextareas();
    const node = e.target.dataset.node;
    const base = state.prompts.find((p) => p.node === node)?.base_text || "";
    state.draftEntries = (state.draftEntries || []).filter((x) => !(x.category === "prompt" && x.key === node));
    if (e.target.value !== base) state.draftEntries.push({ category: "prompt", key: node, value: e.target.value, scope: "this_optimizer_session" });
    byId("editStatus").textContent = `modo edición · ${pendingChangesCount()} cambio${pendingChangesCount() === 1 ? "" : "s"}`;
    e.target.closest(".card")?.classList.toggle("changed", e.target.value !== base);
  }));

  byId("editStatus")?.addEventListener("click", async () => {
    if (!state.editing || pendingChangesCount() === 0) return;
    if (!window.confirm("¿Confirmar cambios?")) return;
    await api(`/overrides/${state.optimizerSessionId}/confirm`, { method: "POST", body: JSON.stringify({ entries: state.draftEntries }) });
    await refresh();
    showToast(`Cambios confirmados · v${state.overrides.workspace_version}`);
    renderTopbar(); renderTab(); bindEvents();
  });
}

async function sendChat(message, repeatFrom = null) {
  const s = selectedSession();
  if (!s) throw new Error("No hay sesión activa en optimizador");
  state.waitingReply = true;
  renderTab();
  try {
    const result = await api("/sandbox/turn", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, user_id: s.user_id, session_id: s.session_id, message, conversation_id: state.selectedConversation || null, scope_turn_id: state.selectedTurnId || null, repeat_from_turn_id: repeatFrom }) });
    await refresh({ autoSelect: true });
    if (result?.reply && !state.dialogue.some((d) => d.role === "assistant" && d.text === result.reply)) {
      state.dialogue.push({ role: "assistant", text: result.reply });
    }
  } catch (e) {
    state.waitingReply = false;
    showToast(`Chat falló: ${e.message || e}`, "err");
    throw e;
  }
  renderTopbar(); renderTab(); bindEvents();
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    const typingChat = byId("chatInput") === document.activeElement;
    const prevTurnId = state.lastKnownTurnId;
    const beforeSnapshot = state.lastUiSnapshot || buildUiSnapshot();
    const interaction = captureInteractionState();
    try {
      await refresh();
      const afterSnapshot = buildUiSnapshot();
      const hasChanges = beforeSnapshot !== afterSnapshot;
      const hasNewTurn = prevTurnId !== state.lastKnownTurnId;
      state.lastUiSnapshot = afterSnapshot;

      if (!hasChanges && !hasNewTurn) return;

      if (state.activeTab === "Chat" && typingChat && !hasNewTurn) {
        byId("chatHistory").innerHTML = state.dialogue.map((d) => `<div class='msg ${d.role}'>${d.role === "user" ? "Usuario" : "IA"}: ${escapeHtml(d.text || "")}</div>`).join("") + (state.waitingReply ? "<div class='msg assistant pending'>IA: pensando...</div>" : "");
      } else {
        renderTopbar();
        renderTab();
        bindEvents();
        restoreInteractionState(interaction);
      }
    } catch (_) {}
  }, POLL_IDLE_MS);
}

async function boot() {
  renderTabs();
  await refresh({ autoSelect: true });
  renderTopbar();
  renderTab();
  bindEvents();
  state.lastUiSnapshot = buildUiSnapshot();
  startPolling();
}

boot().catch((e) => { document.body.innerHTML = `<pre>${escapeHtml(e.message)}</pre>`; });
