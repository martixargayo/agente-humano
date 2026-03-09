const TABS = ["Chat","Resumen","Timeline","Nodos","Guardrails","Trace","Evals","Datasets / Casos","Prompts","Comparar","Diálogo","Experimentos"];
const POLL_MS = 2500;

const state = {
  optimizerSessionId: "default",
  sessions: [],
  selectedSessionKey: "",
  selectedConversation: "",
  turns: [],
  selectedTurnId: "",
  turn: null,
  conversations: [],
  dialogue: [],
  prompts: [],
  cases: [],
  overrides: { mode: "mirror", entries: [] },
  compareResult: null,
  liveFollow: true,
  editing: false,
  busy: false,
  pollTimer: null,
};

const $ = (q) => document.querySelector(q);

async function api(path, opts = {}) {
  const r = await fetch(`/api/optimizador${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function showToast(text, type = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1800);
}

function selectedSession() { return state.sessions.find((s) => s.session_key === state.selectedSessionKey) || null; }
function modeLabel(mode) { return mode === "sandbox" ? "Probar" : "Ver"; }
function activeTab() { return $("#tabs button.active")?.dataset.tab || "Chat"; }

function turnTitle() {
  const t = state.turn || {};
  const row = state.turns.find((x) => x.turn_id === t.turn_id);
  if (!row) return "Turno - · v1";
  return `Turno ${row.index} · v${row.version || 1}`;
}

async function refresh({ autoSelect = false } = {}) {
  const prevSelected = state.selectedTurnId;
  const prevLast = state.turns[state.turns.length - 1]?.turn_id;

  state.sessions = (await api("/sessions")).items;
  if (!state.selectedSessionKey && state.sessions[0]) state.selectedSessionKey = state.sessions[0].session_key;
  const s = selectedSession();
  if (!s) return;

  const base = `/sessions/${encodeURIComponent(s.user_id)}/${encodeURIComponent(s.session_id)}`;
  state.conversations = (await api(`${base}/conversations`)).items;
  state.turns = (await api(`${base}/turns${state.selectedConversation ? `?conversation_id=${encodeURIComponent(state.selectedConversation)}` : ""}`)).items;

  const nextLast = state.turns[state.turns.length - 1]?.turn_id;
  if (state.liveFollow || autoSelect) state.selectedTurnId = nextLast || "";
  else if (prevSelected && state.turns.some((x) => x.turn_id === prevSelected)) state.selectedTurnId = prevSelected;
  else state.selectedTurnId = nextLast || "";

  if (!state.liveFollow && prevLast && nextLast && prevLast !== nextLast) showToast("Nuevo turno disponible", "warn");

  state.turn = state.selectedTurnId ? await api(`/turns/${state.selectedTurnId}`) : null;
  state.dialogue = (await api(`${base}/dialogue`)).items;
  state.cases = (await api("/cases")).items;
  state.prompts = (await api("/prompts")).items;
  state.overrides = await api(`/overrides/${state.optimizerSessionId}`);
}

async function runAction(label, fn) {
  if (state.busy) return;
  state.busy = true;
  renderTopbar();
  try {
    await fn();
    showToast(label);
  } catch (e) {
    showToast(`${label} falló`, "err");
  } finally {
    state.busy = false;
    renderTopbar();
    renderTab(activeTab());
  }
}

function copyTextForTab(tab) {
  const t = state.turn || {};
  if (["Resumen", "Experimentos"].includes(tab)) return null;
  if (tab === "Chat" || tab === "Diálogo") return state.dialogue.map((d) => `${d.role}: ${d.text}`).join("\n");
  if (tab === "Timeline") return (t.logs || []).map((l) => `${l.node_name}: ${l.status} (${l.source}) ${l.latency_ms}ms`).join("\n");
  if (tab === "Nodos") return JSON.stringify(t.nodes || {}, null, 2);
  if (tab === "Guardrails") return JSON.stringify({ input: { decision: t.input_guardrail_decision, reasons: t.input_guardrail_reasons }, output: { decision: t.output_guardrail_decision, reasons: t.output_guardrail_reasons } }, null, 2);
  if (tab === "Trace") return JSON.stringify(t, null, 2);
  if (tab === "Prompts") return (state.prompts || []).map((p) => `# ${p.node}\n${p.base_text}`).join("\n\n");
  if (tab === "Comparar") return JSON.stringify(state.compareResult || {}, null, 2);
  if (tab === "Datasets / Casos") return JSON.stringify(state.cases.slice(-10), null, 2);
  if (tab === "Evals") return $("#evalOut")?.textContent || "";
  return JSON.stringify(t, null, 2);
}

async function onCopy() {
  const txt = copyTextForTab(activeTab());
  if (txt == null) return showToast("Copiar no disponible aquí", "warn");
  await navigator.clipboard.writeText(txt);
  showToast("Copiado");
}

async function onEdit() {
  const s = selectedSession();
  if (!s) return;
  if (state.overrides.mode === "mirror") {
    const clone = await api("/sandbox/clone", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, source_user_id: s.user_id, source_session_id: s.session_id, source_conversation_id: state.selectedConversation || null }) });
    state.selectedSessionKey = clone.session_key;
    await api(`/overrides/${state.optimizerSessionId}`, { method: "PUT", body: JSON.stringify({ mode: "sandbox", entries: state.overrides.entries || [] }) });
    state.editing = true;
    await refresh({ autoSelect: true });
    return;
  }
  state.editing = !state.editing;
}

async function sendChat(message, repeatFrom = null) {
  const s = selectedSession();
  if (!s || !message?.trim()) return;
  await api("/sandbox/turn", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, user_id: s.user_id, session_id: s.session_id, message, conversation_id: state.selectedConversation || null, scope_turn_id: state.selectedTurnId || null, repeat_from_turn_id: repeatFrom }) });
  await refresh({ autoSelect: true });
}

async function newConversation() {
  const s = selectedSession();
  if (!s) return;
  const created = await api("/sandbox/new_conversation", { method: "POST", body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, user_id: s.user_id, session_id: s.session_id }) });
  state.selectedSessionKey = created.session_key;
  state.selectedConversation = "";
  await refresh({ autoSelect: true });
}

function renderTopbar() {
  const t = state.turn || {};
  const lat = t.total_latency_ms ? `${(Number(t.total_latency_ms) / 1000).toFixed(1)}s` : "-";
  $("#topbar").innerHTML = `
    <div class='top-left'>${turnTitle()}</div>
    <div class='top-mid'>latencia total: ${lat}</div>
    <div class='top-right'>
      <button id='copyBtn' ${["Resumen", "Experimentos"].includes(activeTab()) ? "disabled" : ""}>Copiar</button>
      <button id='editBtn' class='${state.editing ? "active" : ""}'>${state.busy ? "..." : "Editar"}</button>
    </div>
  `;
  $("#copyBtn").onclick = () => runAction("Copiado", onCopy);
  $("#editBtn").onclick = () => runAction(state.editing ? "Edición desactivada" : "Modo edición", onEdit);
}

function renderTabs() {
  $("#tabs").innerHTML = TABS.map((t) => `<button data-tab='${t}'>${t}</button>`).join("");
  $("#tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) renderTab(b.dataset.tab); };
}

function renderToolbar() {
  const s = selectedSession();
  const meta = s?.sandbox_meta || {};
  return `
  <div class='toolbar'>
    <span class='badge'>${modeLabel(state.overrides.mode)}</span>
    <span class='badge'>follow:${state.liveFollow ? "on" : "off"}</span>
    ${s?.is_sandbox ? `<span class='badge'>sandbox clonado · ${meta.source_session_id || "-"}</span>` : ""}
    ${state.editing ? "<span class='badge'>modo edición</span>" : ""}
    <button id='toggleFollow'>live follow</button>
    <button id='repeatBtn'>Repetir</button>
    <button id='newConvBtn'>Nueva conversación</button>
    <button id='saveCaseBtn'>Guardar caso</button>
    <button id='resetOverridesBtn'>Reset overrides</button>
  </div>`;
}

function renderTab(tab) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const c = $("#content");
  const t = state.turn || {};
  let html = renderToolbar();
  if (tab === "Chat") html += `<div class='panel'><div class='card scroll'>${state.dialogue.map((d) => `<div class='msg ${d.role}'>${d.role === "user" ? "Usuario" : "IA"}: ${escapeHtml(d.text || "")}</div>`).join("")}</div><div class='card'><textarea id='chatInput' placeholder='Escribe...'></textarea><button id='sendBtn'>Enviar</button></div></div>`;
  if (tab === "Resumen") html += `<div class='card scroll'><pre>${escapeHtml(JSON.stringify(t, null, 2))}</pre></div>`;
  if (tab === "Timeline") html += `<div class='card scroll'>${(t.logs || []).map((l) => `<div class='timeline-item ${statusClass(l.source, l.status)}'><b>${l.node_name}</b> · ${l.status} · ${l.latency_ms}ms · ${l.source}</div>`).join("")}</div>`;
  if (tab === "Nodos") html += `<div class='grid2'>${Object.entries(t.nodes || {}).map(([k, v]) => `<div class='card scroll'><h3>${k}</h3><pre>${escapeHtml(JSON.stringify(v, null, 2))}</pre></div>`).join("")}</div>`;
  if (tab === "Guardrails") html += `<div class='grid2'><div class='card scroll'><h3>Input</h3><pre>${escapeHtml(JSON.stringify({decision:t.input_guardrail_decision,reasons:t.input_guardrail_reasons,triggered:t.input_guardrail_triggered,moderation:t.input_moderation_used},null,2))}</pre></div><div class='card scroll'><h3>Output</h3><pre>${escapeHtml(JSON.stringify({decision:t.output_guardrail_decision,reasons:t.output_guardrail_reasons,triggered:t.output_guardrail_triggered,rewrite:t.output_guardrail_rewrite_applied,moderation:t.output_moderation_used},null,2))}</pre></div></div>`;
  if (tab === "Trace") html += `<div class='card scroll'><pre>${escapeHtml(JSON.stringify(t, null, 2))}</pre></div>`;
  if (tab === "Evals") html += `<div class='card'>${["run_fixture_evals","run_live_evals","run_e2e_mock","run_e2e_live","run_all","run_all_live"].map((a)=>`<button class='evalBtn' data-act='${a}'>${a}</button>`).join(" ")}<pre id='evalOut'></pre></div>`;
  if (tab === "Datasets / Casos") html += `<div class='card scroll'><pre>${escapeHtml(JSON.stringify(state.cases.slice(-30), null, 2))}</pre></div>`;
  if (tab === "Prompts") html += `<div class='panel'>${state.prompts.map((p)=>`<div class='card'><h3>${p.node}</h3><textarea data-node='${p.node}'>${escapeHtml(p.base_text)}</textarea><button class='applyPrompt' data-node='${p.node}'>Aplicar override</button></div>`).join("")}</div>`;
  if (tab === "Comparar") html += renderCompare();
  if (tab === "Diálogo") html += `<div class='card scroll'>${state.dialogue.map((d)=>`<div class='msg ${d.role}'><b>${d.role}:</b> ${escapeHtml(d.text||"")}</div>`).join("")}</div>`;
  if (tab === "Experimentos") html += `<div class='card scroll'><h3>Modo: ${modeLabel(state.overrides.mode)}</h3><button id='setView'>Ver</button><button id='setTry'>Probar</button><pre>${escapeHtml(JSON.stringify(state.overrides.entries || [], null, 2))}</pre></div>`;
  c.innerHTML = html;
  bindEvents(tab);
}

function renderCompare() {
  const opts = state.turns.map((t)=>`<option value='${t.turn_id}'>Turno ${t.index} · v${t.version||1}</option>`).join("");
  if (!state.compareResult) return `<div class='card'><select id='cmpA'>${opts}</select><select id='cmpB'>${opts}</select><button id='runCmp'>Comparar</button></div>`;
  const r = state.compareResult;
  return `<div class='panel'><div class='card'><select id='cmpA'>${opts}</select><select id='cmpB'>${opts}</select><button id='runCmp'>Comparar</button></div><div class='grid2'><div class='card scroll'><h3>A</h3><pre>${escapeHtml(JSON.stringify(r.a, null, 2))}</pre></div><div class='card scroll'><h3>B</h3><pre>${escapeHtml(JSON.stringify(r.b, null, 2))}</pre></div></div><div class='card scroll'><h3>Diferencias clave</h3><pre>${escapeHtml(JSON.stringify({relationship:r.relationship, effective_overrides:r.effective_overrides, diff:r.diff}, null, 2))}</pre></div></div>`;
}

function bindEvents(tab) {
  $("#toggleFollow").onclick = () => runAction("Follow actualizado", async()=>{ state.liveFollow = !state.liveFollow; await refresh({autoSelect:true}); });
  $("#repeatBtn").onclick = () => runAction("Turno repetido", async()=>{ const text = state.turn?.user_turn?.raw_text; if(!text) throw new Error("sin turno"); await sendChat(text, state.selectedTurnId); });
  $("#newConvBtn").onclick = () => runAction("Nueva conversación", newConversation);
  $("#saveCaseBtn").onclick = () => runAction("Caso guardado", async()=>{ if(!state.selectedTurnId) throw new Error("sin turno"); await api('/cases',{method:'POST',body:JSON.stringify({turn_id:state.selectedTurnId,family:'end_to_end',tags:['manual'],notes:'guardado desde optimizador'})}); await refresh(); });
  $("#resetOverridesBtn").onclick = () => runAction("Overrides reseteados", async()=>{ await api(`/overrides/${state.optimizerSessionId}`,{method:'DELETE'}); await refresh(); });

  if (tab === "Chat") $("#sendBtn").onclick = () => runAction("Mensaje enviado", async()=>{ await sendChat($("#chatInput").value); });
  if (tab === "Evals") document.querySelectorAll(".evalBtn").forEach((b)=>b.onclick=()=>runAction("Eval ejecutada", async()=>{$("#evalOut").textContent = JSON.stringify(await api(`/evals/${b.dataset.act}`,{method:'POST'}),null,2);}));
  if (tab === "Prompts") document.querySelectorAll(".applyPrompt").forEach((b)=>b.onclick=()=>runAction("Override aplicado", async()=>{
    if (!state.editing || state.overrides.mode !== "sandbox") throw new Error("Activa Editar en Probar");
    const node = b.dataset.node;
    const val = document.querySelector(`textarea[data-node='${node}']`).value;
    const entries = [...(state.overrides.entries||[]).filter((e)=>!(e.category==='prompt' && e.key===node && e.scope==='this_optimizer_session')),{category:'prompt',key:node,value:val,scope:'this_optimizer_session'}];
    await api(`/overrides/${state.optimizerSessionId}`,{method:'PUT',body:JSON.stringify({mode:'sandbox',entries})});
    await refresh();
  }));
  if (tab === "Comparar") $("#runCmp").onclick = () => runAction("Comparación lista", async()=>{ state.compareResult = await api('/compare',{method:'POST',body:JSON.stringify({turn_a:$('#cmpA').value,turn_b:$('#cmpB').value})}); });
  if (tab === "Experimentos") {
    $("#setView").onclick = () => runAction("Modo Ver", async()=>{ await api(`/overrides/${state.optimizerSessionId}`,{method:'PUT',body:JSON.stringify({mode:'mirror',entries:state.overrides.entries||[]})}); state.editing=false; await refresh(); });
    $("#setTry").onclick = () => runAction("Modo Probar", async()=>{ await api(`/overrides/${state.optimizerSessionId}`,{method:'PUT',body:JSON.stringify({mode:'sandbox',entries:state.overrides.entries||[]})}); await refresh(); });
  }
}

function statusClass(source, status) {
  if (["exception", "parse_error", "refusal"].includes(source) || ["refuse", "block"].includes(status)) return "err";
  if (source === "fallback" || status === "rewrite") return "warn";
  return "ok";
}

function escapeHtml(s) { return String(s ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }

async function boot() {
  renderTabs();
  await refresh({ autoSelect: true });
  renderTopbar();
  renderTab("Chat");
  state.pollTimer = setInterval(async()=>{
    try { await refresh(); renderTopbar(); renderTab(activeTab()); } catch(_e){}
  }, POLL_MS);
}

boot().catch((e) => { document.body.innerHTML = `<pre>${escapeHtml(e.message)}</pre>`; });
