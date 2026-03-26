(function attachCommunicationApp(global) {
  const SCREEN_SETUP = 'setup';
  const SCREEN_AIDA_PREP = 'aida_prep';
  const SCREEN_RECORDING = 'recording';
  const SCREEN_REVIEW = 'review';
  const SCREEN_UPLOADING = 'uploading';
  const SCREEN_PROCESSING = 'processing';
  const SCREEN_REPORT = 'report';
  const SCREEN_ERROR = 'error';
  const EMBED_MESSAGE_VERSION = 1;
  const EMBED_NAMESPACE = 'gestionce.simulator';
  const WAVEFORM_BAR_COUNT = 24;
  const ProcessingStageLabel = {
    queued: 'Preparando análisis...',
    extracting: 'Procesando recursos...',
    extracting_media: 'Preparando medios...',
    transcription_started: 'Analizando transcripción...',
    transcript_ready: 'Transcripción lista.',
    content_analysis_started: 'Evaluando claridad del mensaje...',
    content_analysis_ready: 'Contenido evaluado.',
    delivery_analysis_started: 'Evaluando entrega y ritmo...',
    audio_metrics_started: 'Midiendo audio...',
    audio_features_ready: 'Audio analizado.',
    delivery_analysis_ready: 'Entrega evaluada.',
    frame_extraction_started: 'Analizando lenguaje visual...',
    frames_ready: 'Frames procesados.',
    visual_analysis_started: 'Evaluando presencia visual...',
    visual_analysis_ready: 'Presencia visual analizada.',
    synthesis_started: 'Integrando hallazgos...',
    synthesis_ready: 'Sintetizando feedback...',
    assembling_report: 'Preparando informe final...',
    completed: 'Informe listo.',
  };
  const FloatingPhrases = [
    'Estructura y claridad del discurso',
    'Orden y narrativa del mensaje',
    'Ritmo, pausas y expresividad',
    'Presencia visual y apoyo gestual',
    'AIDA y llamada a la acción',
    'Consistencia del argumento',
  ];

  const SCREEN_ORDER = [
    SCREEN_SETUP,
    SCREEN_AIDA_PREP,
    SCREEN_RECORDING,
    SCREEN_REVIEW,
    SCREEN_UPLOADING,
    SCREEN_PROCESSING,
    SCREEN_REPORT,
  ];

  const state = {
    session: {
      user_id: null,
      session_id: null,
      context_id: null,
      public_slug: null,
      bootstrap_state: 'unknown',
    },
    context: {
      presentation_config: null,
      activity_brief: null,
      capture_policy: null,
    },
    ui: {
      screen: SCREEN_SETUP,
      busy: false,
      error_message: null,
      notice_message: null,
    },
    capture: {
      permission_camera: 'prompt',
      permission_mic: 'prompt',
      selected_video_device_id: null,
      selected_audio_device_id: null,
      available_video_devices: [],
      available_audio_devices: [],
      stream_active: false,
      is_recording: false,
      recorded_blob: null,
      blob_url: null,
      duration_ms: 0,
      mime_type: null,
      blob_size_bytes: 0,
      media_recorder: null,
      media_stream: null,
      record_started_at_ms: null,
      record_timer_id: null,
      elapsed_label: '00:00',
      av_panel_open: false,
      audio_level_ratio: 0,
      av_status_timer_id: null,
      audio_context: null,
      audio_analyser: null,
      audio_source_node: null,
      audio_data_array: null,
      audio_raf_id: null,
    },
    brainmap: {
      attention: '',
      interest: '',
      development: '',
      action: '',
      updated_at: null,
    },
    attempt: {
      attempt_id: null,
      status: null,
      rerecord_count: 0,
    },
    upload: {
      in_flight: false,
      recording_id: null,
      video_ref: null,
      poster_frame_ref: null,
    },
    evaluation: {
      evaluation_id: null,
      status: 'idle',
      stage: null,
      poll_timer_id: null,
      report_available: false,
    },
    report: {
      payload: null,
      placeholder_ready: false,
    },
    final_delivery: {
      status: 'idle',
      last_error: null,
      pending_ack: null,
      last_payload: null,
      ack_meta: null,
    },
  };
  let floatingPhraseTimer = null;
  let floatingPhrasesActive = false;
  let finalSaveToastTimer = null;

  function $(id) { return document.getElementById(id); }
  function transitionTo(screen) { state.ui.screen = screen; renderApp(); }
  function setBusy(value) { state.ui.busy = Boolean(value); renderApp(); }
  function clearError() { state.ui.error_message = null; }
  function setNotice(message) { state.ui.notice_message = message || null; renderApp(); }
  function setError(message) { state.ui.error_message = message || 'Ha ocurrido un error inesperado.'; state.ui.notice_message = null; transitionTo(SCREEN_ERROR); }
  function hideFinalSaveToast() {
    const toast = $('finalSaveToast');
    if (!toast) return;
    toast.classList.remove('visible');
    if (finalSaveToastTimer) {
      global.clearTimeout(finalSaveToastTimer);
      finalSaveToastTimer = null;
    }
  }
  function showFinalSaveToast(message = 'Resultados guardados', durationMs = 4200) {
    const toast = $('finalSaveToast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('visible');
    if (finalSaveToastTimer) global.clearTimeout(finalSaveToastTimer);
    finalSaveToastTimer = global.setTimeout(() => {
      finalSaveToastTimer = null;
      toast.classList.remove('visible');
    }, durationMs);
  }

  function formatDurationLabel(durationMs) {
    const totalSeconds = Math.max(0, Math.round((durationMs || 0) / 1000));
    const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const seconds = (totalSeconds % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
  }

  function formatBytes(bytes) {
    const size = Number(bytes || 0);
    if (!size) return '0 B';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function isSetupReady() {
    return state.capture.permission_camera === 'granted'
      && state.capture.permission_mic === 'granted'
      && state.capture.stream_active
      && Boolean(state.capture.selected_video_device_id)
      && Boolean(state.capture.selected_audio_device_id);
  }

  function readCommunicationSlugFromUrl() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const idx = parts.indexOf('comunicacion');
    if (idx >= 0 && parts[idx + 1]) return decodeURIComponent(parts[idx + 1]);
    return 'comunicacion';
  }


  function readEmbedModeFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const raw = (params.get('embed') || '').trim().toLowerCase();
    if (!raw) return null;
    if (['1', 'true', 'yes', 'on', 'embed'].includes(raw)) return true;
    if (['0', 'false', 'no', 'off'].includes(raw)) return false;
    return null;
  }

  function readEmbedOriginFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const raw = (params.get('parent_origin') || '').trim();
    return raw || null;
  }

  function isEmbeddedRuntime() {
    return window.parent && window.parent !== window;
  }

  function detectEmbedMode() {
    const explicit = readEmbedModeFromUrl();
    if (explicit !== null) return explicit;
    return isEmbeddedRuntime();
  }

  function buildCommunicationEmbedEnvelope(type, payload = {}, options = {}) {
    const correlationId = typeof options.correlationId === 'string' && options.correlationId.trim()
      ? options.correlationId.trim()
      : `${state.session.session_id || 'no-session'}:${type}`;
    return {
      ns: EMBED_NAMESPACE,
      v: EMBED_MESSAGE_VERSION,
      type,
      correlation_id: correlationId,
      session_id: state.session.session_id || null,
      context_id: state.session.context_id || null,
      public_slug: state.session.public_slug || null,
      payload,
    };
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

  function deriveCommunicationFinalPayloadHash(payload) {
    const hashInput = stableStringifyForHash({
      activity_type: payload.activity_type || null,
      title: payload.title || null,
      activityid: payload.activityid || null,
      session_id: payload.session_id || null,
      attempt_id: payload.attempt_id || null,
      recording_id: payload.recording_id || null,
      evaluation_id: payload.evaluation_id || null,
      payloadjson: payload.payloadjson || null,
      summary_html: payload.summary_html || null,
      snapshot_png_dataurl: payload.snapshot_png_dataurl || null,
      video_ref: payload.video_ref || null,
      poster_frame_ref: payload.poster_frame_ref || null,
      duration_ms: payload.duration_ms || null,
    });
    return simpleHashString(hashInput);
  }

  function buildCommunicationFinalCorrelationId(payload) {
    return `${payload.session_id || 'no-session'}:final:${payload.evaluation_id || 'no-eval'}:${payload.payload_hash || 'no-hash'}`;
  }

  function registerPendingCommunicationFinalAck(payload, envelope) {
    state.final_delivery.pending_ack = {
      session_id: payload.session_id,
      activityid: payload.activityid,
      evaluation_id: payload.evaluation_id,
      payload_hash: payload.payload_hash,
      correlation_id: envelope.correlation_id,
      pending_ack: true,
      ack_confirmed: false,
    };
  }

  function isAllowedParentOrigin(origin) {
    const configured = readEmbedOriginFromUrl();
    if (!configured) return false;
    return origin === configured;
  }

  function readCommunicationAckComparableIds(message) {
    const payload = message && typeof message.payload === 'object' ? message.payload : {};
    return {
      session_id: payload.session_id || message.session_id || null,
      activityid: payload.activityid || message.activityid || null,
      evaluation_id: payload.evaluation_id || message.evaluation_id || null,
      payload_hash: payload.payload_hash || message.payload_hash || null,
      correlation_id: payload.correlation_id || message.correlation_id || null,
    };
  }

  function handleCommunicationEmbeddedSaveAck(message, options = {}) {
    if (!message || typeof message !== 'object') return false;
    if (message.ns !== EMBED_NAMESPACE || message.v !== EMBED_MESSAGE_VERSION || message.type !== 'final_result_saved') return false;
    if (options.origin && !isAllowedParentOrigin(options.origin)) return false;
    if (!state.final_delivery.pending_ack || state.final_delivery.pending_ack.pending_ack !== true) return false;
    const payload = message.payload || {};
    const ackOk = payload.status === 'ok' || payload.saved === true;
    if (!ackOk) return false;
    const ids = readCommunicationAckComparableIds(message);
    const pending = state.final_delivery.pending_ack;
    if (ids.session_id !== pending.session_id || ids.activityid !== pending.activityid) return false;
    if (!ids.payload_hash || ids.payload_hash !== pending.payload_hash) return false;
    const complementaryMatches = [
      ids.evaluation_id && ids.evaluation_id === pending.evaluation_id,
      ids.correlation_id && ids.correlation_id === pending.correlation_id,
    ].filter(Boolean);
    pending.pending_ack = false;
    pending.ack_confirmed = true;
    state.final_delivery.status = 'ack_received';
    state.final_delivery.last_error = null;
    state.final_delivery.ack_meta = {
      correlation_id: ids.correlation_id,
      payload_hash: ids.payload_hash,
      complementary_matches: complementaryMatches.length,
      acknowledged_at: new Date().toISOString(),
    };
    if (typeof showFinalSaveToast === 'function') {
      showFinalSaveToast('Resultados guardados');
    }
    renderApp();
    return true;
  }

  async function buildCommunicationFinalResultPayload(report, options = {}) {
    if (!report) throw new Error('No hay report final para serializar');
    const summaryHtml = global.CommunicationReportView.serializeCommunicationReportToHtml(report);
    const snapshot = await global.CommunicationReportView.captureCommunicationReportPngDataUrl(report, options);
    const payload = {
      schema_version: 'comunicacion_final_result.v1',
      activity_type: 'comunicacion',
      title: report.header && report.header.report_title ? report.header.report_title : 'Evaluación de tu comunicación oral',
      activityid: state.session.public_slug || 'comunicacion',
      session_id: state.session.session_id || null,
      user_id: state.session.user_id || null,
      attempt_id: state.attempt.attempt_id || report.attempt_id || null,
      recording_id: report.recording_id || (report.media && report.media.recording_id) || null,
      evaluation_id: report.evaluation_id || state.evaluation.evaluation_id || null,
      context_id: state.session.context_id || null,
      public_slug: state.session.public_slug || 'comunicacion',
      summary_html: summaryHtml,
      snapshot_png_dataurl: snapshot,
      payloadjson: report.exports && report.exports.report_json ? report.exports.report_json : report,
      video_ref: report.media && report.media.video_ref ? report.media.video_ref : null,
      poster_frame_ref: report.media && report.media.poster_frame_ref ? report.media.poster_frame_ref : null,
      duration_ms: report.media && report.media.duration_ms ? report.media.duration_ms : null,
      created_at: new Date().toISOString(),
      media: {
        video_ref: report.media && report.media.video_ref ? report.media.video_ref : null,
        poster_frame_ref: report.media && report.media.poster_frame_ref ? report.media.poster_frame_ref : null,
        duration_ms: report.media && report.media.duration_ms ? report.media.duration_ms : null,
        mime_type: report.media && report.media.mime_type ? report.media.mime_type : null,
      },
    };
    payload.payload_hash = deriveCommunicationFinalPayloadHash(payload);
    return payload;
  }

  function buildCommunicationFinalAvailabilityPayload(report, payload) {
    const header = report && report.header ? report.header : {};
    return {
      evaluation_id: payload.evaluation_id || null,
      activity_type: payload.activity_type || 'comunicacion',
      title: payload.title || null,
      available_exports: ['html', 'json', 'png'],
      score_global_100: header.score_global_100 || null,
      stars_0_5: header.stars_0_5 || null,
      recording_id: payload.recording_id || null,
    };
  }

  async function emitCommunicationFinalResultLifecycle(report, options = {}) {
    const payload = await buildCommunicationFinalResultPayload(report, options);
    state.final_delivery.last_payload = payload;
    if (!detectEmbedMode() || !isEmbeddedRuntime()) {
      state.final_delivery.status = 'ready';
      state.final_delivery.last_error = 'embed_runtime_not_detected';
      if (typeof showFinalSaveToast === 'function') {
        showFinalSaveToast('Resultado final listo');
      }
      renderApp();
      return payload;
    }
    const parentOrigin = readEmbedOriginFromUrl();
    if (!parentOrigin) {
      state.final_delivery.status = 'error';
      state.final_delivery.last_error = 'embed_parent_origin_missing';
      renderApp();
      return payload;
    }
    const availabilityEnvelope = buildCommunicationEmbedEnvelope('final_result_available', buildCommunicationFinalAvailabilityPayload(report, payload));
    window.parent.postMessage(availabilityEnvelope, parentOrigin);
    const envelope = buildCommunicationEmbedEnvelope('final_result', payload, { correlationId: buildCommunicationFinalCorrelationId(payload) });
    state.final_delivery.status = 'sending';
    state.final_delivery.last_error = null;
    registerPendingCommunicationFinalAck(payload, envelope);
    window.parent.postMessage(envelope, parentOrigin);
    renderApp();
    return payload;
  }

  function resolveCommunicationViewMode() {
    if (state.ui.screen === SCREEN_PROCESSING) return 'loading';
    if (state.ui.screen === SCREEN_REPORT) return 'report';
    if (state.ui.screen === SCREEN_ERROR) return 'error';
    return 'app';
  }

  function showCommunicationView(mode) {
    const appRoot = $('communicationMainApp');
    const loadingRoot = $('communicationLoadingScreen');
    const reportRoot = $('communicationReportScreen');
    const errorRoot = $('communicationErrorScreen');
    if (!appRoot || !loadingRoot || !reportRoot || !errorRoot) return;
    appRoot.classList.toggle('hidden', mode !== 'app');
    loadingRoot.classList.toggle('hidden', mode !== 'loading');
    reportRoot.classList.toggle('hidden', mode !== 'report');
    errorRoot.classList.toggle('hidden', mode !== 'error');
    if (mode === 'loading') startFloatingPhrases();
    else stopFloatingPhrases();
  }

  function installCommunicationEmbedMessageListener() {
    window.addEventListener('message', (event) => {
      try {
        handleCommunicationEmbeddedSaveAck(event.data, { origin: event.origin });
      } catch (error) {
        state.final_delivery.status = 'error';
        state.final_delivery.last_error = String(error.message || error);
        renderApp();
      }
    });
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const text = await response.text();
    let payload = null;
    if (text) {
      try { payload = JSON.parse(text); } catch (_err) { payload = text; }
    }
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : payload;
      const message = typeof detail === 'string' ? detail : detail && detail.error ? detail.error : response.statusText;
      throw new Error(message || `http_${response.status}`);
    }
    return payload;
  }

  async function bootstrapCommunicationSession() {
    const out = await api('/api/comunicacion/sessions/bootstrap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ public_slug: readCommunicationSlugFromUrl() }),
    });
    state.session.user_id = out.user_id;
    state.session.session_id = out.session_id;
    state.session.context_id = out.context_id;
    state.session.public_slug = out.public_slug;
    state.session.bootstrap_state = out.session_bootstrap_state;
    state.context.presentation_config = out.presentation_config;
    state.context.activity_brief = out.activity_brief;
    state.context.capture_policy = out.capture_policy;
    state.attempt.attempt_id = out.last_attempt_id;
    state.evaluation.evaluation_id = out.last_evaluation_id;
    state.ui.notice_message = `Sesión ${out.session_bootstrap_state === 'new' ? 'creada' : 'rehidratada'} para ${out.public_slug}.`;
    state.final_delivery.status = 'idle';
    renderApp();
    return out;
  }

  async function requestCapturePermissions() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('getUserMedia no soportado en este navegador');
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    state.capture.permission_camera = 'granted';
    state.capture.permission_mic = 'granted';
    return stream;
  }

  async function listCaptureDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
      state.capture.available_video_devices = []; state.capture.available_audio_devices = []; return;
    }
    const devices = await navigator.mediaDevices.enumerateDevices();
    state.capture.available_video_devices = devices.filter((device) => device.kind === 'videoinput');
    state.capture.available_audio_devices = devices.filter((device) => device.kind === 'audioinput');
    if (!state.capture.selected_video_device_id && state.capture.available_video_devices[0]) state.capture.selected_video_device_id = state.capture.available_video_devices[0].deviceId;
    if (!state.capture.selected_audio_device_id && state.capture.available_audio_devices[0]) state.capture.selected_audio_device_id = state.capture.available_audio_devices[0].deviceId;
    renderApp();
  }

  async function openPreviewStream({ videoDeviceId, audioDeviceId } = {}) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('getUserMedia no soportado en este navegador');
    stopPreviewStream();
    const stream = await navigator.mediaDevices.getUserMedia({
      video: videoDeviceId ? { deviceId: { exact: videoDeviceId } } : true,
      audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true,
    });
    state.capture.media_stream = stream;
    state.capture.stream_active = true;
    state.capture.selected_video_device_id = videoDeviceId || state.capture.selected_video_device_id;
    state.capture.selected_audio_device_id = audioDeviceId || state.capture.selected_audio_device_id;
    startAudioMonitoring(stream);
    startAvStatusLoop();
    renderApp();
    syncVideoElements();
    refreshCaptureHealthIndicators();
    return stream;
  }

  function stopPreviewStream() {
    if (state.capture.media_stream) state.capture.media_stream.getTracks().forEach((track) => track.stop());
    state.capture.media_stream = null;
    state.capture.stream_active = false;
    stopAudioMonitoring();
    stopAvStatusLoop();
    syncVideoElements();
  }

  function getTrackHealth(track) {
    if (!track) return 'missing';
    if (track.readyState === 'live' && track.enabled) return 'ok';
    return 'ko';
  }

  function refreshCaptureHealthIndicators() {
    const stream = state.capture.media_stream;
    const audioTrack = stream ? stream.getAudioTracks()[0] : null;
    const videoTrack = stream ? stream.getVideoTracks()[0] : null;
    const micBadge = $('recordingMicBadge');
    const camBadge = $('recordingCamBadge');
    if (micBadge) {
      const micHealth = getTrackHealth(audioTrack);
      micBadge.className = `recording-av-item status-badge--${micHealth}`;
      const micText = micBadge.querySelector('span:last-child');
      if (micText) micText.textContent = micHealth === 'ok' ? 'Micrófono · OK' : 'Micrófono · Sin señal';
    }
    if (camBadge) {
      const camHealth = getTrackHealth(videoTrack);
      camBadge.className = `recording-av-item status-badge--${camHealth}`;
      const camText = camBadge.querySelector('span:last-child');
      if (camText) camText.textContent = camHealth === 'ok' ? 'Cámara · OK' : 'Cámara · Sin señal';
    }
  }

  function ensureWaveformBars() {
    const node = $('recordingWaveform');
    if (!node || node.dataset.hydrated === 'true') return;
    node.innerHTML = new Array(WAVEFORM_BAR_COUNT).fill(0).map(() => '<span class="recording-waveform__bar"></span>').join('');
    node.dataset.hydrated = 'true';
  }

  function renderWaveform(levelRatio) {
    ensureWaveformBars();
    const node = $('recordingWaveform');
    if (!node) return;
    const bars = node.querySelectorAll('.recording-waveform__bar');
    const clamped = Math.max(0, Math.min(1, levelRatio || 0));
    const activeBars = Math.max(1, Math.round(clamped * WAVEFORM_BAR_COUNT));
    bars.forEach((bar, index) => {
      const shouldGlow = index < activeBars;
      bar.style.setProperty('--bar-scale', shouldGlow ? `${0.35 + (index / WAVEFORM_BAR_COUNT) * 0.65}` : '0.16');
      bar.classList.toggle('active', shouldGlow);
    });
  }

  function startAvStatusLoop() {
    stopAvStatusLoop();
    state.capture.av_status_timer_id = global.setInterval(() => {
      refreshCaptureHealthIndicators();
    }, 300);
  }

  function stopAvStatusLoop() {
    if (state.capture.av_status_timer_id) {
      global.clearInterval(state.capture.av_status_timer_id);
      state.capture.av_status_timer_id = null;
    }
  }

  function startAudioMonitoring(stream) {
    stopAudioMonitoring();
    if (!stream) return;
    try {
      const AudioCtx = global.AudioContext || global.webkitAudioContext;
      if (!AudioCtx) return;
      const audioTrack = stream.getAudioTracks()[0];
      if (!audioTrack) return;
      const context = new AudioCtx();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.75;
      const source = context.createMediaStreamSource(stream);
      source.connect(analyser);
      state.capture.audio_context = context;
      state.capture.audio_analyser = analyser;
      state.capture.audio_source_node = source;
      state.capture.audio_data_array = new Uint8Array(analyser.fftSize);

      const loop = () => {
        if (!state.capture.audio_analyser || !state.capture.audio_data_array) return;
        state.capture.audio_analyser.getByteTimeDomainData(state.capture.audio_data_array);
        let sumSquares = 0;
        for (let i = 0; i < state.capture.audio_data_array.length; i += 1) {
          const centered = (state.capture.audio_data_array[i] - 128) / 128;
          sumSquares += centered * centered;
        }
        const rms = Math.sqrt(sumSquares / state.capture.audio_data_array.length);
        state.capture.audio_level_ratio = Math.min(1, rms * 3.2);
        renderWaveform(state.capture.audio_level_ratio);
        state.capture.audio_raf_id = global.requestAnimationFrame(loop);
      };
      loop();
    } catch (_error) {
      // noop: monitor visual es best-effort
    }
  }

  function stopAudioMonitoring() {
    if (state.capture.audio_raf_id) {
      global.cancelAnimationFrame(state.capture.audio_raf_id);
      state.capture.audio_raf_id = null;
    }
    state.capture.audio_level_ratio = 0;
    renderWaveform(0);
    if (state.capture.audio_source_node && typeof state.capture.audio_source_node.disconnect === 'function') {
      state.capture.audio_source_node.disconnect();
    }
    if (state.capture.audio_analyser && typeof state.capture.audio_analyser.disconnect === 'function') {
      state.capture.audio_analyser.disconnect();
    }
    if (state.capture.audio_context && typeof state.capture.audio_context.close === 'function') {
      state.capture.audio_context.close().catch(() => {});
    }
    state.capture.audio_context = null;
    state.capture.audio_analyser = null;
    state.capture.audio_source_node = null;
    state.capture.audio_data_array = null;
  }

  async function createAttempt() {
    if (state.attempt.attempt_id) return state.attempt.attempt_id;
    const out = await api('/api/comunicacion/attempts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: state.session.user_id, session_id: state.session.session_id }),
    });
    state.attempt.attempt_id = out.attempt_id;
    state.attempt.status = out.status;
    return out.attempt_id;
  }

  function resolveRecorderMimeType() {
    if (!global.MediaRecorder) return null;
    const preferred = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'];
    for (const mimeType of preferred) {
      if (!global.MediaRecorder.isTypeSupported || global.MediaRecorder.isTypeSupported(mimeType)) return mimeType;
    }
    return '';
  }

  async function startRecording() {
    if (!global.MediaRecorder) throw new Error('MediaRecorder no soportado en este navegador');
    clearError();
    if (!state.capture.media_stream) {
      await openPreviewStream({ videoDeviceId: state.capture.selected_video_device_id, audioDeviceId: state.capture.selected_audio_device_id });
    }
    resetRecordedBlobState();
    const mimeType = resolveRecorderMimeType();
    const chunks = [];
    const recorder = new MediaRecorder(state.capture.media_stream, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (event) => { if (event.data && event.data.size > 0) chunks.push(event.data); };
    recorder.onerror = () => setError('Error durante la grabación local.');
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || 'video/webm' });
      state.capture.recorded_blob = blob;
      state.capture.blob_size_bytes = blob.size;
      state.capture.mime_type = blob.type || 'video/webm';
      state.capture.blob_url = URL.createObjectURL(blob);
      const startedAt = state.capture.record_started_at_ms || Date.now();
      state.capture.duration_ms = Math.max(1, Date.now() - startedAt);
      state.capture.is_recording = false;
      stopRecordingTimer();
      state.capture.elapsed_label = formatDurationLabel(state.capture.duration_ms);
      transitionTo(SCREEN_REVIEW);
      syncVideoElements();
    };
    state.capture.media_recorder = recorder;
    state.capture.record_started_at_ms = Date.now();
    state.capture.is_recording = true;
    state.capture.mime_type = recorder.mimeType || mimeType || 'video/webm';
    startRecordingTimer();
    recorder.start(250);
    transitionTo(SCREEN_RECORDING);
  }

  async function stopRecording() {
    if (!state.capture.media_recorder || !state.capture.is_recording) throw new Error('No hay grabación en curso');
    state.capture.media_recorder.stop();
  }

  function resetRecordingReview() {
    stopRecordingTimer();
    resetRecordedBlobState();
    stopEvaluationPolling();
    state.upload.recording_id = null;
    state.upload.video_ref = null;
    state.upload.poster_frame_ref = null;
    state.evaluation.evaluation_id = null;
    state.evaluation.status = 'idle';
    state.evaluation.stage = null;
    state.evaluation.report_available = false;
    state.report.payload = null;
    state.report.placeholder_ready = false;
    state.capture.av_panel_open = false;
    state.attempt.attempt_id = null;
    state.attempt.status = null;
    state.attempt.rerecord_count += 1;
    setNotice('Grabación reiniciada. Puedes volver a grabar antes de registrar metadata.');
    transitionTo(SCREEN_RECORDING);
  }

  function deriveTemporaryVideoRef() {
    const attemptId = state.attempt.attempt_id || 'attempt_pending';
    const extension = state.capture.mime_type && state.capture.mime_type.includes('mp4') ? 'mp4' : 'webm';
    return `client-temp://${state.session.session_id}/${attemptId}/${Date.now()}.${extension}`;
  }

  async function registerRecordingMetadata() {
    if (!state.capture.recorded_blob || !state.capture.blob_url) throw new Error('No hay una grabación local lista para registrar');
    setBusy(true);
    try {
      await createAttempt();
      let out = null;
      try {
        const form = new FormData();
        form.append('user_id', state.session.user_id || '');
        form.append('session_id', state.session.session_id || '');
        form.append('mime_type', state.capture.mime_type || 'video/webm');
        form.append('duration_ms', String(state.capture.duration_ms || 1));
        form.append('poster_frame_ref', '');
        form.append('capture_meta', JSON.stringify({
          blob_size_bytes: state.capture.blob_size_bytes,
          provisional_client_ref: false,
          client_transport: 'multipart_form_data',
        }));
        form.append('video_file', state.capture.recorded_blob, `capture-${Date.now()}.webm`);
        out = await api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/upload`, {
          method: 'POST',
          body: form,
        });
      } catch (uploadError) {
        out = await api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: state.session.user_id,
            session_id: state.session.session_id,
            mime_type: state.capture.mime_type || 'video/webm',
            duration_ms: state.capture.duration_ms || 1,
            video_ref: deriveTemporaryVideoRef(),
            poster_frame_ref: null,
            capture_meta: {
              blob_size_bytes: state.capture.blob_size_bytes,
              provisional_client_ref: true,
              upload_binary_failed: true,
              upload_binary_error: uploadError && uploadError.message ? uploadError.message : 'unknown_upload_error',
            },
          }),
        });
      }
      state.upload.recording_id = out.recording_id;
      state.upload.video_ref = out.video_ref;
      state.upload.poster_frame_ref = out.poster_frame_ref;
      state.attempt.status = out.status;
      setNotice('Grabación registrada. Ya puedes enviarla a evaluación mínima.');
      transitionTo(SCREEN_REVIEW);
    } finally {
      setBusy(false);
    }
  }

  async function submitCommunicationAttempt() {
    if (!state.attempt.attempt_id) throw new Error('No hay attempt listo para submit');
    setBusy(true);
    transitionTo(SCREEN_PROCESSING);
    try {
      const out = await api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.session.user_id, session_id: state.session.session_id }),
      });
      state.evaluation.evaluation_id = out.evaluation_id;
      state.evaluation.status = out.status;
      state.evaluation.stage = 'queued';
      state.report.payload = null;
      state.report.placeholder_ready = false;
      setNotice('Evaluación enviada. Estamos procesando el report placeholder.');
      await pollEvaluationUntilReportReady();
    } finally {
      setBusy(false);
    }
  }

  async function sendAndEvaluate() {
    if (!state.capture.recorded_blob) throw new Error('No hay grabación lista para enviar');
    if (!state.upload.recording_id) {
      await registerRecordingMetadata();
    }
    await submitCommunicationAttempt();
  }

  async function fetchEvaluationStatus() {
    if (!state.evaluation.evaluation_id) throw new Error('No existe evaluation_id para consultar');
    const params = new URLSearchParams({
      user_id: state.session.user_id || '',
      session_id: state.session.session_id || '',
    });
    const out = await api(`/api/comunicacion/evaluations/${state.evaluation.evaluation_id}?${params.toString()}`);
    state.evaluation.status = out.status;
    state.evaluation.stage = out.stage;
    state.evaluation.report_available = Boolean(out.report_available);
    state.attempt.status = out.status === 'completed' ? 'completed' : state.attempt.status;
    renderApp();
    return out;
  }

  async function fetchEvaluationReport() {
    if (!state.evaluation.evaluation_id) throw new Error('No existe evaluation_id para leer report');
    const params = new URLSearchParams({
      user_id: state.session.user_id || '',
      session_id: state.session.session_id || '',
    });
    const out = await api(`/api/comunicacion/evaluations/${state.evaluation.evaluation_id}/report?${params.toString()}`);
    state.report.payload = out;
    state.report.placeholder_ready = true;
    transitionTo(SCREEN_REPORT);
    try {
      await emitCommunicationFinalResultLifecycle(out, { rootElement: $('reportPlaceholderRoot') });
    } catch (error) {
      state.final_delivery.status = 'error';
      state.final_delivery.last_error = error.message;
    }
    renderApp();
    return out;
  }

  function stopEvaluationPolling() {
    if (state.evaluation.poll_timer_id) {
      global.clearTimeout(state.evaluation.poll_timer_id);
      state.evaluation.poll_timer_id = null;
    }
  }

  async function pollEvaluationUntilReportReady() {
    stopEvaluationPolling();
    const step = async () => {
      const status = await fetchEvaluationStatus();
      if (status.status === 'failed') throw new Error(status.error || 'evaluation_failed');
      if (status.report_available && status.status === 'completed') {
        await fetchEvaluationReport();
        stopEvaluationPolling();
        return;
      }
      state.evaluation.poll_timer_id = global.setTimeout(async () => {
        try { await step(); } catch (error) { setError(`No se pudo completar el polling: ${error.message}`); }
      }, 150);
    };
    await step();
  }

  function stopFloatingPhrases() {
    floatingPhrasesActive = false;
    if (floatingPhraseTimer) {
      global.clearTimeout(floatingPhraseTimer);
      floatingPhraseTimer = null;
    }
    const layer = $('feedbackFloatingLayer');
    if (layer) layer.innerHTML = '';
  }

  function spawnFloatingPhrase() {
    const layer = $('feedbackFloatingLayer');
    if (!layer || state.ui.screen !== SCREEN_PROCESSING) return;
    const phrase = FloatingPhrases[Math.floor(Math.random() * FloatingPhrases.length)];
    const line = document.createElement('span');
    line.className = 'feedback-floating-line';
    line.textContent = phrase;
    line.style.left = `${8 + Math.random() * 72}%`;
    line.style.top = `${10 + Math.random() * 70}%`;
    line.style.setProperty('--line-duration', `${7600 + Math.random() * 2200}ms`);
    layer.appendChild(line);
    global.setTimeout(() => line.remove(), 9800);
  }

  function startFloatingPhrases() {
    if (floatingPhrasesActive) return;
    floatingPhrasesActive = true;
    stopFloatingPhrases();
    floatingPhrasesActive = true;
    for (let i = 0; i < 4; i += 1) spawnFloatingPhrase();
    const loop = () => {
      if (state.ui.screen !== SCREEN_PROCESSING) return;
      spawnFloatingPhrase();
      floatingPhraseTimer = global.setTimeout(loop, 900 + Math.random() * 1200);
    };
    floatingPhraseTimer = global.setTimeout(loop, 800);
  }

  function renderApp() {
    showCommunicationView(resolveCommunicationViewMode());
    const errorBanner = $('communicationErrorBanner');
    if (state.ui.error_message) { errorBanner.textContent = state.ui.error_message; errorBanner.classList.remove('hidden'); }
    else { errorBanner.classList.add('hidden'); }

    for (const screen of SCREEN_ORDER) {
      const node = document.querySelector(`[data-screen="${screen}"]`);
      if (!node) continue;
      node.classList.toggle('hidden', state.ui.screen !== screen);
    }

    $('reviewDuration').textContent = state.capture.duration_ms ? formatDurationLabel(state.capture.duration_ms) : '-';
    $('reviewBlobSize').textContent = state.capture.blob_size_bytes ? formatBytes(state.capture.blob_size_bytes) : '-';
    $('recordingIndicator').textContent = `● ${state.capture.elapsed_label}`;
    $('recordingAidaAttention').textContent = state.brainmap.attention || 'Sin contenido todavía.';
    $('recordingAidaInterest').textContent = state.brainmap.interest || 'Sin contenido todavía.';
    $('recordingAidaDevelopment').textContent = state.brainmap.development || 'Sin contenido todavía.';
    $('recordingAidaAction').textContent = state.brainmap.action || 'Sin contenido todavía.';
    const avPanel = $('avDevicePanel');
    if (avPanel) avPanel.classList.toggle('hidden', !state.capture.av_panel_open);
    const manageAvBtn = $('manageAvBtn');
    if (manageAvBtn) manageAvBtn.setAttribute('aria-expanded', state.capture.av_panel_open ? 'true' : 'false');
    const uploadStatusNode = $('uploadStatusText');
    if (uploadStatusNode) {
      uploadStatusNode.textContent = state.ui.busy
        ? 'Estamos creando el attempt y enviando la referencia provisional de la grabación.'
        : 'El registro de metadata ha finalizado o está pendiente de reintento.';
    }
    const processingNode = $('processingStatusText');
    if (processingNode) processingNode.textContent = ProcessingStageLabel[state.evaluation.stage || state.evaluation.status] || 'Analizando la comunicación...';
    const errorMessageNode = $('communicationErrorMessage');
    if (errorMessageNode && state.ui.error_message) errorMessageNode.textContent = state.ui.error_message;

    const reportRoot = $('reportPlaceholderRoot');
    if (state.report.payload) {
      global.CommunicationReportView.renderCommunicationReport(reportRoot, state.report.payload);
    } else {
      global.CommunicationReportView.renderCommunicationReportPlaceholder(reportRoot, {
        title: 'Report placeholder',
        summary: 'La Fase 5 necesita un report cargado para renderizar el informe final.',
      });
    }

    syncDeviceSelects();
    renderDevicePanelOptions();
    syncBrainmapInputs();
    renderSetupEntryState();
    syncVideoElements();
    refreshCaptureHealthIndicators();
    ensureWaveformBars();
    syncRecordingActionVisibility();
    syncButtons();
  }

  function renderSetupEntryState() {
    const setupStatus = $('setupStatusText');
    const setupPrimaryBtn = $('setupPrimaryBtn');
    if (!setupStatus || !setupPrimaryBtn) return;
    if (state.capture.permission_camera === 'denied' || state.capture.permission_mic === 'denied') {
      setupStatus.textContent = 'Permiso denegado. Activa cámara y micrófono en el navegador para continuar.';
    } else if (!state.capture.stream_active) {
      setupStatus.textContent = 'Necesitamos activar cámara y micrófono para continuar.';
    } else {
      setupStatus.textContent = 'Cámara y micrófono listos. Ya puedes empezar.';
    }
    setupPrimaryBtn.textContent = isSetupReady() ? 'Empezar' : 'Activar cámara y micrófono';
  }

  function syncRecordingActionVisibility() {
    const startBtn = $('startRecordingBtn');
    const stopBtn = $('stopRecordingBtn');
    if (startBtn) startBtn.classList.toggle('hidden', state.capture.is_recording);
    if (stopBtn) stopBtn.classList.toggle('hidden', !state.capture.is_recording);
  }

  function syncBrainmapInputs() {
    const map = {
      brainmapAttention: 'attention',
      brainmapInterest: 'interest',
      brainmapDevelopment: 'development',
      brainmapAction: 'action',
    };
    Object.entries(map).forEach(([id, key]) => {
      const node = $(id);
      if (!node) return;
      const nextValue = state.brainmap[key] || '';
      if (node.value !== nextValue) node.value = nextValue;
    });
  }

  function syncDeviceSelects() {
    const videoSelect = $('videoDeviceSelect');
    const audioSelect = $('audioDeviceSelect');
    hydrateDeviceSelect(videoSelect, state.capture.available_video_devices, state.capture.selected_video_device_id, 'Sin cámaras detectadas');
    hydrateDeviceSelect(audioSelect, state.capture.available_audio_devices, state.capture.selected_audio_device_id, 'Sin micrófonos detectados');
  }

  function hydrateDeviceSelect(select, devices, selectedId, emptyLabel) {
    if (!select) return;
    const entries = devices.length > 0 ? devices.map((device, index) => ({ value: device.deviceId, label: device.label || `Dispositivo ${index + 1}` })) : [{ value: '', label: emptyLabel }];
    const signature = JSON.stringify(entries.map((entry) => `${entry.value}:${entry.label}`));
    if (select.dataset.signature !== signature) {
      select.innerHTML = entries.map((entry) => `<option value="${escapeHtml(entry.value)}">${escapeHtml(entry.label)}</option>`).join('');
      select.dataset.signature = signature;
    }
    const nextValue = selectedId || entries[0].value;
    if (select.value !== nextValue) select.value = nextValue;
  }

  function buildDeviceOptionsMarkup(devices, selectedId, kind) {
    if (!devices.length) return '<div class="av-device-empty">No hay dispositivos disponibles.</div>';
    return devices.map((device, index) => {
      const label = device.label || `${kind === 'video' ? 'Cámara' : 'Micrófono'} ${index + 1}`;
      const isActive = selectedId === device.deviceId;
      return `<button class="av-device-option${isActive ? ' active' : ''}" type="button" data-device-kind="${kind}" data-device-id="${escapeHtml(device.deviceId)}"><span>${escapeHtml(label)}</span><span class="av-device-option__check">${isActive ? '✓' : ''}</span></button>`;
    }).join('');
  }

  function renderDevicePanelOptions() {
    const videoList = $('recordingVideoDeviceList');
    const audioList = $('recordingAudioDeviceList');
    if (videoList) {
      const signature = JSON.stringify([state.capture.selected_video_device_id, ...state.capture.available_video_devices.map((d) => `${d.deviceId}:${d.label || ''}`)]);
      if (videoList.dataset.signature !== signature) {
        videoList.innerHTML = buildDeviceOptionsMarkup(state.capture.available_video_devices, state.capture.selected_video_device_id, 'video');
        videoList.dataset.signature = signature;
      }
    }
    if (audioList) {
      const signature = JSON.stringify([state.capture.selected_audio_device_id, ...state.capture.available_audio_devices.map((d) => `${d.deviceId}:${d.label || ''}`)]);
      if (audioList.dataset.signature !== signature) {
        audioList.innerHTML = buildDeviceOptionsMarkup(state.capture.available_audio_devices, state.capture.selected_audio_device_id, 'audio');
        audioList.dataset.signature = signature;
      }
    }
  }

  function syncVideoElements() {
    const previewVideo = $('setupPreviewVideo');
    const recordingVideo = $('recordingVideo');
    const reviewVideo = $('reviewVideo');
    if (previewVideo && previewVideo.srcObject !== (state.capture.media_stream || null)) previewVideo.srcObject = state.capture.media_stream || null;
    if (recordingVideo && recordingVideo.srcObject !== (state.capture.media_stream || null)) recordingVideo.srcObject = state.capture.media_stream || null;
    if (reviewVideo) {
      if (reviewVideo.srcObject !== null) reviewVideo.srcObject = null;
      const nextUrl = state.capture.blob_url || '';
      if ((reviewVideo.getAttribute('src') || '') !== nextUrl) reviewVideo.src = nextUrl;
    }
  }

  function syncButtons() {
    const busy = state.ui.busy;
    toggleDisabled('setupPrimaryBtn', busy);
    toggleDisabled('refreshDevicesBtn', busy);
    toggleDisabled('startRecordingBtn', busy || !state.capture.stream_active || state.capture.is_recording);
    toggleDisabled('stopRecordingBtn', busy || !state.capture.is_recording);
    toggleDisabled('backToAidaBtn', busy || state.capture.is_recording);
    toggleDisabled('manageAvBtn', busy);
    toggleDisabled('closeAvPanelBtn', busy);
    toggleDisabled('backToSetupBtn', busy);
    toggleDisabled('continueToRecordingBtn', busy || !isSetupReady());
    toggleDisabled('rerecordBtn', busy);
    toggleDisabled('sendAndEvaluateBtn', busy || !state.capture.recorded_blob);
  }

  function toggleDisabled(id, value) { const node = $(id); if (node) node.disabled = Boolean(value); }

  function downloadTextFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    triggerDownload(url, filename);
    global.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function triggerDownload(url, filename) {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  async function exportReportJson() {
    if (!state.report.payload) throw new Error('No hay report para exportar');
    downloadTextFile(`communication-report-${state.evaluation.evaluation_id || 'latest'}.json`, JSON.stringify(state.report.payload, null, 2), 'application/json');
  }

  async function exportReportHtml() {
    if (!state.report.payload) throw new Error('No hay report para exportar');
    const html = global.CommunicationReportView.serializeCommunicationReportToHtml(state.report.payload);
    downloadTextFile(`communication-report-${state.evaluation.evaluation_id || 'latest'}.html`, html, 'text/html');
  }

  async function exportReportPng() {
    if (!state.report.payload) throw new Error('No hay report para exportar');
    const dataUrl = await global.CommunicationReportView.captureCommunicationReportPngDataUrl(state.report.payload);
    triggerDownload(dataUrl, `communication-report-${state.evaluation.evaluation_id || 'latest'}.png`);
  }

  function startRecordingTimer() {
    stopRecordingTimer();
    state.capture.elapsed_label = '00:00';
    const indicator = $('recordingIndicator');
    state.capture.record_timer_id = global.setInterval(() => {
      const elapsed = Date.now() - (state.capture.record_started_at_ms || Date.now());
      state.capture.duration_ms = elapsed;
      state.capture.elapsed_label = formatDurationLabel(elapsed);
      if (indicator) indicator.textContent = `● ${state.capture.elapsed_label}`;
    }, 250);
  }

  function stopRecordingTimer() {
    if (state.capture.record_timer_id) { global.clearInterval(state.capture.record_timer_id); state.capture.record_timer_id = null; }
  }

  function resetRecordedBlobState() {
    if (state.capture.blob_url) URL.revokeObjectURL(state.capture.blob_url);
    state.capture.recorded_blob = null;
    state.capture.blob_url = null;
    state.capture.duration_ms = 0;
    state.capture.blob_size_bytes = 0;
    state.capture.elapsed_label = '00:00';
  }

  async function handleDeviceChange(kind, deviceId) {
    if (!deviceId) return;
    if (state.capture.is_recording) {
      setNotice('Para cambiar dispositivo de forma segura, detén la grabación actual.');
      return;
    }
    if (kind === 'video') state.capture.selected_video_device_id = deviceId;
    if (kind === 'audio') state.capture.selected_audio_device_id = deviceId;
    const videoSelect = $('videoDeviceSelect');
    const audioSelect = $('audioDeviceSelect');
    if (videoSelect && kind === 'video') videoSelect.value = deviceId;
    if (audioSelect && kind === 'audio') audioSelect.value = deviceId;
    if (!state.capture.stream_active) {
      renderDevicePanelOptions();
      return;
    }
    try {
      setBusy(true);
      await openPreviewStream({
        videoDeviceId: state.capture.selected_video_device_id,
        audioDeviceId: state.capture.selected_audio_device_id,
      });
      renderDevicePanelOptions();
    } catch (error) {
      setError(`No se pudo cambiar el dispositivo: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  function installEventHandlers() {
    $('setupPrimaryBtn').addEventListener('click', async () => {
      clearError();
      if (isSetupReady()) {
        transitionTo(SCREEN_AIDA_PREP);
        return;
      }
      setBusy(true);
      try {
        const stream = await requestCapturePermissions();
        stopPreviewStream();
        state.capture.media_stream = stream;
        state.capture.stream_active = true;
        await listCaptureDevices();
        await openPreviewStream({
          videoDeviceId: $('videoDeviceSelect').value || state.capture.selected_video_device_id || null,
          audioDeviceId: $('audioDeviceSelect').value || state.capture.selected_audio_device_id || null,
        });
      } catch (error) {
        state.capture.permission_camera = 'denied';
        state.capture.permission_mic = 'denied';
        setError(`No se pudieron conceder permisos: ${error.message}`);
      } finally {
        setBusy(false);
      }
    });
    $('backToSetupBtn').addEventListener('click', () => transitionTo(SCREEN_SETUP));
    $('continueToRecordingBtn').addEventListener('click', async () => {
      clearError();
      setBusy(true);
      try {
        if (!state.capture.stream_active) {
          await openPreviewStream({
            videoDeviceId: state.capture.selected_video_device_id,
            audioDeviceId: state.capture.selected_audio_device_id,
          });
        }
        transitionTo(SCREEN_RECORDING);
      } catch (error) {
        setError(`No se pudo preparar la grabación: ${error.message}`);
      } finally {
        setBusy(false);
      }
    });
    $('refreshDevicesBtn').addEventListener('click', async () => { setBusy(true); try { await listCaptureDevices(); await openPreviewStream({ videoDeviceId: $('videoDeviceSelect').value || null, audioDeviceId: $('audioDeviceSelect').value || null }); } catch (error) { setError(`No se pudieron refrescar los dispositivos: ${error.message}`); } finally { setBusy(false); } });
    $('videoDeviceSelect').addEventListener('change', async (event) => { await handleDeviceChange('video', event.target.value || null); });
    $('audioDeviceSelect').addEventListener('change', async (event) => { await handleDeviceChange('audio', event.target.value || null); });
    ['brainmapAttention', 'brainmapInterest', 'brainmapDevelopment', 'brainmapAction'].forEach((id) => {
      const map = {
        brainmapAttention: 'attention',
        brainmapInterest: 'interest',
        brainmapDevelopment: 'development',
        brainmapAction: 'action',
      };
      $(id).addEventListener('input', (event) => {
        state.brainmap[map[id]] = event.target.value || '';
        state.brainmap.updated_at = new Date().toISOString();
      });
    });
    $('backToAidaBtn').addEventListener('click', () => { if (!state.capture.is_recording) transitionTo(SCREEN_AIDA_PREP); });
    $('manageAvBtn').addEventListener('click', () => {
      state.capture.av_panel_open = !state.capture.av_panel_open;
      renderApp();
    });
    $('closeAvPanelBtn').addEventListener('click', () => {
      state.capture.av_panel_open = false;
      renderApp();
    });
    $('recordingVideoDeviceList').addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-device-kind="video"]');
      if (!button) return;
      await handleDeviceChange('video', button.dataset.deviceId || '');
    });
    $('recordingAudioDeviceList').addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-device-kind="audio"]');
      if (!button) return;
      await handleDeviceChange('audio', button.dataset.deviceId || '');
    });
    $('startRecordingBtn').addEventListener('click', async () => { setBusy(true); try { await startRecording(); } catch (error) { setError(`No se pudo iniciar la grabación: ${error.message}`); } finally { setBusy(false); } });
    $('stopRecordingBtn').addEventListener('click', async () => { setBusy(true); try { await stopRecording(); } catch (error) { setError(`No se pudo detener la grabación: ${error.message}`); } finally { setBusy(false); } });
    $('rerecordBtn').addEventListener('click', () => { clearError(); resetRecordingReview(); });
    $('sendAndEvaluateBtn').addEventListener('click', async () => { clearError(); try { await sendAndEvaluate(); } catch (error) { setError(`No se pudo enviar la evaluación: ${error.message}`); } });
    const exportReportJsonBtn = $('exportReportJsonBtn');
    if (exportReportJsonBtn) exportReportJsonBtn.addEventListener('click', async () => {
      try { await exportReportJson(); } catch (error) { setError(`No se pudo exportar JSON: ${error.message}`); }
    });
    const exportReportHtmlBtn = $('exportReportHtmlBtn');
    if (exportReportHtmlBtn) exportReportHtmlBtn.addEventListener('click', async () => {
      try { await exportReportHtml(); } catch (error) { setError(`No se pudo exportar HTML: ${error.message}`); }
    });
    const exportReportPngBtn = $('exportReportPngBtn');
    if (exportReportPngBtn) exportReportPngBtn.addEventListener('click', async () => {
      try { await exportReportPng(); } catch (error) { setError(`No se pudo exportar PNG: ${error.message}`); }
    });
    const backToReviewBtn = $('communicationBackToReviewBtn');
    if (backToReviewBtn) backToReviewBtn.addEventListener('click', () => {
      clearError();
      transitionTo(SCREEN_REVIEW);
    });
  }

  function escapeHtml(value) { return String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'); }

  async function initialize() {
    renderApp(); installEventHandlers(); installCommunicationEmbedMessageListener();
    window.addEventListener('beforeunload', () => {
      stopAudioMonitoring();
      stopAvStatusLoop();
      stopRecordingTimer();
      stopEvaluationPolling();
      stopPreviewStream();
      stopFloatingPhrases();
    });
    try { await bootstrapCommunicationSession(); } catch (error) { setError(`No se pudo preparar la sesión: ${error.message}`); return; }
    try { await listCaptureDevices(); } catch (_error) { }
    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', async () => {
        try { await listCaptureDevices(); } catch (_error) { }
      });
    }
    renderApp();
  }

  document.addEventListener('DOMContentLoaded', initialize);

  global.CommunicationApp = {
    state,
    SCREEN_SETUP,
    SCREEN_AIDA_PREP,
    SCREEN_RECORDING,
    SCREEN_REVIEW,
    SCREEN_UPLOADING,
    SCREEN_PROCESSING,
    SCREEN_REPORT,
    SCREEN_ERROR,
    bootstrapCommunicationSession,
    requestCapturePermissions,
    listCaptureDevices,
    openPreviewStream,
    stopPreviewStream,
    createAttempt,
    startRecording,
    stopRecording,
    resetRecordingReview,
    sendAndEvaluate,
    registerRecordingMetadata,
    submitCommunicationAttempt,
    pollEvaluationUntilReportReady,
    fetchEvaluationStatus,
    fetchEvaluationReport,
    exportReportJson,
    exportReportHtml,
    exportReportPng,
    buildCommunicationEmbedEnvelope,
    buildCommunicationFinalResultPayload,
    buildCommunicationFinalAvailabilityPayload,
    buildCommunicationFinalCorrelationId,
    deriveCommunicationFinalPayloadHash,
    emitCommunicationFinalResultLifecycle,
    handleCommunicationEmbeddedSaveAck,
    registerPendingCommunicationFinalAck,
    detectEmbedMode,
    isEmbeddedRuntime,
    readCommunicationAckComparableIds,
    stableStringifyForHash,
    simpleHashString,
    transitionTo,
    renderApp,
  };
})(window);
