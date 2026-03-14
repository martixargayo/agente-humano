(function attachFeedbackReportView(global) {
  const NS = 'http://www.w3.org/2000/svg';

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

  function helpReason(turn) {
    if (!turn) return '';
    if (turn.direction === 'up') return 'Este turno te acercó al entendimiento.';
    if (turn.direction === 'down') return 'Este turno te alejó del entendimiento.';
    return 'Este turno dejó la negociación casi en el mismo punto.';
  }

  function tooltipMarkup(turn) {
    return `
      <h4>Turno ${Number(turn?.turn_index || 0)}</h4>
      <p><strong>Tú:</strong> ${escapeHtml(turn?.user_excerpt || '')}</p>
      <p><strong>Él:</strong> ${escapeHtml(turn?.counterpart_excerpt || '')}</p>
      <p>${escapeHtml(helpReason(turn))} ${escapeHtml(turn?.impact_reason || '')}</p>
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

  function renderReport(container, report, options = {}) {
    if (!container || !report) return;
    ensureStyles();

    const header = report.header || {};
    const blocks = report.block_cards || [];
    const trajectory = report.trajectory_chart || [];
    const recs = report.recommendations || { general: [], correction_cases: [] };
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
        <div class="fb-skill-top"><h3>${escapeHtml(section.title || '')}</h3><span class="fb-badge ${status}">${escapeHtml(section.status_visual || '')}</span></div>
        <ul>${checks}</ul>
      `;
      blockRoot.appendChild(card);
    });

    const combinedRecommendations = [];
    (recs.general || []).forEach((text, idx) => {
      combinedRecommendations.push({
        title: recommendationTitle(text),
        explanation: text,
        case: recs.correction_cases?.[idx] || null,
      });
    });

    const remainingCases = (recs.correction_cases || []).slice((recs.general || []).length);
    remainingCases.forEach((item) => {
      combinedRecommendations.push({
        title: recommendationTitle(item.expected_effect || 'Te faltó concretar mejor este momento'),
        explanation: item.expected_effect || 'Con este ajuste puedes mejorar el avance en el siguiente intento.',
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
        const article = document.createElement('article');
        article.className = 'fb-rec-item';
        article.innerHTML = `
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.explanation)}</p>
          ${item.case ? `<div class="fb-rec-example"><p class="fb-rec-user"><strong>Tú</strong> ${escapeHtml(item.case.original_excerpt || '')}</p><p class="fb-rec-better"><strong>Mejora:</strong> ${escapeHtml(item.case.better_rephrase || '')}</p></div>` : ''}
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
      tooltip.innerHTML = tooltipMarkup(turn);
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

      document.addEventListener('click', (ev) => {
        if (!(ev.target instanceof Node) || !chartShell.contains(ev.target)) {
          stickyIndex = null;
          tooltip.classList.add('hidden');
        }
      });
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

  global.FeedbackReportView = { renderReport };
})(window);
