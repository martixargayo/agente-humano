const DEMO_FORCED_REPLIES = [
  'Si claro Lluís, dime.',
  'No es que no quiera compartirla. Muchas veces todavía la estoy revisando y no quiero enviarte algo incompleto.',
  'Entonces… ¿quieres que te pase información que todavía puede ser errónea?',
];

const DEMO_FEEDBACK_TEXT = `DESCRIBIR
✔️ Se describió un hecho concreto sin juicios.
✖️ No se generó clima previo antes de entrar en el tema principal.

EXPRESAR
✔️ Usaste correctamente el “yo siento” para expresar cómo la situación afecta a tu trabajo, reduciendo la defensividad del interlocutor.

SUGERIR
✔️ Propusiste una alternativa lógica y alineada con los intereses de las dos partes.

CONSECUENCIAS
✔️ Mencionaste los beneficios que aportaría a ambos disponer de la información antes, para avanzar y planificar mejor.

RECOMENDACIONES GENERALES
✖️ Hubo dos situaciones durante la conversación en las que deberías haber usado el “yo siento” en vez del “tú eres”.`;

const DEMO_MODE_CONFIG = {
  demo_feedback: {
    forcedReplies: DEMO_FORCED_REPLIES,
    feedbackText: DEMO_FEEDBACK_TEXT,
  },
};

export function createDemoFeedbackMode({
  urlParams = new URLSearchParams(window.location.search),
  onFinish = () => {},
} = {}) {
  let finishHook = onFinish;
  const modeName = urlParams.get('mode') || '';
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

    const overlay = document.createElement('section');
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-label', 'Feedback final de la demo');

    Object.assign(overlay.style, {
      position: 'fixed',
      inset: '0',
      zIndex: '40',
      display: 'none',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(2, 6, 23, 0.95)',
      padding: 'clamp(18px, 4vw, 48px)',
    });

    const card = document.createElement('article');
    Object.assign(card.style, {
      width: 'min(920px, 96vw)',
      maxHeight: '90vh',
      overflow: 'auto',
      borderRadius: '22px',
      border: '1px solid rgba(148, 163, 184, 0.35)',
      background: 'rgba(15, 23, 42, 0.92)',
      boxShadow: '0 28px 64px rgba(0, 0, 0, 0.5)',
      padding: 'clamp(18px, 4vw, 40px)',
    });

    const body = document.createElement('pre');
    body.textContent = config.feedbackText;
    Object.assign(body.style, {
      margin: '0',
      whiteSpace: 'pre-wrap',
      color: 'rgba(226, 232, 240, 0.95)',
      fontSize: 'clamp(14px, 1.65vw, 20px)',
      lineHeight: '1.55',
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    });

    card.appendChild(body);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    ui.feedbackOverlay = overlay;
  }

  function updateFinishButtonVisibility() {
    if (!ui.finishButton) return;
    ui.finishButton.style.display = api.shouldAllowFinish() ? 'inline-flex' : 'none';
  }
}
