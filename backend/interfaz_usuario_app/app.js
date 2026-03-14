const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
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

const InputMode = { TALK: 'talk', WRITE: 'write' };

const JobStageLabel = {
  created: 'Creando evaluación...',
  queued: 'Evaluación en cola...',
  building_inputs: 'Analizando la conversación...',
  running_core: 'Evaluando desempeño global...',
  running_trajectory: 'Evaluando trayectoria turno a turno...',
  assembling_report: 'Preparando el informe...',
  completed: 'Informe listo.',
  failed: 'No se pudo completar la evaluación.',
};

let currentInputMode = InputMode.TALK;
let finishButtonArmed = false;
let lastSessionKey = '';
let orbTimer = null;
let finalizePopoverOpen = false;
let feedbackPollingTimer = null;
let feedbackEvaluationId = null;

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
  if (lastSessionKey && lastSessionKey !== currentSessionKey) resetFinishButtonArmed();
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

function stopFeedbackPolling() {
  if (feedbackPollingTimer) {
    window.clearTimeout(feedbackPollingTimer);
    feedbackPollingTimer = null;
  }
}

function closeFinalizePopover() {
  finalizePopoverOpen = false;
  $('finishConfirmPopover')?.classList.remove('visible');
}

function openFinalizePopover() {
  finalizePopoverOpen = true;
  $('finishConfirmPopover')?.classList.add('visible');
}

function setFeedbackStageText(status) {
  $('feedbackLoadingText').textContent = JobStageLabel[status] || 'Procesando evaluación...';
}

function showFeedbackView(mode) {
  const app = $('mainApp');
  const loading = $('feedbackLoadingScreen');
  const report = $('feedbackReportScreen');
  const error = $('feedbackErrorScreen');
  if (!app || !loading || !report || !error) return;

  app.classList.toggle('hidden', mode !== 'app');
  loading.classList.toggle('hidden', mode !== 'loading');
  report.classList.toggle('hidden', mode !== 'report');
  error.classList.toggle('hidden', mode !== 'error');
}

function renderFinalReport(report) {
  const root = $('feedbackReportRoot');
  if (!root || !window.FeedbackReportView) return;
  window.FeedbackReportView.renderReport(root, report);
}

async function fetchEvaluationReport(evaluationId) {
  const out = await api(`/feedback/evaluations/${evaluationId}/report`, { method: 'GET' });
  showFeedbackView('report');
  renderFinalReport(out.report);
}

async function pollEvaluationStatus(evaluationId) {
  try {
    const status = await api(`/feedback/evaluations/${evaluationId}`, { method: 'GET' });
    setFeedbackStageText(status.status);

    if (status.status === 'completed') {
      stopFeedbackPolling();
      await fetchEvaluationReport(evaluationId);
      return;
    }

    if (status.status === 'failed') {
      stopFeedbackPolling();
      $('feedbackErrorMessage').textContent = status.error || 'La evaluación no pudo completarse.';
      showFeedbackView('error');
      return;
    }

    feedbackPollingTimer = window.setTimeout(() => pollEvaluationStatus(evaluationId), 1700);
  } catch (err) {
    stopFeedbackPolling();
    $('feedbackErrorMessage').textContent = `Error de red durante la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
}

async function startFeedbackEvaluation() {
  const out = await api('/feedback/evaluations', { method: 'POST', body: JSON.stringify(ids()) });
  feedbackEvaluationId = out.evaluation_id;
  showFeedbackView('loading');
  setFeedbackStageText(out.status);
  stopFeedbackPolling();
  feedbackPollingTimer = window.setTimeout(() => pollEvaluationStatus(feedbackEvaluationId), 200);
}

$('bootstrap').onclick = async () => {
  syncSessionBoundaryReset();
  const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(ids()) });
  $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
};

$('newConv').onclick = async () => {
  const payload = ids();
  const out = await api('/negociacion/new_conversation', { method: 'POST', body: JSON.stringify(payload) });
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
  const out = await api('/negociacion/turn', { method: 'POST', body: JSON.stringify(payload) });
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
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  $('userId').value = `u_interfaz_${suffix}`;
  $('sessionId').value = `interfaz-main__${suffix}`;
}

$('finishTurnBtn').onclick = () => {
  $('statusText').textContent = 'Modo hablar solo visual';
  window.setTimeout(() => {
    if (currentInputMode === InputMode.TALK) $('statusText').textContent = 'Escuchando (visual)';
  }, 1000);
};

$('modeTalk').onclick = () => setInputMode(InputMode.TALK);
$('modeWrite').onclick = () => setInputMode(InputMode.WRITE);

$('finishNegotiationBtn').onclick = () => {
  if (!finishButtonArmed) return;
  if (finalizePopoverOpen) {
    closeFinalizePopover();
    return;
  }
  openFinalizePopover();
};

$('finishCancelBtn').onclick = closeFinalizePopover;

$('finishConfirmBtn').onclick = async () => {
  closeFinalizePopover();
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo iniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackBackBtn').onclick = () => showFeedbackView('app');

$('feedbackRetryBtn').onclick = async () => {
  showFeedbackView('app');
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo reiniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

window.addEventListener('click', (ev) => {
  if (!finalizePopoverOpen) return;
  const popover = $('finishConfirmPopover');
  const btn = $('finishNegotiationBtn');
  const target = ev.target;
  if (popover && btn && target instanceof Node && !popover.contains(target) && !btn.contains(target)) closeFinalizePopover();
});

(async function initInterfazUsuarioSession() {
  _seedDefaultIds();
  syncSessionBoundaryReset();
  try {
    const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(ids()) });
    lastSessionKey = `${out.user_id}::${out.session_id}`;
    resetFinishButtonArmed();
    $('meta').textContent = `session=${out.session_id} traces=${out.trace_count} conversation_id=${out.conversation_id || '-'}`;
  } catch (err) {
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }
  setInputMode(InputMode.WRITE);
})();
