const DEMO_FORCED_REPLIES = [
  'Si claro Lluís, dime.',
  'No es que no quiera compartirla. Muchas veces todavía la estoy revisando y no quiero enviarte algo incompleto.',
  'Entonces… ¿quieres que te pase información que todavía puede ser errónea?',
];

const DEMO_FEEDBACK_CARD_ITEMS = [
  {
    title: 'DESCRIBIR',
    rows: [
      {
        icon: '✔️',
        tone: 'success',
        text: 'Se describió un hecho concreto sin juicios.',
      },
      {
        icon: '✖️',
        tone: 'error',
        text: 'No se generó clima previo antes de entrar en el tema principal.',
      },
    ],
  },
  {
    title: 'EXPRESAR',
    rows: [
      {
        icon: '✔️',
        tone: 'success',
        text: 'Usaste correctamente el “yo siento” para expresar cómo la situación afecta a tu trabajo, reduciendo la defensividad del interlocutor.',
      },
    ],
  },
  {
    title: 'SUGERIR',
    rows: [
      {
        icon: '✔️',
        tone: 'success',
        text: 'Propusiste una alternativa lógica y alineada con los intereses de las dos partes.',
      },
    ],
  },
  {
    title: 'CONSECUENCIAS',
    rows: [
      {
        icon: '✔️',
        tone: 'success',
        text: 'Mencionaste los beneficios que aportaría a ambos disponer de la información antes, para avanzar y planificar mejor.',
      },
    ],
  },
  {
    title: 'ENTENDIMIENTO / ACUERDO',
    rows: [
      {
        icon: '🤝',
        tone: 'neutral',
        text: 'Se alcanzó un acuerdo funcional y claro para ambas partes.',
      },
    ],
  },
];

const DEMO_FEEDBACK_RECOMMENDATION = {
  icon: '✖️',
  text: 'Hubo dos situaciones durante la conversación en las que deberías haber usado el “yo siento” en vez del “tú eres”.',
};

const DEMO_MODE_CONFIG = {
  demo_feedback: {
    forcedReplies: DEMO_FORCED_REPLIES,
    feedbackCards: DEMO_FEEDBACK_CARD_ITEMS,
    recommendation: DEMO_FEEDBACK_RECOMMENDATION,
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
      ui.feedbackOverlay.style.display = 'flex';
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

    const card = document.createElement('article');
    card.className = 'demo-feedback-panel';

    const header = document.createElement('header');
    header.className = 'demo-feedback-header';

    const title = document.createElement('h2');
    title.className = 'demo-feedback-title';
    title.textContent = 'Feedback de la conversación';

    const subtitle = document.createElement('p');
    subtitle.className = 'demo-feedback-subtitle';
    subtitle.textContent = 'Evaluación de habilidades relacionales';

    const metrics = document.createElement('div');
    metrics.className = 'demo-feedback-metrics';

    const stars = document.createElement('p');
    stars.className = 'demo-feedback-stars';
    stars.setAttribute('aria-label', '4 de 5 estrellas');
    stars.textContent = '★★★★☆';

    const progress = document.createElement('div');
    progress.className = 'demo-feedback-progress';
    progress.setAttribute('role', 'progressbar');
    progress.setAttribute('aria-label', 'Puntuación global');
    progress.setAttribute('aria-valuemin', '0');
    progress.setAttribute('aria-valuemax', '100');
    progress.setAttribute('aria-valuenow', '80');

    const progressFill = document.createElement('div');
    progressFill.className = 'demo-feedback-progress-fill';
    progress.appendChild(progressFill);

    const score = document.createElement('span');
    score.className = 'demo-feedback-score';
    score.textContent = '80%';

    metrics.append(stars, progress, score);
    header.append(title, subtitle, metrics);

    const grid = document.createElement('div');
    grid.className = 'demo-feedback-grid';

    for (const section of config.feedbackCards || []) {
      const sectionCard = document.createElement('section');
      sectionCard.className = 'demo-feedback-card';

      const sectionTitle = document.createElement('h3');
      sectionTitle.className = 'demo-feedback-card-title';
      sectionTitle.textContent = section.title;

      sectionCard.appendChild(sectionTitle);

      for (const row of section.rows) {
        const line = document.createElement('p');
        line.className = `demo-feedback-line ${row.tone === 'error' ? 'error' : row.tone === 'success' ? 'success' : 'neutral'}`;

        const icon = document.createElement('span');
        icon.className = 'demo-feedback-line-icon';
        icon.textContent = row.icon;

        const text = document.createElement('span');
        text.textContent = row.text;

        line.append(icon, text);
        sectionCard.appendChild(line);
      }

      grid.appendChild(sectionCard);
    }

    const recommendation = document.createElement('aside');
    recommendation.className = 'demo-feedback-card demo-feedback-card-highlight';

    const recommendationTitle = document.createElement('h3');
    recommendationTitle.className = 'demo-feedback-card-title';
    recommendationTitle.textContent = 'RECOMENDACIÓN GENERAL';

    const recommendationText = document.createElement('p');
    recommendationText.className = 'demo-feedback-line error';
    recommendationText.innerHTML = `<span class="demo-feedback-line-icon">${config.recommendation.icon}</span><span>${config.recommendation.text}</span>`;

    recommendation.append(recommendationTitle, recommendationText);

    card.append(header, grid, recommendation);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    ui.feedbackOverlay = overlay;
  }

  function ensureFeedbackStyles() {
    if (document.getElementById('demo-feedback-styles')) return;

    const style = document.createElement('style');
    style.id = 'demo-feedback-styles';
    style.textContent = `
      .demo-feedback-overlay {
        --feedback-bg: #ffffff;
        --feedback-text: #0f172a;
        --feedback-muted: #475569;
        --feedback-border: #e2e8f0;
        --feedback-success: #16a34a;
        --feedback-error: #dc2626;
        --feedback-callout: #f8fafc;
        position: fixed;
        inset: 0;
        z-index: 40;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(15, 23, 42, 0.64);
        padding: clamp(18px, 4vw, 48px);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .demo-feedback-panel {
        width: min(1080px, 100%);
        max-height: min(920px, 92vh);
        overflow: auto;
        border: 1px solid var(--feedback-border);
        border-radius: 24px;
        background: var(--feedback-bg);
        box-shadow: 0 28px 56px rgba(15, 23, 42, 0.22);
        color: var(--feedback-text);
        padding: clamp(20px, 4vw, 40px);
      }

      .demo-feedback-header {
        text-align: center;
        margin-bottom: clamp(20px, 3.2vw, 30px);
      }

      .demo-feedback-title {
        margin: 0;
        font-size: clamp(30px, 3.6vw, 40px);
        line-height: 1.1;
      }

      .demo-feedback-subtitle {
        margin: 10px 0 0;
        color: var(--feedback-muted);
        font-size: clamp(14px, 1.5vw, 18px);
      }

      .demo-feedback-metrics {
        margin: 22px auto 0;
        display: grid;
        justify-items: center;
        gap: 12px;
        width: min(520px, 100%);
      }

      .demo-feedback-stars {
        margin: 0;
        color: #f59e0b;
        font-size: clamp(22px, 2.5vw, 30px);
        letter-spacing: 0.2em;
      }

      .demo-feedback-progress {
        width: 100%;
        height: 8px;
        border-radius: 999px;
        background: #e2e8f0;
        overflow: hidden;
      }

      .demo-feedback-progress-fill {
        width: 80%;
        height: 100%;
        background: linear-gradient(90deg, #16a34a, #22c55e);
      }

      .demo-feedback-score {
        color: var(--feedback-muted);
        font-size: 14px;
        font-weight: 700;
      }

      .demo-feedback-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: clamp(12px, 2vw, 18px);
      }

      .demo-feedback-card {
        border: 1px solid var(--feedback-border);
        border-radius: 24px;
        background: var(--feedback-bg);
        padding: 16px;
      }

      .demo-feedback-card-title {
        margin: 0 0 12px;
        font-size: 13px;
        letter-spacing: 0.08em;
        color: var(--feedback-muted);
      }

      .demo-feedback-line {
        margin: 0;
        display: flex;
        gap: 10px;
        align-items: flex-start;
        font-size: 15px;
        line-height: 1.45;
        color: var(--feedback-text);
      }

      .demo-feedback-line + .demo-feedback-line {
        margin-top: 10px;
      }

      .demo-feedback-line-icon {
        width: 20px;
        flex: 0 0 auto;
      }

      .demo-feedback-line.success {
        color: var(--feedback-success);
      }

      .demo-feedback-line.error {
        color: var(--feedback-error);
      }

      .demo-feedback-card-highlight {
        margin-top: clamp(14px, 2.2vw, 20px);
        background: var(--feedback-callout);
      }

      @media (max-width: 700px) {
        .demo-feedback-panel {
          border-radius: 24px;
          max-height: 95vh;
          padding: 18px;
        }

        .demo-feedback-grid {
          grid-template-columns: 1fr;
        }

        .demo-feedback-line {
          font-size: 14px;
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
