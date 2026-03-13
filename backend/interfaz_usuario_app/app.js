const $ = (id) => document.getElementById(id);

// Standalone parity-safe UI. It only talks to /api/interfaz_usuario.
// It does not depend on avatar_app legacy mode selection (/chat vs /negociar).
async function api(path, opts={}) {
  const r = await fetch(`/api/interfaz_usuario${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function append(role, text) {
  const chat = $('chat');
  chat.textContent += `${role}: ${text}\n`;
  chat.scrollTop = chat.scrollHeight;
}

function ids() {
  return { user_id: $('userId').value.trim(), session_id: $('sessionId').value.trim() };
}

$('bootstrap').onclick = async () => {
  const payload = ids();
  const out = await api('/sessions/bootstrap', { method:'POST', body: JSON.stringify(payload) });
  $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
};

$('newConv').onclick = async () => {
  const payload = ids();
  const out = await api('/negociacion/new_conversation', { method:'POST', body: JSON.stringify(payload) });
  $('sessionId').value = out.session_id;
  $('meta').textContent = `nueva session=${out.session_id}`;
};

$('send').onclick = async () => {
  const message = $('msg').value.trim();
  if (!message) return;
  const payload = { ...ids(), message, new_conversation: false };
  append('user', message);
  const out = await api('/negociacion/turn', { method:'POST', body: JSON.stringify(payload) });
  append('assistant', out.reply);
  const contract = out.entry_contract;
  $('meta').textContent =
    `session=${out.session_id} endpoint=${contract.entrypoint} runtime=execute_turn_with_contract ` +
    `overrides=${contract.overrides_applied} turn=${out.latest_turn_id || '-'} ` +
    `conversation=${out.conversation_id_after || '-'} traces=${out.trace_count}`;
  $('msg').value = '';
};


function _seedDefaultIds() {
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2,8)}`;
  $('userId').value = `u_interfaz_${suffix}`;
  $('sessionId').value = `interfaz-main__${suffix}`;
}

(async function initInterfazUsuarioSession() {
  _seedDefaultIds();
  try {
    const out = await api('/sessions/bootstrap', { method:'POST', body: JSON.stringify(ids()) });
    $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
  } catch (err) {
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }
})();
