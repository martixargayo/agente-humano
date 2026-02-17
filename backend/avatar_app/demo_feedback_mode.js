const DEMO_FORCED_REPLIES = [
  'Si claro Lluís, dime.',
  'No es que no quiera compartirla. Muchas veces todavía la estoy revisando y no quiero enviarte algo incompleto.',
  'Entonces… ¿quieres que te pase información que todavía puede ser errónea?',
];

const FEEDBACK_SCORE = 84;
const ACCEPTANCE_THRESHOLD = 80;
const TURN_SCORES = [48, 44, 52, 58, 61, 72, 81, 78, 83, 86, 79, 84, 88, 90, 87, 89, 91, 92, 90, 93, 95];

const FEEDBACK_CARDS = [
  {
    title: 'DESCRIBIR',
    status: 'bad',
    badge: 'A mejorar',
    rows: [
      { tone: 'ok', text: 'Se describió un hecho concreto sin juicios.' },
      { tone: 'bad', text: 'No se generó clima previo antes de entrar en el tema principal.' },
    ],
  },
  {
    title: 'EXPRESAR',
    status: 'ok',
    badge: 'Sólido',
    rows: [
      {
        tone: 'ok',
        text: 'Usaste correctamente el “yo siento” para expresar cómo la situación afecta a tu trabajo, reduciendo la defensividad del interlocutor.',
      },
    ],
  },
  {
    title: 'SUGERIR',
    status: 'ok',
    badge: 'Sólido',
    rows: [{ tone: 'ok', text: 'Propusiste una alternativa lógica y alineada con los intereses de las dos partes.' }],
  },
  {
    title: 'CONSECUENCIAS',
    status: 'ok',
    badge: 'Sólido',
    rows: [
      {
        tone: 'ok',
        text: 'Mencionaste los beneficios que aportaría a ambos disponer de la información antes, para avanzar y planificar mejor.',
      },
    ],
  },
];

const TURN_DETAILS = [
  {
    user: 'hola tienes un momento para hablar conmigo',
    avatar: 'Sí Lluís claro dime',
  },
  ...Array.from({ length: TURN_SCORES.length - 1 }, () => ({ user: '', avatar: '' })),
];

const DEMO_MODE_CONFIG = {
  demo_feedback: {
    forcedReplies: DEMO_FORCED_REPLIES,
  },
};

const DEMO_MODE_ALIASES = {
  'demo-feedback': 'demo_feedback',
  demofeedback: 'demo_feedback',
};

export function createDemoFeedbackMode({
  urlParams = new URLSearchParams(window.location.search),
  onFinish = () => {},
} = {}) {
  let finishHook = onFinish;

  const rawModeName = urlParams.get('mode') || '';
  const normalizedModeName = rawModeName.trim().toLowerCase();
  const modeName = DEMO_MODE_ALIASES[normalizedModeName] || normalizedModeName;
  const config = DEMO_MODE_CONFIG[modeName] || null;

  const state = {
    userTurns: 0,
    forcedRepliesUsed: 0,
    finished: false,
  };

  const ui = {
    hiddenContainers: [],
    finishButton: null,
    feedbackOverlay: null,
  };

  const api = {
    modeName,
    isActive: () => Boolean(config),
    isFinished: () => state.finished,
    getState: () => ({ ...state }),
    mount,
    getReplyForTurn,
    shouldAllowFinish,
    finishConversation,
    ensureFeedbackOverlay,
    getForcedReplyOrBackend: getReplyForTurn,
    state,
  };

  return api;

  function mount({ hiddenContainers = [], onFinish: mountOnFinish } = {}) {
    if (typeof mountOnFinish === 'function') finishHook = mountOnFinish;
    if (!config) return;

    ui.hiddenContainers = hiddenContainers.filter(Boolean);
    ensureFeedbackOverlay();
    ensureFinishButton();
    updateFinishButtonVisibility();
  }

  function shouldAllowFinish() {
    return Boolean(config) && !state.finished;
  }

  function getReplyForTurn() {
    if (!config || state.finished) {
      return { shouldSkipBackend: false, replyText: null };
    }

    state.userTurns += 1;
    updateFinishButtonVisibility();

    if (state.forcedRepliesUsed < config.forcedReplies.length) {
      const replyText = config.forcedReplies[state.forcedRepliesUsed];
      state.forcedRepliesUsed += 1;
      return {
        shouldSkipBackend: true,
        replyText,
        emotion: 'neutral',
        intensity: 1.0,
      };
    }

    return { shouldSkipBackend: false, replyText: null };
  }

  function finishConversation() {
    if (!config || state.finished) return;

    state.finished = true;
    updateFinishButtonVisibility();

    for (const el of ui.hiddenContainers) {
      el.style.display = 'none';
    }

    if (ui.feedbackOverlay) {
      ui.feedbackOverlay.style.display = 'block';
    }

    finishHook();
  }

  function ensureFinishButton() {
    if (ui.finishButton) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Finalizar conversación';
    button.setAttribute('aria-label', 'Finalizar conversación de demo');

    Object.assign(button.style, {
      position: 'fixed',
      right: '24px',
      bottom: '24px',
      zIndex: '30',
      border: '1px solid rgba(148, 163, 184, 0.4)',
      borderRadius: '999px',
      background: 'rgba(15, 23, 42, 0.88)',
      color: '#fff',
      padding: '10px 16px',
      fontSize: '13px',
      fontWeight: '600',
      cursor: 'pointer',
      display: 'none',
      boxShadow: '0 14px 34px rgba(0, 0, 0, 0.45)',
      backdropFilter: 'blur(8px)',
    });

    button.addEventListener('click', finishConversation);
    document.body.appendChild(button);
    ui.finishButton = button;
  }

  function ensureFeedbackOverlay() {
    if (!config || ui.feedbackOverlay) return;

    ensureFeedbackStyles();
    ensureFinishButton();

    const overlay = document.createElement('section');
    overlay.className = 'demo-feedback-overlay';
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-label', 'Feedback final de la demo');

    const dashboard = document.createElement('div');
    dashboard.className = 'demo-feedback-dashboard';

    dashboard.innerHTML = `
      <header class="fb-card fb-header">
        <div>
          <h1>Informe de Feedback</h1>
          <p>Cambio de comportamiento · ${TURN_SCORES.length} turnos · 8:12 min</p>
        </div>
        <div class="fb-header-right">
          <div class="fb-stars" role="img" aria-label="4 de 5 estrellas">${createStarsMarkup()}</div>
          <div class="fb-score-pill">${FEEDBACK_SCORE} / 100</div>
          <div class="fb-header-state"><span class="dot ok"></span>Acuerdo alcanzado</div>
        </div>
      </header>

      <section class="fb-grid-cards" aria-label="Resumen por dimensión"></section>

      <section class="fb-card fb-chart-card">
        <div class="fb-chart-top">
          <h2>Cercanía al entendimiento</h2>
        </div>
        <div class="fb-chart-layout">
          <div class="fb-chart-shell">
            <svg class="fb-chart" viewBox="0 0 860 260" preserveAspectRatio="none" role="img" aria-label="Serie de cercanía al entendimiento por turno"></svg>
          </div>
          <aside class="fb-detail-panel" aria-live="polite">
            <p class="fb-detail-line"><strong>Tú:</strong></p>
            <p class="fb-detail-line"><strong>Él:</strong></p>
          </aside>
        </div>
      </section>

      <section class="fb-card fb-recommendations">
        <div class="fb-recommendations-grid">
          <article>
            <h3>Recomendaciones generales</h3>
            <p class="muted">Acciones concretas para mejorar el próximo intento</p>
            <ol class="fb-numbered-list">
              <li>
                <span class="fb-number">1</span>
                <div><strong>Genera clima antes de entrar al tema</strong><p>Abre con una frase breve de intención y respeto antes de señalar el problema.</p></div>
              </li>
              <li>
                <span class="fb-number">2</span>
                <div><strong>Sustituye ‘tú eres’ por ‘yo siento’</strong><p>Reduce defensividad y mantiene el foco en el impacto.</p></div>
              </li>
              <li>
                <span class="fb-number">3</span>
                <div><strong>Cierra con un compromiso medible</strong><p>Define momento, formato y qué hacer si la información no está completa.</p></div>
              </li>
            </ol>
          </article>
          <article>
            <h3>Momentos a corregir</h3>
            <p class="fb-correct-note"><span>${crossSvg()}</span>Hubo dos situaciones durante la conversación en las que deberías haber usado el ‘yo siento’ en vez del ‘tú eres’.</p>
            <div class="fb-mini-cards">
              <div class="fb-mini-card">
                <div class="fb-mini-head"><strong>Turno 8</strong><span class="fb-mini-badge">A corregir</span></div>
                <p><span class="muted">Dijiste:</span> Es que tú siempre lo dejas para el final.</p>
                <p><span class="muted">Mejor:</span> <span class="fb-better">Yo siento que cuando llega al final del día sin el parte, me cuesta planificar.</span></p>
              </div>
              <div class="fb-mini-card">
                <div class="fb-mini-head"><strong>Turno 13</strong><span class="fb-mini-badge">A corregir</span></div>
                <p><span class="muted">Dijiste:</span> Tú eres muy desordenado con los tiempos.</p>
                <p><span class="muted">Mejor:</span> <span class="fb-better">Yo siento que cuando no tengo el parte temprano se me desordena el día.</span></p>
              </div>
            </div>
          </article>
        </div>
        <div class="fb-close-block">
          <div>
            <h3>Frase recomendada de cierre</h3>
            <p>“¿Te parece si lo dejamos así: me lo envías antes de las 12:00 cada lunes, y si no lo tienes completo me mandas un avance?”</p>
          </div>
        </div>
      </section>
    `;

    const grid = dashboard.querySelector('.fb-grid-cards');
    for (const section of FEEDBACK_CARDS) {
      const card = document.createElement('article');
      card.className = `fb-card fb-skill-card ${section.status}`;

      const rows = section.rows
        .map(
          (row) => `
          <li>
            <span class="fb-item-icon ${row.tone}">${row.tone === 'ok' ? checkSvg() : crossSvg()}</span>
            <span>${row.text}</span>
          </li>
        `,
        )
        .join('');

      card.innerHTML = `
        <div class="fb-skill-top">
          <h2>${section.title}</h2>
          <span class="fb-badge ${section.status}">${section.badge}</span>
        </div>
        <ul>${rows}</ul>
      `;
      grid.appendChild(card);
    }

    const svg = dashboard.querySelector('.fb-chart');
    const detailPanel = dashboard.querySelector('.fb-detail-panel');

    let selectedIndex = 0;

    renderChart(svg, setSelectedTurn, () => selectedIndex);
    setSelectedTurn(0);

    overlay.appendChild(dashboard);
    document.body.appendChild(overlay);
    ui.feedbackOverlay = overlay;

    function setSelectedTurn(index) {
      selectedIndex = index;
      renderDetailPanel(detailPanel, selectedIndex);
      updateChartSelection(svg, selectedIndex);
    }
  }

  function ensureFeedbackStyles() {
    if (document.getElementById('demo-feedback-styles')) return;

    const style = document.createElement('style');
    style.id = 'demo-feedback-styles';
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

      .demo-feedback-overlay * { box-sizing: border-box; }

      .demo-feedback-overlay {
        position: fixed;
        inset: 0;
        z-index: 40;
        display: none;
        overflow: auto;
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

      .fb-header p, .muted {
        margin: 6px 0 0;
        color: var(--muted);
        font-size: 12.5px;
      }

      .fb-header-right { display: inline-flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
      .fb-stars { display: inline-flex; gap: 4px; }

      .fb-score-pill {
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 7px 10px;
        font-size: 16px;
        font-weight: 600;
      }

      .fb-header-state { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12.5px; }
      .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
      .dot.ok { background: var(--ok); }

      .fb-grid-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }

      .fb-skill-card {
        padding: 18px;
        border-width: 2.1px;
      }

      .fb-skill-card.ok { border-color: var(--ok); }
      .fb-skill-card.bad { border-color: var(--bad); }
      .fb-skill-card.warn { border-color: var(--warn); }

      .fb-skill-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .fb-skill-top h2, .fb-chart-top h2 { margin: 0; font-size: 14px; font-weight: 600; }

      .fb-badge {
        display: inline-flex;
        align-items: center;
        height: 24px;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid var(--border);
        font-size: 12px;
      }

      .fb-badge.ok { background: var(--okBg); color: var(--ok); }
      .fb-badge.warn { background: var(--warnBg); color: var(--warn); }
      .fb-badge.bad { background: var(--badBg); color: var(--bad); }

      .fb-skill-card ul { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 8px; }
      .fb-skill-card li { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; line-height: 1.5; }

      .fb-item-icon { width: 14px; height: 14px; flex: 0 0 14px; margin-top: 2px; }
      .fb-item-icon.ok svg { color: var(--ok); }
      .fb-item-icon.bad svg { color: var(--bad); }

      .fb-chart-card, .fb-recommendations { padding: 22px; }
      .fb-chart-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }

      .fb-chart-layout {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
      }

      .fb-chart-shell { height: 260px; width: 100%; }
      .fb-chart { width: 100%; height: 260px; display: block; }

      .fb-detail-panel {
        position: relative;
        border: 2px solid var(--focus);
        border-radius: var(--radius-md);
        background: #FFFFFF;
        padding: 14px;
        margin-top: 0;
        margin-left: 10px;
        max-width: 440px;
      }

      .fb-detail-panel::before {
        content: '';
        position: absolute;
        top: -10px;
        left: 22px;
        width: 0;
        height: 0;
        border-left: 9px solid transparent;
        border-right: 9px solid transparent;
        border-bottom: 10px solid var(--focus);
      }

      .fb-detail-panel::after {
        content: '';
        position: absolute;
        top: -8px;
        left: 23px;
        width: 0;
        height: 0;
        border-left: 8px solid transparent;
        border-right: 8px solid transparent;
        border-bottom: 9px solid #fff;
      }

      .fb-detail-line { margin: 0; font-size: 13px; line-height: 1.6; }
      .fb-detail-line + .fb-detail-line { margin-top: 6px; }

      .fb-recommendations-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
      .fb-recommendations h3 { margin: 0; font-size: 14px; font-weight: 600; }

      .fb-numbered-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 12px; }
      .fb-numbered-list li { display: grid; grid-template-columns: 26px 1fr; gap: 10px; }

      .fb-number {
        width: 26px; height: 26px; border-radius: 50%;
        background: rgba(46,144,250,0.10);
        border: 1px solid rgba(46,144,250,0.25);
        color: var(--focus);
        font-weight: 600;
        font-size: 13px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }

      .fb-numbered-list p, .fb-mini-card p, .fb-close-block p {
        margin: 4px 0 0;
        font-size: 12.5px;
        color: var(--muted);
      }

      .fb-correct-note { margin: 12px 0; display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }
      .fb-correct-note svg { color: var(--bad); width: 14px; height: 14px; margin-top: 2px; }

      .fb-mini-cards { display: grid; gap: 10px; }
      .fb-mini-card { background: #FFF; border: 1px solid var(--border); border-radius: 14px; padding: 12px; }

      .fb-mini-head { display: flex; align-items: center; justify-content: space-between; }

      .fb-mini-badge {
        padding: 2px 8px;
        border-radius: 999px;
        border: 1px solid var(--border);
        font-size: 12px;
        color: var(--bad);
        background: var(--badBg);
      }

      .fb-better { color: var(--ok); }

      .fb-close-block {
        margin-top: 16px;
        border-radius: 14px;
        border: 1px solid rgba(102,112,133,0.12);
        background: rgba(102,112,133,0.05);
        padding: 12px;
      }

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

  function updateFinishButtonVisibility() {
    if (!ui.finishButton) return;
    ui.finishButton.style.display = shouldAllowFinish() ? 'inline-flex' : 'none';
  }
}

function createStarsMarkup() {
  return [1, 2, 3, 4, 5]
    .map((n) => {
      const filled = n <= 4;
      return `<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" style="${
        filled
          ? 'opacity:0.85;color:var(--text);fill:currentColor;stroke:none;'
          : 'color:var(--muted2);fill:none;stroke:currentColor;stroke-width:1.6;'
      }"><path d="M12 3.5l2.87 5.82 6.43.93-4.65 4.53 1.1 6.4L12 18.13l-5.75 3.05 1.1-6.4L2.7 10.25l6.43-.93L12 3.5z"/></svg>`;
    })
    .join('');
}

function checkSvg() {
  return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.3 6.1 11.4 13 4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

function crossSvg() {
  return '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
}

function renderDetailPanel(panel, index) {
  const detail = TURN_DETAILS[index] || { user: '', avatar: '' };
  panel.innerHTML = `
    <p class="fb-detail-line"><strong>Tú:</strong> ${escapeHtml(detail.user || '')}</p>
    <p class="fb-detail-line"><strong>Él:</strong> ${escapeHtml(detail.avatar || '')}</p>
  `;
}

function renderChart(svg, onSelectTurn, getSelectedIndex) {
  const NS = 'http://www.w3.org/2000/svg';
  const width = 860;
  const height = 260;
  const pad = { top: 16, right: 0, bottom: 32, left: 0 };

  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const xFor = (idx) => pad.left + (idx / (TURN_SCORES.length - 1)) * innerW;
  const yFor = (value) => pad.top + ((100 - value) / 100) * innerH;

  svg.innerHTML = '';

  const defs = document.createElementNS(NS, 'defs');
  defs.innerHTML =
    '<filter id="fbPointShadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="6" stdDeviation="4" flood-color="rgba(11,15,20,0.12)"/></filter>';
  svg.appendChild(defs);

  const acceptanceRect = document.createElementNS(NS, 'rect');
  acceptanceRect.setAttribute('x', String(pad.left));
  acceptanceRect.setAttribute('y', String(yFor(100)));
  acceptanceRect.setAttribute('width', String(innerW));
  acceptanceRect.setAttribute('height', String(yFor(ACCEPTANCE_THRESHOLD) - yFor(100)));
  acceptanceRect.setAttribute('fill', 'rgba(18,183,106,0.06)');
  svg.appendChild(acceptanceRect);

  for (const v of [0, 50, ACCEPTANCE_THRESHOLD, 100]) {
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', String(pad.left));
    line.setAttribute('x2', String(width - pad.right));
    line.setAttribute('y1', String(yFor(v)));
    line.setAttribute('y2', String(yFor(v)));
    line.setAttribute('stroke', v === ACCEPTANCE_THRESHOLD ? 'rgba(102,112,133,0.22)' : 'rgba(102,112,133,0.12)');
    svg.appendChild(line);
  }

  const zoneText = document.createElementNS(NS, 'text');
  zoneText.setAttribute('x', String(width - 198));
  zoneText.setAttribute('y', String(yFor(100) + 14));
  zoneText.setAttribute('fill', 'rgba(18,183,106,0.65)');
  zoneText.setAttribute('font-size', '12');
  zoneText.textContent = `Zona de aceptación (${ACCEPTANCE_THRESHOLD}–100)`;
  svg.appendChild(zoneText);

  for (let i = 0; i < TURN_SCORES.length - 1; i += 1) {
    drawSegment(
      svg,
      xFor(i),
      yFor(TURN_SCORES[i]),
      xFor(i + 1),
      yFor(TURN_SCORES[i + 1]),
      TURN_SCORES[i],
      TURN_SCORES[i + 1],
    );
  }

  const pointLayer = document.createElementNS(NS, 'g');
  svg.appendChild(pointLayer);

  TURN_SCORES.forEach((value, idx) => {
    const x = xFor(idx);
    const y = yFor(value);
    const color = value >= ACCEPTANCE_THRESHOLD ? 'var(--ok)' : value >= 60 ? 'var(--warn)' : 'var(--bad)';

    const ring = document.createElementNS(NS, 'circle');
    ring.setAttribute('cx', String(x));
    ring.setAttribute('cy', String(y));
    ring.setAttribute('r', '9');
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'var(--focus)');
    ring.setAttribute('stroke-width', '2');
    ring.setAttribute('opacity', idx === 0 ? '0.9' : '0');
    ring.classList.add('fb-chart-ring');
    pointLayer.appendChild(ring);

    const point = document.createElementNS(NS, 'circle');
    point.setAttribute('cx', String(x));
    point.setAttribute('cy', String(y));
    point.setAttribute('r', idx === 0 ? '7' : '5');
    point.setAttribute('fill', color);
    point.setAttribute('stroke', '#FFFFFF');
    point.setAttribute('stroke-width', '2');
    point.setAttribute('filter', 'url(#fbPointShadow)');
    point.classList.add('fb-chart-point');
    point.setAttribute('tabindex', '0');
    point.setAttribute('role', 'button');
    point.setAttribute('aria-label', `Turno ${idx + 1}`);

    const activate = () => onSelectTurn(idx);
    point.addEventListener('click', activate);
    point.addEventListener('mouseenter', activate);
    point.addEventListener('focus', activate);
    pointLayer.appendChild(point);
  });

  const turnOneConnector = document.createElementNS(NS, 'line');
  turnOneConnector.setAttribute('x1', String(xFor(0)));
  turnOneConnector.setAttribute('x2', String(xFor(0)));
  turnOneConnector.setAttribute('y1', String(yFor(TURN_SCORES[0]) + 9));
  turnOneConnector.setAttribute('y2', String(height - 2));
  turnOneConnector.setAttribute('stroke', 'var(--focus)');
  turnOneConnector.setAttribute('stroke-width', '2');
  turnOneConnector.setAttribute('stroke-dasharray', '4 4');
  svg.appendChild(turnOneConnector);

  const labels = [];
  for (let t = 1; t <= TURN_SCORES.length; t += 2) labels.push(t);

  labels.forEach((turnLabel) => {
    const label = document.createElementNS(NS, 'text');
    const idx = turnLabel - 1;
    label.setAttribute('x', String(xFor(idx)));
    label.setAttribute('y', String(height - 8));
    label.setAttribute('class', 'fb-axis-label');
    label.setAttribute('text-anchor', 'middle');
    label.textContent = `T${turnLabel}`;
    svg.appendChild(label);
  });

  function drawSegment(container, x1, y1, x2, y2, v1, v2) {
    const state = (v) => (v >= ACCEPTANCE_THRESHOLD ? 'ok' : v >= 60 ? 'warn' : 'bad');
    const colorFor = (s) => (s === 'ok' ? 'var(--ok)' : s === 'warn' ? 'var(--warn)' : 'var(--bad)');

    const s1 = state(v1);
    const s2 = state(v2);

    if (s1 === s2 || (v1 < ACCEPTANCE_THRESHOLD && v2 < ACCEPTANCE_THRESHOLD && (v1 >= 60 || v2 >= 60))) {
      const line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', String(x1));
      line.setAttribute('y1', String(y1));
      line.setAttribute('x2', String(x2));
      line.setAttribute('y2', String(y2));
      line.setAttribute('stroke', colorFor(s2));
      line.setAttribute('stroke-width', '2.25');
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('stroke-linejoin', 'round');
      container.appendChild(line);
      return;
    }

    if (
      (v1 < ACCEPTANCE_THRESHOLD && v2 >= ACCEPTANCE_THRESHOLD) ||
      (v1 >= ACCEPTANCE_THRESHOLD && v2 < ACCEPTANCE_THRESHOLD)
    ) {
      const t = (ACCEPTANCE_THRESHOLD - v1) / (v2 - v1);
      const cx = x1 + (x2 - x1) * t;
      const cy = y1 + (y2 - y1) * t;

      const first = document.createElementNS(NS, 'line');
      first.setAttribute('x1', String(x1));
      first.setAttribute('y1', String(y1));
      first.setAttribute('x2', String(cx));
      first.setAttribute('y2', String(cy));
      first.setAttribute('stroke', colorFor(state(Math.min(v1, v2))));
      first.setAttribute('stroke-width', '2.25');
      first.setAttribute('stroke-linecap', 'round');
      first.setAttribute('stroke-linejoin', 'round');

      const second = document.createElementNS(NS, 'line');
      second.setAttribute('x1', String(cx));
      second.setAttribute('y1', String(cy));
      second.setAttribute('x2', String(x2));
      second.setAttribute('y2', String(y2));
      second.setAttribute('stroke', colorFor(state(Math.max(v1, v2))));
      second.setAttribute('stroke-width', '2.25');
      second.setAttribute('stroke-linecap', 'round');
      second.setAttribute('stroke-linejoin', 'round');

      container.append(first, second);
      return;
    }

    const fallback = document.createElementNS(NS, 'line');
    fallback.setAttribute('x1', String(x1));
    fallback.setAttribute('y1', String(y1));
    fallback.setAttribute('x2', String(x2));
    fallback.setAttribute('y2', String(y2));
    fallback.setAttribute('stroke', colorFor(s2));
    fallback.setAttribute('stroke-width', '2.25');
    fallback.setAttribute('stroke-linecap', 'round');
    fallback.setAttribute('stroke-linejoin', 'round');
    container.appendChild(fallback);
  }
}

function updateChartSelection(svg, index) {
  const points = Array.from(svg.querySelectorAll('.fb-chart-point'));
  const rings = Array.from(svg.querySelectorAll('.fb-chart-ring'));

  points.forEach((p, idx) => {
    p.setAttribute('r', idx === index ? '7' : '5');
  });

  rings.forEach((r, idx) => {
    r.setAttribute('opacity', idx === index ? '0.9' : '0');
  });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
