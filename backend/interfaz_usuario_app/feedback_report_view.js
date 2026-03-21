(function attachFeedbackReportView(global) {
  const NS = 'http://www.w3.org/2000/svg';


  const BLOCK_LABELS = {
    valores: 'Valores',
    vision: 'Visión',
    relacion: 'Relación',
    proceso: 'Proceso',
  };

  function orderBlocks(blocks = []) {
    const rank = { valores: 0, vision: 1, relacion: 2, proceso: 3 };
    return [...blocks].sort((a, b) => (rank[a?.block_id] ?? 99) - (rank[b?.block_id] ?? 99));
  }
  function ensureStyles() {
    if (document.getElementById('feedback-report-view-styles')) return;
    const style = document.createElement('style');
    style.id = 'feedback-report-view-styles';
    style.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600&display=swap');
      .feedback-report-root * { box-sizing: border-box; }
      .feedback-report-root {
        min-height: 100vh;
        background: #FFFFFF;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        color: #101828;
        font-weight: 500;
      }

      .feedback-dashboard {
        width: min(1180px, 100%);
        margin: 0 auto;
        padding: 24px 26px 38px;
        display: grid;
        gap: 18px;
      }

      .fb-card {
        background: #FFFFFF;
        border: 1px solid #E4E7EC;
        border-radius: 16px;
        box-shadow: 0 5px 18px rgba(16,24,40,0.05);
      }

      .fb-header {
        padding: 22px;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 14px;
      }
      .fb-title { margin: 0; font-size: 30px; line-height: 1.15; font-weight: 600; }
      .fb-case-row { margin-top: 10px; color: #344054; font-size: 18px; font-weight: 600; }
      .fb-header-right { display: inline-flex; align-items: center; gap: 10px; }
      .fb-stars { display: inline-flex; gap: 4px; }
      .fb-score-pill { border: 1px solid #E4E7EC; border-radius: 999px; padding: 8px 12px; font-size: 20px; font-weight: 600; }

      .fb-result { padding: 20px 22px; }
      .fb-result-head { display: inline-flex; align-items: center; gap: 10px; }
      .fb-result-head h2 { margin: 0; font-size: 23px; font-weight: 600; }
      .fb-result-dot { width: 12px; height: 12px; border-radius: 999px; display: inline-block; }
      .fb-result-dot.ok { background: #16A34A; }
      .fb-result-dot.bad { background: #DC2626; }
      .fb-result p { margin: 10px 0 0; font-size: 17px; line-height: 1.55; color: #475467; }

      .fb-grid-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
      .fb-skill-card { padding: 18px; border-width: 2px; }
      .fb-skill-card.ok { border-color: #16A34A; }
      .fb-skill-card.warn { border-color: #D97706; }
      .fb-skill-card.bad { border-color: #DC2626; }
      .fb-skill-top { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
      .fb-skill-top h3 { margin: 0; font-size: 18px; font-weight: 600; }
      .fb-badge { display: inline-flex; align-items: center; border-radius: 999px; color: #fff; height: 27px; padding: 4px 10px; font-size: 12px; font-weight: 600; text-transform: capitalize; }
      .fb-badge.ok { background: #16A34A; }
      .fb-badge.warn { background: #D97706; }
      .fb-badge.bad { background: #DC2626; }
      .fb-skill-card ul { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 8px; }
      .fb-skill-card li { display: grid; grid-template-columns: 18px 1fr; gap: 10px; align-items: flex-start; color: #475467; font-size: 15px; line-height: 1.45; }
      .fb-item-icon { width: 18px; height: 18px; border-radius: 999px; display: inline-flex; justify-content: center; align-items: center; }
      .fb-item-icon.ok { color: #16A34A; background: rgba(22,163,74,0.10); }
      .fb-item-icon.bad { color: #DC2626; background: rgba(220,38,38,0.10); }

      .fb-chart-card { padding: 18px 20px 22px; }
      .fb-chart-top h2 { margin: 0; font-size: 23px; font-weight: 600; }
      .fb-chart-hint { margin: 6px 0 0; font-size: 14px; color: #667085; }
      .fb-chart-shell {
        width: 100%;
        margin-top: 14px;
        position: relative;
      }
      .fb-chart {
        width: 100%;
        height: clamp(280px, 38vw, 390px);
        display: block;
      }
      .fb-axis-label { font-size: 12px; fill: #98A2B3; }

      .fb-turn-tooltip {
        position: absolute;
        z-index: 12;
        width: min(380px, calc(100% - 12px));
        border: 1px solid #D0D5DD;
        border-radius: 12px;
        background: #fff;
        box-shadow: 0 16px 28px rgba(16,24,40,0.14);
        padding: 12px;
        pointer-events: none;
      }
      .fb-turn-tooltip.hidden { display: none; }
      .fb-turn-tooltip h4 { margin: 0 0 8px; font-size: 15px; font-weight: 600; }
      .fb-turn-tooltip p { margin: 6px 0 0; font-size: 14px; line-height: 1.45; color: #475467; }
      .fb-turn-tooltip p strong { color: #101828; font-weight: 600; }

      .fb-recommendations { padding: 18px 20px 20px; }
      .fb-recommendations h2 { margin: 0; font-size: 23px; font-weight: 600; }
      .fb-recommendations-grid { margin-top: 14px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 22px; }
      .fb-rec-item h3 { margin: 0; font-size: 17px; font-weight: 600; line-height: 1.35; }
      .fb-rec-item p { margin: 7px 0 0; font-size: 15px; color: #475467; line-height: 1.45; }
      .fb-rec-example { margin-top: 10px; border: 1px solid #D0D5DD; border-radius: 10px; padding: 10px; background: #fff; }
      .fb-rec-example p { margin-top: 6px; font-size: 14px; }
      .fb-rec-user { color: #475467; }
      .fb-rec-better { color: #027A48; }
      .fb-empty { margin-top: 12px; color: #475467; font-size: 15px; }
      .hidden { display: none; }

      @media (max-width: 940px) {
        .feedback-dashboard { padding: 14px; }
        .fb-grid-cards, .fb-recommendations-grid { grid-template-columns: 1fr; }
        .fb-header { flex-direction: column; }
      }
    `;
    document.head.appendChild(style);
  }

  function getFeedbackReportStyles() {
    ensureStyles();
    return document.getElementById('feedback-report-view-styles')?.textContent || '';
  }

  function getXmlSafeCaptureStyles() {
    const captureFontStack = `Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif`;
    const styles = getFeedbackReportStyles();
    if (!styles) return '';
    return styles
      .replace(/^\s*@import\s+url\(([^)]+)\);\s*/gm, '')
      .replace(
        /font-family:\s*Inter,\s*ui-sans-serif,\s*system-ui,\s*-apple-system,\s*Segoe UI,\s*Roboto,\s*Helvetica,\s*Arial,\s*sans-serif;/g,
        `font-family: ${captureFontStack};`
      );
  }

  function escapeHtml(value) {
    return String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  }

  function normalizeStatus(status) {
    if (status === 'solid' || status === 'ok' || status === 'correcto') return 'ok';
    if (status === 'watch' || status === 'warn' || status === 'mejorable') return 'warn';
    return 'bad';
  }

  function checkSvg() {
    return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.3 6.1 11.4 13 4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  function crossSvg() {
    return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  }

  function createStarsMarkup(stars) {
    const starCount = Math.max(0, Math.min(5, Math.round(Number(stars || 0))));
    return [1, 2, 3, 4, 5]
      .map((n) => {
        const filled = n <= starCount;
        return `<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" style="${
          filled
            ? 'opacity:0.92;color:#F59E0B;fill:currentColor;stroke:none;'
            : 'color:#98A2B3;fill:none;stroke:currentColor;stroke-width:1.6;'
        }"><path d="M12 3.5l2.87 5.82 6.43.93-4.65 4.53 1.1 6.4L12 18.13l-5.75 3.05 1.1-6.4L2.7 10.25l6.43-.93L12 3.5z"/></svg>`;
      })
      .join('');
  }

  function colorForScore(score) {
    if (score >= 67) return '#16A34A';
    if (score >= 34) return '#D97706';
    return '#DC2626';
  }

  function durationFromReport(report, trajectoryLength) {
    const direct = report?.header?.duration_label || report?.header?.conversation_duration || report?.duration_label;
    if (direct) return String(direct);
    const estMinutes = Math.max(1, Math.round((trajectoryLength || 1) * 1.05));
    return `${estMinutes}:00 min`;
  }

  function resultFirstLine(outcome) {
    if (outcome === 'agreement_reached') return 'Lograste un acuerdo: cerraste la negociación en términos aceptables para ambas partes.';
    return 'No cerraste un acuerdo final en esta conversación.';
  }

  function buildResultSummary(outcome, summary) {
    return `${resultFirstLine(outcome)} ${summary || ''}`.trim();
  }

  function helpReason(turn, previousTurn) {
    if (!turn) return '';
    const current = Number(turn.agreement_closeness_score_0_100 || 0);
    const previous = Number(previousTurn?.agreement_closeness_score_0_100 || current);
    const delta = current - previous;
    if (delta > 0) return 'Este turno te acercó al entendimiento.';
    if (delta < 0) return 'Este turno te alejó del entendimiento.';
    return 'Este turno dejó la negociación casi en el mismo punto.';
  }

  function tooltipMarkup(turn, previousTurn) {
    return `
      <h4>Turno ${Number(turn?.turn_index || 0)}</h4>
      <p><strong>Tú:</strong> ${escapeHtml(turn?.user_excerpt || '')}</p>
      <p><strong>Él:</strong> ${escapeHtml(turn?.counterpart_excerpt || '')}</p>
      <p>${escapeHtml(helpReason(turn, previousTurn))} ${escapeHtml(turn?.impact_reason || '')}</p>
      <p><strong>Pensamiento del otro:</strong> ${escapeHtml(turn?.counterpart_thought_effect || '')}</p>
    `;
  }

  function getCardChecks(checks = []) {
    const trimmed = checks.slice(0, 4);
    if (trimmed.length > 0) return trimmed;
    return [{ polarity: 'check', micro_explanation: 'Cuidaste bien este bloque durante la conversación.' }];
  }

  function recommendationTitle(text) {
    const clean = String(text || '').trim();
    if (!clean) return 'Ajuste clave para el siguiente intento';
    const firstSentence = clean.split('.').map((s) => s.trim()).find(Boolean) || clean;
    const head = firstSentence.split(':')[0].trim();
    if (head.length >= 16 && head.length <= 90) return head;
    return clean.slice(0, 90).trim();
  }

  function renderChart(svg, trajectory, handlers) {
    const width = 980;
    const height = 360;
    const pad = { top: 18, right: 18, bottom: 38, left: 20 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const values = trajectory.map((t) => Number(t.agreement_closeness_score_0_100 || 0));
    const xFor = (idx) => pad.left + (idx / Math.max(1, values.length - 1)) * innerW;
    const yFor = (value) => pad.top + ((100 - value) / 100) * innerH;

    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.innerHTML = '';

    [25, 50, 75].forEach((n) => {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', String(pad.left));
      line.setAttribute('x2', String(width - pad.right));
      line.setAttribute('y1', String(yFor(n)));
      line.setAttribute('y2', String(yFor(n)));
      line.setAttribute('stroke', '#EAECF0');
      line.setAttribute('stroke-width', '1');
      svg.appendChild(line);
    });

    for (let i = 0; i < values.length - 1; i += 1) {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', String(xFor(i)));
      line.setAttribute('y1', String(yFor(values[i])));
      line.setAttribute('x2', String(xFor(i + 1)));
      line.setAttribute('y2', String(yFor(values[i + 1])));
      line.setAttribute('stroke', colorForScore((values[i] + values[i + 1]) / 2));
      line.setAttribute('stroke-width', '3');
      line.setAttribute('stroke-linecap', 'round');
      svg.appendChild(line);
    }

    values.forEach((value, idx) => {
      const circle = document.createElementNS(NS, 'circle');
      circle.setAttribute('cx', String(xFor(idx)));
      circle.setAttribute('cy', String(yFor(value)));
      circle.setAttribute('r', '5.5');
      circle.setAttribute('fill', '#fff');
      circle.setAttribute('stroke', colorForScore(value));
      circle.setAttribute('stroke-width', '3');
      circle.style.cursor = 'pointer';
      circle.dataset.turnIndex = String(idx);
      circle.addEventListener('mouseenter', (ev) => handlers.onHover(idx, ev));
      circle.addEventListener('mouseleave', () => handlers.onLeave());
      circle.addEventListener('click', (ev) => handlers.onClick(idx, ev));
      svg.appendChild(circle);
    });

    const xStart = document.createElementNS(NS, 'text');
    xStart.setAttribute('x', String(pad.left));
    xStart.setAttribute('y', String(height - 12));
    xStart.setAttribute('class', 'fb-axis-label');
    xStart.textContent = 'Inicio';
    svg.appendChild(xStart);

    const xEnd = document.createElementNS(NS, 'text');
    xEnd.setAttribute('x', String(width - 50));
    xEnd.setAttribute('y', String(height - 12));
    xEnd.setAttribute('class', 'fb-axis-label');
    xEnd.textContent = 'Final';
    svg.appendChild(xEnd);
  }

  function placeTooltip(tooltip, shell, event) {
    const shellRect = shell.getBoundingClientRect();
    const pointX = event.clientX - shellRect.left;
    const pointY = event.clientY - shellRect.top;

    const maxLeft = shell.clientWidth - tooltip.offsetWidth - 6;
    const left = Math.max(6, Math.min(pointX + 12, maxLeft));
    const top = Math.max(8, pointY - tooltip.offsetHeight - 12);

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function buildDetachedReportRoot(report) {
    const root = document.createElement('div');
    root.style.width = '1180px';
    root.style.background = '#FFFFFF';
    renderReport(root, report);
    return root;
  }

  function serializeReportToHtml(report) {
    if (!report) return '';
    const detachedRoot = buildDetachedReportRoot(report);
    const styles = getFeedbackReportStyles();
    return `<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Evaluación de tu desempeño</title>
    <style>${styles}</style>
  </head>
  <body>
    ${detachedRoot.outerHTML}
  </body>
</html>`;
  }

  function serializeReportToJson(report) {
    return JSON.stringify(report || {}, null, 2);
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      if (!(blob instanceof Blob)) {
        reject(new Error('Blob PNG inválido para serializar a Data URL.'));
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string' && reader.result.startsWith('data:image/png;base64,')) {
          resolve(reader.result);
          return;
        }
        reject(new Error('No se pudo convertir el PNG del informe a Data URL.'));
      };
      reader.onerror = () => reject(reader.error || new Error('No se pudo leer el Blob PNG.'));
      reader.readAsDataURL(blob);
    });
  }

  function waitForNextAnimationFrame() {
    return new Promise((resolve) => requestAnimationFrame(() => resolve()));
  }

  function waitForTimeout(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function nowMs() {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
      return performance.now();
    }
    return Date.now();
  }

  function getCaptureRootMetrics(root) {
    if (!root) {
      return { width: 0, height: 0, scrollWidth: 0, scrollHeight: 0 };
    }
    const rect = typeof root.getBoundingClientRect === 'function'
      ? root.getBoundingClientRect()
      : { width: 0, height: 0 };
    return {
      width: Math.ceil(Number(rect.width) || Number(root.offsetWidth) || 0),
      height: Math.ceil(Number(rect.height) || Number(root.offsetHeight) || 0),
      scrollWidth: Math.ceil(Number(root.scrollWidth) || 0),
      scrollHeight: Math.ceil(Number(root.scrollHeight) || 0),
    };
  }

  function metricsAreStable(current, previous) {
    if (!previous) return false;
    return Math.abs(current.width - previous.width) <= 1
      && Math.abs(current.height - previous.height) <= 1
      && Math.abs(current.scrollWidth - previous.scrollWidth) <= 1
      && Math.abs(current.scrollHeight - previous.scrollHeight) <= 1;
  }

  async function waitForStableReportCapture(root, options = {}) {
    const {
      extraAnimationFrames = 3,
      settleDelayMs = 60,
      requireVisible = true,
    } = options;
    if (document.fonts?.ready) {
      try {
        await document.fonts.ready;
      } catch (_) {
        // Continuamos con las fuentes de fallback disponibles en runtime.
      }
    }

    for (let idx = 0; idx < extraAnimationFrames; idx += 1) {
      await waitForNextAnimationFrame();
    }
    await waitForTimeout(settleDelayMs);

    let previousMetrics = null;
    let stableReads = 0;
    for (let attempt = 1; attempt <= 6; attempt += 1) {
      await waitForNextAnimationFrame();
      const metrics = getCaptureRootMetrics(root);
      if (requireVisible && metrics.width <= 0 && metrics.height <= 0) {
        stableReads = 0;
      } else if (metricsAreStable(metrics, previousMetrics)) {
        stableReads += 1;
        if (stableReads >= 2) return metrics;
      } else {
        stableReads = 0;
      }
      previousMetrics = metrics;
    }

    return previousMetrics || getCaptureRootMetrics(root);
  }

  async function waitForReportImages(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return { total: 0, decoded: 0, pending: 0 };
    const images = Array.from(root.querySelectorAll('img'));
    if (images.length === 0) return { total: 0, decoded: 0, pending: 0 };

    let decoded = 0;
    await Promise.all(images.map(async (img) => {
      try {
        if (!img.complete) {
          await new Promise((resolve) => {
            img.addEventListener('load', resolve, { once: true });
            img.addEventListener('error', resolve, { once: true });
          });
        }
        if (typeof img.decode === 'function') {
          try {
            await img.decode();
          } catch (_) {
            // Seguimos incluso si el decode falla; el objetivo es estabilizar al máximo.
          }
        }
        decoded += 1;
      } catch (_) {
        // Ignoramos errores individuales para no bloquear toda la captura.
      }
    }));
    return {
      total: images.length,
      decoded,
      pending: Math.max(0, images.length - decoded),
    };
  }

  function createCaptureSandboxRoot(report) {
    const sandboxRoot = buildDetachedReportRoot(report);
    sandboxRoot.style.margin = '0';
    sandboxRoot.style.padding = '0';
    sandboxRoot.style.position = 'fixed';
    sandboxRoot.style.left = '0';
    sandboxRoot.style.top = '0';
    sandboxRoot.style.opacity = '0';
    sandboxRoot.style.pointerEvents = 'none';
    sandboxRoot.style.zIndex = '-1';
    sandboxRoot.style.width = '1180px';
    sandboxRoot.setAttribute('data-capture-sandbox', '1');
    document.body.appendChild(sandboxRoot);
    return sandboxRoot;
  }

  function resolveCaptureRoot(report, options = {}) {
    const liveRoot = options.rootElement || null;
    if (liveRoot && liveRoot.isConnected) {
      return {
        liveRoot,
        captureRoot: liveRoot,
        sandboxRoot: null,
        source: 'live-root',
      };
    }

    const sandboxRoot = createCaptureSandboxRoot(report);
    return {
      liveRoot,
      captureRoot: sandboxRoot,
      sandboxRoot,
      source: 'sandbox-root',
    };
  }

  async function runCapturePreflight(captureRoot, options = {}) {
    const startedAt = nowMs();
    const stableMetrics = await waitForStableReportCapture(captureRoot, options);
    const imageStatus = await waitForReportImages(captureRoot);
    await waitForNextAnimationFrame();
    const measured = getCaptureRootMetrics(captureRoot);
    const durationMs = Math.round(nowMs() - startedAt);
    return {
      stableMetrics,
      measured,
      imageStatus,
      durationMs,
    };
  }

  function deriveCaptureDimensions(stableMetrics, measured) {
    return {
      width: Math.max(1180, stableMetrics.width || measured.width || stableMetrics.scrollWidth || measured.scrollWidth || 1180),
      height: Math.max(760, stableMetrics.height || measured.height || stableMetrics.scrollHeight || measured.scrollHeight || 760),
    };
  }

  function buildDomCaptureSvgMarkup(clonedRoot, width, height) {
    return `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
        <foreignObject width="100%" height="100%">
          <div xmlns="http://www.w3.org/1999/xhtml">
            <style>${getXmlSafeCaptureStyles()}</style>
            ${clonedRoot.outerHTML}
          </div>
        </foreignObject>
      </svg>
    `;
  }

  function validateSvgMarkup(svgMarkup) {
    const doc = new DOMParser().parseFromString(svgMarkup, 'image/svg+xml');
    const parserError = doc.querySelector('parsererror');
    return {
      ok: !parserError,
      errorText: parserError ? parserError.textContent || 'SVG inválido para XML.' : null,
    };
  }

  function svgMarkupToDataUrl(svgMarkup) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`;
  }

  async function loadImageFromUrl(src) {
    const img = new Image();
    img.decoding = 'sync';
    const loadPromise = new Promise((resolve, reject) => {
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('No se pudo rasterizar el informe a PNG.'));
    });
    img.src = src;
    if (typeof img.decode === 'function') {
      try {
        await img.decode();
        return img;
      } catch (_) {
        // Fallback al modelo tradicional de eventos si decode falla o no aplica.
      }
    }
    return loadPromise;
  }


  function canvasToBlob(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error('No se pudo generar el PNG del informe.'));
      }, 'image/png');
    });
  }
  function notifyCaptureDebug(stage, payload) {
    try {
      const hook = typeof window !== 'undefined' ? window.__feedbackCaptureDebugHook : null;
      if (typeof hook === 'function') hook({ stage, ...payload });
    } catch (_) {
      // Instrumentación defensiva; nunca debe romper la captura.
    }
  }

  async function rasterizeLoadedImageToPng(image, { width, height, emptySampleMessage = null, smallBlobMessage = null, report = null } = {}) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas 2D no disponible para exportar PNG.');
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0, width, height);
    const sample = sampleCanvasContent(canvas, ctx);
    const debugBlob = await canvasToBlob(canvas);
    const debugInfo = {
      width,
      height,
      blobSize: debugBlob.size,
      sample,
    };
    console.info('[feedback-capture] Validación de rasterización', debugInfo);
    notifyCaptureDebug('post-rasterize', {
      ...debugInfo,
      blob: debugBlob,
    });
    if (!sample.hasVisibleContent) {
      if (emptySampleMessage) console.warn('[feedback-capture] ' + emptySampleMessage, debugInfo);
      if (report) return renderReportFromDataAsPng(report, { width });
      throw new Error('La rasterización del informe quedó vacía.');
    }

    const pngBlob = debugBlob;

    if (pngBlob.size < 2048) {
      if (smallBlobMessage) console.warn('[feedback-capture] ' + smallBlobMessage, { blobSize: pngBlob.size });
      if (report) return renderReportFromDataAsPng(report, { width });
      throw new Error('Blob PNG demasiado pequeño.');
    }

    return { blob: pngBlob, width, height };
  }

  async function captureReportAsPngPrimary(report, captureRoot, context = {}) {
    const { width, height } = context.dimensions || {};
    const effectiveWidth = Math.max(1180, Number(width) || 1180);
    const effectiveHeight = Math.max(760, Number(height) || 760);
    const clonedRoot = captureRoot.cloneNode(true);
    clonedRoot.style.margin = '0';
    clonedRoot.style.width = `${effectiveWidth}px`;
    clonedRoot.style.minHeight = `${effectiveHeight}px`;
    clonedRoot.querySelectorAll('.fb-turn-tooltip').forEach((tooltip) => tooltip.remove());

    const svgMarkup = buildDomCaptureSvgMarkup(clonedRoot, effectiveWidth, effectiveHeight);
    const validation = validateSvgMarkup(svgMarkup);
    if (!validation.ok) {
      throw new Error(`SVG de captura inválido: ${validation.errorText || 'parsererror'}`);
    }

    const svgDataUrl = svgMarkupToDataUrl(svgMarkup);
    const image = await loadImageFromUrl(svgDataUrl);
    const png = await rasterizeLoadedImageToPng(image, {
      width: effectiveWidth,
      height: effectiveHeight,
      emptySampleMessage: 'La rasterización del motor principal salió vacía.',
      smallBlobMessage: 'Blob PNG demasiado pequeño en el motor principal.',
    });
    return {
      ...png,
      strategy: 'dom-data-url',
    };
  }

  async function captureReportAsPngFallback(report, context = {}) {
    const { width } = context.dimensions || {};
    const effectiveWidth = Math.max(1180, Number(width) || 1180);
    const fallbackPng = await renderReportFromDataAsPng(report, { width: effectiveWidth });
    return {
      ...fallbackPng,
      strategy: 'svg-data-fallback',
    };
  }

  function summarizeCaptureFailures(failures = []) {
    return failures.map((entry) => ({
      engine: entry.engine,
      error: entry.error,
    }));
  }

  function triggerDownload(filename, blob, { targetWindow = window } = {}) {
    const url = URL.createObjectURL(blob);
    const link = targetWindow.document.createElement('a');
    link.href = url;
    link.download = filename;
    targetWindow.document.body.appendChild(link);
    link.click();
    link.remove();
    targetWindow.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadReportHtml(report, options = {}) {
    const html = serializeReportToHtml(report);
    triggerDownload(options.filename || 'evaluacion-desempeno.html', new Blob([html], { type: 'text/html;charset=utf-8' }), options);
    return html;
  }

  function downloadReportJson(report, options = {}) {
    const json = serializeReportToJson(report);
    triggerDownload(options.filename || 'evaluacion-desempeno.json', new Blob([json], { type: 'application/json;charset=utf-8' }), options);
    return json;
  }

  async function captureReportAsPng(report, options = {}) {
    if (!report) throw new Error('No hay informe para exportar.');
    const resolved = resolveCaptureRoot(report, options);
    const { liveRoot, captureRoot, sandboxRoot, source } = resolved;

    try {
      const preflight = await runCapturePreflight(captureRoot, {
        requireVisible: captureRoot === liveRoot,
      });
      const dimensions = deriveCaptureDimensions(preflight.stableMetrics, preflight.measured);
      const { width, height } = dimensions;
      console.info('[feedback-capture] Preparando captura', {
        source,
        width,
        height,
        stableMetrics: preflight.stableMetrics,
        measured: preflight.measured,
        preflightMs: preflight.durationMs,
        images: preflight.imageStatus,
        engine: 'dom-data-url',
      });
      if (width <= 0 || height <= 0) {
        throw new Error(`Root de captura inválido (${width}x${height}).`);
      }

      const engines = [
        {
          name: 'dom-data-url',
          run: () => captureReportAsPngPrimary(report, captureRoot, {
            dimensions,
            source,
            preflight,
          }),
        },
        {
          name: 'svg-data-fallback',
          run: () => captureReportAsPngFallback(report, {
            dimensions,
            source,
            preflight,
            failedEngine: 'dom-data-url',
          }),
        },
      ];
      const failures = [];

      for (const engine of engines) {
        try {
          const snapshot = await engine.run();
          const failureSummary = summarizeCaptureFailures(failures);
          console.info('[feedback-capture] Snapshot generado', {
            engine: engine.name,
            source,
            width: snapshot.width,
            height: snapshot.height,
            blobSize: snapshot.blob?.size || null,
            recoveredFrom: failureSummary,
            preflightMs: preflight.durationMs,
          });
          return {
            ...snapshot,
            source,
            preflightMs: preflight.durationMs,
            images: preflight.imageStatus,
            recoveredFrom: failureSummary.length ? failureSummary : null,
          };
        } catch (error) {
          const failure = {
            engine: engine.name,
            error: String(error?.message || error),
          };
          failures.push(failure);
          console.warn('[feedback-capture] Error en motor de captura; se intentará el siguiente motor disponible.', {
            source,
            engine: failure.engine,
            error: failure.error,
          });
        }
      }

      throw new Error(`No se pudo capturar el snapshot del informe con ningún motor disponible. ${JSON.stringify(summarizeCaptureFailures(failures))}`);
    } finally {
      if (sandboxRoot) sandboxRoot.remove();
    }
  }

  function sampleCanvasContent(canvas, ctx) {
    const sampleWidth = Math.max(16, Math.min(canvas.width, 64));
    const sampleHeight = Math.max(16, Math.min(canvas.height, canvas.height > canvas.width ? 96 : 64));
    const maxX = Math.max(0, canvas.width - sampleWidth);
    const maxY = Math.max(0, canvas.height - sampleHeight);
    const anchorFractions = [
      { name: 'top-left', x: 0, y: 0 },
      { name: 'top-center', x: 0.5, y: 0 },
      { name: 'middle-center', x: 0.5, y: 0.5 },
      { name: 'lower-center', x: 0.5, y: 0.72 },
      { name: 'bottom-left', x: 0, y: 1 },
      { name: 'bottom-center', x: 0.5, y: 1 },
    ];
    const regions = anchorFractions.map((anchor) => {
      const sx = Math.round(maxX * anchor.x);
      const sy = Math.round(maxY * anchor.y);
      const source = ctx.getImageData(sx, sy, sampleWidth, sampleHeight).data;
      let nonWhitePixels = 0;
      let opaquePixels = 0;
      for (let idx = 0; idx < source.length; idx += 4) {
        const alpha = source[idx + 3];
        if (alpha > 0) opaquePixels += 1;
        if (alpha > 8 && (source[idx] < 248 || source[idx + 1] < 248 || source[idx + 2] < 248)) nonWhitePixels += 1;
      }
      return {
        name: anchor.name,
        sx,
        sy,
        sampleWidth,
        sampleHeight,
        opaquePixels,
        nonWhitePixels,
      };
    });
    const opaquePixels = regions.reduce((sum, region) => sum + region.opaquePixels, 0);
    const nonWhitePixels = regions.reduce((sum, region) => sum + region.nonWhitePixels, 0);
    const richestRegion = regions.reduce((best, region) => (region.nonWhitePixels > (best?.nonWhitePixels || -1) ? region : best), null);
    const contentRegions = regions.filter((region) => region.nonWhitePixels > 12).length;
    return {
      sampleWidth,
      sampleHeight,
      sampledRegions: regions.length,
      opaquePixels,
      nonWhitePixels,
      contentRegions,
      richestRegion,
      regions,
      hasVisibleContent: contentRegions >= 1 || nonWhitePixels > 24,
    };
  }

  function escapeXml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&apos;');
  }

  function wrapTextLines(text, maxChars) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) return [];
    const lines = [];
    let current = '';
    words.forEach((word) => {
      const candidate = current ? `${current} ${word}` : word;
      if (candidate.length <= maxChars || !current) current = candidate;
      else {
        lines.push(current);
        current = word;
      }
    });
    if (current) lines.push(current);
    return lines;
  }

  function renderReportSvgMarkup(report, options = {}) {
    const width = Math.max(1180, Number(options.width) || 1180);
    const blocks = orderBlocks(report.block_cards || []).slice(0, 4);
    const recs = (report.recommendations?.items || []).slice(0, 4);
    const header = report.header || {};
    const summaryLines = wrapTextLines(buildResultSummary(header.interaction_outcome, header.summary_2_3_lines), 94);
    const headerTitle = escapeXml(header.activity_name || 'Actividad');
    const recommendationsStartY = 610;
    const recommendationLines = recs.flatMap((item, idx) => {
      const title = `${idx + 1}. ${item.title || recommendationTitle(item.description)}`;
      const bodyLines = wrapTextLines(item.description || '', 84).slice(0, 3);
      return [
        `<text x="72" y="${recommendationsStartY + idx * 110}" font-size="24" font-weight="600" fill="#101828">${escapeXml(title)}</text>`,
        ...bodyLines.map((line, lineIdx) => `<text x="72" y="${recommendationsStartY + 36 + idx * 110 + lineIdx * 28}" font-size="20" fill="#475467">${escapeXml(line)}</text>`),
      ];
    });
    const blockMarkup = blocks.map((block, idx) => {
      const column = idx % 2;
      const row = Math.floor(idx / 2);
      const x = 72 + column * 522;
      const y = 254 + row * 150;
      const status = normalizeStatus(block.status_visual);
      const stroke = status === 'ok' ? '#16A34A' : (status === 'warn' ? '#D97706' : '#DC2626');
      const lines = getCardChecks(block.checks).slice(0, 3);
      return `
        <rect x="${x}" y="${y}" width="486" height="124" rx="18" fill="#FFFFFF" stroke="${stroke}" stroke-width="3" />
        <text x="${x + 24}" y="${y + 34}" font-size="24" font-weight="600" fill="#101828">${escapeXml(BLOCK_LABELS[block.block_id] || block.title || '')}</text>
        <text x="${x + 24}" y="${y + 68}" font-size="18" font-weight="600" fill="${stroke}">${escapeXml(block.status_visual || '')}</text>
        ${lines.map((line, lineIdx) => `<text x="${x + 24}" y="${y + 96 + lineIdx * 22}" font-size="18" fill="#475467">• ${escapeXml(line.micro_explanation || '')}</text>`).join('')}
      `;
    }).join('');
    const svgHeight = Math.max(980, recommendationsStartY + Math.max(1, recs.length) * 110 + 60);
    return `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${svgHeight}" viewBox="0 0 ${width} ${svgHeight}">
        <rect width="100%" height="100%" fill="#FFFFFF" />
        <rect x="48" y="40" width="${width - 96}" height="120" rx="22" fill="#FFFFFF" stroke="#E4E7EC" />
        <text x="72" y="86" font-size="36" font-weight="700" fill="#101828">Evaluación de tu desempeño</text>
        <text x="72" y="124" font-size="24" font-weight="600" fill="#344054">${headerTitle}</text>
        <text x="${width - 248}" y="98" font-size="28" font-weight="700" fill="#101828">${escapeXml(`${Number(header.score_global_100 || 0)} / 100`)}</text>
        <rect x="48" y="182" width="${width - 96}" height="94" rx="20" fill="#FFFFFF" stroke="#E4E7EC" />
        <text x="72" y="220" font-size="28" font-weight="700" fill="#101828">Resultado</text>
        ${summaryLines.map((line, idx) => `<text x="72" y="${248 + idx * 24}" font-size="20" fill="#475467">${escapeXml(line)}</text>`).join('')}
        ${blockMarkup}
        <rect x="48" y="${recommendationsStartY - 48}" width="${width - 96}" height="${svgHeight - recommendationsStartY + 32}" rx="20" fill="#FFFFFF" stroke="#E4E7EC" />
        <text x="72" y="${recommendationsStartY - 12}" font-size="28" font-weight="700" fill="#101828">Recomendaciones generales</text>
        ${recommendationLines.join('') || `<text x="72" y="${recommendationsStartY + 36}" font-size="20" fill="#475467">No hay recomendaciones relevantes que añadir en este caso.</text>`}
      </svg>
    `;
  }

  async function renderReportFromDataAsPng(report, options = {}) {
    const svgMarkup = renderReportSvgMarkup(report, options);
    const width = Math.max(1180, Number(options.width) || 1180);
    const heightMatch = svgMarkup.match(/height="(\d+)"/);
    const height = heightMatch ? Number(heightMatch[1]) : 980;
    const svgBlob = new Blob([svgMarkup], { type: 'image/svg+xml;charset=utf-8' });
    const svgUrl = URL.createObjectURL(svgBlob);
    try {
      const image = await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('No se pudo rasterizar el SVG de respaldo del informe.'));
        img.src = svgUrl;
      });
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas 2D no disponible para respaldo SVG.');
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(image, 0, 0, width, height);
      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob((pngBlob) => {
          if (pngBlob) resolve(pngBlob);
          else reject(new Error('No se pudo generar el PNG de respaldo del informe.'));
        }, 'image/png');
      });
      console.info('[feedback-capture] PNG generado desde renderer SVG de respaldo', { width, height, blobSize: blob.size });
      return { blob, width, height, strategy: 'svg-data-fallback' };
    } finally {
      URL.revokeObjectURL(svgUrl);
    }
  }

  async function downloadReportPng(report, options = {}) {
    const png = await captureReportAsPng(report, options);
    triggerDownload(options.filename || 'evaluacion-desempeno.png', png.blob, options);
    return png;
  }

  async function captureReportPngDataUrl(report, options = {}) {
    const png = await captureReportAsPng(report, options);
    return blobToDataUrl(png.blob);
  }

  function renderReport(container, report, options = {}) {
    if (!container || !report) return;
    ensureStyles();

    const header = report.header || {};
    const blocks = orderBlocks(report.block_cards || []);
    const trajectory = report.trajectory_chart || [];
    const recs = report.recommendations || { items: [] };
    const activityName = header.activity_name || 'Compra de un Mustang clásico';
    const durationLabel = durationFromReport(report, trajectory.length);
    const outcome = header.interaction_outcome;
    const agreementReached = outcome === 'agreement_reached';

    container.classList.add('feedback-report-root');
    container.innerHTML = `
      <div class="feedback-dashboard">
        <header class="fb-card fb-header">
          <div>
            <h1 class="fb-title">Evaluación de tu desempeño</h1>
            <div class="fb-case-row">${escapeHtml(activityName)} · ${escapeHtml(durationLabel)}</div>
          </div>
          <div class="fb-header-right">
            <div class="fb-stars" role="img" aria-label="${Number(header.stars_0_5 || 0)} de 5 estrellas">${createStarsMarkup(header.stars_0_5)}</div>
            <div class="fb-score-pill">${Number(header.score_global_100 || 0)} / 100</div>
          </div>
        </header>

        <section class="fb-card fb-result">
          <div class="fb-result-head">
            <h2>Resultado</h2>
            <span class="fb-result-dot ${agreementReached ? 'ok' : 'bad'}" aria-hidden="true"></span>
          </div>
          <p>${escapeHtml(buildResultSummary(outcome, header.summary_2_3_lines))}</p>
        </section>

        <section class="fb-grid-cards" aria-label="Resumen por dimensión"></section>

        <section class="fb-card fb-chart-card">
          <div class="fb-chart-top"><h2>Cercanía al entendimiento</h2></div>
          <p class="fb-chart-hint">Pasa el ratón por encima de cada momento de la conversación para conocer más.</p>
          <div class="fb-chart-shell">
            <svg class="fb-chart" role="img" aria-label="Serie de cercanía al entendimiento por turno"></svg>
            <aside class="fb-turn-tooltip hidden" aria-live="polite"></aside>
          </div>
        </section>

        <section class="fb-card fb-recommendations">
          <h2>Recomendaciones generales</h2>
          <div class="fb-recommendations-grid"></div>
          <div class="fb-empty hidden">No hay recomendaciones relevantes que añadir en este caso.</div>
        </section>
      </div>
    `;

    const blockRoot = container.querySelector('.fb-grid-cards');
    blocks.forEach((section) => {
      const status = normalizeStatus(section.status_visual);
      const checks = getCardChecks(section.checks)
        .map((row) => `<li><span class="fb-item-icon ${row.polarity === 'check' ? 'ok' : 'bad'}">${row.polarity === 'check' ? checkSvg() : crossSvg()}</span><span>${escapeHtml(row.micro_explanation || '')}</span></li>`)
        .join('');
      const card = document.createElement('article');
      card.className = `fb-card fb-skill-card ${status}`;
      card.innerHTML = `
        <div class="fb-skill-top"><h3>${escapeHtml(BLOCK_LABELS[section.block_id] || section.title || '')}</h3><span class="fb-badge ${status}">${escapeHtml(section.status_visual || '')}</span></div>
        <ul>${checks}</ul>
      `;
      blockRoot.appendChild(card);
    });

    const finalRecommendations = (recs.items || []).slice(0, 6);
    const recGrid = container.querySelector('.fb-recommendations-grid');
    const emptyRec = container.querySelector('.fb-empty');

    if (finalRecommendations.length === 0) {
      emptyRec.classList.remove('hidden');
    } else {
      finalRecommendations.forEach((item) => {
        const article = document.createElement('article');
        article.className = 'fb-rec-item';
        article.innerHTML = `
          <h3>${escapeHtml(item.title || recommendationTitle(item.description))}</h3>
          <p>${escapeHtml(item.description || '')}</p>
          ${item.example ? `<div class="fb-rec-example"><p class="fb-rec-user"><strong>Tú</strong> ${escapeHtml(item.example.original_excerpt || '')}</p><p class="fb-rec-better"><strong>Mejora:</strong> ${escapeHtml(item.example.better_rephrase || '')}</p></div>` : ''}
        `;
        recGrid.appendChild(article);
      });
    }

    const chart = container.querySelector('.fb-chart');
    const chartShell = container.querySelector('.fb-chart-shell');
    const tooltip = container.querySelector('.fb-turn-tooltip');
    let stickyIndex = null;

    const hideTooltip = () => {
      if (stickyIndex !== null) return;
      tooltip.classList.add('hidden');
    };

    const showTooltip = (index, event) => {
      const turn = trajectory[index];
      if (!turn) return;
      tooltip.innerHTML = tooltipMarkup(turn, trajectory[index - 1] || null);
      tooltip.classList.remove('hidden');
      placeTooltip(tooltip, chartShell, event);
    };

    if (trajectory.length > 0) {
      renderChart(chart, trajectory, {
        onHover: (idx, ev) => showTooltip(idx, ev),
        onLeave: () => hideTooltip(),
        onClick: (idx, ev) => {
          stickyIndex = stickyIndex === idx ? null : idx;
          if (stickyIndex === null) {
            tooltip.classList.add('hidden');
            return;
          }
          showTooltip(idx, ev);
        },
      });

      chartShell.addEventListener('mouseleave', () => {
        if (stickyIndex === null) tooltip.classList.add('hidden');
      });

      if (container.isConnected) {
        if (typeof container.__feedbackOutsideClickCleanup === 'function') {
          container.__feedbackOutsideClickCleanup();
        }
        const onDocumentClick = (ev) => {
          if (!(ev.target instanceof Node) || !chartShell.contains(ev.target)) {
            stickyIndex = null;
            tooltip.classList.add('hidden');
          }
        };
        document.addEventListener('click', onDocumentClick);
        container.__feedbackOutsideClickCleanup = () => {
          document.removeEventListener('click', onDocumentClick);
          container.__feedbackOutsideClickCleanup = null;
        };
      }
    } else {
      chart.remove();
      tooltip.classList.remove('hidden');
      tooltip.innerHTML = '<p>No hay trayectoria disponible.</p>';
      tooltip.style.position = 'static';
      tooltip.style.width = '100%';
      tooltip.style.pointerEvents = 'auto';
      tooltip.style.boxShadow = 'none';
      tooltip.style.border = '1px solid #E4E7EC';
    }

    if (typeof options.onRendered === 'function') options.onRendered();
  }

  global.FeedbackReportView = {
    renderReport,
    serializeReportToHtml,
    serializeReportToJson,
    downloadReportHtml,
    downloadReportJson,
    captureReportAsPng,
    captureReportPngDataUrl,
    downloadReportPng,
  };
})(window);
