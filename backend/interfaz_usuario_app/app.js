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
  if (!chat) return;
  const row = document.createElement('div');
  row.className = 'chat-line';
  const label = document.createElement('strong');
  label.textContent = role;
  row.appendChild(label);
  row.appendChild(document.createTextNode(`: ${text}`));
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function ids() {
  return { user_id: $('userId').value.trim(), session_id: $('sessionId').value.trim() };
}

const InputMode = {
  TALK: 'talk',
  WRITE: 'write',
};

let currentInputMode = InputMode.TALK;
let finishButtonArmed = false;
let lastSessionKey = '';
let orbTimer = null;

function updateFinishNegotiationButton() {
  const btn = $('finishNegotiationBtn');
  if (!btn) return;
  btn.classList.toggle('is-armed', finishButtonArmed);
}

function armFinishButton(nextArmed) {
  finishButtonArmed = finishButtonArmed || Boolean(nextArmed);
  updateFinishNegotiationButton();
}

function resetFinishButtonArmed() {
  finishButtonArmed = false;
  updateFinishNegotiationButton();
}

function syncSessionBoundaryReset() {
  const { user_id, session_id } = ids();
  const currentSessionKey = `${user_id}::${session_id}`;
  if (lastSessionKey && lastSessionKey !== currentSessionKey) {
    resetFinishButtonArmed();
  }
  lastSessionKey = currentSessionKey;
}

function setListeningGlowEnabled(enabled) {
  $('listeningGlow')?.classList.toggle('active', Boolean(enabled));
}

function stopInputOrb() {
  if (orbTimer) {
    window.clearInterval(orbTimer);
    orbTimer = null;
  }
  $('inputOrb')?.style.setProperty('--orb-scale', '0.85');
}

function startInputOrb() {
  stopInputOrb();
  orbTimer = window.setInterval(() => {
    const scale = 0.82 + Math.random() * 0.42;
    $('inputOrb')?.style.setProperty('--orb-scale', scale.toFixed(2));
  }, 110);
}

function setInputMode(mode) {
  currentInputMode = mode;
  $('modeTalk')?.classList.toggle('active', mode === InputMode.TALK);
  $('modeWrite')?.classList.toggle('active', mode === InputMode.WRITE);
  $('modeTalk')?.setAttribute('aria-selected', String(mode === InputMode.TALK));
  $('modeWrite')?.setAttribute('aria-selected', String(mode === InputMode.WRITE));
  $('talkMode')?.classList.toggle('hidden', mode !== InputMode.TALK);
  $('writeMode')?.classList.toggle('hidden', mode !== InputMode.WRITE);

  const orb = $('inputOrb');
  if (mode === InputMode.TALK) {
    orb?.classList.remove('inactive');
    $('statusText').textContent = 'Escuchando (visual)';
    setListeningGlowEnabled(true);
    startInputOrb();
  } else {
    orb?.classList.add('inactive');
    $('statusText').textContent = 'Listo (visual)';
    setListeningGlowEnabled(false);
    stopInputOrb();
  }
}

$('bootstrap').onclick = async () => {
  syncSessionBoundaryReset();
  const payload = ids();
  const out = await api('/sessions/bootstrap', { method:'POST', body: JSON.stringify(payload) });
  $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
};

$('newConv').onclick = async () => {
  const payload = ids();
  const out = await api('/negociacion/new_conversation', { method:'POST', body: JSON.stringify(payload) });
  $('sessionId').value = out.session_id;
  lastSessionKey = `${payload.user_id}::${out.session_id}`;
  resetFinishButtonArmed();
  $('meta').textContent = `nueva session=${out.session_id}`;
};

$('send').onclick = async () => {
  syncSessionBoundaryReset();
  const message = $('msg').value.trim();
  if (!message) return;
  const payload = { ...ids(), message, new_conversation: false };
  append('user', message);
  const out = await api('/negociacion/turn', { method:'POST', body: JSON.stringify(payload) });
  append('assistant', out.reply);
  armFinishButton(out.finish_button_armed);
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

$('finishTurnBtn').onclick = () => {
  $('statusText').textContent = 'Modo hablar solo visual';
  window.setTimeout(() => {
    if (currentInputMode === InputMode.TALK) {
      $('statusText').textContent = 'Escuchando (visual)';
    }
  }, 1000);
};

$('modeTalk').onclick = () => setInputMode(InputMode.TALK);
$('modeWrite').onclick = () => setInputMode(InputMode.WRITE);

$('finishNegotiationBtn').onclick = () => {
  console.log('finish button clicked');
};

(async function initInterfazUsuarioSession() {
  _seedDefaultIds();
  syncSessionBoundaryReset();
  try {
    const out = await api('/sessions/bootstrap', { method:'POST', body: JSON.stringify(ids()) });
    lastSessionKey = `${out.user_id}::${out.session_id}`;
    resetFinishButtonArmed();
    $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
  } catch (err) {
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }
  setInputMode(InputMode.WRITE);
})();
