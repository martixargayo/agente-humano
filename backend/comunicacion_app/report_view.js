(function attachCommunicationReportView(global) {
  function renderCommunicationReport(root, report, options = {}) {
    if (!root) return;
    root.innerHTML = buildCommunicationReportSnapshotMarkup(report, options);
  }

  function renderCommunicationReportPlaceholder(root, report) {
    if (!root) return;
    const payload = report || {};
    root.innerHTML = `
      <section class="communication-report-placeholder" data-report-placeholder="true">
        <h2>${escapeHtml(payload.title || 'Informe placeholder de comunicación')}</h2>
        <p>${escapeHtml(payload.summary || 'Pipeline mínimo completado. Este informe sigue siendo provisional y honesto.')}</p>
      </section>
    `;
  }

  function buildCommunicationReportSnapshotMarkup(report, options = {}) {
    const payload = report || {};
    const header = payload.header || {};
    const media = payload.media || {};
    const recommendations = payload.recommendations && Array.isArray(payload.recommendations.items) ? payload.recommendations.items : [];
    const blockCards = Array.isArray(payload.block_cards) ? payload.block_cards : [];
    const aidaCards = resolveAidaCards(blockCards);
    const summary = buildImmediateSummary(header, recommendations, blockCards);
    const intonation = resolveIntonationBlock(payload, blockCards, recommendations);
    const gestures = resolveGesturesBlock(payload, blockCards, recommendations);

    return `
      <section class="comm-report-v3" data-report-root="true">
        <header class="comm-v3-card comm-v3-hero">
          <div>
            <p class="comm-report__eyebrow">Informe final · Comunicación</p>
            <h2>${escapeHtml(header.report_title || 'Evaluación de tu comunicación oral')}</h2>
            <p>${escapeHtml(header.activity_name || 'Presentación breve grabada')}</p>
          </div>
          <div class="comm-v3-score">
            <strong>${escapeHtml(String(header.score_global_100 || '-'))}<small>/100</small></strong>
            <div class="comm-v3-stars">${renderStars(header.stars_0_5)}</div>
          </div>
        </header>

        <section class="comm-v3-card comm-v3-summary">
          <h3>Resumen inmediato</h3>
          <p><strong>Por qué esta nota:</strong> ${escapeHtml(summary.why)}</p>
          <p><strong>Lo más fuerte:</strong> ${escapeHtml(summary.good)}</p>
          <p><strong>Prioridad de mejora:</strong> ${escapeHtml(summary.improve)}</p>
        </section>

        <section class="comm-v3-card">
          <h3>AIDA</h3>
          <div class="comm-v3-aida">
            ${aidaCards.map(renderAidaCard).join('')}
          </div>
        </section>

        <section class="comm-v3-card comm-v3-meter">
          <h3>Entonación</h3>
          <div class="comm-v3-meter-bars">${renderMeterBars(intonation.level)}</div>
          <p>${escapeHtml(intonation.description)}</p>
        </section>

        <section class="comm-v3-card">
          <h3>Gestos y presencia visual</h3>
          <p><strong>Nivel:</strong> ${escapeHtml(gestures.level_label)}</p>
          <p>${escapeHtml(gestures.description)}</p>
        </section>

        <section class="comm-v3-card">
          <h3>Tu grabación</h3>
          ${renderCommunicationVideoPanel(media, options)}
        </section>

        <section class="comm-v3-card comm-report__recommendations">
          <h3>Recomendaciones</h3>
          <ol>${recommendations.map(renderRecommendation).join('')}</ol>
        </section>
      </section>
    `;
  }

  function renderCommunicationVideoPanel(media, options = {}) {
    const poster = media.poster_frame_ref ? ` poster="${escapeHtml(media.poster_frame_ref)}"` : '';
    const resolvedVideoSrc = resolveCommunicationVideoSrc(media);
    const showSource = options.disableVideo !== true && resolvedVideoSrc;
    return `
      <video class="comm-report__video" controls preload="metadata" playsinline${poster}>
        ${showSource ? `<source src="${escapeHtml(resolvedVideoSrc)}" type="${escapeHtml(media.mime_type || 'video/webm')}" />` : ''}
      </video>
      <dl class="comm-report__video-meta">
        <div><dt>recording_id</dt><dd>${escapeHtml(media.recording_id || '-')}</dd></div>
        <div><dt>video_ref</dt><dd>${escapeHtml(media.video_ref || '-')}</dd></div>
      </dl>
    `;
  }

  function resolveAidaCards(blockCards) {
    const fallbackTitles = ['Atención', 'Interés', 'Desarrollo', 'Acción'];
    const cards = fallbackTitles.map((title, index) => {
      const source = blockCards[index] || {};
      return {
        title,
        score: Number.isFinite(source.score_0_100) ? source.score_0_100 : null,
        verdict: source.block_verdict || source.summary || 'Sección preparada; pendiente de mayor granularidad en el contrato actual.',
        status: normalizeStatus(source.status_visual, source.score_0_100),
      };
    });
    return cards;
  }

  function buildImmediateSummary(header, recommendations, blockCards) {
    const why = header.summary_2_3_lines || 'La nota combina contenido, delivery y presencia visual observada en la grabación.';
    const bestCard = [...blockCards].sort((a, b) => Number(b.score_0_100 || 0) - Number(a.score_0_100 || 0))[0];
    const worstCard = [...blockCards].sort((a, b) => Number(a.score_0_100 || 0) - Number(b.score_0_100 || 0))[0];
    const good = bestCard ? `${bestCard.title || 'Bloque fuerte'}: ${bestCard.block_verdict || bestCard.summary || 'buen desempeño relativo.'}` : 'Estructura general consistente.';
    const improve = recommendations[0]?.description || (worstCard ? `${worstCard.title || 'Bloque crítico'}: prioriza una mejora concreta en esta área.` : 'Define una prioridad de mejora y practícala en la siguiente toma.');
    return { why, good, improve };
  }

  function resolveIntonationBlock(payload, blocks, recommendations) {
    const candidate = findByKeyword(blocks, ['enton', 'voz', 'ritmo']) || findByKeyword(recommendations, ['enton', 'voz', 'ritmo']);
    const score = Number(candidate?.score_0_100 || candidate?.score || 60);
    const level = Math.max(1, Math.min(5, Math.round(score / 20)));
    return {
      level,
      description: candidate?.description || candidate?.summary || candidate?.block_verdict || 'Valoración simplificada de entonación basada en señales disponibles en el reporte actual.',
    };
  }

  function resolveGesturesBlock(payload, blocks, recommendations) {
    const candidate = findByKeyword(blocks, ['gest', 'visual', 'presencia']) || findByKeyword(recommendations, ['gest', 'visual', 'presencia']);
    const score = Number(candidate?.score_0_100 || candidate?.score || 60);
    const level = Math.max(1, Math.min(5, Math.round(score / 20)));
    return {
      level_label: `${level}/5`,
      description: candidate?.description || candidate?.summary || candidate?.block_verdict || 'Bloque visual en fallback honesto: preparado para enriquecerse cuando el contrato aporte más detalle de gestualidad.',
    };
  }

  function findByKeyword(items, keywords) {
    return (items || []).find((item) => {
      const raw = `${item?.title || ''} ${item?.description || ''} ${item?.summary || ''}`.toLowerCase();
      return keywords.some((keyword) => raw.includes(keyword));
    });
  }

  function normalizeStatus(raw, score) {
    if (raw === 'correcto') return 'ok';
    if (raw === 'mejorable') return 'warn';
    if (raw === 'placeholder') return 'neutral';
    if (Number.isFinite(score)) {
      if (score >= 75) return 'ok';
      if (score >= 50) return 'warn';
      return 'bad';
    }
    return 'neutral';
  }

  function renderAidaCard(card) {
    const scoreText = Number.isFinite(card.score) ? `${card.score}/100` : 'Sin score';
    return `
      <article class="comm-v3-card comm-v3-aida-card--${escapeHtml(card.status)}">
        <h4>${escapeHtml(card.title)}</h4>
        <p><strong>${escapeHtml(scoreText)}</strong></p>
        <p>${escapeHtml(card.verdict)}</p>
      </article>
    `;
  }

  function renderMeterBars(level) {
    const safe = Math.max(1, Math.min(5, Number(level || 1)));
    return new Array(5).fill(0).map((_, index) => `<span class="${index < safe ? 'active' : ''}" style="height:${35 + (index * 10)}%"></span>`).join('');
  }

  function renderStars(value) {
    const numeric = Math.max(0, Math.min(5, Number(value || 0)));
    const full = Math.round(numeric);
    return `${'★'.repeat(full)}${'☆'.repeat(5 - full)} <span>${escapeHtml(String(value || 0))}/5</span>`;
  }

  function resolveCommunicationVideoSrc(media) {
    const playback = String(media && media.playback_url ? media.playback_url : '').trim();
    if (playback) return playback;
    const fallback = String(media && media.video_ref ? media.video_ref : '').trim();
    if (fallback.startsWith('file://')) return '';
    return fallback;
  }

  function renderRecommendation(item) {
    const example = item.example
      ? `<p class="comm-report__example"><strong>Ejemplo:</strong> ${escapeHtml(item.example.better_rephrase || '')}</p>`
      : '';
    return `<li><strong>${escapeHtml(item.title || '')}</strong><p>${escapeHtml(item.description || '')}</p>${example}</li>`;
  }

  function serializeCommunicationReportToHtml(report) {
    const markup = buildCommunicationReportSnapshotMarkup(report, { disableVideo: false });
    return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Communication report</title></head><body>${markup}</body></html>`;
  }

  async function captureCommunicationReportPngDataUrl(report, options = {}) {
    try {
      return await captureCommunicationReportPngDataUrlFromDom(report, options);
    } catch (error) {
      console.warn('[comm-report-capture] Falló captura DOM real; se usará fallback sintético.', error);
      return buildCommunicationReportSyntheticFallbackPngDataUrl(report, options);
    }
  }

  async function captureCommunicationReportPngDataUrlFromDom(report, options = {}) {
    const attached = attachDetachedCaptureRootIfNeeded(report, options);
    const captureRoot = attached.captureRoot;
    const cleanup = attached.cleanup;
    try {
      await waitForCaptureStability(captureRoot);
      const { width, height } = deriveCaptureDimensions(captureRoot, options);
      if (width <= 0 || height <= 0) throw new Error(`Root de captura inválido (${width}x${height})`);
      const clonedRoot = captureRoot.cloneNode(true);
      clonedRoot.style.margin = '0';
      const svgMarkup = buildCaptureSvgMarkup(clonedRoot, width, height);
      const svgDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`;
      const image = await loadImage(svgDataUrl);
      const canvas = global.document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas 2D no disponible');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(image, 0, 0, width, height);
      return canvas.toDataURL('image/png');
    } finally {
      cleanup();
    }
  }

  function attachDetachedCaptureRootIfNeeded(report, options = {}) {
    const liveRoot = options.rootElement && options.rootElement.isConnected
      ? options.rootElement.querySelector('[data-report-root="true"]') || options.rootElement
      : null;
    if (liveRoot && liveRoot.isConnected) {
      return {
        captureRoot: liveRoot,
        cleanup: () => {},
      };
    }
    const detachedRoot = global.document.createElement('div');
    detachedRoot.style.position = 'fixed';
    detachedRoot.style.left = '0';
    detachedRoot.style.top = '0';
    detachedRoot.style.opacity = '0';
    detachedRoot.style.pointerEvents = 'none';
    detachedRoot.style.zIndex = '-1';
    detachedRoot.style.width = `${Math.max(1180, Number(options.width) || 1180)}px`;
    renderCommunicationReport(detachedRoot, report, options);
    global.document.body.appendChild(detachedRoot);
    return {
      captureRoot: detachedRoot.querySelector('[data-report-root="true"]') || detachedRoot,
      cleanup: () => detachedRoot.remove(),
    };
  }

  async function waitForCaptureStability(root) {
    if (!root) return;
    if (global.document?.fonts?.ready) {
      try {
        await global.document.fonts.ready;
      } catch (_) {
        // Fuentes no bloqueantes.
      }
    }
    await waitForRaf();
    await waitForRaf();
    await waitForTimeout(60);
  }

  function deriveCaptureDimensions(root, options = {}) {
    const rect = typeof root.getBoundingClientRect === 'function'
      ? root.getBoundingClientRect()
      : { width: 0, height: 0 };
    const preferredWidth = Math.max(
      Number(options.width) || 0,
      Math.ceil(rect.width || 0),
      Math.ceil(root.scrollWidth || 0),
      1180
    );
    const preferredHeight = Math.max(
      Number(options.height) || 0,
      Math.ceil(rect.height || 0),
      Math.ceil(root.scrollHeight || 0),
      720
    );
    return {
      width: preferredWidth,
      height: preferredHeight,
    };
  }

  function buildCaptureSvgMarkup(clonedRoot, width, height) {
    return `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
        <foreignObject width="100%" height="100%">
          <div xmlns="http://www.w3.org/1999/xhtml">
            <style>${collectCaptureStyles()}</style>
            ${clonedRoot.outerHTML}
          </div>
        </foreignObject>
      </svg>
    `;
  }

  function collectCaptureStyles() {
    const preferredSelectors = ['.comm-report', '.comm-v3', '.communication-report-placeholder', '[data-report-root="true"]'];
    const chunks = [];
    const sheets = Array.from(global.document?.styleSheets || []);
    sheets.forEach((sheet) => {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch (_) {
        return;
      }
      if (!rules) return;
      Array.from(rules).forEach((rule) => {
        const cssText = String(rule.cssText || '');
        if (!cssText || cssText.startsWith('@import')) return;
        const selector = String(rule.selectorText || '');
        if (!selector || preferredSelectors.some((candidate) => selector.includes(candidate))) {
          chunks.push(cssText);
        }
      });
    });
    return chunks.join('\n');
  }

  function waitForRaf() {
    return new Promise((resolve) => global.requestAnimationFrame(() => resolve()));
  }

  function waitForTimeout(ms) {
    return new Promise((resolve) => global.setTimeout(resolve, ms));
  }

  async function loadImage(src) {
    const img = new global.Image();
    img.decoding = 'sync';
    const loaded = new Promise((resolve, reject) => {
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('No se pudo rasterizar el DOM del informe a PNG.'));
    });
    img.src = src;
    if (typeof img.decode === 'function') {
      try {
        await img.decode();
        return img;
      } catch (_) {
        // continuamos con onload.
      }
    }
    return loaded;
  }

  function buildCommunicationReportSyntheticFallbackPngDataUrl(report, options = {}) {
    const width = options.width || 1200;
    const height = options.height || 720;
    const canvas = global.document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9VEWilQAAAAASUVORK5CYII=';
    }
    const header = report && report.header ? report.header : {};
    const recommendations = report && report.recommendations && Array.isArray(report.recommendations.items) ? report.recommendations.items : [];
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#101828';
    ctx.font = 'bold 34px sans-serif';
    ctx.fillText(header.report_title || 'Evaluación de tu comunicación oral', 48, 72);
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#475467';
    wrapText(ctx, header.summary_2_3_lines || 'Snapshot PNG simplificado del informe de comunicación.', 48, 120, width - 96, 30);
    ctx.fillStyle = '#1d4ed8';
    ctx.font = 'bold 28px sans-serif';
    ctx.fillText(`Score global: ${String(header.score_global_100 || '-')}/100`, 48, 220);
    ctx.fillStyle = '#101828';
    ctx.font = '22px sans-serif';
    ctx.fillText('Recomendaciones principales', 48, 290);
    ctx.font = '18px sans-serif';
    recommendations.slice(0, 3).forEach((item, index) => {
      wrapText(ctx, `• ${item.title}: ${item.description}`, 48, 340 + (index * 90), width - 96, 26);
    });
    return canvas.toDataURL('image/png');
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = String(text || '').split(/\s+/).filter(Boolean);
    let line = '';
    let currentY = y;
    words.forEach((word) => {
      const candidate = line ? `${line} ${word}` : word;
      if (ctx.measureText(candidate).width > maxWidth && line) {
        ctx.fillText(line, x, currentY);
        line = word;
        currentY += lineHeight;
      } else {
        line = candidate;
      }
    });
    if (line) {
      ctx.fillText(line, x, currentY);
    }
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  }

  global.CommunicationReportView = {
    buildCommunicationReportSnapshotMarkup,
    captureCommunicationReportPngDataUrl,
    renderCommunicationReport,
    renderCommunicationReportPlaceholder,
    renderCommunicationVideoPanel,
    serializeCommunicationReportToHtml,
  };
})(window);
