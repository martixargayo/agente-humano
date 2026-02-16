const DEMO_FORCED_REPLIES = [
  'Si claro Lluís, dime.',
  'No es que no quiera compartirla. Muchas veces todavía la estoy revisando y no quiero enviarte algo incompleto.',
  'Entonces… ¿quieres que te pase información que todavía puede ser errónea?',
];

const FEEDBACK_SCORE = 84;
const ACCEPTANCE_THRESHOLD = 80;
const TURN_SCORES = [22, 24, 27, 31, 34, 39, 43, 38, 46, 52, 58, 63, 69, 61, 67, 72, 76, 81, 79, 84, 87, 85, 89, 92];

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
    rows: [
      { tone: 'ok', text: 'Propusiste una alternativa lógica y alineada con los intereses de las dos partes.' },
    ],
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
  { user: 'Oye, me está llegando tarde el parte de varias jornadas.', avatar: 'Sí, voy justo y se me acumula al cierre.', impacts: ['– Clima', '– Rapporte'] },
  { user: 'Así me cuesta organizar el trabajo del día siguiente.', avatar: 'Lo entiendo, pero no siempre lo tengo completo.', impacts: ['– Fricción', '+ Claridad inicial'] },
  { user: 'Si llega tarde, el equipo arranca con incertidumbre.', avatar: 'Tiene sentido, os afecta la coordinación.', impacts: ['+ Contexto', '+ Escucha'] },
  { user: 'Necesito una referencia más temprana, aunque sea parcial.', avatar: 'Podría enviarte algo breve por la mañana.', impacts: ['+ Apertura', '+ Opción parcial'] },
  { user: 'Con un avance temprano ya puedo reordenar prioridades.', avatar: 'Vale, eso suena viable para empezar.', impacts: ['+ Cooperación', '+ Viabilidad'] },
  { user: 'Yo siento presión cuando no tengo datos al inicio.', avatar: 'Así lo entiendo mejor, gracias por decirlo así.', impacts: ['+ Expresión sin ataque', '+ Empatía'] },
  { user: '¿Podemos acordar una hora de envío de avance?', avatar: 'Sí, podría ser antes de media mañana.', impacts: ['+ Propuesta concreta', '+ Acercamiento'] },
  { user: 'Tú eres muy inconsistente con estos envíos.', avatar: 'Dicho así me pongo a la defensiva.', impacts: ['– “Tú eres”', '– Defensividad'] },
  { user: 'Reformulo: yo siento bloqueo si no tengo señal temprana.', avatar: 'Así sí, lo veo más razonable.', impacts: ['+ Reparación', '+ Alineamiento'] },
  { user: 'Si no está completo, bastan tres puntos clave.', avatar: 'Eso sí te lo puedo mandar sin problema.', impacts: ['+ Simplificación', '+ Compromiso'] },
  { user: 'Perfecto, con eso avanzamos sin esperar al cierre.', avatar: 'Nos ahorra urgencias a ambos.', impacts: ['+ Beneficio mutuo', '+ Estabilidad'] },
  { user: 'También necesito saber qué parte queda pendiente.', avatar: 'Te puedo marcar pendientes y bloqueo.', impacts: ['+ Transparencia', '+ Claridad'] },
  { user: 'Bien, así no improvisamos al final de la tarde.', avatar: 'Correcto, quedaría bastante más ordenado.', impacts: ['+ Orden', '+ Progreso'] },
  { user: 'Tú eres demasiado caótico cuando hay presión.', avatar: 'Eso me suena a juicio personal.', impacts: ['– “Tú eres”', '– Tensión'] },
  { user: 'Perdón, yo siento incertidumbre cuando cambia el formato.', avatar: 'Gracias, esa forma me ayuda a escucharte.', impacts: ['+ Reencuadre', '+ Escucha activa'] },
  { user: 'Propongo formato fijo: avance, pendientes y riesgo.', avatar: 'Me encaja, es fácil de sostener.', impacts: ['+ Estructura', '+ Factibilidad'] },
  { user: 'Y si no llegas, un aviso rápido con hora estimada.', avatar: 'Sí, ese aviso lo puedo mantener.', impacts: ['+ Prevención', '+ Confiabilidad'] },
  { user: 'Con eso entramos en un flujo bastante estable.', avatar: 'De acuerdo, nos da previsibilidad.', impacts: ['+ Entrada a zona 80', '+ Acuerdo'] },
  { user: 'Probemos esta semana y revisamos el viernes.', avatar: 'Perfecto, hacemos un chequeo corto.', impacts: ['+ Seguimiento', '± Ajuste'] },
  { user: 'Hoy el avance llegó mejor y más claro.', avatar: 'Me ayudó tener el formato definido.', impacts: ['+ Refuerzo positivo', '+ Consistencia'] },
  { user: 'Sigamos con el mismo esquema la próxima semana.', avatar: 'Sí, lo mantengo igual.', impacts: ['+ Consolidación', '+ Alineamiento'] },
  { user: 'Si cambia algo, te aviso con antelación.', avatar: 'Genial, así reajustamos sin fricción.', impacts: ['+ Proactividad', '+ Confianza'] },
  { user: 'Estamos mucho más coordinados que al inicio.', avatar: 'Totalmente, se nota en el ritmo.', impacts: ['+ Cierre positivo', '+ Rapporte'] },
  { user: 'Entonces cerramos: avance temprano y actualización al cierre.', avatar: 'Queda acordado, lo sostengo desde hoy.', impacts: ['+ Acuerdo firme', '+ Cierre'] },
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
    finishButton: null,
    feedbackOverlay: null,
    hiddenContainers: [],
  };

  const api = {
    modeName,
    isActive: () => Boolean(config),
    isFinished: () => state.finished,
    getState: () => ({ ...state }),
    mount,
    getReplyForTurn,
    shouldAllowFinish: () => Boolean(config) && !state.finished && state.userTurns >= 4,
    finishConversation,
  };

  return api;

  function mount({
    hiddenContainers = [],
    onFinish: mountOnFinish,
  } = {}) {
    if (typeof mountOnFinish === 'function') finishHook = mountOnFinish;
    if (!config) return;

    ui.hiddenContainers = hiddenContainers.filter(Boolean);
    ensureFinishButton();
    ensureFeedbackOverlay();
    updateFinishButtonVisibility();
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
    if (ui.feedbackOverlay) return;

    ensureFeedbackStyles();

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
          <p>Cambio de comportamiento · 24 turnos · 8:12 min</p>
        </div>
        <div class="fb-header-right">
          <div class="fb-stars" role="img" aria-label="4 de 5 estrellas">${createStarsMarkup()}</div>
          <div class="fb-score-pill">84 / 100</div>
          <div class="fb-header-state"><span class="dot ok"></span>Alta probabilidad de acuerdo</div>
        </div>
      </header>

      <section class="fb-grid-cards" aria-label="Resumen por dimensión"></section>

      <section class="fb-card fb-chart-card">
        <div class="fb-chart-top">
          <div>
            <h2>Cercanía al entendimiento</h2>
            <p>Umbral de aceptación: 80</p>
          </div>
          <div class="fb-header-state"><span class="dot ok"></span>Estado actual: Susceptible de aceptar</div>
        </div>
        <div class="fb-chart-layout">
          <div>
            <div class="fb-chart-shell">
              <svg class="fb-chart" viewBox="0 0 860 240" role="img" aria-label="Serie de cercanía al entendimiento por turno"></svg>
            </div>
            <div class="fb-scrubber-wrap">
              <div class="fb-scrubber-dots" aria-hidden="true"></div>
              <input class="fb-scrubber" type="range" min="1" max="24" value="12" step="1" aria-label="Seleccionar turno" />
            </div>
          </div>
          <p class="fb-hover-hint">Pasa el ratón por un turno para ver qué dijo cada parte y el impacto.</p>
          <aside class="fb-detail-panel" aria-live="polite"></aside>
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
                <p><span class="muted">Dijiste:</span> Tú eres muy inconsistente con estos envíos.</p>
                <p><span class="muted">Mejor:</span> <span class="fb-better">Yo siento que cuando no tengo avance temprano se me bloquea la planificación.</span></p>
              </div>
              <div class="fb-mini-card">
                <div class="fb-mini-head"><strong>Turno 14</strong><span class="fb-mini-badge">A corregir</span></div>
                <p><span class="muted">Dijiste:</span> Tú eres demasiado caótico cuando hay presión.</p>
                <p><span class="muted">Mejor:</span> <span class="fb-better">Yo siento incertidumbre cuando cambia el formato sin aviso.</span></p>
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
    const scrubber = dashboard.querySelector('.fb-scrubber');
    
    let selectedIndex = null;

    renderChart(svg, setSelectedTurn, () => selectedIndex);
    renderDetailPanel(detailPanel, null);
    updateScrubberUI(dashboard, Number(scrubber.value));

    scrubber.addEventListener('input', () => {
      const turn = Number(scrubber.value);
      setSelectedTurn(turn - 1);
    });

    overlay.appendChild(dashboard);
    document.body.appendChild(overlay);
    ui.feedbackOverlay = overlay;

    function setSelectedTurn(index) {
      selectedIndex = index;
      renderDetailPanel(detailPanel, selectedIndex);
      updateChartSelection(svg, selectedIndex);
      scrubber.value = String((selectedIndex ?? 11) + 1);
      updateScrubberUI(dashboard, Number(scrubber.value));
    }
  }

  function ensureFeedbackStyles() {
    if (document.getElementById('demo-feedback-styles')) return;

    const style = document.createElement('style');
    style.id = 'demo-feedback-styles';
    style.textContent = `
      :root {
        --bg: #FFFFFF;
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
        --focusBg: rgba(46,144,250,0.12);
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

      .demo-feedback-overlay::before {
        content: '';
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image: radial-gradient(rgba(11,15,20,1) 0.5px, transparent 0.5px);
        background-size: 3px 3px;
        opacity: 0.03;
      }

      .demo-feedback-dashboard {
        position: relative;
        max-width: 1200px;
        margin: 0 auto;
        padding: 28px;
        display: grid;
        gap: 16px;
      }

      .fb-card {
        background: var(--card);
        border: 1px solid var(--border);
        position: relative;
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow);
        transition: border-color 150ms ease-out, box-shadow 150ms ease-out, transform 150ms ease-out, opacity 150ms ease-out;
      }

      .fb-card::after {
        content: "";
        position: absolute;
        left: 14px;
        right: 14px;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(46,144,250,0.35), transparent);
        opacity: 0.35;
        pointer-events: none;
      }

      .fb-card:hover {
        border-color: rgba(46,144,250,0.35);
        box-shadow: 0 10px 36px rgba(11,15,20,0.08);
      }

      .fb-header {
        min-height: 76px;
        padding: 0 22px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        animation: fbFade 120ms ease-out both;
      }

      .fb-header h1 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
        letter-spacing: -0.2px;
      }

      .fb-header p,
      .fb-chart-top p,
      .muted {
        margin: 6px 0 0;
        color: var(--muted);
        font-size: 12.5px;
        font-weight: 400;
      }

      .fb-header-right {
        display: inline-flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .fb-stars {
        display: inline-flex;
        gap: 4px;
      }

      .fb-score-pill {
        border: 1px solid var(--border);
        background: #FFFFFF;
        border-radius: 999px;
        padding: 7px 10px;
        font-size: 16px;
        font-weight: 600;
        line-height: 1;
      }

      .fb-header-state {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--muted);
        font-size: 12.5px;
        white-space: nowrap;
      }

      .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
      .dot.ok { background: var(--ok); }

      .fb-grid-cards {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }

      .fb-skill-card {
        position: relative;
        padding: 18px;
        overflow: hidden;
        opacity: 0;
        transform: translateY(6px);
        animation: fbCardIn 160ms ease-out forwards;
      }

      .fb-skill-card:nth-child(1) { animation-delay: 30ms; }
      .fb-skill-card:nth-child(2) { animation-delay: 60ms; }
      .fb-skill-card:nth-child(3) { animation-delay: 90ms; }
      .fb-skill-card:nth-child(4) { animation-delay: 120ms; }

      .fb-skill-card::before {
        content: '';
        position: absolute;
        left: 8px;
        top: 8px;
        bottom: 8px;
        width: 3px;
        border-radius: 3px;
      }

      .fb-skill-card.ok::before { background: var(--ok); }
      .fb-skill-card.warn::before { background: var(--warn); }
      .fb-skill-card.bad::before { background: var(--bad); }

      .fb-skill-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        margin-left: 10px;
      }

      .fb-skill-top h2,
      .fb-chart-top h2,
      .fb-recommendations h2 {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
      }

      .fb-badge {
        display: inline-flex;
        align-items: center;
        height: 24px;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid var(--border);
        font-size: 12px;
        font-weight: 500;
      }

      .fb-badge.ok { background: var(--okBg); color: var(--ok); }
      .fb-badge.warn { background: var(--warnBg); color: var(--warn); }
      .fb-badge.bad { background: var(--badBg); color: var(--bad); }

      .fb-skill-card ul {
        list-style: none;
        margin: 12px 0 0 10px;
        padding: 0;
        display: grid;
        gap: 8px;
      }

      .fb-skill-card li {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        font-size: 13px;
        line-height: 1.5;
        font-weight: 400;
        color: rgba(11,15,20,0.92);
      }

      .fb-item-icon {
        width: 14px;
        height: 14px;
        flex: 0 0 14px;
        margin-top: 2px;
      }

      .fb-item-icon.ok svg { color: var(--ok); }
      .fb-item-icon.bad svg { color: var(--bad); }

      .fb-chart-card,
      .fb-recommendations {
        padding: 22px;
      }

      .fb-chart-top {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: flex-start;
      }

      .fb-chart-layout {
        margin-top: 16px;
        display: grid;
        grid-template-columns: 1fr;
        gap: 16px;
        align-items: start;
      }

      .fb-chart-shell { height: 240px; width: 100%; }
      .fb-chart { width: 100%; height: 240px; display: block; }

      .fb-hover-hint {
        margin: 10px 0 0;
        font-size: 12.5px;
        color: var(--muted);
        text-align: left;
      }

      .fb-detail-panel {
        margin-top: 10px;
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        background: #FFFFFF;
        padding: 14px;
      }

      .fb-detail-empty {
        margin: 0;
        color: var(--muted);
        font-size: 12.5px;
      }

      .fb-detail-head {
        font-size: 13px;
        font-weight: 600;
      }

      .fb-detail-head .meta { color: var(--muted); font-weight: 400; }
      .fb-detail-head .delta.up { color: var(--ok); }
      .fb-detail-head .delta.flat { color: var(--warn); }
      .fb-detail-head .delta.down { color: var(--bad); }

      .fb-detail-block { margin-top: 10px; }
      .fb-detail-block h4 {
        margin: 0 0 6px;
        font-size: 12px;
        font-weight: 500;
        color: var(--muted);
      }

      .fb-quote {
        background: rgba(102,112,133,0.06);
        border: 1px solid rgba(102,112,133,0.12);
        border-radius: 12px;
        padding: 10px;
        font-size: 12.5px;
        margin: 0;
      }

      .fb-impact-tags { display: flex; flex-wrap: wrap; gap: 8px; }
      .fb-impact-tag {
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 11.5px;
        border: 1px solid var(--border);
        background: #FFFFFF;
        color: var(--muted);
      }

      .fb-impact-tag.pos { color: var(--ok); border-color: rgba(18,183,106,0.35); }
      .fb-impact-tag.neg { color: var(--bad); border-color: rgba(240,68,56,0.35); }

      .fb-scrubber-wrap {
        position: relative;
        margin-top: 12px;
        height: 28px;
        display: flex;
        align-items: center;
      }

      .fb-scrubber-dots {
        position: absolute;
        inset: 0;
        display: grid;
        grid-template-columns: repeat(24, 1fr);
        align-items: center;
        pointer-events: none;
      }

      .fb-scrubber-dots span {
        width: 3px;
        height: 3px;
        border-radius: 50%;
        background: rgba(102,112,133,0.45);
        justify-self: center;
      }

      .fb-scrubber {
        appearance: none;
        -webkit-appearance: none;
        width: 100%;
        height: 28px;
        margin: 0;
        background: transparent;
      }

      .fb-scrubber:focus-visible,
      .fb-chart-point:focus-visible {
        outline: 1px solid var(--focus);
        box-shadow: 0 0 0 2px var(--focusBg);
      }

      .fb-scrubber::-webkit-slider-runnable-track {
        height: 2px;
        background: rgba(102,112,133,0.18);
        border-radius: 999px;
      }

      .fb-scrubber::-moz-range-track {
        height: 2px;
        background: rgba(102,112,133,0.18);
        border-radius: 999px;
      }

      .fb-scrubber::-webkit-slider-thumb {
        appearance: none;
        -webkit-appearance: none;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        border: 2px solid #FFFFFF;
        background: var(--focus);
        margin-top: -5px;
      }

      .fb-scrubber::-moz-range-thumb {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        border: 2px solid #FFFFFF;
        background: var(--focus);
      }

      .fb-recommendations h2 { margin-bottom: 14px; }

      .fb-recommendations-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }

      .fb-recommendations h3 {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
      }

      .fb-numbered-list {
        list-style: none;
        margin: 12px 0 0;
        padding: 0;
        display: grid;
        gap: 12px;
      }

      .fb-numbered-list li {
        display: grid;
        grid-template-columns: 26px 1fr;
        gap: 10px;
      }

      .fb-number {
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background: rgba(46,144,250,0.10);
        border: 1px solid rgba(46,144,250,0.25);
        color: var(--focus);
        font-weight: 600;
        font-size: 13px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }

      .fb-numbered-list strong,
      .fb-correct-note,
      .fb-mini-card p {
        font-size: 13px;
      }

      .fb-numbered-list p,
      .fb-mini-card p,
      .fb-close-block p {
        margin: 4px 0 0;
        font-size: 12.5px;
        color: var(--muted);
      }

      .fb-correct-note {
        margin: 12px 0;
        display: flex;
        gap: 8px;
        align-items: flex-start;
      }

      .fb-correct-note svg { color: var(--bad); width: 14px; height: 14px; margin-top: 2px; }

      .fb-mini-cards {
        display: grid;
        gap: 10px;
      }

      .fb-mini-card {
        background: #FFF;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 12px;
      }

      .fb-mini-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }

      .fb-mini-badge {
        padding: 2px 8px;
        border-radius: 999px;
        border: 1px solid var(--border);
        font-size: 12px;
        font-weight: 500;
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
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
      }

      .fb-close-block h3 { margin-bottom: 6px; }

      .fb-zone-label { fill: var(--muted2); font-size: 12px; }
      .fb-axis-label { fill: var(--muted2); font-size: 11px; }
      .fb-threshold-label { fill: var(--muted); font-size: 12px; }

      @keyframes fbFade { from { opacity: 0; } to { opacity: 1; } }
      @keyframes fbCardIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

      @media (max-width: 1023px) {
        .demo-feedback-dashboard { padding: 20px; }
        .fb-grid-cards,
        .fb-recommendations-grid,
        .fb-chart-layout { grid-template-columns: 1fr; }
      }

      @media (max-width: 767px) {
        .demo-feedback-dashboard { padding: 16px; }
        .fb-header {
          min-height: auto;
          height: auto;
          padding: 18px 22px;
          align-items: flex-start;
          flex-direction: column;
          gap: 12px;
        }

        .fb-close-block {
          flex-direction: column;
          align-items: flex-start;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function updateFinishButtonVisibility() {
    if (!ui.finishButton) return;
    ui.finishButton.style.display = api.shouldAllowFinish() ? 'inline-flex' : 'none';
  }
}

function createStarsMarkup() {
  return [1, 2, 3, 4, 5]
    .map((n) => {
      const filled = n <= 4;
      return `<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" style="${filled ? 'opacity:0.85;color:var(--text);fill:currentColor;stroke:none;' : 'color:var(--muted2);fill:none;stroke:currentColor;stroke-width:1.6;'}"><path d="M12 3.5l2.87 5.82 6.43.93-4.65 4.53 1.1 6.4L12 18.13l-5.75 3.05 1.1-6.4L2.7 10.25l6.43-.93L12 3.5z"/></svg>`;
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
  if (index === null || index === undefined) {
    panel.innerHTML = '<p class="fb-detail-empty">Selecciona un turno para ver el detalle.</p>';
    return;
  }

  const turn = index + 1;
  const score = TURN_SCORES[index];
  const prev = index === 0 ? TURN_SCORES[0] : TURN_SCORES[index - 1];
  const delta = score - prev;
  const deltaText = `${delta >= 0 ? '+' : ''}${delta}`;
  const deltaClass = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
  const detail = TURN_DETAILS[index];

  panel.innerHTML = `
    <div class="fb-detail-head">Turno ${turn} <span class="meta">· Score ${score}</span> <span class="delta ${deltaClass}">(${deltaText})</span></div>
    <section class="fb-detail-block">
      <h4>Tú dijiste</h4>
      <p class="fb-quote">${detail.user}</p>
    </section>
    <section class="fb-detail-block">
      <h4>El avatar respondió</h4>
      <p class="fb-quote">${detail.avatar}</p>
    </section>
    <section class="fb-detail-block">
      <h4>Impacto detectado</h4>
      <div class="fb-impact-tags">
        ${detail.impacts
          .map((impact) => {
            const cls = impact.trim().startsWith('+') ? 'pos' : impact.trim().startsWith('–') ? 'neg' : '';
            return `<span class="fb-impact-tag ${cls}">${impact}</span>`;
          })
          .join('')}
      </div>
    </section>
  `;
}

function renderChart(svg, onSelectTurn, getSelectedIndex) {
  const NS = 'http://www.w3.org/2000/svg';
  const width = 1120;
  const height = 240;
  const pad = { top: 16, right: 12, bottom: 32, left: 42 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const xFor = (idx) => pad.left + (idx / (TURN_SCORES.length - 1)) * innerW;
  const yFor = (value) => pad.top + ((100 - value) / 100) * innerH;

  svg.innerHTML = '';

  const defs = document.createElementNS(NS, 'defs');
  defs.innerHTML = '<filter id="fbPointShadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="6" stdDeviation="4" flood-color="rgba(11,15,20,0.12)"/></filter>';
  svg.appendChild(defs);

  const acceptanceRect = document.createElementNS(NS, 'rect');
  acceptanceRect.setAttribute('x', String(pad.left));
  acceptanceRect.setAttribute('y', String(yFor(100)));
  acceptanceRect.setAttribute('width', String(innerW));
  acceptanceRect.setAttribute('height', String(yFor(80) - yFor(100)));
  acceptanceRect.setAttribute('fill', 'rgba(18,183,106,0.06)');
  svg.appendChild(acceptanceRect);

  for (const v of [0, 50, 80, 100]) {
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', String(pad.left));
    line.setAttribute('x2', String(width - pad.right));
    line.setAttribute('y1', String(yFor(v)));
    line.setAttribute('y2', String(yFor(v)));
    line.setAttribute('stroke', v === 80 ? 'rgba(102,112,133,0.22)' : 'rgba(102,112,133,0.12)');
    svg.appendChild(line);
  }

  const threshold = document.createElementNS(NS, 'text');
  threshold.setAttribute('x', '8');
  threshold.setAttribute('y', String(yFor(80) + 4));
  threshold.setAttribute('class', 'fb-threshold-label');
  threshold.textContent = '80';
  svg.appendChild(threshold);

  const zones = [
    { text: 'Cerca', y: yFor(96) },
    { text: 'En progreso', y: yFor(52) },
    { text: 'Lejos', y: yFor(6) },
  ];
  for (const z of zones) {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', '4');
    t.setAttribute('y', String(z.y));
    t.setAttribute('class', 'fb-zone-label');
    t.textContent = z.text;
    svg.appendChild(t);
  }

  const zoneText = document.createElementNS(NS, 'text');
  zoneText.setAttribute('x', String(width - pad.right - 190));
  zoneText.setAttribute('y', String(yFor(100) + 14));
  zoneText.setAttribute('fill', 'rgba(18,183,106,0.65)');
  zoneText.setAttribute('font-size', '12');
  zoneText.textContent = 'Zona de aceptación (80–100)';
  svg.appendChild(zoneText);

  for (let i = 0; i < TURN_SCORES.length - 1; i += 1) {
    drawSegment(svg, xFor(i), yFor(TURN_SCORES[i]), xFor(i + 1), yFor(TURN_SCORES[i + 1]), TURN_SCORES[i], TURN_SCORES[i + 1]);
  }

  const guide = document.createElementNS(NS, 'line');
  guide.setAttribute('x1', String(xFor(0)));
  guide.setAttribute('x2', String(xFor(0)));
  guide.setAttribute('y1', String(pad.top));
  guide.setAttribute('y2', String(height - pad.bottom));
  guide.setAttribute('stroke', 'rgba(46,144,250,0.25)');
  guide.setAttribute('stroke-dasharray', '3 4');
  guide.style.display = 'none';
  guide.classList.add('fb-guide');
  svg.appendChild(guide);

  const pointLayer = document.createElementNS(NS, 'g');
  pointLayer.classList.add('fb-points-layer');
  svg.appendChild(pointLayer);

  TURN_SCORES.forEach((value, idx) => {
    const x = xFor(idx);
    const y = yFor(value);
    const color = value >= 80 ? 'var(--ok)' : value >= 60 ? 'var(--warn)' : 'var(--bad)';

    const ring = document.createElementNS(NS, 'circle');
    ring.setAttribute('cx', String(x));
    ring.setAttribute('cy', String(y));
    ring.setAttribute('r', '9');
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'var(--focus)');
    ring.setAttribute('stroke-width', '2');
    ring.setAttribute('opacity', '0');
    ring.classList.add('fb-chart-ring');
    pointLayer.appendChild(ring);

    const point = document.createElementNS(NS, 'circle');
    point.setAttribute('cx', String(x));
    point.setAttribute('cy', String(y));
    point.setAttribute('r', '5');
    point.setAttribute('fill', color);
    point.setAttribute('stroke', '#FFFFFF');
    point.setAttribute('stroke-width', '2');
    point.setAttribute('filter', 'url(#fbPointShadow)');
    point.classList.add('fb-chart-point');
    point.setAttribute('tabindex', '0');
    point.setAttribute('role', 'button');
    point.setAttribute('aria-label', `Turno ${idx + 1}, score ${value}`);

    const activate = () => onSelectTurn(idx);
    point.addEventListener('mouseenter', activate);
    point.addEventListener('focus', activate);
    point.addEventListener('click', activate);
    pointLayer.appendChild(point);
  });

  const labels = [];
  for (let t = 1; t <= TURN_SCORES.length; t += 2) labels.push(t);
  labels.forEach((turnLabel) => {
    const label = document.createElementNS(NS, 'text');
    const idx = turnLabel - 1;
    label.setAttribute('x', String(xFor(idx) - 8));
    label.setAttribute('y', String(height - 8));
    label.setAttribute('class', 'fb-axis-label');
    label.textContent = `T${turnLabel}`;
    svg.appendChild(label);
  });

  updateChartSelection(svg, getSelectedIndex());

  function drawSegment(container, x1, y1, x2, y2, v1, v2) {
    const state = (v) => (v >= 80 ? 'ok' : v >= 60 ? 'warn' : 'bad');
    const colorFor = (s) => (s === 'ok' ? 'var(--ok)' : s === 'warn' ? 'var(--warn)' : 'var(--bad)');

    const s1 = state(v1);
    const s2 = state(v2);

    if (s1 === s2 || (v1 < 80 && v2 < 80 && (v1 >= 60 || v2 >= 60))) {
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

    if ((v1 < ACCEPTANCE_THRESHOLD && v2 >= ACCEPTANCE_THRESHOLD) || (v1 >= ACCEPTANCE_THRESHOLD && v2 < ACCEPTANCE_THRESHOLD)) {
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
  const guide = svg.querySelector('.fb-guide');

  points.forEach((p, idx) => {
    p.setAttribute('r', idx === index ? '7' : '5');
  });

  rings.forEach((r, idx) => {
    r.setAttribute('opacity', idx === index ? '0.9' : '0');
  });

  if (guide && index !== null && index !== undefined) {
    const point = points[index];
    const x = point.getAttribute('cx');
    const y = point.getAttribute('cy');
    guide.setAttribute('x1', x);
    guide.setAttribute('x2', x);
    guide.setAttribute('y1', y);
    guide.style.display = 'block';
  }
}

function updateScrubberUI(dashboard, value) {
  const dotsContainer = dashboard.querySelector('.fb-scrubber-dots');
  if (!dotsContainer) return;
  if (!dotsContainer.childElementCount) {
    for (let i = 1; i <= 24; i += 1) {
      dotsContainer.appendChild(document.createElement('span'));
    }
  }

  const dots = dotsContainer.querySelectorAll('span');
  dots.forEach((dot, idx) => {
    dot.style.background = idx + 1 === value ? 'var(--focus)' : 'rgba(102,112,133,0.45)';
  });
}
