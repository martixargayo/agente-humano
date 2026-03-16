const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(`/api/interfaz_usuario${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function ids() {
  return { user_id: $('userId').value.trim(), session_id: $('sessionId').value.trim() };
}

const InputMode = { TALK: 'talk', WRITE: 'write' };
const AgentMode = { CHAT: 'chat', NEGOTIATION: 'negotiation' };
const AgentModeLabels = { chat: 'Chat', negotiation: 'Negociación' };

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
let currentAgentMode = AgentMode.CHAT;
let finishButtonArmed = false;
let lastSessionKey = '';
let orbRaf = null;
let orbLevel = 0;
let fakeListening = false;
let finalizePopoverOpen = false;
let feedbackPollingTimer = null;
let feedbackEvaluationId = null;

const ui = {
  listeningGlow: $('listeningGlow'),
  permissionOverlay: $('permissionOverlay'),
  startBtn: $('startBtn'),
  replyContainer: $('replyContainer'),
  lastReply: $('lastReply'),
  statusText: $('statusText'),
  inputOrb: $('inputOrb'),
  finishTurnBtn: $('finishTurnBtn'),
  modeTalk: $('modeTalk'),
  modeWrite: $('modeWrite'),
  talkMode: $('talkMode'),
  writeMode: $('writeMode'),
  textInput: $('textInput'),
  sendTextBtn: $('sendTextBtn'),
  finishNegotiationBtn: $('finishNegotiationBtn'),
};

function updateReplyText(text) {
  ui.lastReply.textContent = text;
  ui.replyContainer.classList.toggle('hidden', !text);
}

function setStatusText(text) {
  ui.statusText.textContent = text;
}

function setListeningGlowEnabled(enabled) {
  ui.listeningGlow.classList.toggle('active', Boolean(enabled));
}

function updateFinishNegotiationButton() {
  ui.finishNegotiationBtn.classList.toggle('is-armed', finishButtonArmed);
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

function updateUi() {
  ui.modeTalk.classList.toggle('active', currentInputMode === InputMode.TALK);
  ui.modeWrite.classList.toggle('active', currentInputMode === InputMode.WRITE);
  ui.modeTalk.setAttribute('aria-selected', String(currentInputMode === InputMode.TALK));
  ui.modeWrite.setAttribute('aria-selected', String(currentInputMode === InputMode.WRITE));
  ui.talkMode.classList.toggle('hidden', currentInputMode !== InputMode.TALK);
  ui.writeMode.classList.toggle('hidden', currentInputMode !== InputMode.WRITE);

  const canSendText = currentInputMode === InputMode.WRITE;
  ui.textInput.disabled = !canSendText;
  ui.sendTextBtn.disabled = !canSendText;
  ui.finishTurnBtn.disabled = !(currentInputMode === InputMode.TALK && fakeListening);
  ui.inputOrb.classList.toggle('inactive', !fakeListening);
  updateFinishNegotiationButton();
}

function setInputMode(mode) {
  currentInputMode = mode;
  if (mode === InputMode.WRITE) fakeListening = false;
  setListeningGlowEnabled(fakeListening);
  setStatusText(mode === InputMode.TALK ? (fakeListening ? 'Escuchando…' : 'Listo') : 'Listo');
  updateUi();
}

function startOrbLoop() {
  cancelAnimationFrame(orbRaf);
  const tick = () => {
    const t = performance.now();
    const idle = 0.08 * (0.5 + 0.5 * Math.sin((t * 2 * Math.PI) / 3800));
    const target = fakeListening ? Math.max(idle, 0.25 + 0.2 * Math.abs(Math.sin(t / 250))) : idle;
    orbLevel += (target - orbLevel) * 0.18;
    ui.inputOrb.style.setProperty('--orb-scale', (0.85 + orbLevel * 0.55).toFixed(2));
    orbRaf = requestAnimationFrame(tick);
  };
  orbRaf = requestAnimationFrame(tick);
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

function _seedDefaultIds() {
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  $('userId').value = `u_interfaz_${suffix}`;
  $('sessionId').value = `interfaz-main__${suffix}`;
}

async function handleSend() {
  syncSessionBoundaryReset();
  const message = ui.textInput.value.trim();
  if (!message) return;

  const payload = { ...ids(), message, new_conversation: false };
  updateReplyText('...');
  setStatusText('Procesando…');

  const out = await api('/negociacion/turn', { method: 'POST', body: JSON.stringify(payload) });
  updateReplyText(out.reply || '');
  armFinishButton(out.finish_button_armed);

  const contract = out.entry_contract;
  $('meta').textContent =
    `session=${out.session_id} endpoint=${contract.entrypoint} runtime=execute_turn_with_contract ` +
    `overrides=${contract.overrides_applied} turn=${out.latest_turn_id || '-'} ` +
    `conversation=${out.conversation_id_after || '-'} traces=${out.trace_count}`;
  ui.textInput.value = '';
  setStatusText('Listo');
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
  updateReplyText('');
};

ui.startBtn.addEventListener('click', () => {
  ui.permissionOverlay.style.display = 'none';
  fakeListening = true;
  setListeningGlowEnabled(true);
  setStatusText('Escuchando…');
  updateReplyText('Te escucho. Empieza a hablar cuando quieras.');
  updateUi();
});

ui.modeTalk.addEventListener('click', () => setInputMode(InputMode.TALK));
ui.modeWrite.addEventListener('click', () => setInputMode(InputMode.WRITE));

ui.sendTextBtn.addEventListener('click', handleSend);
ui.textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

ui.finishTurnBtn.addEventListener('click', () => {
  fakeListening = false;
  setListeningGlowEnabled(false);
  setStatusText('Procesando…');
  ui.finishTurnBtn.classList.remove('highlight');
  void ui.finishTurnBtn.offsetWidth;
  ui.finishTurnBtn.classList.add('highlight');
  setTimeout(() => {
    setStatusText('Listo');
    setInputMode(InputMode.TALK);
  }, 500);
});

ui.finishNegotiationBtn.onclick = () => {
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

document.addEventListener('click', (e) => {
  if (!ui.conversationMode.contains(e.target)) closeConversationModeMenu();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeConversationModeMenu();
});

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
  startOrbLoop();
})();
