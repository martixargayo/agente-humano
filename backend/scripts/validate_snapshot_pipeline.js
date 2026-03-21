const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const APP_JS = path.join(REPO_ROOT, 'backend', 'interfaz_usuario_app', 'app.js');
const FEEDBACK_JS = path.join(REPO_ROOT, 'backend', 'interfaz_usuario_app', 'feedback_report_view.js');
const ARTIFACT_DIR = path.join(REPO_ROOT, 'artifacts', 'snapshot_validation');

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function extractFunctionSource(source, name) {
  const asyncMarker = `async function ${name}(`;
  const marker = source.includes(asyncMarker) ? asyncMarker : `function ${name}(`;
  const start = source.indexOf(marker);
  if (start === -1) throw new Error(`No se encontró ${name}`);
  const paramsEnd = source.indexOf(')', start);
  const braceStart = source.indexOf('{', paramsEnd);
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  let inTemplate = false;
  let escaped = false;
  for (let idx = braceStart; idx < source.length; idx += 1) {
    const ch = source[idx];
    if (escaped) {
      escaped = false;
    } else if (ch === '\\') {
      escaped = true;
    } else if (inSingle) {
      if (ch === "'") inSingle = false;
    } else if (inDouble) {
      if (ch === '"') inDouble = false;
    } else if (inTemplate) {
      if (ch === '`') inTemplate = false;
    } else if (ch === "'") {
      inSingle = true;
    } else if (ch === '"') {
      inDouble = true;
    } else if (ch === '`') {
      inTemplate = true;
    } else if (ch === '{') {
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, idx + 1);
    }
  }
  throw new Error(`No se pudo extraer ${name}`);
}

function crc32(buf) {
  let crc = ~0;
  for (let i = 0; i < buf.length; i += 1) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j += 1) {
      crc = (crc >>> 1) ^ (0xEDB88320 & -(crc & 1));
    }
  }
  return (~crc) >>> 0;
}

function pngChunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii');
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePng(width, height, rgba) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y += 1) {
    const rowStart = y * (width * 4 + 1);
    raw[rowStart] = 0;
    rgba.copy(raw, rowStart + 1, y * width * 4, (y + 1) * width * 4);
  }
  const signature = Buffer.from([137,80,78,71,13,10,26,10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const idat = zlib.deflateSync(raw);
  return Buffer.concat([
    signature,
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', idat),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function parseColor(input, fallback = [0, 0, 0, 255]) {
  if (!input || typeof input !== 'string') return fallback;
  const value = input.trim();
  if (/^#([0-9a-f]{6})$/i.test(value)) {
    const hex = value.slice(1);
    return [
      parseInt(hex.slice(0, 2), 16),
      parseInt(hex.slice(2, 4), 16),
      parseInt(hex.slice(4, 6), 16),
      255,
    ];
  }
  if (/^rgba?\(/i.test(value)) {
    const parts = value.replace(/rgba?\(|\)/gi, '').split(',').map((item) => item.trim());
    const alpha = parts[3] == null ? 1 : Number(parts[3]);
    return [Number(parts[0]) || 0, Number(parts[1]) || 0, Number(parts[2]) || 0, Math.max(0, Math.min(255, Math.round(alpha * 255)))];
  }
  return fallback;
}

class FakeCanvasContext2D {
  constructor(canvas) {
    this.canvas = canvas;
    this.fillStyle = '#000000';
    this.strokeStyle = '#000000';
    this.lineWidth = 1;
    this.font = '16px sans-serif';
  }

  _paintRect(x, y, w, h, color) {
    const [r, g, b, a] = parseColor(color, [0, 0, 0, 255]);
    const width = this.canvas.width;
    const height = this.canvas.height;
    const startX = Math.max(0, Math.floor(x));
    const startY = Math.max(0, Math.floor(y));
    const endX = Math.min(width, Math.ceil(x + w));
    const endY = Math.min(height, Math.ceil(y + h));
    for (let py = startY; py < endY; py += 1) {
      for (let px = startX; px < endX; px += 1) {
        const idx = (py * width + px) * 4;
        this.canvas.rgba[idx] = r;
        this.canvas.rgba[idx + 1] = g;
        this.canvas.rgba[idx + 2] = b;
        this.canvas.rgba[idx + 3] = a;
      }
    }
  }

  fillRect(x, y, w, h) {
    this._paintRect(x, y, w, h, this.fillStyle);
  }

  strokeRect(x, y, w, h) {
    const lw = Math.max(1, Number(this.lineWidth) || 1);
    this._paintRect(x, y, w, lw, this.strokeStyle);
    this._paintRect(x, y + h - lw, w, lw, this.strokeStyle);
    this._paintRect(x, y, lw, h, this.strokeStyle);
    this._paintRect(x + w - lw, y, lw, h, this.strokeStyle);
  }

  fillText(text, x, y) {
    const fontSizeMatch = String(this.font).match(/(\d+)px/);
    const fontSize = fontSizeMatch ? Number(fontSizeMatch[1]) : 16;
    const width = Math.max(fontSize, Math.ceil(String(text || '').length * fontSize * 0.5));
    const height = Math.max(8, Math.ceil(fontSize * 0.7));
    this._paintRect(x, y - height, width, height, this.fillStyle);
  }

  measureText(text) {
    const fontSizeMatch = String(this.font).match(/(\d+)px/);
    const fontSize = fontSizeMatch ? Number(fontSizeMatch[1]) : 16;
    return { width: Math.ceil(String(text || '').length * fontSize * 0.5) };
  }

  drawImage(image, dx, dy, dw, dh) {
    const color = image && image.mockColor ? image.mockColor : '#4F46E5';
    this._paintRect(dx, dy, dw, dh, color);
  }

  getImageData(sx, sy, sw, sh) {
    const out = Buffer.alloc(sw * sh * 4);
    for (let y = 0; y < sh; y += 1) {
      for (let x = 0; x < sw; x += 1) {
        const srcX = Math.min(this.canvas.width - 1, Math.max(0, sx + x));
        const srcY = Math.min(this.canvas.height - 1, Math.max(0, sy + y));
        const srcIdx = (srcY * this.canvas.width + srcX) * 4;
        const dstIdx = (y * sw + x) * 4;
        this.canvas.rgba.copy(out, dstIdx, srcIdx, srcIdx + 4);
      }
    }
    return { data: Uint8ClampedArray.from(out) };
  }
}

class FakeCanvas {
  constructor(width = 300, height = 150) {
    this._width = width;
    this._height = height;
    this.rgba = Buffer.alloc(width * height * 4, 0);
    this._ctx = new FakeCanvasContext2D(this);
  }

  get width() {
    return this._width;
  }

  set width(value) {
    this._width = Math.max(1, Number(value) || 1);
    this.rgba = Buffer.alloc(this._width * this._height * 4, 0);
  }

  get height() {
    return this._height;
  }

  set height(value) {
    this._height = Math.max(1, Number(value) || 1);
    this.rgba = Buffer.alloc(this._width * this._height * 4, 0);
  }

  getContext(kind) {
    if (kind !== '2d') return null;
    return this._ctx;
  }

  _buffer() {
    return encodePng(this.width, this.height, this.rgba);
  }

  toDataURL(type = 'image/png') {
    return `data:${type};base64,${this._buffer().toString('base64')}`;
  }

  toBlob(callback, type = 'image/png') {
    callback(new Blob([this._buffer()], { type }));
  }
}

function bufferFromDataUrl(dataUrl) {
  const [, base64] = String(dataUrl).split(',', 2);
  return Buffer.from(base64, 'base64');
}

function sampleRgbaStats(rgba) {
  let opaque = 0;
  let nonWhite = 0;
  for (let i = 0; i < rgba.length; i += 4) {
    const a = rgba[i + 3];
    if (a > 0) opaque += 1;
    if (a > 8 && (rgba[i] < 248 || rgba[i + 1] < 248 || rgba[i + 2] < 248)) nonWhite += 1;
  }
  return { opaquePixels: opaque, nonWhitePixels: nonWhite };
}

function makeFixturePngDataUrl(label, color = '#16A34A', width = 320, height = 180) {
  const canvas = new FakeCanvas(width, height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = color;
  ctx.fillRect(24, 24, width - 48, height - 48);
  ctx.fillStyle = '#101828';
  ctx.font = '28px sans-serif';
  ctx.fillText(label, 40, 96);
  return { dataUrl: canvas.toDataURL('image/png'), canvas };
}

function buildReport(overrides = {}) {
  return {
    schema_version: 'ui_feedback_report.v1',
    evaluation_id: 'eval-123',
    header: {
      report_title: 'Evaluación de tu desempeño',
      activity_name: 'Compra de un Mustang clásico',
      score_global_100: 87,
      stars_0_5: 4.4,
      interaction_outcome: 'agreement_reached',
      summary_2_3_lines: 'Resumen breve del informe.',
      ...overrides.header,
    },
    block_cards: overrides.block_cards || [],
    trajectory_chart: overrides.trajectory_chart || [],
    key_moments: {
      best_moment: {},
      most_delicate_moment: {},
      turning_point: {},
    },
    recommendations: overrides.recommendations || { items: [] },
    provenance: {
      evaluation_id: 'eval-123',
      flow_id: 'negociacion',
      context_id: 'ctx-001',
      ...overrides.provenance,
    },
  };
}

function writeArtifact(name, dataUrl) {
  const buffer = bufferFromDataUrl(dataUrl);
  const target = path.join(ARTIFACT_DIR, name);
  fs.writeFileSync(target, buffer);
  return target;
}

function runAppScenario(mode) {
  const appSource = fs.readFileSync(APP_JS, 'utf8');
  const functions = [
    'deriveFinalResultTitle',
    'wrapPlaceholderText',
    'buildSnapshotFailurePlaceholderPngDataUrl',
    'deriveFinalResultActivityId',
    'buildEmbedEnvelope',
    'emitEmbedMessage',
    'normalizeComparableId',
    'stableStringifyForHash',
    'simpleHashString',
    'deriveFinalResultPayloadHash',
    'buildFinalResultCorrelationId',
    'registerPendingEmbeddedFinalResultAck',
    'buildFinalResultPayload',
    'emitFinalResultLifecycle',
  ];
  const extracted = functions.map((name) => extractFunctionSource(appSource, name)).join('\n\n');
  const successFixture = makeFixturePngDataUrl('snapshot-ok', '#16A34A', 420, 240);
  const sentEnvelopes = [];
  const sandboxCanvases = [];
  const feedbackView = {
    serializeReportToHtml(report) {
      return `<html><body><h1>${report.header.report_title}</h1></body></html>`;
    },
  };
  if (mode === 'success' || mode === 'emit') {
    feedbackView.captureReportPngDataUrl = async () => successFixture.dataUrl;
  } else if (mode === 'failure') {
    feedbackView.captureReportPngDataUrl = async () => { throw new Error('primary_and_fallback_failed'); };
  }

  const context = {
    Blob,
    Date,
    Math,
    JSON,
    process,
    EMBED_MESSAGE_VERSION: 1,
    EMBED_NAMESPACE: 'gestionce.simulator',
    PARENT_EMBED_ORIGIN: 'https://academia.gestionce.com',
    feedbackEvaluationId: 'eval-123',
    embedModeActive: true,
    pendingEmbeddedFinalResultAck: null,
    getSessionCorrelationMeta() {
      return {
        session_id: 'sess-001',
        conversation_id: 'conv-001',
        context_id: 'ctx-001',
        public_slug: 'negociacion',
        trace_count: 14,
        bootstrapped_at: '2026-03-20T10:00:00.000Z',
      };
    },
    isEmbeddedRuntime() { return true; },
    $(id) { return { id }; },
    window: null,
    document: {
      createElement(tag) {
        if (tag === 'canvas') {
          const canvas = new FakeCanvas();
          sandboxCanvases.push(canvas);
          return canvas;
        }
        return { tagName: tag.toUpperCase() };
      },
    },
    console: {
      info() {},
      warn() {},
      error() {},
      log() {},
    },
  };
  context.window = {
    parent: {
      postMessage(envelope) {
        sentEnvelopes.push(envelope);
      },
    },
    FeedbackReportView: feedbackView,
  };

  vm.createContext(context);
  vm.runInContext(`${extracted}\nglobalThis.__exports = { buildFinalResultPayload, emitFinalResultLifecycle };`, context);

  const report = buildReport(mode === 'long' ? {
    recommendations: { items: Array.from({ length: 6 }, (_, idx) => ({ title: `Rec ${idx + 1}`, description: `Detalle ${idx + 1}` })) },
    trajectory_chart: Array.from({ length: 8 }, (_, idx) => ({ turn_index: idx + 1, agreement_closeness_score_0_100: 20 + idx * 10 })),
  } : {});

  return (async () => {
    const payload = await context.__exports.buildFinalResultPayload(report, { reason: 'report-fetched' });
    if (mode === 'emit') {
      await context.__exports.emitFinalResultLifecycle(report, { reason: 'report-fetched' });
    }
    return {
      payload,
      sentEnvelopes,
      placeholderCanvas: sandboxCanvases[sandboxCanvases.length - 1] || null,
      successFixture: { width: successFixture.canvas.width, height: successFixture.canvas.height },
    };
  })();
}

function runFeedbackOrchestrationScenario(mode) {
  const feedbackSource = fs.readFileSync(FEEDBACK_JS, 'utf8');
  const functions = [
    'captureReportAsPng',
    'summarizeCaptureFailures',
  ];
  const extracted = functions.map((name) => extractFunctionSource(feedbackSource, name)).join('\n\n');
  let appended = 0;
  let removed = 0;
  const sandboxRoot = {
    isConnected: true,
    remove() { removed += 1; },
  };
  const context = {
    console: { info() {}, warn() {}, error() {} },
    resolveCaptureRoot(report, options = {}) {
      if (mode === 'sandbox-fallback') {
        return { liveRoot: null, captureRoot: sandboxRoot, sandboxRoot, source: 'sandbox-root' };
      }
      return { liveRoot: options.rootElement || null, captureRoot: options.rootElement || sandboxRoot, sandboxRoot: null, source: 'live-root' };
    },
    runCapturePreflight: async () => ({
      stableMetrics: { width: 1180, height: mode === 'long' ? 1420 : 860 },
      measured: { width: 1180, height: mode === 'long' ? 1420 : 860 },
      imageStatus: { total: 0, decoded: 0, pending: 0 },
      durationMs: 12,
    }),
    deriveCaptureDimensions: (stable, measured) => ({ width: stable.width || measured.width, height: stable.height || measured.height }),
    captureReportAsPngPrimary: async () => {
      if (mode === 'primary-success' || mode === 'long') {
        return { blob: new Blob(['primary-ok']), width: 1180, height: mode === 'long' ? 1420 : 860, strategy: 'dom-data-url' };
      }
      throw new Error('primary_failed');
    },
    captureReportAsPngFallback: async () => {
      if (mode === 'sandbox-fallback' || mode === 'all-fail-root') {
        return { blob: new Blob(['fallback-ok']), width: 1180, height: 980, strategy: 'svg-data-fallback' };
      }
      throw new Error('fallback_failed');
    },
  };
  vm.createContext(context);
  vm.runInContext(`${extracted}\nglobalThis.__exports = { captureReportAsPng, summarizeCaptureFailures };`, context);
  const report = buildReport();
  const liveRoot = {
    id: 'feedbackReportRoot',
    isConnected: true,
  };

  return context.__exports.captureReportAsPng(report, { rootElement: liveRoot })
    .then((result) => ({ ok: true, result, appended, removed }))
    .catch((error) => ({ ok: false, error: String(error.message || error), appended, removed }));
}

function runResolveCaptureRootScenario() {
  const feedbackSource = fs.readFileSync(FEEDBACK_JS, 'utf8');
  const functions = [
    'createCaptureSandboxRoot',
    'resolveCaptureRoot',
  ];
  const extracted = functions.map((name) => extractFunctionSource(feedbackSource, name)).join('\n\n');
  const bodyAppends = [];
  const sandbox = { style: {}, setAttribute() {}, isConnected: true };
  const context = {
    buildDetachedReportRoot() { return sandbox; },
    document: { body: { appendChild(node) { bodyAppends.push(node); } } },
  };
  vm.createContext(context);
  vm.runInContext(`${extracted}\nglobalThis.__exports = { createCaptureSandboxRoot, resolveCaptureRoot };`, context);
  const liveRoot = { isConnected: true, id: 'feedbackReportRoot' };
  const live = context.__exports.resolveCaptureRoot({}, { rootElement: liveRoot });
  const detached = context.__exports.resolveCaptureRoot({}, { rootElement: { isConnected: false } });
  return {
    liveSource: live.source,
    liveIsRoot: live.captureRoot === liveRoot,
    detachedSource: detached.source,
    detachedUsesSandbox: detached.captureRoot === sandbox,
    bodyAppendCount: bodyAppends.length,
  };
}

async function runWaitForReportImagesScenario() {
  const feedbackSource = fs.readFileSync(FEEDBACK_JS, 'utf8');
  const extracted = extractFunctionSource(feedbackSource, 'waitForReportImages');
  function makeImage({ complete, decodeFails = false }) {
    const listeners = {};
    return {
      complete,
      addEventListener(type, cb) { listeners[type] = cb; if (!complete && type === 'load') setTimeout(cb, 0); },
      async decode() { if (decodeFails) throw new Error('decode_failed'); },
    };
  }
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${extracted}\nglobalThis.__exports = { waitForReportImages };`, context);
  const root = {
    querySelectorAll() {
      return [makeImage({ complete: true }), makeImage({ complete: false }), makeImage({ complete: true, decodeFails: true })];
    },
  };
  return context.__exports.waitForReportImages(root);
}

(async () => {
  ensureDir(ARTIFACT_DIR);
  const results = {
    metadata: {
      artifactDir: ARTIFACT_DIR,
    },
    feedback: {},
    app: {},
  };

  results.feedback.resolveCaptureRoot = runResolveCaptureRootScenario();
  results.feedback.waitForReportImages = await runWaitForReportImagesScenario();
  results.feedback.primarySuccess = await runFeedbackOrchestrationScenario('primary-success');
  results.feedback.longPrimarySuccess = await runFeedbackOrchestrationScenario('long');
  results.feedback.sandboxFallback = await runFeedbackOrchestrationScenario('sandbox-fallback');
  results.feedback.allFail = await runFeedbackOrchestrationScenario('all-fail');

  const success = await runAppScenario('success');
  const failure = await runAppScenario('failure');
  const missing = await runAppScenario('missing-api');
  const emit = await runAppScenario('emit');

  const successArtifact = writeArtifact('capture_success_payload.png', success.payload.snapshot_png_dataurl);
  const failureArtifact = writeArtifact('placeholder_capture_failure.png', failure.payload.snapshot_png_dataurl);
  const missingArtifact = writeArtifact('placeholder_missing_api.png', missing.payload.snapshot_png_dataurl);

  results.app.captureSuccess = {
    payloadHasPng: success.payload.snapshot_png_dataurl.startsWith('data:image/png;base64,'),
    artifact: successArtifact,
    reportHtml: success.payload.report_html,
    snapshotPrefix: success.payload.snapshot_png_dataurl.slice(0, 22),
    stats: sampleRgbaStats(success.successFixture ? makeFixturePngDataUrl('snapshot-ok').canvas.rgba : Buffer.alloc(0)),
  };
  results.app.captureFailure = {
    payloadHasPng: failure.payload.snapshot_png_dataurl.startsWith('data:image/png;base64,'),
    artifact: failureArtifact,
    usesPlaceholder: failure.payload.snapshot_png_dataurl !== success.payload.snapshot_png_dataurl,
    stats: sampleRgbaStats(failure.placeholderCanvas.rgba),
  };
  results.app.missingApi = {
    payloadHasPng: missing.payload.snapshot_png_dataurl.startsWith('data:image/png;base64,'),
    artifact: missingArtifact,
    stats: sampleRgbaStats(missing.placeholderCanvas.rgba),
  };
  results.app.emitLifecycle = {
    envelopeTypes: emit.sentEnvelopes.map((entry) => entry.type),
    finalPayloadHasPng: emit.sentEnvelopes.find((entry) => entry.type === 'final_result')?.payload?.snapshot_png_dataurl?.startsWith('data:image/png;base64,') || false,
  };

  fs.writeFileSync(
    path.join(ARTIFACT_DIR, 'snapshot_validation_results.json'),
    JSON.stringify(results, null, 2),
  );

  process.stdout.write(JSON.stringify(results, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
