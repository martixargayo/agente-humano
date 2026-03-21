const $ = (id) => document.getElementById(id);

const SessionBootstrapState = {
  NEW: 'new',
  REHYDRATED: 'rehydrated',
  UNKNOWN: 'unknown',
};

const PARENT_EMBED_ORIGIN = 'https://academia.gestionce.com';
const EMBED_NAMESPACE = 'gestionce.simulator';
const EMBED_MESSAGE_VERSION = 1;

class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status ?? null;
    this.errorCode = options.errorCode ?? null;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
    this.detail = options.detail ?? null;
    this.headers = options.headers ?? {};
  }
}

async function api(path, opts = {}) {
  const r = await fetch(`/api/interfaz_usuario${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const contentType = r.headers.get('content-type') || '';
    let bodyText = '';
    let bodyJson = null;

    try {
      if (contentType.includes('application/json')) {
        bodyJson = await r.json();
      } else {
        bodyText = await r.text();
      }
    } catch (_) {
      bodyText = '';
    }

    const detail = bodyJson?.detail ?? bodyJson ?? bodyText;
    const errorCode = typeof detail?.error === 'string'
      ? detail.error
      : (typeof bodyJson?.error === 'string' ? bodyJson.error : null);
    const retryAfterHeader = r.headers.get('Retry-After');
    const retryAfterSeconds = Number.isFinite(Number(detail?.retry_after_seconds))
      ? Number(detail.retry_after_seconds)
      : (Number.isFinite(Number(retryAfterHeader)) ? Number(retryAfterHeader) : null);
    const message = typeof detail === 'string'
      ? detail
      : (typeof detail?.message === 'string' ? detail.message : `HTTP ${r.status}`);

    throw new ApiError(message, {
      status: r.status,
      errorCode,
      retryAfterSeconds,
      detail,
      headers: {
        retry_after: retryAfterHeader,
      },
    });
  }
  return r.json();
}

function ids() {
  const userId = $('userId').value.trim();
  const sessionId = $('sessionId').value.trim();
  return {
    ...(userId ? { user_id: userId } : {}),
    ...(sessionId ? { session_id: sessionId } : {}),
  };
}

function applyBootstrapIdentity(out) {
  if (!out || typeof out !== 'object') return;
  if (typeof out.user_id === 'string') $('userId').value = out.user_id;
  if (typeof out.session_id === 'string') $('sessionId').value = out.session_id;
  if (out.user_id && out.session_id) lastSessionKey = `${out.user_id}::${out.session_id}`;
  setBootstrapSessionState(out);
}

function readPublicSlugFromUrl() {
  const path = window.location.pathname.replace(/\/+$/, '');
  const match = path.match(/^\/interfaz_usuario\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function readEmbedModeFromUrl() {
  const url = new URL(window.location.href);
  const raw = (url.searchParams.get('embed') || '').trim().toLowerCase();
  if (['1', 'true', 'yes', 'on', 'embed'].includes(raw)) return true;
  if (['0', 'false', 'no', 'off'].includes(raw)) return false;
  return null;
}

function bootstrapPayload() {
  const payload = ids();
  const publicSlug = readPublicSlugFromUrl();
  if (publicSlug) payload.public_slug = publicSlug;
  return payload;
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

const FeedbackFloatingPhrases = [
  [['token-keyword', 'Analizando'], ['token-entity', 'tendencias']],
  [['token-keyword', 'Detectando'], ['token-value', 'patrones']],
  [['token-keyword', 'Evaluando'], ['token-metric', 'puntos fuertes']],
  [['token-keyword', 'Identificando'], ['token-entity', 'áreas de mejora']],
  [['token-keyword', 'Procesando'], ['token-value', 'métricas']],
  [['token-keyword', 'Correlacionando'], ['token-entity', 'resultados']],
  [['token-keyword', 'Comparando'], ['token-metric', 'desempeño']],
  [['token-keyword', 'Generando'], ['token-value', 'insights']],
  [['token-keyword', 'Estimando'], ['token-entity', 'evolución']],
  [['token-keyword', 'Revisando'], ['token-metric', 'consistencia']],
  [['token-keyword', 'Mapeando'], ['token-value', 'habilidades']],
  [['token-keyword', 'Sintetizando'], ['token-entity', 'observaciones']],
];

const FloatingPhraseQuadrantsDesktop = {
  topLeft: [
    { top: [10, 18], left: [6, 16] },
    { top: [22, 32], left: [10, 22] },
    { top: [38, 46], left: [4, 14] },
  ],
  topRight: [
    { top: [10, 18], left: [72, 84] },
    { top: [22, 32], left: [76, 88] },
    { top: [38, 46], left: [82, 92] },
  ],
  bottomLeft: [
    { top: [62, 72], left: [8, 18] },
    { top: [74, 84], left: [12, 24] },
    { top: [82, 90], left: [18, 30] },
  ],
  bottomRight: [
    { top: [62, 72], left: [72, 84] },
    { top: [74, 84], left: [66, 78] },
    { top: [82, 90], left: [62, 76] },
  ],
};

const FloatingPhraseQuadrantsMobile = {
  topLeft: [
    { top: [11, 19], left: [4, 16] },
    { top: [24, 32], left: [6, 18] },
  ],
  topRight: [
    { top: [12, 20], left: [64, 78] },
    { top: [26, 34], left: [68, 82] },
  ],
  bottomLeft: [
    { top: [66, 76], left: [8, 20] },
    { top: [80, 88], left: [10, 22] },
  ],
  bottomRight: [
    { top: [66, 76], left: [64, 78] },
    { top: [80, 88], left: [60, 74] },
  ],
};

const FloatingPhraseQuadrantOrder = ['topLeft', 'topRight', 'bottomLeft', 'bottomRight'];

let currentInputMode = InputMode.TALK;
let currentAgentMode = AgentMode.CHAT;
let finishButtonArmed = false;
let finishButtonHighlightTimer = null;
let finishButtonAttentionActive = false;
let latestTraceCount = 0;
let lastSessionKey = '';
const MIN_TURNS_BEFORE_FINALIZE = 1;
let orbRaf = null;
let orbLevel = 0;
let finalizePopoverOpen = false;
let feedbackPollingTimer = null;
let feedbackEvaluationId = null;
let feedbackReportSnapshot = null;
let feedbackFloatingTimer = null;
let feedbackQuadrantCursor = 0;
let audioCtx = null;
let ttsWarmedUp = false;
let micStream = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recorderMimeType = 'audio/webm;codecs=opus';
let discardRecording = false;
let hasMicPermission = false;
let waveAudioCtx = null;
let waveAnalyser = null;
let waveDataArray = null;
let waveSourceNode = null;
let turnInFlight = false;
let voiceTurnInFlight = false;
let entryMode = InputMode.TALK;
let scenarioReady = false;
let entryRequested = false;
let entryInProgress = false;
let entryRequestedMode = null;
let entryResolvedInputMode = null;
let entryPermissionStatus = 'unknown';
let lastEntryMicError = '';
let availableInputDevices = [];
let selectedEntryDeviceId = null;
let entryDeviceRefreshTimer = null;
let entryDeviceDebounceTimer = null;
let refreshInFlight = false;
let refreshPendingAfterInFlight = false;
let refreshSequence = 0;
let audioDevicePopoverOpen = false;
let audioDevicePopoverPollTimer = null;
let audioDeviceSwitchInFlight = false;
let audioDeviceToastTimer = null;
let currentPresentationConfig = null;
let consolidatedSessionIdentity = null;
let sessionBusyState = null;
let sessionBusyTimer = null;
let embedModeActive = false;
let embedReadySessionKey = '';
let embedHeightRaf = null;
let lastEmbeddedHeight = 0;
let finalSaveToastTimer = null;
let pendingEmbeddedFinalResultAck = null;
const LAST_DEVICE_STORAGE_KEY = 'interfaz_usuario:last_audio_input_device';

const ui = {
  listeningGlow: $('listeningGlow'),
  entryOverlay: $('entryOverlay'),
  entryModeTalk: $('entryModeTalk'),
  entryModeWrite: $('entryModeWrite'),
  entryTalkContent: $('entryTalkContent'),
  entryWriteContent: $('entryWriteContent'),
  entrySubtitle: $('entrySubtitle'),
  entryDeviceLabel: $('entryDeviceLabel'),
  entryDeviceSearch: $('entryDeviceSearch'),
  entryDeviceList: $('entryDeviceList'),
  entryDeviceStatus: $('entryDeviceStatus'),
  entryError: $('entryError'),
  entryScenarioState: $('entryScenarioState'),
  entryScenarioSpinner: $('entryScenarioSpinner'),
  entryLoadingText: $('entryLoadingText'),
  startBtn: $('startBtn'),
  replyContainer: $('replyContainer'),
  lastReply: $('lastReply'),
  audioDeviceToast: $('audioDeviceToast'),
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
  finishConfirmMessage: $('finishConfirmMessage'),
  finishConfirmHint: $('finishConfirmHint'),
  finishConfirmBtn: $('finishConfirmBtn'),
  conversationMode: $('conversationMode'),
  audioDeviceSelector: $('audioDeviceSelector'),
  audioDeviceTrigger: $('audioDeviceTrigger'),
  audioDeviceTriggerLabel: $('audioDeviceTriggerLabel'),
  audioDevicePopover: $('audioDevicePopover'),
  audioDeviceSelectedList: $('audioDeviceSelectedList'),
  audioDeviceOtherList: $('audioDeviceOtherList'),
  audioDevicePopoverDivider: $('audioDevicePopoverDivider'),
  feedbackFloatingLayer: $('feedbackFloatingLayer'),
  finalSaveToast: $('finalSaveToast'),
};

// Hard guard: if any stale HTML/version still injects the old Chat/Negociación selector,
// remove it at runtime so the negotiation flow remains fixed and selector-free.
$('conversationMode')?.remove();

function closeConversationModeMenu() {
  if (!ui.conversationMode) return;
  ui.conversationMode.classList.remove('open');
}

function isEntryOverlayVisible() {
  return Boolean(ui.entryOverlay && ui.entryOverlay.style.display !== 'none');
}

function isAnyAudioDeviceSurfaceVisible() {
  return isEntryOverlayVisible() || audioDevicePopoverOpen;
}

function withAvatarRuntime(fn) {
  const runtime = window.__avatarRuntime;
  if (!runtime) return;
  fn(runtime);
}

function syncAvatarMode() {
  withAvatarRuntime((runtime) => {
    if (isMicActuallyRecording() && currentInputMode === InputMode.TALK) {
      runtime.setMode('LISTENING');
      runtime.setTalkLevel(0);
      return;
    }
    runtime.setMode('IDLE');
    runtime.setTalkLevel(0);
  });
}

function isMicActuallyRecording() {
  return Boolean(isRecording && mediaRecorder && mediaRecorder.state === 'recording');
}

function updateReplyText(text) {
  ui.lastReply.textContent = text;
  ui.replyContainer.classList.toggle('hidden', !text);
  scheduleEmbedHeightEmission('reply');
}

function getPresentationVoiceConfig() {
  const voice = currentPresentationConfig?.voice;
  if (!voice || typeof voice !== 'object') return null;
  return {
    voice_id: typeof voice.voice_id === 'string' && voice.voice_id.trim() ? voice.voice_id.trim() : null,
    speaking_rate: Number.isFinite(Number(voice.speaking_rate)) ? Number(voice.speaking_rate) : null,
  };
}

function applyPresentationConfigToDom(presentationConfig) {
  currentPresentationConfig = presentationConfig || null;
  const root = document.documentElement;
  const background = presentationConfig?.background || null;
  const theme = presentationConfig?.theme || null;
  const themeName = typeof theme?.shell_theme === 'string' && theme.shell_theme.trim() ? theme.shell_theme.trim() : 'realistic';
  root.setAttribute('data-avatar-theme', themeName);

  const hasBackground = Boolean(background && background.type === 'image' && typeof background.url === 'string' && background.url.trim());
  root.setAttribute('data-avatar-background-enabled', hasBackground ? '1' : '0');
  root.style.setProperty('--avatar-bg-image', hasBackground ? `url("${background.url}")` : 'none');

  const bgEl = $('bg');
  if (bgEl && background && typeof background === 'object') {
    bgEl.style.backgroundSize = typeof background.size === 'string' && background.size.trim() ? background.size : 'contain';
    bgEl.style.backgroundPosition = typeof background.position === 'string' && background.position.trim() ? background.position : 'center center';
  }
}

function initAvatarRuntimeOnce(presentationConfig) {
  const initRuntime = window.__initAvatarRuntime;
  if (typeof initRuntime !== 'function') {
    throw new Error('avatar_runtime_init_unavailable');
  }
  return initRuntime({ presentationConfig, stageEl: $('stage') });
}

function normalizeBootstrapSessionState(raw) {
  if (raw === SessionBootstrapState.NEW || raw === SessionBootstrapState.REHYDRATED) return raw;
  return SessionBootstrapState.UNKNOWN;
}

function setBootstrapSessionState(out) {
  if (!out || typeof out !== 'object') return;

  const nextIdentity = {
    user_id: typeof out.user_id === 'string' ? out.user_id : '',
    session_id: typeof out.session_id === 'string' ? out.session_id : '',
    trace_count: Number.isFinite(Number(out.trace_count)) ? Number(out.trace_count) : 0,
    session_bootstrap_state: normalizeBootstrapSessionState(out.session_bootstrap_state),
    existing_session: out.existing_session === true,
    conversation_id: typeof out.conversation_id === 'string' && out.conversation_id.trim() ? out.conversation_id : null,
    previous_response_id: typeof out.previous_response_id === 'string' && out.previous_response_id.trim() ? out.previous_response_id : null,
    context_id: typeof out.context_id === 'string' ? out.context_id : null,
    public_slug: typeof out.public_slug === 'string' ? out.public_slug : null,
    last_updated: typeof out.last_updated === 'string' ? out.last_updated : null,
    bootstrapped_at: new Date().toISOString(),
  };

  if (!nextIdentity.user_id || !nextIdentity.session_id) {
    consolidatedSessionIdentity = null;
    document.documentElement.dataset.sessionBootstrapState = SessionBootstrapState.UNKNOWN;
    return;
  }

  consolidatedSessionIdentity = nextIdentity;
  document.documentElement.dataset.sessionBootstrapState = nextIdentity.session_bootstrap_state;
  document.documentElement.dataset.sessionReady = '1';
}

function resetBootstrapSessionState() {
  consolidatedSessionIdentity = null;
  document.documentElement.dataset.sessionBootstrapState = SessionBootstrapState.UNKNOWN;
  document.documentElement.dataset.sessionReady = '0';
}

function hasConsolidatedSessionIdentity() {
  return Boolean(consolidatedSessionIdentity?.user_id && consolidatedSessionIdentity?.session_id);
}

function getSessionCorrelationMeta() {
  if (!hasConsolidatedSessionIdentity()) return null;
  return { ...consolidatedSessionIdentity };
}

function formatBootstrapMeta(identity) {
  if (!identity) return 'session=uninitialized';
  const stateLabel = identity.session_bootstrap_state === SessionBootstrapState.REHYDRATED ? 'rehydrated' : 'new';
  return [
    `session=${identity.session_id}`,
    `bootstrap=${stateLabel}`,
    `existing=${identity.existing_session ? 'yes' : 'no'}`,
    `traces=${identity.trace_count}`,
    `conversation_id=${identity.conversation_id || '-'}`,
    `context=${identity.context_id || '-'}`,
  ].join(' ');
}

function updateBootstrapMeta(out = null) {
  const meta = out ? getSessionCorrelationMeta() : consolidatedSessionIdentity;
  $('meta').textContent = formatBootstrapMeta(meta);
}

function notifyBootstrapSessionReady() {
  const detail = getSessionCorrelationMeta();
  if (!detail) return;
  window.dispatchEvent(new CustomEvent('interfaz-usuario-session-ready', { detail }));
}

function isEmbeddedRuntime() {
  return window.parent && window.parent !== window;
}

function detectEmbedMode() {
  const explicit = readEmbedModeFromUrl();
  if (explicit !== null) return explicit;
  return isEmbeddedRuntime();
}

function applyEmbedMode() {
  embedModeActive = detectEmbedMode();
  document.documentElement.dataset.embedMode = embedModeActive ? '1' : '0';
  if (document.body) document.body.dataset.embedMode = embedModeActive ? '1' : '0';
}

function buildEmbedEnvelope(type, payload = {}, options = {}) {
  const correlation = getSessionCorrelationMeta();
  const sessionId = correlation?.session_id || null;
  const bootstrapCorrelation = correlation?.bootstrapped_at || 'no-bootstrap';
  const correlationId = typeof options.correlationId === 'string' && options.correlationId.trim()
    ? options.correlationId.trim()
    : (sessionId ? `${sessionId}:${bootstrapCorrelation}` : bootstrapCorrelation);
  return {
    v: EMBED_MESSAGE_VERSION,
    ns: EMBED_NAMESPACE,
    type,
    event_id: `${type}:${Date.now()}:${Math.random().toString(16).slice(2, 10)}`,
    correlation_id: correlationId,
    session_id: sessionId,
    conversation_id: correlation?.conversation_id || null,
    context_id: correlation?.context_id || null,
    public_slug: correlation?.public_slug || null,
    payload,
  };
}

function emitEmbedMessage(type, payload = {}, options = {}) {
  if (!embedModeActive || !isEmbeddedRuntime()) return;
  try {
    const envelope = buildEmbedEnvelope(type, payload, options);
    window.parent.postMessage(envelope, PARENT_EMBED_ORIGIN);
    return envelope;
  } catch (err) {
    console.warn('[embed] No se pudo emitir mensaje al padre', err);
  }
}

function isAllowedParentOrigin(origin) {
  return origin === PARENT_EMBED_ORIGIN;
}

function hideFinalSaveToast() {
  if (!ui.finalSaveToast) return;
  ui.finalSaveToast.classList.remove('visible');
  if (finalSaveToastTimer) {
    window.clearTimeout(finalSaveToastTimer);
    finalSaveToastTimer = null;
  }
}

function showFinalSaveToast(message = 'Resultados guardados', durationMs = 4200) {
  if (!ui.finalSaveToast) return;
  ui.finalSaveToast.textContent = message;
  ui.finalSaveToast.classList.add('visible');
  if (finalSaveToastTimer) window.clearTimeout(finalSaveToastTimer);
  finalSaveToastTimer = window.setTimeout(() => {
    finalSaveToastTimer = null;
    ui.finalSaveToast.classList.remove('visible');
  }, durationMs);
  console.info('[embed] Toast de guardado mostrado', { message });
  scheduleEmbedHeightEmission('final-save-toast');
}

function normalizeComparableId(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function stableStringifyForHash(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableStringifyForHash(item)).join(',')}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringifyForHash(value[key])}`).join(',')}}`;
}

function simpleHashString(value) {
  let hash = 2166136261;
  for (let idx = 0; idx < value.length; idx += 1) {
    hash ^= value.charCodeAt(idx);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function deriveFinalResultPayloadHash(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const hashInput = stableStringifyForHash({
    evaluation_id: payload.evaluation_id || null,
    activityid: payload.activityid || null,
    session_id: payload.session_id || null,
    interaction_outcome: payload.interaction_outcome || null,
    summary_2_3_lines: payload.summary_2_3_lines || null,
    score_global_100: payload.score_global_100 || null,
    report: payload.report || null,
  });
  return simpleHashString(hashInput);
}

function buildFinalResultCorrelationId(payload) {
  const sessionId = normalizeComparableId(payload?.session_id) || 'no-session';
  const evaluationId = normalizeComparableId(payload?.evaluation_id) || 'no-evaluation';
  const payloadHash = normalizeComparableId(payload?.payload_hash) || 'no-hash';
  return `${sessionId}:final:${evaluationId}:${payloadHash}`;
}

function registerPendingEmbeddedFinalResultAck(payload, envelope) {
  pendingEmbeddedFinalResultAck = {
    session_id: normalizeComparableId(payload?.session_id),
    activityid: normalizeComparableId(payload?.activityid),
    evaluation_id: normalizeComparableId(payload?.evaluation_id),
    payload_hash: normalizeComparableId(payload?.payload_hash),
    correlation_id: normalizeComparableId(envelope?.correlation_id),
    emitted_at_ms: Date.now(),
    emitted_at_iso: new Date().toISOString(),
    pending_ack: true,
    ack_confirmed: false,
    last_ack_signature: null,
    last_ack_meta: null,
    event_id: normalizeComparableId(envelope?.event_id),
  };
  console.info('[embed] final_result emitido; ACK pendiente registrado', pendingEmbeddedFinalResultAck);
}

function readAckComparableIds(message) {
  const payload = message?.payload && typeof message.payload === 'object' ? message.payload : {};
  return {
    session_id: normalizeComparableId(payload.session_id || message?.session_id),
    activityid: normalizeComparableId(payload.activityid || message?.activityid),
    evaluation_id: normalizeComparableId(payload.evaluation_id || message?.evaluation_id),
    payload_hash: normalizeComparableId(payload.payload_hash || message?.payload_hash),
    correlation_id: normalizeComparableId(payload.correlation_id || message?.correlation_id),
    entryid: normalizeComparableId(payload.entryid || message?.entryid),
    version: normalizeComparableId(payload.version || message?.version),
  };
}

function buildAckSignature(ackIds) {
  return stableStringifyForHash({
    session_id: ackIds.session_id,
    activityid: ackIds.activityid,
    evaluation_id: ackIds.evaluation_id,
    payload_hash: ackIds.payload_hash,
    correlation_id: ackIds.correlation_id,
    entryid: ackIds.entryid,
    version: ackIds.version,
  });
}

function handleEmbeddedSaveAck(message, options = {}) {
  const origin = normalizeComparableId(options.origin);
  console.info('[embed] ACK final_result_saved recibido', {
    origin,
    type: message?.type || null,
    ns: message?.ns || null,
    v: message?.v ?? null,
  });
  if (origin && !isAllowedParentOrigin(origin)) {
    console.info('[embed] ACK rechazado por origin no permitido', { origin });
    return false;
  }
  if (!message || typeof message !== 'object') return false;
  if (message.ns !== EMBED_NAMESPACE || message.v !== EMBED_MESSAGE_VERSION) return false;
  if (message.type !== 'final_result_saved') return false;
  const savedOk = message.payload?.status === 'ok' || message.payload?.saved === true;
  if (!savedOk) {
    console.info('[embed] ACK rechazado porque no confirma guardado exitoso', { payload: message.payload || null });
    return false;
  }
  if (!pendingEmbeddedFinalResultAck || pendingEmbeddedFinalResultAck.pending_ack !== true) {
    console.info('[embed] ACK ignorado: no hay final_result pendiente');
    return false;
  }
  const ackIds = readAckComparableIds(message);
  if (ackIds.session_id !== pendingEmbeddedFinalResultAck.session_id) {
    console.info('[embed] ACK rechazado por session_id', { expected: pendingEmbeddedFinalResultAck.session_id, received: ackIds.session_id });
    return false;
  }
  if (ackIds.activityid !== pendingEmbeddedFinalResultAck.activityid) {
    console.info('[embed] ACK rechazado por activityid', { expected: pendingEmbeddedFinalResultAck.activityid, received: ackIds.activityid });
    return false;
  }
  const strongCorrelationMatched = [
    ['evaluation_id', pendingEmbeddedFinalResultAck.evaluation_id, ackIds.evaluation_id],
    ['payload_hash', pendingEmbeddedFinalResultAck.payload_hash, ackIds.payload_hash],
    ['correlation_id', pendingEmbeddedFinalResultAck.correlation_id, ackIds.correlation_id],
  ].filter(([, expected, received]) => expected && received && expected === received);
  if (strongCorrelationMatched.length === 0) {
    console.info('[embed] ACK rechazado por falta de correlación fuerte', {
      expected: pendingEmbeddedFinalResultAck,
      received: ackIds,
    });
    return false;
  }
  const ackSignature = buildAckSignature(ackIds);
  if (pendingEmbeddedFinalResultAck.ack_confirmed && pendingEmbeddedFinalResultAck.last_ack_signature === ackSignature) {
    console.info('[embed] ACK repetido ignorado', { ackIds });
    return false;
  }
  if (pendingEmbeddedFinalResultAck.ack_confirmed) {
    console.info('[embed] ACK ignorado: el final_result pendiente actual ya había sido confirmado', { ackIds });
    return false;
  }
  pendingEmbeddedFinalResultAck.pending_ack = false;
  pendingEmbeddedFinalResultAck.ack_confirmed = true;
  pendingEmbeddedFinalResultAck.last_ack_signature = ackSignature;
  pendingEmbeddedFinalResultAck.last_ack_meta = {
    entryid: ackIds.entryid,
    version: ackIds.version,
    acknowledged_at_iso: new Date().toISOString(),
    strong_match_keys: strongCorrelationMatched.map(([key]) => key),
  };
  console.info('[embed] ACK aceptado', {
    ackIds,
    strong_match_keys: pendingEmbeddedFinalResultAck.last_ack_meta.strong_match_keys,
  });
  showFinalSaveToast('Resultados guardados');
  return true;
}

function installEmbedMessageListener() {
  window.addEventListener('message', (event) => {
    if (!embedModeActive || !isEmbeddedRuntime()) return;
    try {
      const accepted = handleEmbeddedSaveAck(event.data, { origin: event.origin });
      if (accepted) console.info('[embed] Confirmación de guardado final correlacionada con el último final_result', event.data?.payload || null);
    } catch (err) {
      console.warn('[embed] Error procesando ACK del guardado final', err);
    }
  });
}

function emitParentEmbedError(code, message, extra = {}) {
  emitEmbedMessage('error', {
    code,
    message,
    ...extra,
  });
}

function isSessionBusyError(err) {
  return err instanceof ApiError && err.status === 423 && err.errorCode === 'session_busy';
}

function clearSessionBusyTimer() {
  if (!sessionBusyTimer) return;
  window.clearTimeout(sessionBusyTimer);
  sessionBusyTimer = null;
}

function getActiveSessionBusyState() {
  if (!sessionBusyState) return null;
  if (sessionBusyState.untilMs !== null && Date.now() >= sessionBusyState.untilMs) {
    sessionBusyState = null;
    clearSessionBusyTimer();
    document.documentElement.dataset.sessionBusy = '0';
    cleanupSessionBusyUx();
    return null;
  }
  return sessionBusyState;
}

function clearSessionBusyState() {
  const previousState = sessionBusyState;
  sessionBusyState = null;
  clearSessionBusyTimer();
  document.documentElement.dataset.sessionBusy = '0';
  cleanupSessionBusyUx(previousState);
}

function formatSessionBusyMessage(state) {
  if (!state) return '';
  const seconds = Number.isFinite(Number(state.retryAfterSeconds)) ? Number(state.retryAfterSeconds) : null;
  const retryLabel = seconds && seconds > 0
    ? ` Reintenta en ${seconds} s.`
    : ' Espera unos segundos y reintenta.';
  return `La sesión está ocupada en otra ejecución.${retryLabel}`;
}

function applySessionBusyUx(state, { source = 'runtime' } = {}) {
  const message = formatSessionBusyMessage(state);
  if (ui.entryError && isEntryOverlayVisible()) ui.entryError.textContent = message;
  if (ui.statusText) ui.statusText.textContent = 'Sesión ocupada';
  updateReplyText(message);

  if (source === 'feedback' || !$('feedbackErrorScreen')?.classList.contains('hidden')) {
    $('feedbackErrorMessage').textContent = message;
    showFeedbackView('error');
  }

  $('meta').textContent = `${formatBootstrapMeta(getSessionCorrelationMeta())} session_busy=yes retry_after=${state.retryAfterSeconds ?? '-'}`;
}

function cleanupSessionBusyUx(previousState = null) {
  const busyMessage = previousState ? formatSessionBusyMessage(previousState) : null;
  if (busyMessage && ui.entryError?.textContent === busyMessage) ui.entryError.textContent = '';
  if (ui.statusText?.textContent === 'Sesión ocupada') {
    ui.statusText.textContent = currentInputMode === InputMode.TALK && isMicActuallyRecording() ? 'Escuchando…' : 'Listo';
  }
  if (busyMessage && ui.lastReply?.textContent === busyMessage) updateReplyText('');
  if (busyMessage && $('feedbackErrorMessage')?.textContent === busyMessage) {
    $('feedbackErrorMessage').textContent = 'Ha ocurrido un error durante el proceso.';
  }
  updateBootstrapMeta();
}

function setSessionBusyState(err, { source = 'runtime' } = {}) {
  const retryAfterSeconds = Number.isFinite(Number(err?.retryAfterSeconds))
    ? Math.max(1, Number(err.retryAfterSeconds))
    : null;
  const untilMs = retryAfterSeconds ? Date.now() + retryAfterSeconds * 1000 : null;
  sessionBusyState = {
    source,
    retryAfterSeconds,
    untilMs,
    session_id: err?.detail?.session_id || getSessionCorrelationMeta()?.session_id || null,
    lock_backend: err?.detail?.lock_backend || null,
  };
  document.documentElement.dataset.sessionBusy = '1';
  clearSessionBusyTimer();
  if (untilMs !== null) {
    sessionBusyTimer = window.setTimeout(() => {
      clearSessionBusyState();
      updateBootstrapMeta();
      updateUi();
    }, Math.max(250, untilMs - Date.now()));
  }
  applySessionBusyUx(sessionBusyState, { source });
  emitParentEmbedError('session_busy', formatSessionBusyMessage(sessionBusyState), {
    retry_after_seconds: retryAfterSeconds,
    lock_backend: sessionBusyState.lock_backend,
    source,
  });
}

function getVisibleSurfaceElements() {
  return ['mainApp', 'feedbackLoadingScreen', 'feedbackReportScreen', 'feedbackErrorScreen']
    .map((id) => $(id))
    .filter((el) => el && !el.classList.contains('hidden'));
}

function measureEmbeddedHeight() {
  const surfaces = getVisibleSurfaceElements();
  const values = [];
  surfaces.forEach((el) => {
    values.push(el.scrollHeight || 0, el.offsetHeight || 0, Math.ceil(el.getBoundingClientRect().height || 0));
  });
  values.push(
    document.body?.scrollHeight || 0,
    document.documentElement?.scrollHeight || 0,
    document.body?.offsetHeight || 0,
    document.documentElement?.offsetHeight || 0,
  );
  return Math.max(0, ...values.map((value) => Number(value) || 0));
}

function scheduleEmbedHeightEmission(reason = 'layout') {
  if (!embedModeActive) return;
  if (embedHeightRaf) window.cancelAnimationFrame(embedHeightRaf);
  embedHeightRaf = window.requestAnimationFrame(() => {
    embedHeightRaf = null;
    const heightPx = Math.max(320, Math.ceil(measureEmbeddedHeight()));
    if (Math.abs(heightPx - lastEmbeddedHeight) < 4) return;
    lastEmbeddedHeight = heightPx;
    emitEmbedMessage('height', { height_px: heightPx, reason });
  });
}

function maybeEmitEmbedReady(reason = 'runtime-ready') {
  if (!embedModeActive) return;
  if (!hasConsolidatedSessionIdentity()) return;
  if (!scenarioReady) return;
  const correlation = getSessionCorrelationMeta();
  const sessionKey = `${correlation.session_id}:${correlation.bootstrapped_at || 'boot'}`;
  if (embedReadySessionKey === sessionKey) return;
  embedReadySessionKey = sessionKey;
  emitEmbedMessage('ready', {
    route: window.location.pathname,
    reason,
    session_bootstrap_state: correlation.session_bootstrap_state,
    existing_session: correlation.existing_session,
    trace_count: correlation.trace_count,
    embed_mode: true,
  });
  scheduleEmbedHeightEmission('ready');
}

function showAudioDeviceToast(message, durationMs = 3200) {
  if (!ui.audioDeviceToast) return;
  ui.audioDeviceToast.textContent = message;
  ui.audioDeviceToast.classList.add('visible');
  if (audioDeviceToastTimer) window.clearTimeout(audioDeviceToastTimer);
  audioDeviceToastTimer = window.setTimeout(() => {
    audioDeviceToastTimer = null;
    ui.audioDeviceToast.classList.remove('visible');
  }, durationMs);
  scheduleEmbedHeightEmission('audio-toast');
}

function getOrCreateAudioContext() {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function base64ToAudioData(b64, mimeType = 'audio/wav') {
  if (typeof b64 !== 'string' || !b64.trim()) throw new Error('Respuesta TTS sin audio_base64 válido');

  const sanitized = b64
    .replace(/^data:[^;]+;base64,/, '')
    .replace(/\s+/g, '')
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  let byteChars;
  try {
    byteChars = atob(sanitized);
  } catch (err) {
    console.error('[audio] No se pudo decodificar base64', err);
    throw new Error('Audio base64 corrupto');
  }

  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i += 1) byteNumbers[i] = byteChars.charCodeAt(i);
  const byteArray = new Uint8Array(byteNumbers);
  if (!byteArray.length) throw new Error('Audio vacío tras decodificar base64');

  return {
    mimeType: mimeType || 'audio/wav',
    arrayBuffer: byteArray.buffer.slice(byteArray.byteOffset, byteArray.byteOffset + byteArray.byteLength),
  };
}

async function requestTTS(text, voiceConfig = null) {
  const payload = { text };
  if (voiceConfig?.voice_id) payload.voice = voiceConfig.voice_id;
  if (Number.isFinite(Number(voiceConfig?.speaking_rate))) payload.speaking_rate = Number(voiceConfig.speaking_rate);
  const response = await fetch('/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  return base64ToAudioData(data.audio_base64, data.audio_mime_type || 'audio/wav');
}

async function warmupFrontendTts() {
  if (ttsWarmedUp) return;
  try {
    const audioData = await requestTTS('Calibración de audio.', getPresentationVoiceConfig());
    const ctx = getOrCreateAudioContext();
    const audioBuffer = await ctx.decodeAudioData(audioData.arrayBuffer.slice(0));
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(gain);
    gain.connect(ctx.destination);
    await ctx.resume();
    source.start(ctx.currentTime + 0.05);
    ttsWarmedUp = true;
  } catch (err) {
    console.warn('[warmup] Falló warmup frontend TTS', err);
  }
}

function teardownMic() {
  stopInputOrb();
  if (waveSourceNode) {
    try { waveSourceNode.disconnect(); } catch (_) {}
  }
  waveSourceNode = null;
  waveAudioCtx = null;
  waveAnalyser = null;
  waveDataArray = null;
  isRecording = false;
  mediaRecorder = null;
  audioChunks = [];
  discardRecording = false;
  try { if (micStream) micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  micStream = null;
}

function computeIdlePulse(timeMs) {
  return 0.08 * (0.5 + 0.5 * Math.sin((timeMs * 2 * Math.PI) / 3800));
}

function updateInputOrb() {
  if (!ui.inputOrb) return;
  const now = performance.now();
  const idle = computeIdlePulse(now);
  let level = idle;

  if (waveAnalyser && waveDataArray && isMicActuallyRecording()) {
    waveAnalyser.getByteTimeDomainData(waveDataArray);
    let sum = 0;
    for (let i = 0; i < waveDataArray.length; i += 1) {
      const v = waveDataArray[i] / 128 - 1;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / waveDataArray.length);
    const rmsNorm = Math.min(1, rms * 6);
    level = Math.max(rmsNorm, idle);
  }

  orbLevel += (level - orbLevel) * 0.18;
  const scale = 0.85 + orbLevel * 0.55;
  ui.inputOrb.style.setProperty('--orb-scale', scale.toFixed(2));
  orbRaf = requestAnimationFrame(updateInputOrb);
}

function ensureOrbLoop() {
  if (!orbRaf) orbRaf = requestAnimationFrame(updateInputOrb);
}

function stopInputOrb() {
  if (orbRaf) cancelAnimationFrame(orbRaf);
  orbRaf = null;
  orbLevel = 0;
  if (ui.inputOrb) ui.inputOrb.style.setProperty('--orb-scale', '0.85');
}

async function startVoiceCapture() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('getUserMedia no soportado');
  if (isMicActuallyRecording()) return;

  discardRecording = false;
  teardownMic();

  const buildConstraints = (deviceId = null) => ({
    audio: deviceId
      ? {
          deviceId: { exact: deviceId },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      : {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
  });

  try {
    micStream = await navigator.mediaDevices.getUserMedia(buildConstraints(selectedEntryDeviceId));
  } catch (err) {
    const recoverable = err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError';
    if (!recoverable) throw err;
    micStream = await navigator.mediaDevices.getUserMedia(buildConstraints());
    void refreshEntryDevices('capture-fallback-device');
  }

  recorderMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';

  mediaRecorder = new MediaRecorder(micStream, { mimeType: recorderMimeType });
  audioChunks = [];

  mediaRecorder.ondataavailable = (event) => {
    if (event?.data && event.data.size > 0) audioChunks.push(event.data);
  };

  mediaRecorder.start(250);
  await new Promise((resolve) => setTimeout(resolve, 0));
  isRecording = mediaRecorder.state === 'recording';

  if (!micStream.getTracks().some((track) => track.readyState === 'live')) {
    throw new Error('El micrófono no está activo.');
  }

  if (!isRecording) {
    throw new Error('No se pudo iniciar la grabación.');
  }

  waveAudioCtx = getOrCreateAudioContext();
  await waveAudioCtx.resume();
  waveAnalyser = waveAudioCtx.createAnalyser();
  waveAnalyser.fftSize = 1024;
  waveSourceNode = waveAudioCtx.createMediaStreamSource(micStream);
  waveSourceNode.connect(waveAnalyser);
  waveDataArray = new Uint8Array(waveAnalyser.frequencyBinCount);
  ensureOrbLoop();
}

function stopVoiceCapture() {
  if (!mediaRecorder || !isRecording) return Promise.resolve(null);

  return new Promise((resolve, reject) => {
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: recorderMimeType });
      audioChunks = [];
      isRecording = false;
      mediaRecorder = null;

      if (discardRecording) {
        discardRecording = false;
        resolve(null);
        return;
      }

      resolve(blob);
    };

    try {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.requestData();
        setTimeout(() => {
          try { mediaRecorder.stop(); } catch (err) { reject(err); }
        }, 150);
      } else {
        mediaRecorder.stop();
      }
    } catch (err) {
      reject(err);
    }
  });
}

async function transcribeAudio(blob) {
  const audioFile = new File([blob], 'grabacion.webm', { type: recorderMimeType });
  const formData = new FormData();
  formData.append('file', audioFile);
  const response = await fetch('/stt_google', { method: 'POST', body: formData });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  return (data?.text || '').trim();
}

async function playTtsWithAvatar(replyText) {
  const audioData = await requestTTS(replyText, getPresentationVoiceConfig());
  const ctx = getOrCreateAudioContext();
  const decoded = await ctx.decodeAudioData(audioData.arrayBuffer.slice(0));
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  const source = ctx.createBufferSource();
  source.buffer = decoded;
  source.connect(analyser);
  analyser.connect(ctx.destination);

  withAvatarRuntime((runtime) => {
    runtime.connectAnalyser(analyser);
    runtime.setMode('SPEAKING');
    runtime.setTalkLevel(0);
  });

  await ctx.resume();
  await new Promise((resolve) => {
    source.onended = () => {
      withAvatarRuntime((runtime) => {
        runtime.connectAnalyser(null);
      });
      resolve();
    };
    source.start(ctx.currentTime + 0.05);
  });
}

function setStatusText(text) {
  ui.statusText.textContent = text;
  scheduleEmbedHeightEmission('status');
}

function setListeningGlowEnabled(enabled) {
  ui.listeningGlow.classList.toggle('active', Boolean(enabled));
}

function getRemainingTurnsBeforeFinalize() {
  return Math.max(0, MIN_TURNS_BEFORE_FINALIZE - latestTraceCount);
}

function canFinalizeConversation() {
  return getRemainingTurnsBeforeFinalize() === 0;
}

function getFinalizePopoverCopy() {
  const remainingTurns = getRemainingTurnsBeforeFinalize();
  if (remainingTurns === 0) {
    return {
      message: '¿Seguro que quieres finalizar la conversación?',
      hint: '',
      confirmDisabled: false,
    };
  }

  const turnWord = remainingTurns === 1 ? 'turno' : 'turnos';
  return {
    message: 'La conversación no es suficientemente relevante para haber llegado a un resultado siguiendo el método adecuado.',
    hint: `Finalizar conversación disponible en ${remainingTurns} ${turnWord}.`,
    confirmDisabled: true,
  };
}

function renderFinalizePopoverState() {
  if (!ui.finishConfirmMessage || !ui.finishConfirmHint || !ui.finishConfirmBtn) return;
  const copy = getFinalizePopoverCopy();
  ui.finishConfirmMessage.textContent = copy.message;
  ui.finishConfirmHint.textContent = copy.hint;
  ui.finishConfirmHint.classList.toggle('hidden', !copy.hint);
  ui.finishConfirmBtn.disabled = copy.confirmDisabled;
}

function setLatestTraceCount(nextCount) {
  const numericCount = Number(nextCount);
  latestTraceCount = Number.isFinite(numericCount) && numericCount > 0 ? Math.floor(numericCount) : 0;
  renderFinalizePopoverState();
}

function clearFinishButtonAttentionTimer() {
  if (!finishButtonHighlightTimer) return;
  window.clearTimeout(finishButtonHighlightTimer);
  finishButtonHighlightTimer = null;
}

function setFinishButtonAttentionActive(active) {
  finishButtonAttentionActive = Boolean(active);
  ui.finishNegotiationBtn.classList.toggle('is-attention-active', finishButtonAttentionActive);
}

function startFinishButtonAttentionPulse() {
  clearFinishButtonAttentionTimer();
  setFinishButtonAttentionActive(false);
  void ui.finishNegotiationBtn.offsetWidth;
  setFinishButtonAttentionActive(true);
  finishButtonHighlightTimer = window.setTimeout(() => {
    finishButtonHighlightTimer = null;
    setFinishButtonAttentionActive(false);
  }, 5000);
}

function updateFinishNegotiationButton() {
  ui.finishNegotiationBtn.classList.toggle('is-highlighted', finishButtonArmed);
  if (!finishButtonArmed) setFinishButtonAttentionActive(false);
}

function armFinishButton(nextArmed) {
  const wasArmed = finishButtonArmed;
  finishButtonArmed = finishButtonArmed || Boolean(nextArmed);
  updateFinishNegotiationButton();
  if (!wasArmed && finishButtonArmed) startFinishButtonAttentionPulse();
}

function resetFinishButtonArmed() {
  finishButtonArmed = false;
  clearFinishButtonAttentionTimer();
  updateFinishNegotiationButton();
}

function syncSessionBoundaryReset() {
  const { user_id, session_id } = ids();
  const currentSessionKey = `${user_id}::${session_id}`;
  if (lastSessionKey && lastSessionKey !== currentSessionKey) resetFinishButtonArmed();
  lastSessionKey = currentSessionKey;
}

function updateUi() {
  renderFinalizePopoverState();
  ui.modeTalk.classList.toggle('active', currentInputMode === InputMode.TALK);
  ui.modeWrite.classList.toggle('active', currentInputMode === InputMode.WRITE);
  ui.modeTalk.setAttribute('aria-selected', String(currentInputMode === InputMode.TALK));
  ui.modeWrite.setAttribute('aria-selected', String(currentInputMode === InputMode.WRITE));
  ui.talkMode.classList.toggle('hidden', currentInputMode !== InputMode.TALK);
  ui.writeMode.classList.toggle('hidden', currentInputMode !== InputMode.WRITE);

  const sessionBusy = getActiveSessionBusyState();
  const isBusy = turnInFlight || voiceTurnInFlight || Boolean(sessionBusy);
  const canSendText = currentInputMode === InputMode.WRITE && !isBusy;
  ui.textInput.disabled = currentInputMode !== InputMode.WRITE || isBusy;
  ui.sendTextBtn.disabled = !canSendText;
  const micOn = isMicActuallyRecording();
  ui.finishTurnBtn.disabled = !(currentInputMode === InputMode.TALK && micOn && !isBusy && !audioDeviceSwitchInFlight);
  ui.startBtn.disabled = entryInProgress || Boolean(sessionBusy);
  ui.modeTalk.disabled = Boolean(sessionBusy);
  ui.modeWrite.disabled = Boolean(sessionBusy);
  ui.finishNegotiationBtn.disabled = Boolean(sessionBusy);
  ui.inputOrb.classList.toggle('inactive', !micOn);
  setListeningGlowEnabled(micOn);
  updateFinishNegotiationButton();
  renderAudioDeviceSelector();
  scheduleEmbedHeightEmission('ui');
}

function setInputMode(mode) {
  currentInputMode = mode;
  if (mode === InputMode.WRITE && isMicActuallyRecording()) {
    discardRecording = true;
    void stopVoiceCapture().finally(() => teardownMic());
  }
  setStatusText(mode === InputMode.TALK ? (isMicActuallyRecording() ? 'Escuchando…' : 'Listo') : 'Listo');
  updateUi();
  syncAvatarMode();
}

function resolveEntryInputMode(mode) {
  entryResolvedInputMode = mode;
  setInputMode(mode);
}

function getSavedEntryDeviceId() {
  try {
    return window.localStorage.getItem(LAST_DEVICE_STORAGE_KEY);
  } catch (_) {
    return null;
  }
}

function saveEntryDeviceId(deviceId) {
  try {
    if (deviceId) window.localStorage.setItem(LAST_DEVICE_STORAGE_KEY, deviceId);
  } catch (_) {}
}

function normalizeDeviceLabel(label, index) {
  const raw = String(label || '').trim();
  if (!raw) return `Micrófono ${index + 1}`;
  return raw
    .replace(/^(default|predeterminado)\s*-\s*/i, '')
    .replace(/^(communications|comunicaciones)\s*-\s*/i, '')
    .replace(/\s*\((default|predeterminado|communications|comunicaciones)\)\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function getDeviceLabelKey(label) {
  return String(label || '')
    .toLowerCase()
    .replace(/[^a-z0-9áéíóúüñ]+/gi, ' ')
    .trim();
}

function toUiAudioInputDevices(devices) {
  const byIdentity = new Map();
  devices.forEach((device, index) => {
    if (device.kind !== 'audioinput' || !device.deviceId) return;
    const cleanLabel = normalizeDeviceLabel(device.label, index);
    const groupPart = device.groupId ? `g:${device.groupId}` : '';
    const labelPart = getDeviceLabelKey(cleanLabel);
    const dedupeKey = `${groupPart}|${labelPart}`;
    if (!byIdentity.has(dedupeKey)) {
      byIdentity.set(dedupeKey, {
        deviceId: device.deviceId,
        groupId: device.groupId || '',
        label: device.label || '',
        cleanLabel,
      });
    }
  });
  return [...byIdentity.values()].sort((a, b) => a.cleanLabel.localeCompare(b.cleanLabel, 'es', { sensitivity: 'base' }));
}

function pickReplacementDevice(previousDeviceId, previousList, nextList) {
  if (!nextList.length) return null;
  if (!previousDeviceId) return nextList[0].deviceId;
  const exact = nextList.find((d) => d.deviceId === previousDeviceId);
  if (exact) return exact.deviceId;
  const previous = previousList.find((d) => d.deviceId === previousDeviceId);
  if (!previous) return nextList[0].deviceId;
  if (previous.groupId) {
    const byGroup = nextList.find((d) => d.groupId && d.groupId === previous.groupId);
    if (byGroup) return byGroup.deviceId;
  }
  const prevLabelKey = getDeviceLabelKey(previous.cleanLabel || previous.label || '');
  if (prevLabelKey) {
    const byLabel = nextList.find((d) => getDeviceLabelKey(d.cleanLabel || d.label || '') === prevLabelKey);
    if (byLabel) return byLabel.deviceId;
  }
  return nextList[0].deviceId;
}

function canStartTalkEntry() {
  if (entryPermissionStatus === 'denied') return false;
  if (entryPermissionStatus === 'granted') return Boolean(selectedEntryDeviceId);
  return true;
}

function getEntryModeStartEnabled() {
  if (entryMode === InputMode.WRITE) return true;
  return canStartTalkEntry();
}

function getCanEnterNow() {
  return getEntryModeStartEnabled() && scenarioReady;
}

function setSelectedEntryDevice(deviceId, reason = 'manual') {
  if (!deviceId || !availableInputDevices.some((d) => d.deviceId === deviceId)) return;
  if (selectedEntryDeviceId === deviceId) return;
  selectedEntryDeviceId = deviceId;
  saveEntryDeviceId(deviceId);
  renderEntryDevices();
  renderEntryState();
  renderAudioDeviceSelector();
}

function getAudioDeviceTriggerText() {
  if (entryPermissionStatus === 'denied') {
    return { text: 'Permiso de micrófono bloqueado', muted: true };
  }
  if (entryPermissionStatus === 'prompt' || entryPermissionStatus === 'unknown') {
    return { text: 'Activar micrófono', muted: true };
  }
  const selected = availableInputDevices.find((device) => device.deviceId === selectedEntryDeviceId);
  if (selected) return { text: selected.cleanLabel, muted: false };
  if (availableInputDevices.length) return { text: availableInputDevices[0].cleanLabel, muted: false };
  return { text: 'Sin micrófonos disponibles', muted: true };
}

function createAudioDeviceOption(device, { active = false } = {}) {
  const option = document.createElement('button');
  option.type = 'button';
  option.className = 'audio-device-option';
  option.dataset.deviceId = device.deviceId;
  option.setAttribute('role', 'option');
  option.setAttribute('aria-selected', String(active));
  option.title = device.cleanLabel;

  if (active) option.classList.add('active');
  option.addEventListener('click', () => {
    void handleAudioDeviceChangeRequest(device.deviceId);
  });

  const main = document.createElement('span');
  main.className = 'audio-device-option-main';

  const icon = document.createElement('span');
  icon.className = 'audio-device-option-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '🎧';

  const name = document.createElement('span');
  name.className = 'audio-device-option-name';
  name.textContent = device.cleanLabel;

  const check = document.createElement('span');
  check.className = 'audio-device-option-check';
  check.setAttribute('aria-hidden', 'true');
  check.textContent = '✓';

  main.append(icon, name);
  option.append(main, check);
  return option;
}

function renderAudioDeviceSelector() {
  if (!ui.audioDeviceSelector || !ui.audioDeviceTriggerLabel || !ui.audioDeviceSelectedList || !ui.audioDeviceOtherList) return;

  const triggerState = getAudioDeviceTriggerText();
  ui.audioDeviceTriggerLabel.textContent = triggerState.text;
  ui.audioDeviceTriggerLabel.classList.toggle('muted', triggerState.muted);
  if (ui.audioDeviceTrigger) {
    ui.audioDeviceTrigger.setAttribute('aria-expanded', String(audioDevicePopoverOpen));
    ui.audioDeviceTrigger.disabled = audioDeviceSwitchInFlight;
    ui.audioDeviceTriggerLabel.title = triggerState.text;
  }
  ui.audioDeviceSelector.classList.toggle('open', audioDevicePopoverOpen);

  ui.audioDeviceSelectedList.innerHTML = '';
  ui.audioDeviceOtherList.innerHTML = '';

  if (entryPermissionStatus !== 'granted') {
    const empty = document.createElement('div');
    empty.className = 'audio-device-empty';
    const text = document.createElement('div');
    text.textContent = entryPermissionStatus === 'denied'
      ? 'Necesitamos permiso para listar los micrófonos disponibles.'
      : 'Necesitamos permiso para listar los micrófonos disponibles.';
    empty.appendChild(text);

    const actions = document.createElement('div');
    actions.className = 'audio-device-empty-actions';
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'audio-device-inline-action';
    action.textContent = 'Activar permisos';
    action.addEventListener('click', () => {
      void handleAudioDevicePermissionRequest();
    });
    actions.appendChild(action);
    empty.appendChild(actions);
    ui.audioDeviceSelectedList.appendChild(empty);
    if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = true;
    return;
  }

  if (!availableInputDevices.length) {
    const empty = document.createElement('div');
    empty.className = 'audio-device-empty';
    empty.textContent = 'No hay micrófonos disponibles en este momento.';
    ui.audioDeviceSelectedList.appendChild(empty);
    if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = true;
    return;
  }

  const selected = availableInputDevices.find((device) => device.deviceId === selectedEntryDeviceId) || availableInputDevices[0];
  const others = availableInputDevices.filter((device) => device.deviceId !== selected.deviceId);

  ui.audioDeviceSelectedList.appendChild(createAudioDeviceOption(selected, { active: true }));
  if (ui.audioDevicePopoverDivider) ui.audioDevicePopoverDivider.hidden = others.length === 0;
  others.forEach((device) => {
    ui.audioDeviceOtherList.appendChild(createAudioDeviceOption(device));
  });
}

function getAudioDeviceSwitchFailureMessage(err) {
  if (err?.name === 'NotReadableError') {
    return 'No se pudo activar el nuevo micrófono. Cierra otras apps que lo estén usando y vuelve a intentarlo.';
  }
  if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
    return 'No encontramos ese micrófono disponible. Revisa la conexión y vuelve a intentarlo.';
  }
  return 'No se pudo cambiar el micrófono. Reintenta o usa modo Escribir si el problema continúa.';
}

async function restorePreviousMicrophoneAfterFailure(previousDeviceId) {
  if (previousDeviceId && previousDeviceId !== selectedEntryDeviceId && availableInputDevices.some((device) => device.deviceId === previousDeviceId)) {
    setSelectedEntryDevice(previousDeviceId, 'restore-after-switch-failure');
  }

  if (currentInputMode !== InputMode.TALK || !hasMicPermission) {
    setStatusText('Listo');
    updateUi();
    syncAvatarMode();
    return false;
  }

  try {
    await startVoiceCapture();
    setStatusText('Escuchando…');
    updateUi();
    syncAvatarMode();
    return true;
  } catch (restoreErr) {
    console.error('[audio-selector] No se pudo restaurar el micrófono previo', restoreErr);
    setInputMode(InputMode.WRITE);
    setStatusText('Listo');
    updateUi();
    syncAvatarMode();
    return false;
  }
}

async function restartVoiceCaptureAfterDeviceSwitch(previousDeviceId) {
  audioDeviceSwitchInFlight = true;
  updateUi();
  setStatusText('Cambiando mic…');

  discardRecording = true;
  try {
    await stopVoiceCapture();
  } catch (stopErr) {
    console.warn('[audio-selector] Error deteniendo captura previa para cambiar micrófono', stopErr);
  }
  teardownMic();

  try {
    await startVoiceCapture();
    setStatusText('Escuchando…');
    showAudioDeviceToast('Se ha cambiado el micrófono. Vuelve a decir lo que estabas diciendo porque tu respuesta puede haberse perdido.');
    updateUi();
    syncAvatarMode();
    closeAudioDevicePopover();
    return true;
  } catch (err) {
    console.error('[audio-selector] No se pudo activar el nuevo micrófono', err);
    const restored = await restorePreviousMicrophoneAfterFailure(previousDeviceId);
    showAudioDeviceToast(restored
      ? 'No se pudo activar el nuevo micrófono. Seguimos usando el anterior.'
      : getAudioDeviceSwitchFailureMessage(err));
    return false;
  } finally {
    audioDeviceSwitchInFlight = false;
    updateUi();
    void refreshEntryDevices('audio-selector-post-switch');
  }
}

async function handleAudioDeviceChangeRequest(deviceId) {
  if (!deviceId || !availableInputDevices.some((device) => device.deviceId === deviceId)) return;
  if (audioDeviceSwitchInFlight) return;

  if (turnInFlight || voiceTurnInFlight) {
    showAudioDeviceToast('Espera a que termine este turno para cambiar de micrófono.');
    setStatusText('Procesando…');
    return;
  }

  const previousDeviceId = selectedEntryDeviceId;
  if (previousDeviceId === deviceId) {
    closeAudioDevicePopover();
    return;
  }

  setSelectedEntryDevice(deviceId, 'audio-selector');

  if (!isMicActuallyRecording() || currentInputMode !== InputMode.TALK) {
    closeAudioDevicePopover();
    return;
  }

  await restartVoiceCaptureAfterDeviceSwitch(previousDeviceId);
}

async function handleAudioDevicePermissionRequest() {
  if (audioDeviceSwitchInFlight) return;
  setStatusText('Activando mic…');
  const permissionOk = await requestMicPermissionsForEntry();
  await refreshEntryDevices(permissionOk ? 'audio-selector-permission-ok' : 'audio-selector-permission-error');
  renderAudioDeviceSelector();

  if (permissionOk) {
    setStatusText(isMicActuallyRecording() ? 'Escuchando…' : 'Listo');
    return;
  }

  setStatusText('Listo');
  showAudioDeviceToast(lastEntryMicError || 'No pudimos activar el micrófono. Revisa los permisos e inténtalo de nuevo.');
}

function stopAudioDevicePopoverPolling() {
  if (audioDevicePopoverPollTimer) {
    window.clearInterval(audioDevicePopoverPollTimer);
    audioDevicePopoverPollTimer = null;
  }
}

function closeAudioDevicePopover() {
  if (!audioDevicePopoverOpen) return;
  audioDevicePopoverOpen = false;
  stopAudioDevicePopoverPolling();
  renderAudioDeviceSelector();
}

function openAudioDevicePopover() {
  if (audioDevicePopoverOpen) return;
  audioDevicePopoverOpen = true;
  renderAudioDeviceSelector();
  scheduleEntryDeviceRefresh('audio-selector-open', 0);
  stopAudioDevicePopoverPolling();
  audioDevicePopoverPollTimer = window.setInterval(() => {
    scheduleEntryDeviceRefresh('audio-selector-poll', 120);
  }, 3000);
}

function toggleAudioDevicePopover() {
  if (audioDevicePopoverOpen) {
    closeAudioDevicePopover();
    return;
  }
  openAudioDevicePopover();
}

function renderEntryState() {
  if (!ui.entryOverlay) return;
  ui.entryModeTalk.classList.toggle('active', entryMode === InputMode.TALK);
  ui.entryModeWrite.classList.toggle('active', entryMode === InputMode.WRITE);
  ui.entryModeTalk.setAttribute('aria-selected', String(entryMode === InputMode.TALK));
  ui.entryModeWrite.setAttribute('aria-selected', String(entryMode === InputMode.WRITE));
  ui.entryTalkContent.classList.toggle('entry-hidden', entryMode !== InputMode.TALK);
  ui.entryWriteContent.classList.toggle('entry-hidden', entryMode !== InputMode.WRITE);
  ui.entrySubtitle.textContent = entryMode === InputMode.TALK
    ? (entryPermissionStatus === 'granted'
        ? ''
        : 'Necesitamos permiso de micrófono para detectar tus dispositivos.')
    : '';
  ui.entrySubtitle.classList.toggle('entry-hidden', entryMode !== InputMode.TALK);

  const startEnabled = getEntryModeStartEnabled();
  ui.startBtn.disabled = !startEnabled || entryInProgress;
  if (entryRequested && !scenarioReady) {
    ui.startBtn.textContent = 'Cargando escenario…';
  } else if (entryMode === InputMode.TALK && entryPermissionStatus !== 'granted') {
    ui.startBtn.textContent = 'Activar micrófono';
  } else {
    ui.startBtn.textContent = 'Empezar';
  }

  if (!scenarioReady) {
    ui.entryLoadingText.textContent = 'Cargando escenario';
    ui.entryScenarioSpinner.style.display = 'inline-flex';
    ui.entryScenarioState.classList.remove('ready');
  } else {
    ui.entryLoadingText.textContent = 'Escenario cargado';
    ui.entryScenarioSpinner.style.display = 'none';
    ui.entryScenarioState.classList.add('ready');
  }

  const showSearchHeader = entryMode === InputMode.TALK;
  const waitingForPermission = entryMode === InputMode.TALK && entryPermissionStatus !== 'granted';
  ui.entryDeviceSearch?.classList.toggle('hidden', !showSearchHeader);
  ui.entryDeviceLabel?.classList.toggle('entry-hidden', waitingForPermission || entryMode !== InputMode.TALK);
  if (ui.entryDeviceSearch) {
    ui.entryDeviceSearch.innerHTML = waitingForPermission
      ? '<span>Necesitamos permiso para listar los micrófonos disponibles</span>'
      : '<span>Micrófonos detectados</span><span class="entry-device-search-spinner" aria-hidden="true"></span>';
  }

  if (entryPermissionStatus === 'prompt' || entryPermissionStatus === 'unknown') {
    ui.entryDeviceStatus.textContent = 'Pulsa “Activar micrófono” para conceder acceso y cargar tus dispositivos de audio.';
    ui.entryDeviceStatus.classList.remove('error');
  } else if (entryPermissionStatus === 'denied') {
    ui.entryDeviceStatus.textContent = 'Permiso de micrófono denegado. Habilítalo en el navegador o usa modo Escribir.';
    ui.entryDeviceStatus.classList.add('error');
  } else if (!selectedEntryDeviceId) {
    ui.entryDeviceStatus.textContent = 'No encontramos un micrófono válido después de conceder permiso.';
    ui.entryDeviceStatus.classList.add('error');
  } else {
    ui.entryDeviceStatus.textContent = 'Micrófono seleccionado. Puedes empezar en modo hablar.';
    ui.entryDeviceStatus.classList.remove('error');
  }
  renderAudioDeviceSelector();
}

function renderEntryDevices() {
  if (!ui.entryDeviceList) return;
  const currentChildren = [...ui.entryDeviceList.querySelectorAll('[data-device-id]')];
  const currentById = new Map(currentChildren.map((node) => [node.dataset.deviceId, node]));

  if (entryPermissionStatus !== 'granted') {
    ui.entryDeviceList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'entry-device-empty';
    empty.textContent = 'Activa el micrófono para mostrar tus dispositivos disponibles';
    ui.entryDeviceList.appendChild(empty);
    selectedEntryDeviceId = null;
    return;
  }

  if (!availableInputDevices.length) {
    ui.entryDeviceList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'entry-device-empty';
    empty.textContent = 'Ningún dispositivo conectado';
    ui.entryDeviceList.appendChild(empty);
    selectedEntryDeviceId = null;
    return;
  }

  const fragment = document.createDocumentFragment();
  availableInputDevices.forEach((device) => {
    let option = currentById.get(device.deviceId);
    if (!option) {
      option = document.createElement('button');
      option.type = 'button';
      option.className = 'entry-device-option';
      option.setAttribute('role', 'option');
      option.dataset.deviceId = device.deviceId;
      option.addEventListener('click', () => setSelectedEntryDevice(device.deviceId, 'click'));

      const main = document.createElement('span');
      main.className = 'entry-device-main';
      const icon = document.createElement('span');
      icon.className = 'entry-device-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '🎧';
      const name = document.createElement('span');
      name.className = 'entry-device-name';
      main.append(icon, name);
      const check = document.createElement('span');
      check.className = 'entry-device-check';
      check.setAttribute('aria-hidden', 'true');
      check.textContent = '✓';
      option.append(main, check);
    }

    option.querySelector('.entry-device-name').textContent = device.cleanLabel;
    const isActive = selectedEntryDeviceId === device.deviceId;
    option.classList.toggle('active', isActive);
    option.setAttribute('aria-selected', String(isActive));
    fragment.appendChild(option);
  });

  ui.entryDeviceList.innerHTML = '';
  ui.entryDeviceList.appendChild(fragment);
}

async function syncMicPermissionState() {
  if (!navigator.permissions?.query) return;
  try {
    const status = await navigator.permissions.query({ name: 'microphone' });
    if (status.state === 'granted' || status.state === 'denied' || status.state === 'prompt') {
      entryPermissionStatus = status.state;
      hasMicPermission = status.state === 'granted';
    }
    status.onchange = () => {
      entryPermissionStatus = status.state;
      hasMicPermission = status.state === 'granted';
      scheduleEntryDeviceRefresh('permission-change', 0);
      renderEntryState();
    };
  } catch (_) {}
}

async function requestMicPermissionsForEntry() {
  if (!navigator.mediaDevices?.getUserMedia) {
    entryPermissionStatus = 'denied';
    hasMicPermission = false;
    lastEntryMicError = 'Este navegador no soporta acceso al micrófono.';
    return false;
  }

  lastEntryMicError = '';

  try {
    await getOrCreateAudioContext().resume();
  } catch (_) {}

  const baseAudioConstraints = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  const preferredConstraints = selectedEntryDeviceId
    ? { audio: { ...baseAudioConstraints, deviceId: { exact: selectedEntryDeviceId } } }
    : { audio: baseAudioConstraints };

  try {
    const stream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
    stream.getTracks().forEach((track) => track.stop());
    entryPermissionStatus = 'granted';
    hasMicPermission = true;
    return true;
  } catch (err) {
    const recoverable = err?.name === 'NotReadableError'
      || err?.name === 'NotFoundError'
      || err?.name === 'OverconstrainedError';

    if (recoverable && selectedEntryDeviceId) {
      try {
        const fallbackStream = await navigator.mediaDevices.getUserMedia({ audio: baseAudioConstraints });
        fallbackStream.getTracks().forEach((track) => track.stop());
        entryPermissionStatus = 'granted';
        hasMicPermission = true;
        lastEntryMicError = '';
        return true;
      } catch (fallbackErr) {
        err = fallbackErr;
      }
    }

    if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
      entryPermissionStatus = 'denied';
      lastEntryMicError = 'Has bloqueado el permiso del micrófono.';
    } else if (err?.name === 'NotReadableError') {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No se pudo iniciar el micrófono. Cierra otras apps que lo estén usando y reintenta.';
    } else if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No encontramos un micrófono disponible con esa selección.';
    } else {
      entryPermissionStatus = 'prompt';
      lastEntryMicError = 'No pudimos activar el micrófono. Reintenta.';
    }
    hasMicPermission = false;
    console.error('[entry] Error al pedir permiso de micrófono', err);
    return false;
  }
}

async function refreshEntryDevices(reason = 'manual') {
  if (!navigator.mediaDevices?.enumerateDevices) {
    availableInputDevices = [];
    selectedEntryDeviceId = null;
    renderEntryDevices();
    renderEntryState();
    return;
  }

  if (refreshInFlight) {
    refreshPendingAfterInFlight = true;
    return;
  }

  refreshInFlight = true;
  refreshPendingAfterInFlight = false;
  const sequence = ++refreshSequence;
  const previousList = availableInputDevices;
  const previousSelected = selectedEntryDeviceId;

  try {
    const rawDevices = await navigator.mediaDevices.enumerateDevices();
    if (sequence !== refreshSequence) return;

    const nextDevices = entryPermissionStatus === 'granted'
      ? toUiAudioInputDevices(rawDevices)
      : [];
    availableInputDevices = nextDevices;

    const stored = getSavedEntryDeviceId();
    const storedExists = stored && nextDevices.some((d) => d.deviceId === stored);

    if (storedExists && !previousSelected) {
      selectedEntryDeviceId = stored;
    } else {
      selectedEntryDeviceId = pickReplacementDevice(previousSelected, previousList, nextDevices);
    }

    if (selectedEntryDeviceId) saveEntryDeviceId(selectedEntryDeviceId);

  } catch (err) {
    console.warn('[entry] enumerateDevices falló', err);
    availableInputDevices = [];
    selectedEntryDeviceId = null;
  } finally {
    refreshInFlight = false;
  }

  renderEntryDevices();
  renderEntryState();
  renderAudioDeviceSelector();

  if (refreshPendingAfterInFlight) {
    refreshPendingAfterInFlight = false;
    scheduleEntryDeviceRefresh(`follow-up:${reason}`, 80);
  }
}

function scheduleEntryDeviceRefresh(reason = 'manual', delayMs = 120) {
  if (entryDeviceDebounceTimer) window.clearTimeout(entryDeviceDebounceTimer);
  entryDeviceDebounceTimer = window.setTimeout(() => {
    entryDeviceDebounceTimer = null;
    if (!isAnyAudioDeviceSurfaceVisible()) return;
    void refreshEntryDevices(reason);
  }, delayMs);
}

async function validateTalkModeForEntry() {
  if (ui.entryError) ui.entryError.textContent = '';

  if (entryPermissionStatus !== 'granted') {
    const permissionOk = await requestMicPermissionsForEntry();
    await refreshEntryDevices(permissionOk ? 'validate-post-permission' : 'validate-permission-error');

    if (!permissionOk) {
      if (ui.entryError) {
        ui.entryError.textContent = lastEntryMicError || (entryPermissionStatus === 'denied'
          ? 'No pudimos habilitar el micrófono. Activa permisos o usa Escribir.'
          : 'No pudimos validar el micrófono. Reintenta.');
      }
      renderEntryState();
      return false;
    }

    if (!selectedEntryDeviceId) {
      if (ui.entryError) ui.entryError.textContent = 'Concediste permiso, pero no detectamos un micrófono disponible.';
      renderEntryState();
      return false;
    }

    renderEntryState();
    return 'ready-after-permission';
  }

  await refreshEntryDevices('validate-existing-permission');

  if (!selectedEntryDeviceId) {
    if (ui.entryError) ui.entryError.textContent = 'No se detectó un micrófono disponible.';
    renderEntryState();
    return false;
  }

  renderEntryState();
  return 'ready';
}

async function finalizeEntry() {
  if (entryInProgress) return;
  if (!getCanEnterNow()) return;
  entryInProgress = true;
  ui.startBtn.disabled = true;
  const targetMode = entryRequestedMode || entryMode;

  if (targetMode === InputMode.WRITE) {
    resolveEntryInputMode(InputMode.WRITE);
    setStatusText('Listo');
  } else {
    resolveEntryInputMode(InputMode.TALK);
    updateReplyText('Te escucho. Empieza a hablar cuando quieras.');
    try {
      if (!isMicActuallyRecording()) {
        setStatusText('Activando mic…');
        await startVoiceCapture();
      }
      setStatusText('Escuchando…');
    } catch (err) {
      console.error('[entry] No se pudo iniciar captura en modo hablar', err);
      resolveEntryInputMode(InputMode.WRITE);
      setStatusText('Listo');
      updateReplyText('No se pudo iniciar el micrófono. Puedes continuar en modo escritura.');
    }
    updateUi();
    syncAvatarMode();
  }

  entryRequestedMode = null;
  ui.entryOverlay.classList.add('hidden');
  window.setTimeout(() => {
    ui.entryOverlay.style.display = 'none';
  }, 240);
}

function tryResolveEntryRequest() {
  renderEntryState();
  if (entryRequested && getCanEnterNow()) {
    void finalizeEntry();
  }
}

function setEntryMode(mode) {
  entryMode = mode;
  if (mode === InputMode.WRITE) {
    if (isMicActuallyRecording()) {
      discardRecording = true;
      void stopVoiceCapture().finally(() => teardownMic());
    }
    if (ui.entryError) ui.entryError.textContent = '';
    renderEntryState();
    return;
  }
  renderEntryState();
  scheduleEntryDeviceRefresh('mode-talk', 0);
}

async function handleStartEntry() {
  if (entryMode === InputMode.TALK) {
    const talkReady = await validateTalkModeForEntry();
    if (!talkReady) {
      renderEntryState();
      return;
    }

    if (talkReady === 'ready-after-permission') {
      if (ui.entryError) ui.entryError.textContent = '';
      renderEntryState();
      return;
    }

    try {
      setStatusText('Activando mic…');
      await startVoiceCapture();
      setStatusText('Escuchando…');
      updateUi();
      syncAvatarMode();
    } catch (err) {
      console.error('[entry] No se pudo precalentar captura desde Empezar', err);
      if (ui.entryError) {
        ui.entryError.textContent = err?.name === 'NotReadableError'
          ? 'No se pudo iniciar el micrófono. Puede estar ocupado por otra app; reintenta o usa Escribir.'
          : 'No pudimos iniciar el micrófono. Reintenta o usa Escribir.';
      }
      renderEntryState();
      return;
    }
  }
  entryRequestedMode = entryMode;
  entryRequested = true;
  tryResolveEntryRequest();
}

function stopFeedbackPolling() {
  if (feedbackPollingTimer) {
    window.clearTimeout(feedbackPollingTimer);
    feedbackPollingTimer = null;
  }
}

function stopFeedbackFloatingPhrases() {
  if (feedbackFloatingTimer) {
    window.clearTimeout(feedbackFloatingTimer);
    feedbackFloatingTimer = null;
  }
  if (ui.feedbackFloatingLayer) ui.feedbackFloatingLayer.innerHTML = '';
}

function renderFeedbackPhraseMarkup(parts) {
  return `<code>${parts.map(([klass, text]) => `<span class="token ${klass}">${text}</span>`).join('<span class="token token-muted">&nbsp;</span>')}</code>`;
}

function randomInRange([min, max]) {
  return min + Math.random() * (max - min);
}

function nextFeedbackQuadrant(isMobile) {
  if (!ui.feedbackFloatingLayer) return { quadrant: 'topLeft', anchor: { top: [12, 18], left: [8, 16] } };

  const quadrants = isMobile ? FloatingPhraseQuadrantsMobile : FloatingPhraseQuadrantsDesktop;
  const activeCounts = Object.fromEntries(FloatingPhraseQuadrantOrder.map((name) => [name, 0]));

  Array.from(ui.feedbackFloatingLayer.children).forEach((child) => {
    const quadrant = child?.dataset?.quadrant;
    if (quadrant in activeCounts) activeCounts[quadrant] += 1;
  });

  const minCount = Math.min(...Object.values(activeCounts));
  const candidates = FloatingPhraseQuadrantOrder.filter((name) => activeCounts[name] === minCount);
  const orderedCandidates = candidates.sort((a, b) => {
    const aIdx = FloatingPhraseQuadrantOrder.indexOf(a);
    const bIdx = FloatingPhraseQuadrantOrder.indexOf(b);
    const aDistance = (aIdx - feedbackQuadrantCursor + FloatingPhraseQuadrantOrder.length) % FloatingPhraseQuadrantOrder.length;
    const bDistance = (bIdx - feedbackQuadrantCursor + FloatingPhraseQuadrantOrder.length) % FloatingPhraseQuadrantOrder.length;
    return aDistance - bDistance;
  });

  const quadrant = orderedCandidates[0] || FloatingPhraseQuadrantOrder[feedbackQuadrantCursor % FloatingPhraseQuadrantOrder.length];
  const anchors = quadrants[quadrant] || quadrants.topLeft;
  const anchor = anchors[Math.floor(Math.random() * anchors.length)];
  feedbackQuadrantCursor = (FloatingPhraseQuadrantOrder.indexOf(quadrant) + 1) % FloatingPhraseQuadrantOrder.length;
  return { quadrant, anchor };
}

function constrainFeedbackFloatingPhrase(el) {
  if (!el || !ui.feedbackFloatingLayer) return;

  const containerRect = ui.feedbackFloatingLayer.getBoundingClientRect();
  if (!containerRect.width || !containerRect.height) return;

  const maxWidth = Math.max(160, Math.min(containerRect.width * 0.34, 520, containerRect.width - 24));
  const maxHeight = Math.max(56, Math.min(containerRect.height * 0.22, 180, containerRect.height - 24));
  el.style.maxWidth = `${Math.round(maxWidth)}px`;
  el.style.maxHeight = `${Math.round(maxHeight)}px`;

  const safeInset = Math.max(12, Math.min(containerRect.width, containerRect.height) * 0.03);
  const lineRect = el.getBoundingClientRect();
  const maxLeft = Math.max(safeInset, containerRect.width - lineRect.width - safeInset);
  const maxTop = Math.max(safeInset, containerRect.height - lineRect.height - safeInset);
  const left = Math.min(Math.max(lineRect.left - containerRect.left, safeInset), maxLeft);
  const top = Math.min(Math.max(lineRect.top - containerRect.top, safeInset), maxTop);

  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

function spawnFeedbackFloatingPhrase() {
  if (!$('feedbackLoadingScreen') || $('feedbackLoadingScreen').classList.contains('hidden')) return;
  if (!ui.feedbackFloatingLayer) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia('(max-width: 640px)').matches;
  const maxActive = reducedMotion ? (isMobile ? 4 : 4) : (isMobile ? 4 : 6);
  const activeCount = ui.feedbackFloatingLayer.childElementCount;
  if (activeCount >= maxActive) return;

  const phrase = FeedbackFloatingPhrases[Math.floor(Math.random() * FeedbackFloatingPhrases.length)];
  const { quadrant, anchor } = nextFeedbackQuadrant(isMobile);
  const el = document.createElement('span');
  const durationMs = reducedMotion ? 0 : 7600 + Math.random() * 2400;
  const opacity = reducedMotion ? 0.18 : 0.19 + Math.random() * 0.12;
  const scale = 0.92 + Math.random() * 0.12;
  const blur = reducedMotion ? 0 : Math.random() > 0.72 ? 0.35 : 0;

  el.className = 'feedback-floating-line';
  el.dataset.quadrant = quadrant;
  el.style.top = `${randomInRange(anchor.top).toFixed(2)}%`;
  el.style.left = `${randomInRange(anchor.left).toFixed(2)}%`;
  el.style.setProperty('--line-opacity', opacity.toFixed(2));
  el.style.setProperty('--line-scale', scale.toFixed(2));
  el.style.setProperty('--line-blur', `${blur.toFixed(2)}px`);
  el.style.setProperty('--line-duration', `${durationMs}ms`);
  el.innerHTML = renderFeedbackPhraseMarkup(phrase);
  ui.feedbackFloatingLayer.appendChild(el);
  constrainFeedbackFloatingPhrase(el);

  if (reducedMotion) {
    el.style.opacity = String(opacity);
    el.style.transform = 'none';
    return;
  }

  window.setTimeout(() => el.remove(), durationMs);
}

function scheduleFeedbackFloatingPhrase() {
  if (!$('feedbackLoadingScreen') || $('feedbackLoadingScreen').classList.contains('hidden')) return;

  spawnFeedbackFloatingPhrase();

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia('(max-width: 640px)').matches;
  const nextDelay = reducedMotion ? 2400 : (isMobile ? 1150 : 900) + Math.random() * 1200;
  feedbackFloatingTimer = window.setTimeout(scheduleFeedbackFloatingPhrase, nextDelay);
}

function startFeedbackFloatingPhrases() {
  stopFeedbackFloatingPhrases();
  if (!ui.feedbackFloatingLayer) return;

  feedbackQuadrantCursor = 0;
  const initialBursts = 4;
  for (let idx = 0; idx < initialBursts; idx += 1) spawnFeedbackFloatingPhrase();
  scheduleFeedbackFloatingPhrase();
}

function closeFinalizePopover() {
  finalizePopoverOpen = false;
  $('finishConfirmPopover')?.classList.remove('visible');
}

function openFinalizePopover() {
  renderFinalizePopoverState();
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

  if (mode === 'loading') startFeedbackFloatingPhrases();
  else stopFeedbackFloatingPhrases();
  scheduleEmbedHeightEmission(`view:${mode}`);
}

function renderFinalReport(report) {
  const root = $('feedbackReportRoot');
  if (!root || !window.FeedbackReportView) return;
  feedbackReportSnapshot = report;
  hideFinalSaveToast();
  window.FeedbackReportView.renderReport(root, report);
  scheduleEmbedHeightEmission('report-render');
}

function transparentFallbackPngDataUrl() {
  return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8S0AAAAASUVORK5CYII=';
}

function deriveFinalResultTitle(report) {
  const header = report?.header || {};
  return header.report_title || header.activity_name || 'Resultado final del simulador';
}

function deriveFinalResultActivityId(report, correlation = null) {
  const candidate = correlation?.public_slug
    || correlation?.context_id
    || report?.provenance?.context_id
    || report?.provenance?.flow_id
    || null;
  return typeof candidate === 'string' && candidate.trim() ? candidate.trim() : 'simulador';
}

async function buildFinalResultPayload(report, extra = {}) {
  if (!report) return null;
  const header = report.header || {};
  const correlation = getSessionCorrelationMeta();
  const serializedHtml = window.FeedbackReportView?.serializeReportToHtml?.(report) || null;
  let snapshotPngDataUrl = transparentFallbackPngDataUrl();
  const captureRoot = $('feedbackReportRoot');
  try {
    if (window.FeedbackReportView?.captureReportPngDataUrl) {
      snapshotPngDataUrl = await window.FeedbackReportView.captureReportPngDataUrl(report, { rootElement: captureRoot });
    }
  } catch (err) {
    console.warn('[embed] No se pudo serializar el PNG final del informe; se usará fallback transparente.', err);
  }
  const basePayload = {
    evaluation_id: feedbackEvaluationId,
    available_exports: ['html', 'json', 'png'],
    title: deriveFinalResultTitle(report),
    activityid: deriveFinalResultActivityId(report, correlation),
    session_id: correlation?.session_id || null,
    conversation_id: correlation?.conversation_id || null,
    trace_count: Number.isFinite(Number(correlation?.trace_count)) ? Number(correlation.trace_count) : null,
    context_id: correlation?.context_id || report?.provenance?.context_id || null,
    public_slug: correlation?.public_slug || null,
    generated_at: new Date().toISOString(),
    score_global_100: Number(header.score_global_100 || 0),
    stars_0_5: Number(header.stars_0_5 || 0),
    activity_name: header.activity_name || null,
    interaction_outcome: header.interaction_outcome || null,
    summary_2_3_lines: header.summary_2_3_lines || null,
    report,
    report_html: serializedHtml,
    summary_html: serializedHtml,
    report_json: report,
    payloadjson: report,
    snapshot_png_dataurl: snapshotPngDataUrl,
    ...extra,
  };
  return {
    ...basePayload,
    payload_hash: deriveFinalResultPayloadHash(basePayload),
  };
}

async function emitFinalResultLifecycle(report, { reason = 'report-ready' } = {}) {
  const payload = await buildFinalResultPayload(report, { reason });
  if (!payload) return;
  emitEmbedMessage('final_result_available', {
    evaluation_id: payload.evaluation_id,
    available_exports: payload.available_exports,
    score_global_100: payload.score_global_100,
    stars_0_5: payload.stars_0_5,
    interaction_outcome: payload.interaction_outcome,
    reason,
  });
  const finalEnvelope = emitEmbedMessage('final_result', payload, {
    correlationId: buildFinalResultCorrelationId(payload),
  });
  if (finalEnvelope) registerPendingEmbeddedFinalResultAck(payload, finalEnvelope);
}

async function downloadCurrentReport(format) {
  const report = feedbackReportSnapshot;
  if (!report || !window.FeedbackReportView) return;

  const actions = {
    html: () => window.FeedbackReportView.downloadReportHtml(report),
    json: () => window.FeedbackReportView.downloadReportJson(report),
    png: () => window.FeedbackReportView.downloadReportPng(report),
  };

  const action = actions[format];
  if (!action) return;

  try {
    await action();
    emitEmbedMessage('final_result_available', {
      evaluation_id: feedbackEvaluationId,
      available_exports: ['html', 'json', 'png'],
      exported_format: format,
      reason: 'user-download',
    });
  } catch (err) {
    $('feedbackErrorMessage').textContent = `No se pudo exportar el informe en ${format.toUpperCase()}: ${String(err?.message || err)}`;
    showFeedbackView('error');
  }
}

async function fetchEvaluationReport(evaluationId) {
  const out = await api(`/feedback/evaluations/${evaluationId}/report`, { method: 'GET' });
  feedbackEvaluationId = evaluationId;
  showFeedbackView('report');
  renderFinalReport(out.report);
  await emitFinalResultLifecycle(out.report, { reason: 'report-fetched' });
}

async function pollEvaluationStatus(evaluationId) {
  try {
    const status = await api(`/feedback/evaluations/${evaluationId}`, { method: 'GET' });
    clearSessionBusyState();
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
    if (isSessionBusyError(err)) {
      setSessionBusyState(err, { source: 'feedback' });
      updateUi();
      return;
    }
    $('feedbackErrorMessage').textContent = `Error de red durante la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
}

async function startFeedbackEvaluation() {
  const out = await api('/feedback/evaluations', { method: 'POST', body: JSON.stringify(ids()) });
  clearSessionBusyState();
  feedbackEvaluationId = out.evaluation_id;
  showFeedbackView('loading');
  setFeedbackStageText(out.status);
  stopFeedbackPolling();
  feedbackPollingTimer = window.setTimeout(() => pollEvaluationStatus(feedbackEvaluationId), 200);
}

async function runNegotiationTurnFromText(message, { allowWhileVoiceTurn = false } = {}) {
  syncSessionBoundaryReset();
  if (!message || turnInFlight || (voiceTurnInFlight && !allowWhileVoiceTurn)) return false;

  turnInFlight = true;
  updateUi();
  try {
    const payload = { ...ids(), message, new_conversation: false };
    updateReplyText('...');
    setStatusText('Procesando…');
    withAvatarRuntime((runtime) => { runtime.setMode('THINKING'); runtime.setTalkLevel(0); });

    const out = await api('/negociacion/turn', { method: 'POST', body: JSON.stringify(payload) });
    clearSessionBusyState();
    updateReplyText(out.reply || '');
    armFinishButton(out.finish_button_armed);
    setLatestTraceCount(out.trace_count);

    const contract = out.entry_contract;
    $('meta').textContent =
      `session=${out.session_id} endpoint=${contract.entrypoint} runtime=execute_turn_with_contract ` +
      `overrides=${contract.overrides_applied} turn=${out.latest_turn_id || '-'} ` +
      `conversation=${out.conversation_id_after || '-'} traces=${out.trace_count}`;
    setStatusText('Listo');

    if (out.reply) {
      try {
        await playTtsWithAvatar(out.reply);
      } catch (err) {
        console.warn('[tts] Error reproduciendo TTS; fallback visual', err);
        withAvatarRuntime((runtime) => {
          runtime.setMode('SPEAKING');
          runtime.setTalkLevel(0.38);
          window.setTimeout(() => {
            runtime.setTalkLevel(0.16);
            window.setTimeout(() => {
              runtime.setTalkLevel(0);
              syncAvatarMode();
            }, 240);
          }, 260);
        });
        return;
      }
    }

    syncAvatarMode();
    return true;
  } catch (err) {
    if (isSessionBusyError(err)) {
      setSessionBusyState(err, { source: 'turn' });
      setStatusText('Sesión ocupada');
      updateUi();
      return false;
    }
    throw err;
  } finally {
    turnInFlight = false;
    updateUi();
  }
}

async function handleSend() {
  if (turnInFlight || voiceTurnInFlight || getActiveSessionBusyState()) return;
  const message = ui.textInput.value.trim();
  if (!message) return;
  await runNegotiationTurnFromText(message);
  ui.textInput.value = '';
}

$('bootstrap').onclick = async () => {
  syncSessionBoundaryReset();
  if (getActiveSessionBusyState()) return;
  const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(bootstrapPayload()) });
  clearSessionBusyState();
  applyBootstrapIdentity(out);
  currentPresentationConfig = out.presentation_config || null;
  updateBootstrapMeta(out);
  notifyBootstrapSessionReady();
  maybeEmitEmbedReady('manual-bootstrap');
  updateUi();
};

$('newConv').onclick = async () => {
  if (getActiveSessionBusyState()) return;
  const payload = ids();
  const out = await api('/negociacion/new_conversation', { method: 'POST', body: JSON.stringify(payload) });
  clearSessionBusyState();
  applyBootstrapIdentity(out);
  currentPresentationConfig = out.presentation_config || currentPresentationConfig;
  resetFinishButtonArmed();
  setLatestTraceCount(0);
  updateBootstrapMeta(out);
  notifyBootstrapSessionReady();
  maybeEmitEmbedReady('new-conversation');
  updateReplyText('');
  updateUi();
};

ui.startBtn.addEventListener('click', () => {
  void handleStartEntry();
});

ui.entryModeTalk?.addEventListener('click', () => {
  setEntryMode(InputMode.TALK);
});

ui.entryModeWrite?.addEventListener('click', () => {
  setEntryMode(InputMode.WRITE);
});

ui.audioDeviceTrigger?.addEventListener('click', () => {
  toggleAudioDevicePopover();
});

ui.modeTalk.addEventListener('click', async () => {
  if (turnInFlight || voiceTurnInFlight || getActiveSessionBusyState()) return;

  setInputMode(InputMode.TALK);
  if (!hasMicPermission) return;

  try {
    setStatusText('Activando mic…');
    await startVoiceCapture();
    setStatusText('Escuchando…');
    updateUi();
    syncAvatarMode();
  } catch (err) {
    console.error('[mic] No se pudo iniciar grabación', err);
    setInputMode(InputMode.WRITE);
    setStatusText('Listo');
    syncAvatarMode();
  }
});
ui.modeWrite.addEventListener('click', () => {
  if (turnInFlight || getActiveSessionBusyState()) return;
  if (isRecording) {
    discardRecording = true;
    void stopVoiceCapture().finally(() => teardownMic());
  }
  setInputMode(InputMode.WRITE);
});

ui.sendTextBtn.addEventListener('click', handleSend);
async function handleFinishTurn() {
  if (turnInFlight || voiceTurnInFlight || ui.finishTurnBtn.disabled || getActiveSessionBusyState()) return;
  voiceTurnInFlight = true;
  updateUi();
  setStatusText('Procesando…');
  ui.finishTurnBtn.classList.remove('highlight');
  void ui.finishTurnBtn.offsetWidth;
  ui.finishTurnBtn.classList.add('highlight');

  try {
    const blob = await stopVoiceCapture();
    teardownMic();
    if (!blob || !blob.size) throw new Error('No se capturó audio.');
    const text = await transcribeAudio(blob);
    if (!text) throw new Error('Transcripción vacía.');
    const turnCompleted = await runNegotiationTurnFromText(text, { allowWhileVoiceTurn: true });
    if (turnCompleted !== false && currentInputMode === InputMode.TALK) {
      setStatusText('Escuchando…');
      await startVoiceCapture();
      updateUi();
      syncAvatarMode();
    }
  } catch (err) {
    console.error('[voice] Error procesando turno hablado', err);
    if (isSessionBusyError(err)) {
      setSessionBusyState(err, { source: 'turn' });
      setStatusText('Sesión ocupada');
      updateUi();
      return;
    }
    setStatusText(err?.message || 'No se pudo procesar el audio.');
    if (currentInputMode === InputMode.TALK) {
      try {
        await startVoiceCapture();
        updateUi();
        syncAvatarMode();
      } catch (_) {
        // fallback a escritura solo si mic falla realmente
        setInputMode(InputMode.WRITE);
        syncAvatarMode();
      }
    }
  } finally {
    voiceTurnInFlight = false;
    updateUi();
  }
}

ui.finishTurnBtn.addEventListener('click', () => {
  void handleFinishTurn();
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
  if (!canFinalizeConversation() || getActiveSessionBusyState()) return;
  closeFinalizePopover();
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    if (isSessionBusyError(err)) {
      setSessionBusyState(err, { source: 'feedback' });
      updateUi();
      return;
    }
    $('feedbackErrorMessage').textContent = `No se pudo iniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackRetryBtn').onclick = async () => {
  if (getActiveSessionBusyState()) return;
  showFeedbackView('app');
  try {
    await startFeedbackEvaluation();
  } catch (err) {
    if (isSessionBusyError(err)) {
      setSessionBusyState(err, { source: 'feedback' });
      updateUi();
      return;
    }
    $('feedbackErrorMessage').textContent = `No se pudo reiniciar la evaluación: ${String(err)}`;
    showFeedbackView('error');
  }
};

$('feedbackBackBtnSecondary').onclick = () => showFeedbackView('app');

document.addEventListener('click', (e) => {
  if (!ui.conversationMode) return;
  if (!ui.conversationMode.contains(e.target)) closeConversationModeMenu();
});

document.addEventListener('click', (e) => {
  if (!audioDevicePopoverOpen || !ui.audioDeviceSelector) return;
  if (e.target instanceof Node && !ui.audioDeviceSelector.contains(e.target)) closeAudioDevicePopover();
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeConversationModeMenu();
    closeAudioDevicePopover();
    return;
  }

  if (e.key !== 'Enter' || e.repeat || e.shiftKey || turnInFlight || voiceTurnInFlight || getActiveSessionBusyState()) return;
  const target = e.target;
  if (target instanceof HTMLTextAreaElement && currentInputMode !== InputMode.WRITE) return;

  if (currentInputMode === InputMode.WRITE) {
    e.preventDefault();
    void handleSend();
    return;
  }

  if (currentInputMode === InputMode.TALK && !ui.finishTurnBtn.disabled) {
    e.preventDefault();
    void handleFinishTurn();
  }
});

window.addEventListener('click', (ev) => {
  if (!finalizePopoverOpen) return;
  const popover = $('finishConfirmPopover');
  const btn = $('finishNegotiationBtn');
  const target = ev.target;
  if (popover && btn && target instanceof Node && !popover.contains(target) && !btn.contains(target)) closeFinalizePopover();
});

window.addEventListener('avatar-runtime-ready', () => {
  scenarioReady = true;
  tryResolveEntryRequest();
  maybeEmitEmbedReady('avatar-runtime-ready');
  scheduleEmbedHeightEmission('avatar-runtime-ready');
});

window.addEventListener('avatar-runtime-error', () => {
  scenarioReady = false;
  if (ui.entryError) ui.entryError.textContent = 'No se pudo cargar el escenario. Recarga para reintentar.';
  renderEntryState();
});

function bindRuntimeReadiness() {
  const runtime = window.__avatarRuntime;
  if (!runtime) return;
  if (typeof runtime.onReady === 'function') {
    runtime.onReady(() => {
      scenarioReady = true;
      tryResolveEntryRequest();
      maybeEmitEmbedReady('runtime-onReady');
      scheduleEmbedHeightEmission('runtime-onReady');
    });
  }
  if (typeof runtime.onError === 'function') {
    runtime.onError(() => {
      scenarioReady = false;
      if (ui.entryError) ui.entryError.textContent = 'No se pudo cargar el escenario. Recarga para reintentar.';
      renderEntryState();
    });
  }
  if (typeof runtime.isReady === 'function' && runtime.isReady()) {
    scenarioReady = true;
    maybeEmitEmbedReady('runtime-isReady');
  }
}

async function bootstrapEntryDeviceBackground() {
  await syncMicPermissionState();
  await refreshEntryDevices('bootstrap');
  renderEntryDevices();
  renderEntryState();
}

function startEntryDevicePolling() {
  if (entryDeviceRefreshTimer) window.clearInterval(entryDeviceRefreshTimer);
  entryDeviceRefreshTimer = window.setInterval(() => {
    if (!isEntryOverlayVisible()) return;
    scheduleEntryDeviceRefresh('poll', 220);
  }, 3000);
}

if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', () => {
    scheduleEntryDeviceRefresh('devicechange', 140);
  });
}

window.addEventListener('focus', () => {
  scheduleEntryDeviceRefresh('focus', 120);
  scheduleEmbedHeightEmission('focus');
});

window.addEventListener('pageshow', () => {
  scheduleEntryDeviceRefresh('pageshow', 120);
  scheduleEmbedHeightEmission('pageshow');
});

window.addEventListener('resize', () => {
  scheduleEmbedHeightEmission('resize');
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    scheduleEntryDeviceRefresh('visibilitychange', 80);
    scheduleEmbedHeightEmission('visibilitychange');
  }
});

(async function initInterfazUsuarioSession() {
  syncSessionBoundaryReset();
  applyEmbedMode();
  installEmbedMessageListener();
  resetBootstrapSessionState();
  try {
    const out = await api('/sessions/bootstrap', { method: 'POST', body: JSON.stringify(bootstrapPayload()) });
    applyBootstrapIdentity(out);
    currentPresentationConfig = out.presentation_config || null;
    applyPresentationConfigToDom(currentPresentationConfig);
    initAvatarRuntimeOnce(currentPresentationConfig);
    bindRuntimeReadiness();
    resetFinishButtonArmed();
    setLatestTraceCount(out.trace_count);
    updateBootstrapMeta(out);
    notifyBootstrapSessionReady();
    maybeEmitEmbedReady('initial-bootstrap');
  } catch (err) {
    scenarioReady = false;
    resetBootstrapSessionState();
    if (ui.entryError) ui.entryError.textContent = 'No se pudo preparar la interfaz. Recarga para reintentar.';
    $('meta').textContent = `bootstrap_error=${String(err)}`;
  }

  if (!entryResolvedInputMode) setInputMode(InputMode.WRITE);
  startEntryDevicePolling();
  await bootstrapEntryDeviceBackground();
  setEntryMode(InputMode.TALK);
  renderEntryState();
  scheduleEntryDeviceRefresh('post-init', 0);
  stopInputOrb();
  renderFinalizePopoverState();
  syncAvatarMode();
})();
