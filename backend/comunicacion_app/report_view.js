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
    const videoPanel = payload.video_panel || {};
    const blocks = Array.isArray(payload.block_cards) ? payload.block_cards : [];
    const timeline = payload.timeline && Array.isArray(payload.timeline.segments) ? payload.timeline.segments : [];
    const recommendations = payload.recommendations && Array.isArray(payload.recommendations.items) ? payload.recommendations.items : [];
    return `
      <section class="comm-report" data-report-root="true">
        <header class="comm-report__header">
          <div class="comm-report__hero-copy">
            <p class="comm-report__eyebrow">Informe final · Comunicación</p>
            <h2>${escapeHtml(header.report_title || 'Evaluación de tu comunicación oral')}</h2>
            <p>${escapeHtml(header.summary_2_3_lines || 'Ya puedes leer la evaluación mientras revisas tu vídeo.')}</p>
            <div class="comm-report__score-row">
              <strong>${escapeHtml(String(header.score_global_100 || '-'))}/100</strong>
              <span>${escapeHtml(String(header.stars_0_5 || '-'))} ★</span>
              <span>${escapeHtml(header.activity_name || 'Presentación breve grabada')}</span>
            </div>
          </div>
          ${renderCommunicationVideoPanel(media, videoPanel, options)}
        </header>
        <section class="comm-report__blocks">
          ${blocks.map(renderBlockCard).join('')}
        </section>
        <section class="comm-report__timeline">
          <h3>Timeline</h3>
          <ol>${timeline.map(renderTimelineSegment).join('')}</ol>
        </section>
        <section class="comm-report__recommendations">
          <h3>Recomendaciones</h3>
          <ol>${recommendations.map(renderRecommendation).join('')}</ol>
        </section>
      </section>
    `;
  }

  function renderCommunicationVideoPanel(media, panel, options = {}) {
    const poster = media.poster_frame_ref ? ` poster="${escapeHtml(media.poster_frame_ref)}"` : '';
    const resolvedVideoSrc = resolveCommunicationVideoSrc(media);
    const showSource = options.disableVideo !== true && resolvedVideoSrc;
    return `
      <aside class="comm-report__video-panel">
        <h3>${escapeHtml(panel.title || 'Tu grabación')}</h3>
        <p>${escapeHtml(panel.help_text || 'Reproduce tu vídeo mientras lees la evaluación para contrastar cada observación.')}</p>
        <video class="comm-report__video" controls preload="metadata" playsinline${poster}>
          ${showSource ? `<source src="${escapeHtml(resolvedVideoSrc)}" type="${escapeHtml(media.mime_type || 'video/webm')}" />` : ''}
        </video>
        <dl class="comm-report__video-meta">
          <div><dt>recording_id</dt><dd>${escapeHtml(media.recording_id || '-')}</dd></div>
          <div><dt>video_ref</dt><dd>${escapeHtml(media.video_ref || '-')}</dd></div>
          <div><dt>playback_url</dt><dd>${escapeHtml(media.playback_url || '-')}</dd></div>
        </dl>
      </aside>
    `;
  }

  function resolveCommunicationVideoSrc(media) {
    const playback = String(media && media.playback_url ? media.playback_url : '').trim();
    if (playback) return playback;
    const fallback = String(media && media.video_ref ? media.video_ref : '').trim();
    if (fallback.startsWith('file://')) return '';
    return fallback;
  }

  function renderBlockCard(block) {
    const checks = Array.isArray(block.checks) ? block.checks : [];
    return `
      <article class="comm-report__card comm-report__card--${escapeHtml(block.status_visual || 'mejorable')}">
        <div class="comm-report__card-head">
          <h3>${escapeHtml(block.title || 'Bloque')}</h3>
          <span>${escapeHtml(String(block.score_0_100 ?? '-'))}</span>
        </div>
        <p>${escapeHtml(block.block_verdict || block.summary || '')}</p>
        <ul>${checks.map((item) => `<li>${escapeHtml(item.micro_explanation || '')}</li>`).join('')}</ul>
      </article>
    `;
  }

  function renderTimelineSegment(segment) {
    const signals = Array.isArray(segment.signals) ? segment.signals : [];
    return `<li><strong>${escapeHtml(segment.label || 'Segmento')}</strong> · ${escapeHtml(segment.summary || '')} <span>${signals.map((signal) => escapeHtml(signal)).join(', ')}</span></li>`;
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
