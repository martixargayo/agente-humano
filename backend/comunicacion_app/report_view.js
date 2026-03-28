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
    const sources = resolvePrimaryReportSources(payload);
    const intonation = resolveSpecializedFeedback(sources.audioSpecializedFeedback, {
      title: 'Entonación y pausas',
      fallbackLabel: 'No disponible',
      fallbackReason: 'No hay señal de audio especializada disponible en esta evaluación.',
    });
    const gestures = resolveSpecializedFeedback(sources.visualSpecializedFeedback, {
      title: 'Gesticulación',
      fallbackLabel: 'No disponible',
      fallbackReason: 'No hay señal visual especializada disponible en esta evaluación.',
    });

    return `
      <section class="comm-feedback-root" data-report-root="true">
        <div class="feedback-dashboard">
          <header class="fb-card fb-header">
            <div>
              <h1 class="fb-title">${escapeHtml(sources.header.report_title || 'Evaluación de tu comunicación oral')}</h1>
              <div class="fb-case-row">${escapeHtml(sources.header.activity_name || 'Presentación breve grabada')}</div>
            </div>
            <div class="fb-header-right">
              <div class="fb-stars">${renderStars(sources.header.stars_0_5)}</div>
              <div class="fb-score-pill">${escapeHtml(String(sources.header.score_global_100 || '-'))} / 100</div>
            </div>
          </header>

          <section class="fb-card fb-section">
            <h2>Resumen</h2>
            <p>${escapeHtml(sources.summaryText)}</p>
          </section>

          <section class="fb-grid-cards">
            ${sources.aidaCards.map(renderAidaCard).join('')}
          </section>

          <section class="fb-card fb-section">
            <div class="fb-delivery-stack">
              ${renderSpecializedFeedbackCard(intonation)}
              ${renderSpecializedFeedbackCard(gestures)}
            </div>
          </section>

          <section class="fb-card fb-section">
            <h3>Tu grabación</h3>
            ${renderCommunicationVideoPanel(sources.media, options)}
          </section>

          <section class="fb-card fb-section">
            <h3>Recomendaciones</h3>
            <div class="fb-recommendations-grid">${sources.recommendations.map(renderRecommendation).join('')}</div>
          </section>
        </div>
      </section>
    `;
  }

  function resolvePrimaryReportSources(payload) {
    const header = payload.header || {};
    const globalSynthesis = payload.global_synthesis || {};
    // block_cards remains in `/report` for compatibility, but does not drive
    // this final screen's primary sections anymore.
    return {
      header,
      media: payload.media || {},
      recommendations: payload.recommendations && Array.isArray(payload.recommendations.items) ? payload.recommendations.items : [],
      summaryText: resolveSummaryText(header, globalSynthesis),
      aidaCards: resolveAidaCards(payload.content_aida_feedback),
      audioSpecializedFeedback: payload.audio_specialized_feedback,
      visualSpecializedFeedback: payload.visual_specialized_feedback,
    };
  }

  function renderCommunicationVideoPanel(media, options = {}) {
    const poster = media.poster_frame_ref ? ` poster="${escapeHtml(media.poster_frame_ref)}"` : '';
    const resolvedVideoSrc = resolveCommunicationVideoSrc(media);
    const showSource = options.disableVideo !== true && resolvedVideoSrc;
    return `
      <video class="comm-report__video" controls preload="metadata" playsinline${poster}>
        ${showSource ? `<source src="${escapeHtml(resolvedVideoSrc)}" type="${escapeHtml(media.mime_type || 'video/webm')}" />` : ''}
      </video>
    `;
  }

  function resolveAidaCards(contentAidaFeedback) {
    const source = contentAidaFeedback || {};
    const config = [
      ['attention', 'Atención'],
      ['interest', 'Interés'],
      ['development', 'Desarrollo'],
      ['action', 'Acción'],
    ];
    return config.map(([key, title]) => {
      const block = source[key];
      const hasRealBlock = block && typeof block === 'object';
      const label = String(block?.label || 'mejorable').toLowerCase();
      return {
        title,
        label: hasRealBlock ? label : 'mejorable',
        reason: hasRealBlock
          ? String(block.reason_short || 'Sin observaciones disponibles.')
          : 'No hay evaluación AIDA disponible en esta evaluación.',
        status: mapAidaLabelToStatus(label),
      };
    });
  }

  function resolveSummaryText(header, globalSynthesis) {
    return String(
      header?.summary_2_3_lines
      || globalSynthesis?.summary_short_2_3_lines
      || 'Tu evaluación global ya está disponible.'
    );
  }

  function resolveSpecializedFeedback(raw, options) {
    const score = Number(raw?.score_1_5);
    const hasStructured = Number.isFinite(score) && score >= 1 && score <= 5 && typeof raw?.label === 'string';
    const normalizedScore = hasStructured ? Math.max(1, Math.min(5, Math.round(score))) : null;
    return {
      title: options.title,
      levelLabel: hasStructured ? String(raw.label) : options.fallbackLabel,
      description: hasStructured
        ? String(raw.reason_short || 'Sin detalle disponible.')
        : options.fallbackReason,
      chipClass: hasStructured ? `level-${normalizedScore}` : 'level-na',
    };
  }

  function mapAidaLabelToStatus(label) {
    if (label === 'correcto') return 'ok';
    if (label === 'mal') return 'bad';
    return 'warn';
  }

  function renderAidaCard(card) {
    const badge = card.label === 'correcto' ? 'correcto' : card.label === 'mal' ? 'mal' : 'mejorable';
    return `
      <article class="fb-card fb-skill-card ${escapeHtml(card.status)}">
        <div class="fb-skill-top">
          <h3>${escapeHtml(card.title)}</h3>
          <span class="fb-badge ${escapeHtml(card.status)}">${escapeHtml(badge)}</span>
        </div>
        <p>${escapeHtml(card.reason)}</p>
      </article>
    `;
  }

  function renderSpecializedFeedbackCard(block) {
    return `
      <article class="fb-delivery-card">
        <div class="fb-delivery-top">
          <h4>${escapeHtml(block.title)}</h4>
          <span class="fb-level-chip ${escapeHtml(block.chipClass)}">${escapeHtml(block.levelLabel)}</span>
        </div>
        <p>${escapeHtml(block.description)}</p>
      </article>
    `;
  }

  function renderStars(value) {
    const numeric = Math.max(0, Math.min(5, Number(value || 0)));
    const full = Math.round(numeric);
    return `${'★'.repeat(full)}${'☆'.repeat(5 - full)}`;
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
    return `<article class="fb-rec-item"><h4>${escapeHtml(item.title || '')}</h4><p>${escapeHtml(item.description || '')}</p>${example}</article>`;
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
      const sanitization = sanitizeCaptureCloneForRasterization(clonedRoot);
      if (sanitization.removed_sections > 0 || sanitization.removed_nodes > 0) {
        console.info('[comm-report-capture] Sanitización aplicada antes de rasterizar.', sanitization);
      }
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

  function sanitizeCaptureCloneForRasterization(clonedRoot) {
    if (!clonedRoot || typeof clonedRoot.querySelectorAll !== 'function') {
      return { removed_sections: 0, removed_nodes: 0 };
    }
    const mediaSections = Array.from(clonedRoot.querySelectorAll('.fb-card.fb-section'))
      .filter((section) => section.querySelector('video, audio, iframe, object, embed'));
    mediaSections.forEach((section) => section.remove());
    const mediaNodes = Array.from(clonedRoot.querySelectorAll('video, audio, iframe, object, embed'));
    mediaNodes.forEach((node) => node.remove());
    return {
      removed_sections: mediaSections.length,
      removed_nodes: mediaNodes.length,
    };
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
    const captureFontStack = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
    if (clonedRoot?.style) {
      clonedRoot.style.fontFamily = captureFontStack;
    }
    const captureStyles = collectCaptureStyles(clonedRoot);
    return `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
        <foreignObject width="100%" height="100%">
          <div xmlns="http://www.w3.org/1999/xhtml" class="comm-report-capture-frame">
            <style>
              .comm-report-capture-frame,
              .comm-report-capture-frame * {
                font-family: ${captureFontStack};
              }
              ${captureStyles}
            </style>
            ${clonedRoot.outerHTML}
          </div>
        </foreignObject>
      </svg>
    `;
  }

  function collectCaptureStyles(captureRoot) {
    const chunks = [];
    const sheets = Array.from(global.document?.styleSheets || []);
    const shouldIncludeSelector = (selector) => {
      if (!selector) return false;
      const normalized = selector.trim();
      if (!normalized) return false;
      if (normalized === 'html' || normalized === 'body' || normalized.startsWith(':root')) return true;
      if (!captureRoot || typeof captureRoot.querySelector !== 'function' || typeof captureRoot.matches !== 'function') return true;
      const variants = normalized.split(',').map((value) => value.trim()).filter(Boolean);
      return variants.some((variant) => {
        try {
          return captureRoot.matches(variant) || Boolean(captureRoot.querySelector(variant));
        } catch (_) {
          return false;
        }
      });
    };
    const collectRule = (rule) => {
      const cssText = String(rule?.cssText || '');
      if (!cssText) return;
      if (rule.type === 1) {
        const selector = String(rule.selectorText || '');
        if (shouldIncludeSelector(selector)) chunks.push(cssText);
        return;
      }
      if (rule.type === 4 || rule.type === 12) {
        const nestedRules = Array.from(rule.cssRules || []);
        const nestedChunks = nestedRules
          .map((nestedRule) => {
            if (nestedRule.type !== 1) return '';
            const selector = String(nestedRule.selectorText || '');
            return shouldIncludeSelector(selector) ? String(nestedRule.cssText || '') : '';
          })
          .filter(Boolean);
        if (nestedChunks.length > 0) {
          const prelude = String(rule.conditionText || '').trim();
          const atRuleName = rule.type === 12 ? '@supports' : '@media';
          chunks.push(`${atRuleName} ${prelude}{${nestedChunks.join('\n')}}`);
        }
        return;
      }
      if (rule.type === 5 || rule.type === 7 || rule.type === 8 || rule.type === 16) {
        chunks.push(cssText);
      }
    };
    sheets.forEach((sheet) => {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch (_) {
        return;
      }
      if (!rules) return;
      Array.from(rules).forEach((rule) => collectRule(rule));
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
