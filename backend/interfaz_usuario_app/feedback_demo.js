const $ = (id) => document.getElementById(id);

const StageLabel = {
  created: 'Creando evaluación...',
  queued: 'Evaluación en cola...',
  building_inputs: 'Analizando conversación sintética...',
  running_core: 'Ejecutando core evaluator...',
  running_trajectory: 'Ejecutando trajectory evaluator...',
  assembling_report: 'Ensamblando informe final...',
  completed: 'Informe completado.',
  failed: 'La evaluación falló.',
};

let fixtures = [];
let pollingTimer = null;

async function api(path, opts = {}) {
  const r = await fetch(`/api/interfaz_usuario${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function stopPolling() {
  if (pollingTimer) {
    window.clearTimeout(pollingTimer);
    pollingTimer = null;
  }
}

function showPanel(panel) {
  $('panelLoading').classList.toggle('hidden', panel !== 'loading');
  $('panelReport').classList.toggle('hidden', panel !== 'report');
  $('panelError').classList.toggle('hidden', panel !== 'error');
}

function selectedFixture() {
  const id = $('fixtureSelect').value;
  return fixtures.find((f) => f.fixture_id === id) || null;
}

function renderFixtureMeta() {
  const fixture = selectedFixture();
  if (!fixture) {
    $('fixtureMeta').textContent = 'No hay fixture seleccionado.';
    return;
  }
  $('fixtureMeta').textContent = `Fixture: ${fixture.title} · dominio=${fixture.domain} · turnos=${fixture.turn_count}`;
}

function renderReport(report) {
  const root = $('feedbackReportRoot');
  if (!root || !window.FeedbackReportView) return;
  window.FeedbackReportView.renderReport(root, report);
}

async function pollEvaluation(evaluationId) {
  try {
    const status = await api(`/feedback/evaluations/${evaluationId}`);
    $('loadingText').textContent = StageLabel[status.status] || 'Procesando...';

    if (status.status === 'completed') {
      stopPolling();
      const reportResp = await api(`/feedback/evaluations/${evaluationId}/report`);
      showPanel('report');
      renderReport(reportResp.report);
      return;
    }
    if (status.status === 'failed') {
      stopPolling();
      $('errorText').textContent = status.error || 'La evaluación falló.';
      showPanel('error');
      return;
    }
    pollingTimer = window.setTimeout(() => pollEvaluation(evaluationId), 1700);
  } catch (err) {
    stopPolling();
    $('errorText').textContent = `Error en polling: ${String(err)}`;
    showPanel('error');
  }
}

async function runDemo() {
  const fixture = selectedFixture();
  if (!fixture) return;

  showPanel('loading');
  $('loadingText').textContent = 'Iniciando evaluación demo...';
  stopPolling();

  try {
    const created = await api('/feedback/dev/evaluations', {
      method: 'POST',
      body: JSON.stringify({ fixture_id: fixture.fixture_id }),
    });
    pollingTimer = window.setTimeout(() => pollEvaluation(created.evaluation_id), 200);
  } catch (err) {
    $('errorText').textContent = `No se pudo crear evaluación demo: ${String(err)}`;
    showPanel('error');
  }
}

async function bootstrap() {
  try {
    const out = await api('/feedback/dev/fixtures');
    fixtures = out.fixtures || [];
    const select = $('fixtureSelect');
    select.innerHTML = '';
    for (const f of fixtures) {
      const opt = document.createElement('option');
      opt.value = f.fixture_id;
      opt.textContent = `${f.fixture_id} — ${f.title}`;
      select.appendChild(opt);
    }
    renderFixtureMeta();
  } catch (err) {
    $('errorText').textContent = `No se pudieron cargar fixtures: ${String(err)}`;
    showPanel('error');
  }
}

$('fixtureSelect').addEventListener('change', renderFixtureMeta);
$('runFixtureBtn').addEventListener('click', runDemo);

bootstrap();
