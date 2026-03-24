(function attachCommunicationApp(global) {
  const SCREEN_INTRO = 'intro';
  const SCREEN_PERMISSIONS = 'permissions';
  const SCREEN_PREVIEW = 'preview';
  const SCREEN_RECORDING = 'recording';
  const SCREEN_REVIEW = 'review';
  const SCREEN_UPLOADING = 'uploading';
  const SCREEN_PROCESSING = 'processing';
  const SCREEN_REPORT = 'report';
  const SCREEN_ERROR = 'error';
  const EMBED_MESSAGE_VERSION = 1;
  const EMBED_NAMESPACE = 'gestionce.simulator';

  const SCREEN_ORDER = [
    SCREEN_INTRO,
    SCREEN_PERMISSIONS,
    SCREEN_PREVIEW,
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
      screen: SCREEN_INTRO,
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

  function $(id) { return document.getElementById(id); }
  function transitionTo(screen) { state.ui.screen = screen; renderApp(); }
  function setBusy(value) { state.ui.busy = Boolean(value); renderApp(); }
  function clearError() { state.ui.error_message = null; }
  function setNotice(message) { state.ui.notice_message = message || null; renderApp(); }
  function setError(message) { state.ui.error_message = message || 'Ha ocurrido un error inesperado.'; state.ui.notice_message = null; transitionTo(SCREEN_ERROR); }

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
    renderApp();
    syncVideoElements();
    return stream;
  }

  function stopPreviewStream() {
    if (state.capture.media_stream) state.capture.media_stream.getTracks().forEach((track) => track.stop());
    state.capture.media_stream = null;
    state.capture.stream_active = false;
    syncVideoElements();
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
    state.attempt.attempt_id = null;
    state.attempt.status = null;
    state.attempt.rerecord_count += 1;
    setNotice('Grabación reiniciada. Puedes volver a grabar antes de registrar metadata.');
    transitionTo(SCREEN_PREVIEW);
  }

  function deriveTemporaryVideoRef() {
    const attemptId = state.attempt.attempt_id || 'attempt_pending';
    const extension = state.capture.mime_type && state.capture.mime_type.includes('mp4') ? 'mp4' : 'webm';
    return `client-temp://${state.session.session_id}/${attemptId}/${Date.now()}.${extension}`;
  }

  async function registerRecordingMetadata() {
    if (!state.capture.recorded_blob || !state.capture.blob_url) throw new Error('No hay una grabación local lista para registrar');
    transitionTo(SCREEN_UPLOADING);
    setBusy(true);
    try {
      await createAttempt();
      const out = await api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: state.session.user_id,
          session_id: state.session.session_id,
          mime_type: state.capture.mime_type || 'video/webm',
          duration_ms: state.capture.duration_ms || 1,
          video_ref: deriveTemporaryVideoRef(),
          poster_frame_ref: null,
          capture_meta: { blob_size_bytes: state.capture.blob_size_bytes, provisional_client_ref: true },
        }),
      });
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

  async function fetchEvaluationStatus() {
    if (!state.evaluation.evaluation_id) throw new Error('No existe evaluation_id para consultar');
    const out = await api(`/api/comunicacion/evaluations/${state.evaluation.evaluation_id}`);
    state.evaluation.status = out.status;
    state.evaluation.stage = out.stage;
    state.evaluation.report_available = Boolean(out.report_available);
    state.attempt.status = out.status === 'completed' ? 'completed' : state.attempt.status;
    renderApp();
    return out;
  }

  async function fetchEvaluationReport() {
    if (!state.evaluation.evaluation_id) throw new Error('No existe evaluation_id para leer report');
    const out = await api(`/api/comunicacion/evaluations/${state.evaluation.evaluation_id}/report`);
    state.report.payload = out;
    state.report.placeholder_ready = true;
    transitionTo(SCREEN_REPORT);
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

  function renderApp() {
    const title = state.context.activity_brief?.title || 'Presentación breve grabada';
    $('activityTitle').textContent = title;
    $('introContextSummary').textContent = state.context.activity_brief?.description || 'Vamos a preparar tu sesión y a comprobar permisos de cámara y micrófono.';

    const statusBanner = $('communicationStatusBanner');
    const errorBanner = $('communicationErrorBanner');
    if (state.ui.notice_message) { statusBanner.textContent = state.ui.notice_message; statusBanner.classList.remove('hidden'); }
    else { statusBanner.classList.add('hidden'); }
    if (state.ui.error_message) { errorBanner.textContent = state.ui.error_message; errorBanner.classList.remove('hidden'); }
    else { errorBanner.classList.add('hidden'); }

    for (const screen of SCREEN_ORDER) {
      const node = document.querySelector(`[data-screen="${screen}"]`);
      if (!node) continue;
      node.classList.toggle('hidden', state.ui.screen !== screen);
    }

    $('reviewDuration').textContent = state.capture.duration_ms ? formatDurationLabel(state.capture.duration_ms) : '-';
    $('reviewMimeType').textContent = state.capture.mime_type || '-';
    $('reviewBlobSize').textContent = state.capture.blob_size_bytes ? formatBytes(state.capture.blob_size_bytes) : '-';
    $('reviewVideoRef').textContent = state.upload.video_ref || 'Se generará al registrar metadata';
    $('recordingIndicator').textContent = `● ${state.capture.elapsed_label}`;
    $('uploadStatusText').textContent = state.ui.busy ? 'Estamos creando el attempt y enviando la referencia provisional de la grabación.' : 'El registro de metadata ha finalizado o está pendiente de reintento.';
    const processingNode = $('processingStatusText');
    if (processingNode) processingNode.textContent = state.evaluation.evaluation_id
      ? `evaluation_id=${state.evaluation.evaluation_id} · status=${state.evaluation.status} · stage=${state.evaluation.stage || 'queued'}`
      : 'Aún no has enviado la grabación a evaluación.';

    const deliveryPanel = $('finalResultStatusPanel');
    if (deliveryPanel) {
      deliveryPanel.dataset.deliveryStatus = state.final_delivery.status || 'idle';
      if (state.final_delivery.status === 'ack_received') deliveryPanel.textContent = 'Resultado final enviado y ACK recibido.';
      else if (state.final_delivery.status === 'sending') deliveryPanel.textContent = 'Envío del resultado final en curso. Esperando ACK correlacionado.';
      else if (state.final_delivery.status === 'ready') deliveryPanel.textContent = detectEmbedMode() && isEmbeddedRuntime()
        ? 'Resultado final listo para enviar al contenedor embebido.'
        : 'Resultado final listo localmente. Si se embebe, podrá emitirse como final_result.';
      else if (state.final_delivery.status === 'error') deliveryPanel.textContent = `Error de entrega final: ${state.final_delivery.last_error || 'desconocido'}`;
      else deliveryPanel.textContent = 'El resultado final se habilitará cuando el informe esté disponible.';
    }

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
    syncVideoElements();
    syncButtons();
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
    select.innerHTML = entries.map((entry) => `<option value="${escapeHtml(entry.value)}">${escapeHtml(entry.label)}</option>`).join('');
    select.value = selectedId || entries[0].value;
  }

  function syncVideoElements() {
    const previewVideo = $('previewVideo');
    const recordingVideo = $('recordingVideo');
    const reviewVideo = $('reviewVideo');
    if (previewVideo) previewVideo.srcObject = state.capture.media_stream || null;
    if (recordingVideo) recordingVideo.srcObject = state.capture.media_stream || null;
    if (reviewVideo) { reviewVideo.srcObject = null; reviewVideo.src = state.capture.blob_url || ''; }
  }

  function syncButtons() {
    const busy = state.ui.busy;
    toggleDisabled('startFlowBtn', busy);
    toggleDisabled('grantPermissionsBtn', busy);
    toggleDisabled('openPreviewBtn', busy || !state.capture.permission_camera || state.capture.permission_camera === 'denied');
    toggleDisabled('refreshDevicesBtn', busy);
    toggleDisabled('startRecordingBtn', busy || !state.capture.stream_active);
    toggleDisabled('stopRecordingBtn', busy || !state.capture.is_recording);
    toggleDisabled('rerecordBtn', busy);
    toggleDisabled('registerRecordingBtn', busy || !state.capture.recorded_blob);
    toggleDisabled('submitEvaluationBtn', busy || !state.upload.recording_id);
    toggleDisabled('exportReportJsonBtn', busy || !state.report.payload);
    toggleDisabled('exportReportHtmlBtn', busy || !state.report.payload);
    toggleDisabled('exportReportPngBtn', busy || !state.report.payload);
    toggleDisabled('emitFinalResultBtn', busy || !state.report.payload);
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
    state.capture.record_timer_id = global.setInterval(() => {
      const elapsed = Date.now() - (state.capture.record_started_at_ms || Date.now());
      state.capture.duration_ms = elapsed;
      state.capture.elapsed_label = formatDurationLabel(elapsed);
      renderApp();
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

  function installEventHandlers() {
    $('startFlowBtn').addEventListener('click', () => transitionTo(SCREEN_PERMISSIONS));
    $('grantPermissionsBtn').addEventListener('click', async () => {
      clearError(); setBusy(true);
      try {
        const stream = await requestCapturePermissions();
        stopPreviewStream(); state.capture.media_stream = stream; state.capture.stream_active = true;
        await listCaptureDevices(); setNotice('Permisos concedidos. Ya puedes abrir la preview.');
      } catch (error) {
        state.capture.permission_camera = 'denied'; state.capture.permission_mic = 'denied'; setError(`No se pudieron conceder permisos: ${error.message}`);
      } finally { setBusy(false); }
    });
    $('openPreviewBtn').addEventListener('click', async () => { clearError(); setBusy(true); try { await openPreviewStream({ videoDeviceId: $('videoDeviceSelect').value || null, audioDeviceId: $('audioDeviceSelect').value || null }); transitionTo(SCREEN_PREVIEW); } catch (error) { setError(`No se pudo abrir la preview: ${error.message}`); } finally { setBusy(false); } });
    $('refreshDevicesBtn').addEventListener('click', async () => { setBusy(true); try { await listCaptureDevices(); await openPreviewStream({ videoDeviceId: $('videoDeviceSelect').value || null, audioDeviceId: $('audioDeviceSelect').value || null }); } catch (error) { setError(`No se pudieron refrescar los dispositivos: ${error.message}`); } finally { setBusy(false); } });
    $('videoDeviceSelect').addEventListener('change', async (event) => { state.capture.selected_video_device_id = event.target.value || null; if (state.capture.stream_active) { try { await openPreviewStream({ videoDeviceId: state.capture.selected_video_device_id, audioDeviceId: state.capture.selected_audio_device_id }); } catch (error) { setError(`No se pudo cambiar la cámara: ${error.message}`); } } });
    $('audioDeviceSelect').addEventListener('change', async (event) => { state.capture.selected_audio_device_id = event.target.value || null; if (state.capture.stream_active) { try { await openPreviewStream({ videoDeviceId: state.capture.selected_video_device_id, audioDeviceId: state.capture.selected_audio_device_id }); } catch (error) { setError(`No se pudo cambiar el micrófono: ${error.message}`); } } });
    $('startRecordingBtn').addEventListener('click', async () => { setBusy(true); try { await startRecording(); } catch (error) { setError(`No se pudo iniciar la grabación: ${error.message}`); } finally { setBusy(false); } });
    $('stopRecordingBtn').addEventListener('click', async () => { setBusy(true); try { await stopRecording(); } catch (error) { setError(`No se pudo detener la grabación: ${error.message}`); } finally { setBusy(false); } });
    $('rerecordBtn').addEventListener('click', () => { clearError(); resetRecordingReview(); });
    $('registerRecordingBtn').addEventListener('click', async () => { clearError(); try { await registerRecordingMetadata(); } catch (error) { setError(`No se pudo registrar la grabación: ${error.message}`); } });
    $('submitEvaluationBtn').addEventListener('click', async () => { clearError(); try { await submitCommunicationAttempt(); } catch (error) { setError(`No se pudo enviar la evaluación: ${error.message}`); } });
    $('exportReportJsonBtn').addEventListener('click', async () => { clearError(); try { await exportReportJson(); } catch (error) { setError(`No se pudo exportar el JSON: ${error.message}`); } });
    $('exportReportHtmlBtn').addEventListener('click', async () => { clearError(); try { await exportReportHtml(); } catch (error) { setError(`No se pudo exportar el HTML: ${error.message}`); } });
    $('exportReportPngBtn').addEventListener('click', async () => { clearError(); try { await exportReportPng(); } catch (error) { setError(`No se pudo exportar el PNG: ${error.message}`); } });
    $('emitFinalResultBtn').addEventListener('click', async () => { clearError(); try { await emitCommunicationFinalResultLifecycle(state.report.payload, { rootElement: $('reportPlaceholderRoot') }); } catch (error) { state.final_delivery.status = 'error'; state.final_delivery.last_error = error.message; renderApp(); } });
  }

  function escapeHtml(value) { return String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'); }

  async function initialize() {
    renderApp(); installEventHandlers(); installCommunicationEmbedMessageListener();
    try { await bootstrapCommunicationSession(); } catch (error) { setError(`No se pudo preparar la sesión: ${error.message}`); return; }
    try { await listCaptureDevices(); } catch (_error) { }
    renderApp();
  }

  document.addEventListener('DOMContentLoaded', initialize);

  global.CommunicationApp = {
    state,
    SCREEN_INTRO,
    SCREEN_PERMISSIONS,
    SCREEN_PREVIEW,
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
