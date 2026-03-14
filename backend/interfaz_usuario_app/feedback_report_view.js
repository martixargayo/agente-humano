(function attachFeedbackReportView(global) {
  const NS = 'http://www.w3.org/2000/svg';

  function ensureStyles() {
    if (document.getElementById('feedback-report-view-styles')) return;
    const style = document.createElement('style');
    style.id = 'feedback-report-view-styles';
    style.textContent = `
      :root {
        --bg: #FAFAFA;
        --card: #FFFFFF;
        --border: #E6E8EB;
        --text: #0B0F14;
        --muted: #667085;
        --muted2: #98A2B3;
        --shadow: 0 8px 30px rgba(11,15,20,0.06);
        --radius-lg: 18px;
        --radius-md: 14px;
        --radius-sm: 10px;
        --ok: #12B76A;
        --okBg: rgba(18,183,106,0.10);
        --warn: #F79009;
        --warnBg: rgba(247,144,9,0.12);
        --bad: #F04438;
        --badBg: rgba(240,68,56,0.12);
        --focus: #2E90FA;
      }

      .feedback-report-root * { box-sizing: border-box; }
      .feedback-report-root {
        min-height: 100vh;
        background: var(--bg);
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        color: var(--text);
      }

      .demo-feedback-dashboard {
        max-width: 1240px;
        margin: 0 auto;
        padding: 28px;
        display: grid;
        gap: 16px;
      }

      .fb-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow);
      }

      .fb-header {
        min-height: 76px;
        padding: 0 22px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .fb-header h1 { margin: 0; font-size: 18px; font-weight: 600; }
      .fb-header p, .muted { margin: 6px 0 0; color: var(--muted); font-size: 12.5px; }
      .fb-header-right { display: inline-flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
      .fb-stars { display: inline-flex; gap: 4px; }

      .fb-score-pill { border: 1px solid var(--border); border-radius: 999px; padding: 7px 10px; font-size: 16px; font-weight: 600; }
      .fb-header-state { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12.5px; }
      .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
      .dot.ok { background: var(--ok); }
      .dot.bad { background: var(--bad); }
      .dot.warn { background: var(--warn); }

      .fb-grid-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
      .fb-skill-card { padding: 18px; border-width: 2.1px; }
      .fb-skill-card.ok { border-color: var(--ok); }
      .fb-skill-card.bad { border-color: var(--bad); }
      .fb-skill-card.warn { border-color: var(--warn); }

      .fb-skill-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .fb-skill-top h2, .fb-chart-top h2 { margin: 0; font-size: 14px; font-weight: 600; }

      .fb-badge { display: inline-flex; align-items: center; height: 24px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); font-size: 12px; }
      .fb-badge.ok { background: var(--okBg); color: var(--ok); }
      .fb-badge.warn { background: var(--warnBg); color: var(--warn); }
      .fb-badge.bad { background: var(--badBg); color: var(--bad); }

      .fb-skill-card ul { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 8px; }
      .fb-skill-card li { display: grid; grid-template-columns: 18px 1fr; gap: 8px; align-items: flex-start; font-size: 12.7px; color: var(--muted); }
      .fb-item-icon { width: 18px; height: 18px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; }
      .fb-item-icon.ok { color: var(--ok); background: var(--okBg); }
      .fb-item-icon.bad { color: var(--bad); background: var(--badBg); }

      .fb-chart-card { padding: 16px; }
      .fb-chart-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
      .fb-chart-layout { display: grid; grid-template-columns: 1fr; gap: 12px; }
      .fb-chart-shell { width: 100%; aspect-ratio: 860 / 260; }
      .fb-chart { width: 100%; height: auto; display: block; }

      .fb-detail-panel {
        position: relative;
        border: 2px solid var(--focus);
        border-radius: var(--radius-md);
        background: #FFFFFF;
        padding: 14px;
        margin-left: 10px;
        max-width: 440px;
      }
      .fb-detail-panel::before { content: ''; position: absolute; top: -10px; left: 22px; width: 0; height: 0; border-left: 9px solid transparent; border-right: 9px solid transparent; border-bottom: 10px solid var(--focus); }
      .fb-detail-panel::after { content: ''; position: absolute; top: -8px; left: 23px; width: 0; height: 0; border-left: 8px solid transparent; border-right: 8px solid transparent; border-bottom: 9px solid #fff; }
      .fb-detail-line { margin: 0; font-size: 13px; line-height: 1.6; }
      .fb-detail-line + .fb-detail-line { margin-top: 6px; }

      .fb-recommendations { padding: 16px; }
      .fb-recommendations-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
      .fb-recommendations h3 { margin: 0; font-size: 14px; font-weight: 600; }
      .fb-numbered-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 12px; }
      .fb-numbered-list li { display: grid; grid-template-columns: 26px 1fr; gap: 10px; }
      .fb-number { width: 26px; height: 26px; border-radius: 50%; background: rgba(46,144,250,0.10); border: 1px solid rgba(46,144,250,0.25); color: var(--focus); font-weight: 600; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
      .fb-numbered-list p, .fb-mini-card p, .fb-close-block p { margin: 4px 0 0; font-size: 12.5px; color: var(--muted); }
      .fb-correct-note { margin: 12px 0; display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }
      .fb-correct-note svg { color: var(--bad); width: 14px; height: 14px; margin-top: 2px; }
      .fb-mini-cards { display: grid; gap: 10px; }
      .fb-mini-card { background: #FFF; border: 1px solid var(--border); border-radius: 14px; padding: 12px; }
      .fb-mini-head { display: flex; align-items: center; justify-content: space-between; }
      .fb-mini-badge { padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); font-size: 12px; color: var(--bad); background: var(--badBg); }
      .fb-better { color: var(--ok); }
      .fb-close-block { margin-top: 16px; border-radius: 14px; border: 1px solid rgba(102,112,133,0.12); background: rgba(102,112,133,0.05); padding: 12px; }
      .fb-close-block h3 { margin: 0 0 6px; }
      .fb-axis-label { fill: var(--muted2); font-size: 11px; }

      @media (max-width: 1023px) {
        .demo-feedback-dashboard { padding: 20px; }
        .fb-grid-cards, .fb-recommendations-grid { grid-template-columns: 1fr; }
      }
      @media (max-width: 767px) {
        .demo-feedback-dashboard { padding: 16px; }
        .fb-header { padding: 18px 22px; align-items: flex-start; flex-direction: column; gap: 12px; }
      }
    `;
    document.head.appendChild(style);
  }

  function escapeHtml(value) {
    return String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  }

  function normalizeStatus(status) {
    if (status === 'solid' || status === 'ok') return 'ok';
    if (status === 'watch' || status === 'warn') return 'warn';
    return 'bad';
  }

  function checkSvg() {
    return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.3 6.1 11.4 13 4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  function crossSvg() {
    return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  }

  function createStarsMarkup(stars) {
    const starCount = Math.max(0, Math.min(5, Number(stars || 0)));
    return [1, 2, 3, 4, 5]
      .map((n) => {
        const filled = n <= starCount;
        return `<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" style="${
          filled
            ? 'opacity:0.85;color:var(--text);fill:currentColor;stroke:none;'
            : 'color:var(--muted2);fill:none;stroke:currentColor;stroke-width:1.6;'
        }"><path d="M12 3.5l2.87 5.82 6.43.93-4.65 4.53 1.1 6.4L12 18.13l-5.75 3.05 1.1-6.4L2.7 10.25l6.43-.93L12 3.5z"/></svg>`;
      })
      .join('');
  }

  function renderChart(svg, series, onSelect, getSelected) {
    const width = 860;
    const height = 260;
    const pad = { top: 16, right: 14, bottom: 32, left: 14 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const xFor = (idx) => pad.left + (idx / Math.max(1, series.length - 1)) * innerW;
    const yFor = (value) => pad.top + ((100 - value) / 100) * innerH;

    svg.innerHTML = '';
    const defs = document.createElementNS(NS, 'defs');
    defs.innerHTML = '<filter id="fbPointShadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="6" stdDeviation="4" flood-color="rgba(11,15,20,0.12)"/></filter>';
    svg.appendChild(defs);

    const baseline = document.createElementNS(NS, 'line');
    baseline.setAttribute('x1', String(pad.left)); baseline.setAttribute('y1', String(height - pad.bottom));
    baseline.setAttribute('x2', String(width - pad.right)); baseline.setAttribute('y2', String(height - pad.bottom));
    baseline.setAttribute('stroke', '#E6E8EB'); baseline.setAttribute('stroke-width', '1');
    svg.appendChild(baseline);

    const path = document.createElementNS(NS, 'path');
    const d = series.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i)} ${yFor(v)}`).join(' ');
    path.setAttribute('d', d); path.setAttribute('fill', 'none'); path.setAttribute('stroke', '#2E90FA'); path.setAttribute('stroke-width', '2.5');
    svg.appendChild(path);

    series.forEach((v, i) => {
      const p = document.createElementNS(NS, 'circle');
      p.setAttribute('cx', String(xFor(i))); p.setAttribute('cy', String(yFor(v))); p.setAttribute('r', '4.8');
      p.setAttribute('fill', '#fff'); p.setAttribute('stroke', '#2E90FA'); p.setAttribute('stroke-width', '2'); p.setAttribute('filter', 'url(#fbPointShadow)');
      p.style.cursor = 'pointer';
      p.dataset.turnIndex = String(i);
      p.addEventListener('mouseenter', () => onSelect(i));
      p.addEventListener('click', () => onSelect(i));
      svg.appendChild(p);
    });

    const xLabelA = document.createElementNS(NS, 'text');
    xLabelA.setAttribute('x', String(pad.left)); xLabelA.setAttribute('y', String(height - 8)); xLabelA.setAttribute('class', 'fb-axis-label');
    xLabelA.textContent = 'Inicio'; svg.appendChild(xLabelA);
    const xLabelB = document.createElementNS(NS, 'text');
    xLabelB.setAttribute('x', String(width - 50)); xLabelB.setAttribute('y', String(height - 8)); xLabelB.setAttribute('class', 'fb-axis-label');
    xLabelB.textContent = 'Final'; svg.appendChild(xLabelB);

    updateChartSelection(svg, getSelected());
  }

  function updateChartSelection(svg, selectedIdx) {
    svg.querySelectorAll('circle[data-turn-index]').forEach((circle) => {
      const idx = Number(circle.dataset.turnIndex);
      if (idx === selectedIdx) {
        circle.setAttribute('r', '6.4');
        circle.setAttribute('fill', '#2E90FA');
      } else {
        circle.setAttribute('r', '4.8');
        circle.setAttribute('fill', '#fff');
      }
    });
  }

  function buildDetailPanel(turn) {
    const user = turn?.user_turn_excerpt || turn?.user_text || '';
    const assistant = turn?.assistant_turn_excerpt || turn?.assistant_text || '';
    return `
      <p class="fb-detail-line"><strong>Tú:</strong> ${escapeHtml(user)}</p>
      <p class="fb-detail-line"><strong>Él:</strong> ${escapeHtml(assistant)}</p>
    `;
  }

  function renderReport(container, report, options = {}) {
    if (!container || !report) return;
    ensureStyles();

    const header = report.header || {};
    const blocks = report.block_cards || [];
    const trajectory = report.trajectory_chart || [];
    const recs = report.recommendations || { general: [], correction_cases: [] };
    const outcome = header.interaction_outcome || 'Sin outcome';
    const outcomeClass = String(outcome).toLowerCase().includes('acuerdo') ? 'ok' : 'warn';

    container.classList.add('feedback-report-root');
    container.innerHTML = `
      <div class="demo-feedback-dashboard">
        <header class="fb-card fb-header">
          <div>
            <h1>Informe de Feedback</h1>
            <p>${escapeHtml(header.summary_2_3_lines || 'Análisis de la conversación')}</p>
          </div>
          <div class="fb-header-right">
            <div class="fb-stars" role="img" aria-label="${Number(header.stars_0_5 || 0)} de 5 estrellas">${createStarsMarkup(header.stars_0_5)}</div>
            <div class="fb-score-pill">${Number(header.score_global_100 || 0)} / 100</div>
            <div class="fb-header-state"><span class="dot ${outcomeClass}"></span>${escapeHtml(outcome)}</div>
          </div>
        </header>

        <section class="fb-grid-cards" aria-label="Resumen por dimensión"></section>

        <section class="fb-card fb-chart-card">
          <div class="fb-chart-top"><h2>Cercanía al entendimiento</h2></div>
          <div class="fb-chart-layout">
            <div class="fb-chart-shell">
              <svg class="fb-chart" viewBox="0 0 860 260" preserveAspectRatio="none" role="img" aria-label="Serie de cercanía al entendimiento por turno"></svg>
            </div>
            <aside class="fb-detail-panel" aria-live="polite"></aside>
          </div>
        </section>

        <section class="fb-card fb-recommendations">
          <div class="fb-recommendations-grid">
            <article>
              <h3>Recomendaciones generales</h3>
              <p class="muted">Acciones concretas para mejorar el próximo intento</p>
              <ol class="fb-numbered-list"></ol>
            </article>
            <article>
              <h3>Momentos a corregir</h3>
              <p class="fb-correct-note"><span>${crossSvg()}</span>${escapeHtml(recs.correction_cases?.length ? 'Situaciones en las que conviene reformular para reducir fricción.' : 'No se detectaron momentos críticos de reformulación.')}</p>
              <div class="fb-mini-cards"></div>
            </article>
          </div>
          <div class="fb-close-block"><div><h3>Frase recomendada de cierre</h3><p>${escapeHtml(report.recommended_closing_phrase || '-')}</p></div></div>
        </section>
      </div>
    `;

    const blockRoot = container.querySelector('.fb-grid-cards');
    for (const section of blocks) {
      const status = normalizeStatus(section.status_visual);
      const checks = (section.checks || []).map((row) => `<li><span class="fb-item-icon ${row.polarity === 'check' ? 'ok' : 'bad'}">${row.polarity === 'check' ? checkSvg() : crossSvg()}</span><span>${escapeHtml(row.micro_explanation || '')}</span></li>`).join('');
      const card = document.createElement('article');
      card.className = `fb-card fb-skill-card ${status}`;
      card.innerHTML = `
        <div class="fb-skill-top"><h2>${escapeHtml(section.title || '')}</h2><span class="fb-badge ${status}">${escapeHtml(section.status_visual || '')}</span></div>
        <ul>${checks}</ul>
      `;
      blockRoot.appendChild(card);
    }

    const recList = container.querySelector('.fb-numbered-list');
    (recs.general || []).forEach((text, idx) => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="fb-number">${idx + 1}</span><div><strong>${escapeHtml(text)}</strong></div>`;
      recList.appendChild(li);
    });

    const miniRoot = container.querySelector('.fb-mini-cards');
    (recs.correction_cases || []).forEach((correction) => {
      const el = document.createElement('div');
      el.className = 'fb-mini-card';
      el.innerHTML = `
        <div class="fb-mini-head"><strong>Turno ${Number(correction.turn_index || 0)}</strong><span class="fb-mini-badge">A corregir</span></div>
        <p><span class="muted">Dijiste:</span> ${escapeHtml(correction.original_excerpt || '')}</p>
        <p><span class="muted">Mejor:</span> <span class="fb-better">${escapeHtml(correction.better_rephrase || '')}</span></p>
      `;
      miniRoot.appendChild(el);
    });

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
