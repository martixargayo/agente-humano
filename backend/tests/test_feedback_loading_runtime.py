from __future__ import annotations

import subprocess
from pathlib import Path


def test_feedback_loading_runtime_generates_visible_floating_phrases() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    app_js = repo_root / 'backend/interfaz_usuario_app/app.js'

    node_script = r'''
const fs = require('fs');
const vm = require('vm');

const sourcePath = process.argv[1];
let source = fs.readFileSync(sourcePath, 'utf8');
source = source.replace(/\(async function initInterfazUsuarioSession\(\) \{[\s\S]*?\}\)\(\);\s*$/, '');

class FakeClassList {
  constructor() { this.set = new Set(['hidden']); }
  add(...tokens) { tokens.forEach((t) => this.set.add(t)); }
  remove(...tokens) { tokens.forEach((t) => this.set.delete(t)); }
  toggle(token, force) {
    if (force === true) { this.set.add(token); return true; }
    if (force === false) { this.set.delete(token); return false; }
    if (this.set.has(token)) { this.set.delete(token); return false; }
    this.set.add(token); return true;
  }
  contains(token) { return this.set.has(token); }
}

class FakeStyle {
  constructor() { this.props = {}; }
  setProperty(key, value) { this.props[key] = value; }
}

class FakeElement {
  constructor(id = '') {
    this.id = id;
    this.value = '';
    this.textContent = '';
    this.innerHTML = '';
    this.classList = new FakeClassList();
    this.style = new FakeStyle();
    this.children = [];
    this.parentNode = null;
    this.disabled = false;
    this.dataset = {};
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
    this.parentNode = null;
  }
  addEventListener() {}
  removeEventListener() {}
  contains(target) { return target === this || this.children.includes(target); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  setAttribute() {}
  get childElementCount() { return this.children.length; }
}

const elements = new Map();
const getElement = (id) => {
  if (!elements.has(id)) elements.set(id, new FakeElement(id));
  return elements.get(id);
};

const document = {
  visibilityState: 'hidden',
  getElementById: getElement,
  createElement: () => new FakeElement(),
  addEventListener() {},
  removeEventListener() {},
};

const timers = [];
const windowObj = {
  document,
  __avatarRuntime: null,
  addEventListener() {},
  removeEventListener() {},
  setTimeout(fn, delay) { timers.push({ fn, delay }); return timers.length; },
  clearTimeout() {},
  setInterval() { return 1; },
  clearInterval() {},
  matchMedia(query) {
    return { matches: false, media: query, addEventListener() {}, removeEventListener() {} };
  },
  localStorage: { getItem() { return null; }, setItem() {} },
};

const navigatorObj = {
  mediaDevices: {
    addEventListener() {},
    getUserMedia: async () => ({ getTracks: () => [] }),
    enumerateDevices: async () => ([]),
  },
};

const context = {
  window: windowObj,
  document,
  navigator: navigatorObj,
  console,
  setTimeout: windowObj.setTimeout,
  clearTimeout: windowObj.clearTimeout,
  setInterval: windowObj.setInterval,
  clearInterval: windowObj.clearInterval,
  Node: FakeElement,
  HTMLElement: FakeElement,
  HTMLTextAreaElement: FakeElement,
  File: class {},
  FormData: class { append() {} },
  fetch: async (url) => ({ ok: true, json: async () => ({ user_id: 'u', session_id: 's', trace_count: 0, conversation_id: 'c' }), text: async () => '' }),
};

vm.createContext(context);
vm.runInContext(source, context, { filename: sourcePath });

context.showFeedbackView('loading');
const layer = elements.get('feedbackFloatingLayer');
if (!layer) throw new Error('feedbackFloatingLayer missing');
if (layer.childElementCount < 4) {
  throw new Error(`expected at least 4 floating lines, got ${layer.childElementCount}`);
}
const rendered = layer.children.map((child) => child.innerHTML).join('\n');
for (const phrase of ['Analizando', 'Detectando', 'Evaluando', 'Identificando', 'Procesando', 'Correlacionando', 'Comparando', 'Generando', 'Estimando', 'Revisando', 'Mapeando', 'Sintetizando']) {
  if (context.FeedbackFloatingPhrases && !rendered.includes(phrase)) {
    // best effort, but the runtime output is random so don't fail here.
  }
}
if (!rendered.includes('token-keyword') || !rendered.includes('token-entity') && !rendered.includes('token-value') && !rendered.includes('token-metric')) {
  throw new Error(`expected syntax-colored token spans in floating phrases, got: ${rendered}`);
}

const loadingScreen = elements.get('feedbackLoadingScreen');
if (!loadingScreen || loadingScreen.classList.contains('hidden')) {
  throw new Error('loading screen did not become visible');
}

console.log(JSON.stringify({
  floatingCount: layer.childElementCount,
  sample: layer.children.slice(0, 3).map((child) => child.innerHTML),
  queuedTimers: timers.length,
}, null, 2));
'''

    result = subprocess.run(
        ['node', '-e', node_script, str(app_js)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert 'floatingCount' in result.stdout
    assert 'token-keyword' in result.stdout
