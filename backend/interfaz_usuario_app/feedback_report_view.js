(function attachFeedbackReportView(global) {
  const NS = 'http://www.w3.org/2000/svg';

  function ensureStyles() {
    if (document.getElementById('feedback-report-view-styles')) return;
    const style = document.createElement('style');
    style.id = 'feedback-report-view-styles';
    style.textContent = `
      :root {
        --bg: #FFFFFF;
        --card: #FFFFFF;
        --border: #E4E7EC;
        --text: #101828;
        --muted: #475467;
        --muted2: #98A2B3;
        --shadow: 0 8px 24px rgba(16,24,40,0.06);
        --radius-lg: 18px;
        --radius-md: 14px;
        --ok: #16A34A;
        --warn: #D97706;
        --bad: #DC2626;
        --focus: #2E90FA;
      }

      .feedback-report-root * { box-sizing: border-box; }
      .feedback-report-root {
        min-height: 100vh;
        background: var(--bg);
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        color: var(--text);
      }

      .feedback-dashboard {
        width: min(1200px, 100%);
        margin: 0 auto;
        padding: 28px 28px 42px;
        display: grid;
        gap: 18px;
      }

      .fb-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow);
      }

      .fb-header { padding: 24px 24px 20px; display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
      .fb-header h1 { margin: 0; font-size: 34px; font-weight: 700; line-height: 1.15; }
      .fb-subtitle { margin: 8px 0 0; color: var(--muted); font-size: 19px; }
      .fb-header-right { display: inline-flex; align-items: center; gap: 12px; }
      .fb-stars { display: inline-flex; gap: 4px; }
      .fb-score-pill { border: 1px solid var(--border); border-radius: 999px; padding: 8px 12px; font-size: 22px; font-weight: 700; }

      .fb-result { padding: 22px 24px; }
      .fb-result h2, .fb-chart-top h2, .fb-recommendations h2 { margin: 0; font-size: 24px; line-height: 1.2; }
      .fb-result p { margin: 12px 0 0; font-size: 17px; line-height: 1.6; color: var(--muted); }

      .fb-grid-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
      .fb-skill-card { padding: 20px; border-width: 2.5px; }
      .fb-skill-card.ok { border-color: var(--ok); }
      .fb-skill-card.bad { border-color: var(--bad); }
      .fb-skill-card.warn { border-color: var(--warn); }
      .fb-skill-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .fb-skill-top h3 { margin: 0; font-size: 19px; line-height: 1.3; }

      .fb-badge { display: inline-flex; align-items: center; height: 28px; padding: 4px 11px; border-radius: 999px; font-size: 13px; font-weight: 700; color: #fff; text-transform: capitalize; border: none; }
      .fb-badge.ok { background: var(--ok); }
      .fb-badge.warn { background: var(--warn); }
      .fb-badge.bad { background: var(--bad); }

      .fb-skill-card ul { margin: 14px 0 0; padding: 0; list-style: none; display: grid; gap: 10px; }
      .fb-skill-card li { display: grid; grid-template-columns: 20px 1fr; gap: 10px; align-items: flex-start; font-size: 15px; line-height: 1.45; color: var(--muted); }
      .fb-item-icon { width: 20px; height: 20px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; }
      .fb-item-icon.ok { color: var(--ok); background: rgba(22,163,74,0.12); }
      .fb-item-icon.bad { color: var(--bad); background: rgba(220,38,38,0.12); }

      .fb-chart-card { padding: 20px; }
      .fb-chart-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
      .fb-chart-subtitle { margin: 8px 0 0; color: var(--muted); font-size: 15px; }
      .fb-chart-layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(320px, 1fr); gap: 16px; align-items: start; }
      .fb-chart-shell { width: 100%; aspect-ratio: 900 / 330; border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: #fff; }
      .fb-chart { width: 100%; height: auto; display: block; }

      .fb-detail-panel { border: 1px solid #D0D5DD; border-radius: var(--radius-md); background: #fff; padding: 16px; min-height: 280px; }
      .fb-detail-panel h4 { margin: 0 0 10px; font-size: 17px; }
      .fb-detail-line { margin: 0; font-size: 15px; line-height: 1.5; color: var(--muted); }
      .fb-detail-line + .fb-detail-line { margin-top: 8px; }

      .fb-recommendations { padding: 20px; }
      .fb-recommendations-intro { margin: 8px 0 0; color: var(--muted); font-size: 15px; }
      .fb-recommendations-grid { margin-top: 14px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
      .fb-rec-item { border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
      .fb-rec-item h3 { margin: 0; font-size: 16px; }
      .fb-rec-item p { margin: 8px 0 0; font-size: 15px; color: var(--muted); }
      .fb-rec-example { margin-top: 10px; border: 1px solid #D0D5DD; border-radius: 10px; background: #FCFCFD; padding: 10px; }
      .fb-rec-example p { margin: 6px 0 0; font-size: 14px; }
      .fb-empty { margin-top: 14px; border: 1px dashed #D0D5DD; border-radius: 12px; padding: 14px; color: var(--muted); font-size: 15px; }

      .fb-axis-label { font-size: 12px; fill: #98A2B3; }

      @media (max-width: 1024px) {
        .fb-chart-layout { grid-template-columns: 1fr; }
      }
      @media (max-width: 880px) {
        .feedback-dashboard { padding: 16px; }
        .fb-grid-cards, .fb-recommendations-grid { grid-template-columns: 1fr; }
        .fb-header { flex-direction: column; }
      }
    `;
    document.head.appendChild(style);
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
            : 'color:var(--muted2);fill:none;stroke:currentColor;stroke-width:1.6;'
        }"><path d="M12 3.5l2.87 5.82 6.43.93-4.65 4.53 1.1 6.4L12 18.13l-5.75 3.05 1.1-6.4L2.7 10.25l6.43-.93L12 3.5z"/></svg>`;
      })
      .join('');
  }

  function colorForScore(score) {
    if (score >= 67) return '#16A34A';
    if (score >= 34) return '#D97706';
    return '#DC2626';
  }

  function resultSummary(outcome, summary) {
    const objectiveByOutcome = {
      agreement_reached: 'Lograste cerrar el objetivo principal: sí hubo acuerdo.',
      partial_progress: 'Avanzaste hacia el objetivo, pero el acuerdo quedó parcial.',
      no_agreement: 'No llegaste al acuerdo final en este intento.',
      blocked: 'La conversación se bloqueó antes de cerrar el objetivo.',
    };
    const objective = objectiveByOutcome[outcome] || 'Este fue el resultado frente al objetivo de la negociación.';
    return `${objective} ${summary || ''}`.trim();
  }

  function renderChart(svg, series, onSelect, getSelected) {
    const width = 900;
    const height = 330;
    const pad = { top: 18, right: 18, bottom: 40, left: 20 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const xFor = (idx) => pad.left + (idx / Math.max(1, series.length - 1)) * innerW;
    const yFor = (value) => pad.top + ((100 - value) / 100) * innerH;

    svg.innerHTML = '';

    const zones = [
      { from: 0, to: 33, color: 'rgba(220,38,38,0.12)' },
      { from: 33, to: 66, color: 'rgba(217,119,6,0.11)' },
      { from: 66, to: 100, color: 'rgba(22,163,74,0.12)' },
    ];
    zones.forEach((zone) => {
      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', String(pad.left));
      rect.setAttribute('y', String(yFor(zone.to)));
      rect.setAttribute('width', String(innerW));
      rect.setAttribute('height', String(Math.abs(yFor(zone.from) - yFor(zone.to))));
      rect.setAttribute('fill', zone.color);
      svg.appendChild(rect);
    });

    [20, 40, 60, 80].forEach((n) => {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', String(pad.left)); line.setAttribute('x2', String(width - pad.right));
      line.setAttribute('y1', String(yFor(n))); line.setAttribute('y2', String(yFor(n)));
      line.setAttribute('stroke', '#E4E7EC'); line.setAttribute('stroke-width', '1');
      svg.appendChild(line);
    });

    for (let i = 0; i < series.length - 1; i += 1) {
      const seg = document.createElementNS(NS, 'line');
      seg.setAttribute('x1', String(xFor(i)));
      seg.setAttribute('y1', String(yFor(series[i])));
      seg.setAttribute('x2', String(xFor(i + 1)));
      seg.setAttribute('y2', String(yFor(series[i + 1])));
      seg.setAttribute('stroke', colorForScore((series[i] + series[i + 1]) / 2));
      seg.setAttribute('stroke-width', '3.4');
      seg.setAttribute('stroke-linecap', 'round');
      svg.appendChild(seg);
    }

    series.forEach((v, i) => {
      const p = document.createElementNS(NS, 'circle');
      p.setAttribute('cx', String(xFor(i)));
      p.setAttribute('cy', String(yFor(v)));
      p.setAttribute('r', '5.6');
      p.setAttribute('fill', '#fff');
      p.setAttribute('stroke', colorForScore(v));
      p.setAttribute('stroke-width', '3');
      p.style.cursor = 'pointer';
      p.dataset.turnIndex = String(i);
      p.addEventListener('mouseenter', () => onSelect(i));
      p.addEventListener('click', () => onSelect(i));
      svg.appendChild(p);
    });

    const xLabelA = document.createElementNS(NS, 'text');
    xLabelA.setAttribute('x', String(pad.left)); xLabelA.setAttribute('y', String(height - 12)); xLabelA.setAttribute('class', 'fb-axis-label');
    xLabelA.textContent = 'Inicio'; svg.appendChild(xLabelA);
    const xLabelB = document.createElementNS(NS, 'text');
    xLabelB.setAttribute('x', String(width - 50)); xLabelB.setAttribute('y', String(height - 12)); xLabelB.setAttribute('class', 'fb-axis-label');
    xLabelB.textContent = 'Final'; svg.appendChild(xLabelB);

    updateChartSelection(svg, getSelected());
  }

  function updateChartSelection(svg, selectedIdx) {
    svg.querySelectorAll('circle[data-turn-index]').forEach((circle) => {
      const idx = Number(circle.dataset.turnIndex);
      if (idx === selectedIdx) {
        circle.setAttribute('r', '8');
        circle.setAttribute('fill', circle.getAttribute('stroke') || '#2E90FA');
      } else {
        circle.setAttribute('r', '5.6');
        circle.setAttribute('fill', '#fff');
      }
    });
  }

  function impactLabel(turn) {
    if (turn?.direction === 'up') return 'Este turno sí te acercó al entendimiento.';
    if (turn?.direction === 'down') return 'Este turno te alejó del entendimiento.';
    return 'Este turno casi no movió la negociación.';
  }

  function buildDetailPanel(turn) {
    return `
      <h4>Turno ${Number(turn?.turn_index || 0)}</h4>
      <p class="fb-detail-line"><strong>Tú dijiste:</strong> ${escapeHtml(turn?.user_excerpt || '')}</p>
      <p class="fb-detail-line"><strong>La otra parte respondió:</strong> ${escapeHtml(turn?.counterpart_excerpt || '')}</p>
      <p class="fb-detail-line"><strong>Impacto:</strong> ${escapeHtml(impactLabel(turn))}</p>
      <p class="fb-detail-line"><strong>Por qué:</strong> ${escapeHtml(turn?.impact_reason || '')}</p>
      <p class="fb-detail-line"><strong>Qué recalculó la otra parte:</strong> ${escapeHtml(turn?.counterpart_thought_effect || '')}</p>
    `;
  }

  function getCardChecks(checks = []) {
    const trimmed = checks.slice(0, 4);
    if (trimmed.length > 0) return trimmed;
    return [{ polarity: 'check', micro_explanation: 'No hay observaciones críticas en este bloque.' }];
  }

  function recommendationTitle(text, index) {
    const pieces = String(text || '').split(':');
    const first = (pieces[0] || '').trim();
    if (first && first.length <= 48) return first;
    return `Punto de mejora ${index + 1}`;
  }

  function renderReport(container, report, options = {}) {
    if (!container || !report) return;
    ensureStyles();

    const header = report.header || {};
    const blocks = report.block_cards || [];
    const trajectory = report.trajectory_chart || [];
    const recs = report.recommendations || { general: [], correction_cases: [] };
    const activityName = header.activity_name || 'Compra de un Mustang clásico';
    const score = Number(header.score_global_100 || 0);

    container.classList.add('feedback-report-root');
    container.innerHTML = `
      <div class="feedback-dashboard">
        <header class="fb-card fb-header">
          <div>
            <h1>Evaluación de tu desempeño</h1>
            <p class="fb-subtitle">${escapeHtml(activityName)}</p>
          </div>
          <div class="fb-header-right">
            <div class="fb-stars" role="img" aria-label="${Number(header.stars_0_5 || 0)} de 5 estrellas">${createStarsMarkup(header.stars_0_5)}</div>
            <div class="fb-score-pill">${score} / 100</div>
          </div>
        </header>

        <section class="fb-card fb-result">
          <h2>Resultado</h2>
          <p>${escapeHtml(resultSummary(header.interaction_outcome, header.summary_2_3_lines))}</p>
        </section>

        <section class="fb-grid-cards" aria-label="Resumen por dimensión"></section>

        <section class="fb-card fb-chart-card">
          <div class="fb-chart-top"><h2>Cercanía al entendimiento</h2></div>
          <p class="fb-chart-subtitle">Cuando la línea sube te acercas; cuando baja te alejas.</p>
          <div class="fb-chart-layout">
            <div class="fb-chart-shell">
              <svg class="fb-chart" viewBox="0 0 900 330" preserveAspectRatio="none" role="img" aria-label="Serie de cercanía al entendimiento por turno"></svg>
            </div>
            <aside class="fb-detail-panel" aria-live="polite"></aside>
          </div>
        </section>

        <section class="fb-card fb-recommendations">
          <h2>Recomendaciones generales</h2>
          <p class="fb-recommendations-intro">Solo verás los ajustes que realmente te pueden aportar valor.</p>
          <div class="fb-recommendations-grid"></div>
          <div class="fb-empty hidden">No hay recomendaciones relevantes que añadir en este caso.</div>
        </section>
      </div>
    `;

    const blockRoot = container.querySelector('.fb-grid-cards');
    for (const section of blocks) {
      const status = normalizeStatus(section.status_visual);
      const checks = getCardChecks(section.checks).map((row) => `<li><span class="fb-item-icon ${row.polarity === 'check' ? 'ok' : 'bad'}">${row.polarity === 'check' ? checkSvg() : crossSvg()}</span><span>${escapeHtml(row.micro_explanation || '')}</span></li>`).join('');
      const card = document.createElement('article');
      card.className = `fb-card fb-skill-card ${status}`;
      card.innerHTML = `
        <div class="fb-skill-top"><h3>${escapeHtml(section.title || '')}</h3><span class="fb-badge ${status}">${escapeHtml(section.status_visual || '')}</span></div>
        <ul>${checks}</ul>
      `;
      blockRoot.appendChild(card);
    }

    const combinedRecommendations = [];
    (recs.general || []).forEach((text, idx) => {
      combinedRecommendations.push({ title: recommendationTitle(text, idx), explanation: text, case: recs.correction_cases?.[idx] || null });
    });

    const remainingCases = (recs.correction_cases || []).slice((recs.general || []).length);
    remainingCases.forEach((item, idx) => {
      combinedRecommendations.push({
        title: `Ajuste en turno ${Number(item.turn_index || 0)}`,
        explanation: item.expected_effect || 'Este ajuste puede mejorar tu avance en la negociación.',
        case: item,
      });
    });

    const finalRecommendations = combinedRecommendations.slice(0, 6);
    const recGrid = container.querySelector('.fb-recommendations-grid');
    const emptyRec = container.querySelector('.fb-empty');

    if (finalRecommendations.length === 0) {
      emptyRec.classList.remove('hidden');
    } else {
      finalRecommendations.forEach((item) => {
        const el = document.createElement('article');
        el.className = 'fb-rec-item';
        el.innerHTML = `
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.explanation)}</p>
          ${item.case ? `<div class="fb-rec-example"><p><strong>Turno ${Number(item.case.turn_index || 0)}</strong></p><p><strong>Tu mensaje:</strong> ${escapeHtml(item.case.original_excerpt || '')}</p><p><strong>Mejora propuesta:</strong> ${escapeHtml(item.case.better_rephrase || '')}</p></div>` : ''}
        `;
        recGrid.appendChild(el);
      });
    }

    const chartSeries = trajectory.map((t) => Number(t.agreement_closeness_score_0_100 || 0));
    const svg = container.querySelector('.fb-chart');
    const detailPanel = container.querySelector('.fb-detail-panel');
    let selectedIndex = 0;
    const setSelected = (index) => {
      selectedIndex = Math.max(0, Math.min(index, Math.max(0, trajectory.length - 1)));
      detailPanel.innerHTML = buildDetailPanel(trajectory[selectedIndex]);
      updateChartSelection(svg, selectedIndex);
    };

    if (chartSeries.length > 0) {
      renderChart(svg, chartSeries, setSelected, () => selectedIndex);
      setSelected(0);
    } else {
      svg.remove();
      detailPanel.innerHTML = '<p class="fb-detail-line">No hay trayectoria disponible.</p>';
    }

    if (typeof options.onRendered === 'function') options.onRendered();
  }

  global.FeedbackReportView = { renderReport };
})(window);
