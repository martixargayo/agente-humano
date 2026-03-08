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
  dialogue: [],
  prompts: [],
  cases: [],
  overrides: {mode:"mirror",entries:[]},
  compareResult: null,
  liveFollow: true,
  newTurnAvailable: false,
  pollTimer: null,
};

const $ = (s) => document.querySelector(s);
async function api(path, opts={}) { const r = await fetch(`/api/optimizador${path}`, {headers:{"Content-Type":"application/json"}, ...opts}); if(!r.ok) throw new Error(await r.text()); return r.json(); }

function getSelectedSession(){ return state.sessions.find(s=>s.session_key===state.selectedSessionKey) || null; }

async function bootstrap(){
  renderTabs();
  await fullRefresh({allowTurnAutoSelect:true});
  startPolling();
  switchTab("Chat");
}

function renderTabs(){
  $("#tabs").innerHTML = TABS.map(t=>`<button data-tab="${t}">${t}</button>`).join("");
  $("#tabs").onclick=(e)=>{const b=e.target.closest("button"); if(b) switchTab(b.dataset.tab);};
}

async function fullRefresh({allowTurnAutoSelect=false}={}){
  const prevLastTurn = state.turns[state.turns.length-1]?.turn_id;
  const prevSelected = state.selectedTurnId;

  const sessionsResp = await api('/sessions');
  state.sessions = sessionsResp.items;
  if(!state.selectedSessionKey && state.sessions[0]) state.selectedSessionKey = state.sessions[0].session_key;
  const selected = getSelectedSession();
  if(!selected){ renderTopbar(); return; }

  const basePath = `/sessions/${encodeURIComponent(selected.user_id)}/${encodeURIComponent(selected.session_id)}`;
  state.conversations = (await api(`${basePath}/conversations`)).items;
  state.turns = (await api(`${basePath}/turns${state.selectedConversation?`?conversation_id=${encodeURIComponent(state.selectedConversation)}`:''}`)).items;

  const newLastTurn = state.turns[state.turns.length-1]?.turn_id;
  if (prevLastTurn && newLastTurn && prevLastTurn !== newLastTurn && !state.liveFollow) state.newTurnAvailable = true;

  if(allowTurnAutoSelect || state.liveFollow){
    if(newLastTurn){ state.selectedTurnId = newLastTurn; state.newTurnAvailable = false; }
  } else if(prevSelected && state.turns.some(t=>t.turn_id===prevSelected)) {
    state.selectedTurnId = prevSelected;
  }

  if(state.selectedTurnId) state.turn = await api(`/turns/${state.selectedTurnId}`);
  state.dialogue = (await api(`${basePath}/dialogue`)).items;
  state.cases = (await api('/cases')).items;
  state.prompts = (await api('/prompts')).items;
  state.overrides = await api(`/overrides/${state.optimizerSessionId}`);
  renderTopbar();
}

function startPolling(){
  if(state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async()=>{
    try {
      await fullRefresh({allowTurnAutoSelect:false});
      switchTab(currentTab());
    } catch(_e) {}
  }, POLL_MS);
  window.addEventListener("beforeunload", ()=>{ if(state.pollTimer) clearInterval(state.pollTimer); });
}

function currentTab(){ return $("#tabs button.active")?.dataset.tab || "Chat"; }
function switchTab(name){ document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("active", b.dataset.tab===name)); renderPanel(name); }

function badge(text){ return `<span class='badge'>${text}</span>`; }

function renderTopbar(){
  const turn = state.turn || {};
  const selected = getSelectedSession();
  $("#topbar").innerHTML = `
    <select id='sessionSel'>${state.sessions.map(s=>`<option value='${s.session_key}' ${s.session_key===state.selectedSessionKey?'selected':''}>${s.user_id} / ${s.session_id} (${s.turn_count})</option>`).join('')}</select>
    <select id='convSel'><option value=''>todas conv</option>${(state.conversations||[]).map(c=>`<option value='${c.conversation_id}' ${c.conversation_id===state.selectedConversation?'selected':''}>${c.conversation_id} (${c.turn_count})</option>`).join('')}</select>
    <select id='turnSel'>${state.turns.map(t=>`<option value='${t.turn_id}' ${t.turn_id===state.selectedTurnId?'selected':''}>#${t.index} ${t.final_status} ${t.total_latency_ms}ms ${t.has_override?'[exp]':''}</option>`).join('')}</select>
    ${badge(`estado:${turn.final_status||'-'}`)} ${badge(`lat:${turn.total_latency_ms||0}ms`)} ${badge(`in:${turn.input_guardrail_decision||'-'}`)} ${badge(`out:${turn.output_guardrail_decision||'-'}`)}
    ${badge(`modo:${state.overrides?.mode||'mirror'}`)} ${badge(`follow:${state.liveFollow?'on':'off'}`)}
    ${state.newTurnAvailable?"<span class='badge'>nuevo turno disponible</span>":""}
    ${selected?.is_sandbox?`<span class='badge'>sandbox:${escapeHtml(selected?.sandbox_meta?.clone_strategy||'n/a')} from ${escapeHtml(selected?.sandbox_meta?.source_session_id||'-')} / conv ${escapeHtml(selected?.sandbox_meta?.source_conversation_id||'-')}</span>`:''}
    <button id='prevTurn'>◀</button><button id='nextTurn'>▶</button>
    <button id='toggleFollow'>live follow</button>
    <button id='saveCase'>guardar caso</button>
    <button id='repeatTurn'>repetir turno</button>
    <button id='cloneSandbox'>duplicar sandbox</button>
    <button id='resetSandbox'>reset overrides</button>
  `;

  $('#sessionSel').onchange = async (e)=>{state.selectedSessionKey=e.target.value; state.selectedConversation=''; await fullRefresh({allowTurnAutoSelect:true}); switchTab(currentTab());};
  $('#convSel').onchange = async (e)=>{state.selectedConversation=e.target.value; await fullRefresh({allowTurnAutoSelect:true}); switchTab(currentTab());};
  $('#turnSel').onchange = async (e)=>{state.selectedTurnId=e.target.value; state.liveFollow=false; if(state.selectedTurnId) state.turn = await api(`/turns/${state.selectedTurnId}`); renderTopbar(); switchTab(currentTab());};
  $('#prevTurn').onclick=()=>moveTurn(-1);
  $('#nextTurn').onclick=()=>moveTurn(1);
  $('#toggleFollow').onclick=async()=>{state.liveFollow=!state.liveFollow; if(state.liveFollow) await fullRefresh({allowTurnAutoSelect:true}); renderTopbar();};
  $('#saveCase').onclick=quickSaveCase;
  $('#repeatTurn').onclick=repeatTurn;
  $('#cloneSandbox').onclick=cloneSandbox;
  $('#resetSandbox').onclick=async()=>{await api(`/overrides/${state.optimizerSessionId}`,{method:'DELETE'}); await fullRefresh(); switchTab('Experimentos');};
}

function moveTurn(step){
  const idx = state.turns.findIndex(t=>t.turn_id===state.selectedTurnId);
  const next = state.turns[idx+step]; if(!next) return;
  state.selectedTurnId=next.turn_id; state.liveFollow=false;
  api(`/turns/${next.turn_id}`).then((turn)=>{state.turn=turn; renderTopbar(); switchTab(currentTab());});
}

async function cloneSandbox(){
  const selected = getSelectedSession(); if(!selected) return;
  const payload = {optimizer_session_id:state.optimizerSessionId, source_user_id:selected.user_id, source_session_id:selected.session_id, source_conversation_id:state.selectedConversation||null};
  const sandbox = await api('/sandbox/clone',{method:'POST', body:JSON.stringify(payload)});
  state.selectedSessionKey = sandbox.session_key;
  state.selectedConversation = '';
  await fullRefresh({allowTurnAutoSelect:true});
  switchTab('Chat');
}

async function repeatTurn(){ const text = state.turn?.user_turn?.raw_text; if(text) await sendMessage(text); }
async function quickSaveCase(){ if(!state.selectedTurnId) return; await api('/cases',{method:'POST', body:JSON.stringify({turn_id:state.selectedTurnId,family:'end_to_end',tags:['regression'],notes:'guardado desde optimizador'})}); await fullRefresh(); alert('caso guardado'); }

async function sendMessage(text){
  const selected = getSelectedSession(); if(!selected || !text.trim()) return;
  const payload = {optimizer_session_id:state.optimizerSessionId,user_id:selected.user_id,session_id:selected.session_id,message:text,conversation_id:state.selectedConversation||null,scope_turn_id:state.selectedTurnId||null};
  await api('/sandbox/turn',{method:'POST',body:JSON.stringify(payload)});
  await fullRefresh({allowTurnAutoSelect:true});
  switchTab('Chat');
}

function renderPanel(tab){
  const c = $('#content'); const t=state.turn||{};
  if(tab==='Chat') c.innerHTML = `<div class='panel'><div class='card'>${state.dialogue.map(d=>`<div class='msg ${d.role}'>${d.role==='user'?'Usuario':'IA'}: ${escapeHtml(d.text)}</div>`).join('')}</div><div class='card'><textarea id='chatInput' placeholder='Escribe mensaje...'></textarea><button id='chatSend'>Enviar</button><div>respuesta final: ${escapeHtml(t.final_reply_text||'-')}</div></div></div>`;
  if(tab==='Resumen') c.innerHTML = `<div class='card'><pre>${escapeHtml(JSON.stringify({turn_id:t.turn_id,session_id:t.session_id,user_id:t.user_id,conversation_id:t.conversation_id_after||t.conversation_id_before,turn_started_at:t.turn_started_at,turn_finished_at:t.turn_finished_at,total_latency_ms:t.total_latency_ms,final_status:t.final_status,user_text:t.user_turn?.raw_text,final_reply:t.final_reply_text,assistant_turn_emitted:t.assistant_turn_emitted,input_guardrail_decision:t.input_guardrail_decision,output_guardrail_decision:t.output_guardrail_decision,override_info:t._optimizador||null},null,2))}</pre></div>`;
  if(tab==='Timeline') c.innerHTML = `<div class='panel'>${renderTimeline(t)}</div>`;
  if(tab==='Nodos') c.innerHTML = `<div class='grid2'>${['memory','phase_classifier','planner','executor'].map(n=>renderNode(t.nodes?.[n],n)).join('')}</div>`;
  if(tab==='Guardrails') c.innerHTML = `<div class='grid2'><div class='card'><h3>Input guardrails</h3>${guardBlock(t,'input')}</div><div class='card'><h3>Output guardrails</h3>${guardBlock(t,'output')}</div></div>`;
  if(tab==='Trace') c.innerHTML = `<div class='card'><button id='copyTrace'>Copiar</button> <button id='exportTrace'>Exportar</button><pre>${escapeHtml(JSON.stringify(t,null,2))}</pre></div>`;
  if(tab==='Evals') c.innerHTML = `<div class='card'>${['run_fixture_evals','run_live_evals','run_e2e_mock','run_e2e_live','run_all','run_all_live'].map(a=>`<button class='evalBtn' data-action='${a}'>${a}</button>`).join(' ')}<pre id='evalOut'></pre></div>`;
  if(tab==='Datasets / Casos') c.innerHTML = `<div class='panel'><div class='card'><button id='saveCaseDetailed'>Guardar turno actual como caso</button></div><div class='card'><pre>${escapeHtml(JSON.stringify(state.cases.slice(-40),null,2))}</pre></div></div>`;
  if(tab==='Prompts') c.innerHTML = `<div class='panel'>${state.prompts.map(p=>`<div class='card'><h3>${p.node}</h3><small>${p.file}</small><textarea data-node='${p.node}'>${escapeHtml(p.base_text)}</textarea><label>scope <select data-scope='${p.node}'><option value='this_optimizer_session'>sesión optimizador</option><option value='this_conversation'>conversación</option><option value='this_turn'>turno</option></select></label><button class='applyPrompt' data-node='${p.node}'>Aplicar override real</button></div>`).join('')}</div>`;
  if(tab==='Comparar') c.innerHTML = renderComparePanel();
  if(tab==='Diálogo') c.innerHTML = `<div class='card'>${state.dialogue.map(d=>`<div class='msg ${d.role}' data-turn='${d.turn_id}'><b>${d.role==='user'?'Usuario':'IA'}:</b> ${escapeHtml(d.text)}</div>`).join('')}<button id='copyDialogue'>Copiar conversación</button></div>`;
  if(tab==='Experimentos') c.innerHTML = renderExperimentsPanel();
  bindTabEvents(tab);
}

function renderTimeline(t){
  const items = [
    {label:'input guardrails',type:'input_guard'},
    {label:'memory',type:'node',node:'memory'},
    {label:'phase_classifier',type:'node',node:'phase_classifier'},
    {label:'planner',type:'node',node:'planner'},
    {label:'executor',type:'node',node:'executor'},
    {label:'output guardrails',type:'output_guard'},
    {label:'emisión final / TTS',type:'final'},
  ];
  return items.map(item=>renderTimelineItem(t,item)).join('');
}

function renderTimelineItem(t,item){
  if(item.type==='input_guard'){
    const decision=t.input_guardrail_decision||'not_executed';
    const cls=guardrailClass(decision);
    return `<div class='timeline-item ${cls}'><b>${item.label}</b><div>decision:${decision} moderation:${t.input_moderation_used?'on':'off'}</div><div>reasons:${escapeHtml(JSON.stringify(t.input_guardrail_reasons||[]))}</div></div>`;
  }
  if(item.type==='output_guard'){
    const decision=t.output_guardrail_decision||'not_executed';
    const cls=guardrailClass(decision);
    return `<div class='timeline-item ${cls}'><b>${item.label}</b><div>decision:${decision} rewrite:${t.output_guardrail_rewrite_applied?'yes':'no'} moderation:${t.output_moderation_used?'on':'off'}</div><div>status ${t.output_guardrail_status_before||'-'} → ${t.output_guardrail_status_after||'-'}</div><div>reasons:${escapeHtml(JSON.stringify(t.output_guardrail_reasons||[]))}</div></div>`;
  }
  if(item.type==='node'){
    const node=t.nodes?.[item.node];
    if(!node) return `<div class='timeline-item'><b>${item.label}</b><div>no ejecutado / sin datos</div></div>`;
    const cls=nodeClass(node.source,node.status);
    return `<div class='timeline-item ${cls}'><b>${item.label}</b><div>status:${node.status} source:${node.source} lat:${node.latency_ms}ms</div><div>prompt:${node.prompt_version} schema:${node.output_schema_version}</div></div>`;
  }
  return `<div class='timeline-item ok'><b>${item.label}</b><div>final_status:${t.final_status||'-'}</div></div>`;
}

function guardrailClass(decision){ if(['block','refuse'].includes(decision)) return 'err'; if(['soft_restrict','rewrite'].includes(decision)) return 'warn'; return 'ok'; }
function nodeClass(source,status){ if(['exception','parse_error','refusal'].includes(source)||['refuse','block'].includes(status)) return 'err'; if(source==='fallback'||status==='rewrite') return 'warn'; return 'ok'; }
function renderNode(node,name){ if(!node) return `<div class='card'><h3>${name}</h3><p>sin datos</p></div>`; return `<div class='card'><h3>${name}</h3><pre>${escapeHtml(JSON.stringify({input_summary:node.input_summary,output_summary:node.output_summary,latencia:node.latency_ms,source:node.source,prompt_version:node.prompt_version,input_schema:node.input_schema_version,output_schema:node.output_schema_version,parse_error:node.parse_error,refusal_reason:node.refusal_reason,exception:node.exception_message},null,2))}</pre></div>`; }
function guardBlock(t,type){
  if(type==='input') return `<pre>${escapeHtml(JSON.stringify({decision:t.input_guardrail_decision,reasons:t.input_guardrail_reasons,triggered:t.input_guardrail_triggered,moderation_used:t.input_moderation_used,moderation_flags:t.input_moderation_flags},null,2))}</pre><small>Se muestran solo campos realmente presentes en trace.</small>`;
  return `<pre>${escapeHtml(JSON.stringify({decision:t.output_guardrail_decision,reasons:t.output_guardrail_reasons,triggered:t.output_guardrail_triggered,status_before:t.output_guardrail_status_before,status_after:t.output_guardrail_status_after,rewrite_applied:t.output_guardrail_rewrite_applied,moderation_used:t.output_moderation_used,moderation_flags:t.output_moderation_flags},null,2))}</pre><small>No se muestran señales granulares no persistidas.</small>`;
}

function renderExperimentsPanel(){
  const entries = state.overrides?.entries || [];
  return `<div class='panel'><div class='card'><h3>Experimento activo</h3><label>modo <select id='modeSel'><option value='mirror' ${state.overrides.mode==='mirror'?'selected':''}>mirror</option><option value='sandbox' ${state.overrides.mode==='sandbox'?'selected':''}>sandbox</option></select></label><button id='saveMode'>Guardar modo</button><pre>${escapeHtml(JSON.stringify(entries,null,2))}</pre></div><div class='card'><h3>Config overrides reales (soportados)</h3><label>model_planner <input id='cfgModelPlanner' placeholder='o4-mini'></label><label>feature_moderation <select id='cfgModeration'><option value=''>--</option><option value='true'>true</option><option value='false'>false</option></select></label><label>scope <select id='cfgScope'><option value='this_optimizer_session'>sesión</option><option value='this_conversation'>conversación</option><option value='this_turn'>turno</option></select></label><button id='applyConfig'>Aplicar config override</button></div></div>`;
}

function renderComparePanel(){
  const turnOptions = state.turns.map(t=>`<option value='${t.turn_id}'>#${t.index} ${t.turn_id}</option>`).join('');
  const r = state.compareResult;
  if(!r) return `<div class='card'><select id='cmpA'>${turnOptions}</select><select id='cmpB'>${turnOptions}</select><button id='runCmp'>Comparar</button><p>Sin comparación ejecutada.</p></div>`;
  return `<div class='panel'><div class='card'><select id='cmpA'>${turnOptions}</select><select id='cmpB'>${turnOptions}</select><button id='runCmp'>Comparar</button></div><div class='grid2'><div class='card'><h3>Turno A</h3><p>status:${r.a.final_status} lat:${r.a.latency_ms}ms</p><p>input:${r.a.guardrails.input} output:${r.a.guardrails.output}</p><p>exp:${r.relationship.a_is_experiment?'sí':'no'}</p><pre>${escapeHtml(r.a.final_reply||'')}</pre></div><div class='card'><h3>Turno B</h3><p>status:${r.b.final_status} lat:${r.b.latency_ms}ms</p><p>input:${r.b.guardrails.input} output:${r.b.guardrails.output}</p><p>exp:${r.relationship.b_is_experiment?'sí':'no'}</p><pre>${escapeHtml(r.b.final_reply||'')}</pre></div></div><div class='card'><h3>Diferencias clave</h3><ul><li>tipo comparación: ${r.relationship.experiment_kind}</li><li>misma optimizer_session: ${r.relationship.same_optimizer_session}</li><li>status cambiado: ${r.diff.final_status_changed}</li><li>reply cambiado: ${r.diff.reply_changed}</li><li>latency delta(ms): ${r.diff.latency_delta_ms}</li><li>input decision cambió: ${r.diff.guardrails.input_decision_changed}</li><li>output decision cambió: ${r.diff.guardrails.output_decision_changed}</li><li>output rewrite cambió: ${r.diff.guardrails.output_rewrite_changed}</li></ul></div><div class='card'><h3>Overrides efectivos</h3><pre>${escapeHtml(JSON.stringify(r.effective_overrides,null,2))}</pre></div><div class='card'><h3>Diferencias por nodo</h3><pre>${escapeHtml(JSON.stringify(r.diff.node_changes,null,2))}</pre></div></div>`;
}

function bindTabEvents(tab){
  if(tab==='Chat') $('#chatSend').onclick=()=>sendMessage($('#chatInput').value);
  if(tab==='Trace'){ $('#copyTrace').onclick=()=>navigator.clipboard.writeText(JSON.stringify(state.turn||{},null,2)); $('#exportTrace').onclick=()=>download('trace.json',JSON.stringify(state.turn||{},null,2)); }
  if(tab==='Evals') document.querySelectorAll('.evalBtn').forEach(b=>b.onclick=async()=>$('#evalOut').textContent=JSON.stringify(await api(`/evals/${b.dataset.action}`,{method:'POST'}),null,2));
  if(tab==='Datasets / Casos') $('#saveCaseDetailed').onclick=quickSaveCase;
  if(tab==='Prompts') document.querySelectorAll('.applyPrompt').forEach(btn=>btn.onclick=applyPromptOverride);
  if(tab==='Comparar') $('#runCmp').onclick=runCompare;
  if(tab==='Diálogo'){ document.querySelectorAll('.msg[data-turn]').forEach(m=>m.onclick=async()=>{state.selectedTurnId=m.dataset.turn; state.liveFollow=false; state.turn=await api(`/turns/${state.selectedTurnId}`); renderTopbar(); switchTab('Trace');}); $('#copyDialogue').onclick=()=>navigator.clipboard.writeText(state.dialogue.map(d=>`${d.role}: ${d.text}`).join('\n')); }
  if(tab==='Experimentos'){ $('#saveMode').onclick=saveMode; $('#applyConfig').onclick=applyConfigOverride; }
}

async function applyPromptOverride(e){
  const node = e.target.dataset.node;
  const value = document.querySelector(`textarea[data-node='${node}']`).value;
  const scope = document.querySelector(`select[data-scope='${node}']`).value;
  const entry = scopedEntry({category:'prompt', key:node, value, scope});
  await upsertOverrideEntry(entry);
  await fullRefresh();
  alert('override aplicado');
}

async function saveMode(){
  await api(`/overrides/${state.optimizerSessionId}`,{method:'PUT',body:JSON.stringify({mode:$('#modeSel').value,entries:state.overrides.entries||[]})});
  await fullRefresh();
}

async function applyConfigOverride(){
  const entries=[];
  const model=$('#cfgModelPlanner').value.trim();
  if(model) entries.push(scopedEntry({category:'config',key:'model_planner',value:model,scope:$('#cfgScope').value}));
  const mod=$('#cfgModeration').value;
  if(mod) entries.push(scopedEntry({category:'config',key:'feature_moderation',value:mod==='true',scope:$('#cfgScope').value}));
  for(const entry of entries) await upsertOverrideEntry(entry);
  await fullRefresh();
}

function scopedEntry(base){
  const entry = {...base};
  if(entry.scope==='this_conversation') entry.conversation_id = state.selectedConversation || (state.turn?.conversation_id_after||state.turn?.conversation_id_before||null);
  if(entry.scope==='this_turn') entry.turn_id = state.selectedTurnId || null;
  return entry;
}

async function upsertOverrideEntry(entry){
  const current = await api(`/overrides/${state.optimizerSessionId}`);
  const entries = (current.entries||[]).filter(e=>!(e.category===entry.category && e.key===entry.key && e.scope===entry.scope && (e.conversation_id||null)===(entry.conversation_id||null) && (e.turn_id||null)===(entry.turn_id||null)));
  entries.push(entry);
  await api(`/overrides/${state.optimizerSessionId}`,{method:'PUT',body:JSON.stringify({mode:current.mode,entries})});
}

async function runCompare(){
  const a=$('#cmpA').value, b=$('#cmpB').value;
  state.compareResult = await api('/compare',{method:'POST',body:JSON.stringify({turn_a:a,turn_b:b})});
  switchTab('Comparar');
}

function download(name,text){ const blob = new Blob([text],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name; a.click(); }
function escapeHtml(s){ return String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }

bootstrap().catch(err=>{ document.body.innerHTML = `<pre>${escapeHtml(err.message)}</pre>`; });
