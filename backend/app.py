# backend/app.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import json

import os
import pathlib
import sys
from google.cloud import speech
from google.oauth2 import service_account

import io  # arriba del archivo
import time
from fastapi.responses import StreamingResponse
from openai import OpenAI

import base64

from fastapi.staticfiles import StaticFiles

BASE_DIR = pathlib.Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from state import (
    SESSIONS,
    DEFAULT_CONTEXT_LIMIT_TURNS,
    DEFAULT_KEEP_LAST_TURNS,
    get_session_state,
)
from agent import run_agent


def _migrate_negotiation_env_aliases() -> None:
    """Promueve variables legacy a las nuevas y elimina aliases deprecados."""
    env_aliases = {
        "NEGOCIATION_RAG_DIR": "NEGOTIATION_RAG_DIR",
        "OPENAI_MODEL_NAME": "NEGOTIATION_WORLD_MODEL",
        "PLANNER_MODEL_NAME": "NEGOTIATION_PLANNER_MODEL",
        "PLANNER_TEMPERATURE": "NEGOTIATION_PLANNER_TEMPERATURE",
        "SUMMARY_MODEL_NAME": "NEGOTIATION_SUMMARY_MODEL",
        "SUMMARY_TEMPERATURE": "NEGOTIATION_SUMMARY_TEMPERATURE",
        "EMBEDDINGS_MODEL_NAME": "NEGOTIATION_EMBEDDINGS_MODEL",
        "EXECUTOR_MODEL_NAME": "NEGOTIATION_EXECUTOR_MODEL",
        "EXECUTOR_TEMPERATURE": "NEGOTIATION_EXECUTOR_TEMPERATURE",
    }
    for old_key, new_key in env_aliases.items():
        old_value = os.getenv(old_key)
        if old_value and not os.getenv(new_key):
            os.environ[new_key] = old_value
        if old_key in os.environ:
            del os.environ[old_key]


_migrate_negotiation_env_aliases()

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.summary_jobs import SUMMARY_JOBS, deferred_summary_enabled, make_turn_job
from negotiation.state.deps import DEFAULT_DEPS
from negotiation.telemetry.live_trace import build_trace_event, list_recent_trace_events
from negotiation.telemetry.live_trace2 import (
    append_livetrace2_event,
    build_livetrace2_event,
    list_recent_livetrace2_events,
)

from dotenv import load_dotenv
load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tts_audio")

app = FastAPI(title="Agente Humano - MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # permitir todos los orígenes (incluye localhost:3000)
    allow_credentials=False,      # importante: False si usas "*"
    allow_methods=["*"],          # GET, POST, OPTIONS, etc.
    allow_headers=["*"],          # Content-Type, Authorization, etc.
)

# --- Servir el avatar 3D como estático en /avatar ---

AVATAR_DIR = BASE_DIR / "avatar_app"  # carpeta que has creado

if AVATAR_DIR.exists():
    app.mount(
        "/avatar",
        StaticFiles(directory=str(AVATAR_DIR), html=True),
        name="avatar",
    )


# --- Google Cloud Speech-to-Text (entrada de audio) ---

# Ruta al JSON desde .env
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    "/workspaces/agente-humano/backend/keys/google-stt.json",  # fallback seguro
)

def _build_speech_client() -> speech.SpeechClient | None:
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        logger.warning(
            "google_stt_credentials_missing path=%s",
            GOOGLE_CREDENTIALS_PATH,
        )
        return None

    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH
        )
        return speech.SpeechClient(credentials=credentials)
    except Exception as exc:
        logger.warning("google_stt_client_init_error=%s", exc)
        return None


speech_client = _build_speech_client()

# Google STT config desde .env
GOOGLE_STT_MODEL = os.getenv("GOOGLE_STT_MODEL", "latest_long")
GOOGLE_STT_LANGUAGE = os.getenv("GOOGLE_STT_LANGUAGE", "es-ES")
GOOGLE_STT_PUNCT = os.getenv("GOOGLE_STT_PUNCTUATION", "true").lower() == "true"
GOOGLE_STT_ENCODING = os.getenv("GOOGLE_STT_ENCODING", "WEBM_OPUS")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")

stt_config = speech.RecognitionConfig(
    language_code=GOOGLE_STT_LANGUAGE,
    enable_automatic_punctuation=GOOGLE_STT_PUNCT,
    model=GOOGLE_STT_MODEL,
    encoding=getattr(speech.RecognitionConfig.AudioEncoding, GOOGLE_STT_ENCODING),
)


def _guess_transcription_filename(upload: UploadFile) -> str:
    ct = (upload.content_type or "").lower()
    if "ogg" in ct:
        return "audio.ogg"
    if "mp4" in ct or "mpeg" in ct:
        return "audio.mp4"
    if "wav" in ct:
        return "audio.wav"
    return "audio.webm"

# --- OpenAI Text-to-Speech (salida de audio) ---

def _build_openai_client() -> OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("openai_api_key_missing_tts_disabled=true")
        return None

    try:
        return OpenAI()  # usa OPENAI_API_KEY del entorno
    except Exception as exc:
        logger.warning("openai_tts_client_init_error=%s", exc)
        return None


openai_client = _build_openai_client()

TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_VOICE = os.getenv("OPENAI_TTS_VOICE", "cedar")
DEFAULT_FORMAT = os.getenv("OPENAI_TTS_FORMAT", "wav")
DEFAULT_SPEED = float(os.getenv("OPENAI_TTS_SPEED", "1.10"))
TTS_IDENTITY_INSTRUCTIONS = os.getenv(
    "OPENAI_TTS_INSTRUCTIONS",
    (
        "Hombre de Madrid de 35 años. Acento castellano peninsular puro. "
        "Aplica una distinción fonética estricta entre la 'S' y la 'Z/C' "
        "(ceceo/seseo español). Tono de voz seco, directo y sin variaciones "
        "melódicas. Evita cualquier entonación rítmica o cantada."
    ),
)

@app.on_event("startup")
async def warmup_tts():
    """
    Llamada de calentamiento para que el primer TTS
    no tenga el coste de arranque del modelo.
    """
    if openai_client is None:
        logger.warning("warmup_tts_skipped client_unavailable=true")
        return

    try:
        # Texto corto y neutro, solo para que el modelo cargue.
        resp = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=DEFAULT_VOICE,
            input="Calibración de voz.",
            response_format=DEFAULT_FORMAT,
            speed=DEFAULT_SPEED,
            instructions=TTS_IDENTITY_INSTRUCTIONS,
        )
        # Forzamos a materializar los bytes (según formato)
        audio_bytes = getattr(resp, "content", None) or resp.read()
        print(f"[warmup] TTS precalentado. bytes={len(audio_bytes)}")
    except Exception as e:
        print("[warmup] Falló warmup TTS:", repr(e))




@app.on_event("startup")
async def startup_summary_worker() -> None:
    if deferred_summary_enabled():
        SUMMARY_JOBS.start_worker(DEFAULT_DEPS)


@app.on_event("shutdown")
async def shutdown_summary_worker() -> None:
    SUMMARY_JOBS.stop_worker()

class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str

class TTSRequest(BaseModel):
    text: str
    user_id: str | None = None
    session_id: str | None = None
    voice: str | None = None   # opcional, por si luego quieres cambiar
    format: str | None = None  # "mp3", "opus", "wav"

class TTSAudioResponse(BaseModel):
    audio_base64: str
    audio_mime_type: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    try:
        state = get_session_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

        reply, _ = run_agent(state, payload.message)
        return ChatResponse(reply=reply)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente: {e}",
        )

@app.post("/negociar", response_model=ChatResponse)
def negociar_endpoint(payload: ChatRequest):
    """
    Endpoint específico para el agente NEGOCIADOR (comprador de coche).

    Usa el mismo sistema de sesión (user_id + session_id),
    pero pasa la conversación por el grafo de LangGraph
    con planner + executor.
    """
    try:
        state = get_session_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

        reply, _ = run_negotiation_agent(state, payload.message)

        if deferred_summary_enabled():
            SUMMARY_JOBS.enqueue(
                make_turn_job(
                    state,
                    context_limit_turns=DEFAULT_CONTEXT_LIMIT_TURNS,
                    keep_last_n_turns=DEFAULT_KEEP_LAST_TURNS,
                )
            )

        return ChatResponse(reply=reply)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente de negociación: {e}",
        )


def _trace_sse_generator():
    seen_counts: dict[tuple[str, str], int] = {
        (event["user_id"], event["session_id"]): int(event["trace_index"]) + 1
        for event in list_recent_trace_events(SESSIONS)
    }

    for event in list_recent_trace_events(SESSIONS):
        if os.getenv("TRACE_PERF_DIAGNOSTICS", "0") == "1":
            ser_started = time.perf_counter()
            event_json = json.dumps(event, ensure_ascii=False)
            ser_ms = int((time.perf_counter() - ser_started) * 1000)
            event.setdefault("timing", {}).setdefault("trace_perf", {})["trace_event_json_ms"] = ser_ms
            event["timing"]["trace_perf"]["trace_event_bytes"] = len(event_json.encode("utf-8"))
        yield f"event: trace\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    while True:
        sent = False
        for (user_id, session_id), session in sorted(
            SESSIONS.items(),
            key=lambda item: item[1].last_updated,
        ):
            trace = session.debug_trace or []
            last_seen = seen_counts.get((user_id, session_id), 0)
            if last_seen >= len(trace):
                continue

            for trace_index in range(last_seen, len(trace)):
                event = build_trace_event(
                    user_id=user_id,
                    session_id=session_id,
                    session=session,
                    trace_index=trace_index,
                    trace_item=trace[trace_index],
                )
                if os.getenv("TRACE_PERF_DIAGNOSTICS", "0") == "1":
                    ser_started = time.perf_counter()
                    event_json = json.dumps(event, ensure_ascii=False)
                    ser_ms = int((time.perf_counter() - ser_started) * 1000)
                    event.setdefault("timing", {}).setdefault("trace_perf", {})["trace_event_json_ms"] = ser_ms
                    event["timing"]["trace_perf"]["trace_event_bytes"] = len(event_json.encode("utf-8"))
                yield f"event: trace\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            seen_counts[(user_id, session_id)] = len(trace)
            sent = True

        if not sent:
            yield "event: ping\ndata: {}\n\n"
        time.sleep(1.0)


@app.get("/negociacion/trazas/stream")
def negotiation_trace_stream():
    return StreamingResponse(
        _trace_sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )




def _livetrace2_sse_generator():
    seen_counts: dict[tuple[str, str], int] = {}

    # Handshake inmediato para evitar timeout/buffering en proxies SSE.
    yield ": connected\n\n"

    try:
        for event in list_recent_livetrace2_events(limit=100):
            uid = str(event.get("user_id") or "")
            sid = str(event.get("session_id") or "")
            idx = int(event.get("trace_index") or 0)
            seen_counts[(uid, sid)] = max(seen_counts.get((uid, sid), 0), idx + 1)
            yield f"event: trace2\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        keepalive_every_s = 12.0
        last_keepalive_ts = time.perf_counter()

        while True:
            sent = False
            for (user_id, session_id), session in sorted(SESSIONS.items(), key=lambda item: item[1].last_updated):
                trace = session.debug_trace or []
                last_seen = seen_counts.get((user_id, session_id), 0)
                if last_seen >= len(trace):
                    continue
                for trace_index in range(last_seen, len(trace)):
                    event = build_livetrace2_event(
                        user_id=user_id,
                        session_id=session_id,
                        session=session,
                        trace_index=trace_index,
                        trace_item=trace[trace_index],
                    )
                    append_livetrace2_event(event)
                    yield f"event: trace2\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                seen_counts[(user_id, session_id)] = len(trace)
                sent = True

            now = time.perf_counter()
            if (not sent) and (now - last_keepalive_ts >= keepalive_every_s):
                yield ": ping\n\n"
                last_keepalive_ts = now

            time.sleep(1.0)
    except GeneratorExit:
        return
    except Exception as exc:
        logger.exception("livetrace2_stream_generator_error=%s", exc)
        yield f"event: error\ndata: {json.dumps({'error': str(exc)[:200]}, ensure_ascii=False)}\n\n"


def _livetrace2_stream_response() -> StreamingResponse:
    return StreamingResponse(
        _livetrace2_sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/negociacion/livetrace2/stream")
def negotiation_livetrace2_stream():
    return _livetrace2_stream_response()


@app.get("/livetrace2/stream")
def livetrace2_stream_alias():
    return _livetrace2_stream_response()


@app.get("/negociacion/livetrace2", response_class=HTMLResponse)
@app.get("/livetrace2", response_class=HTMLResponse)
def negotiation_livetrace2_panel():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>LiveTrace2 v1</title>
  <style>
    body { margin:0; font-family: Inter, system-ui, sans-serif; background:#020617; color:#e2e8f0; }
    .wrap { width:96vw; max-width:none; margin:0 auto; padding:14px; }
    .top { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
    .badge { padding:4px 10px; border-radius:999px; font-size:12px; background:#334155; }
    .ok { background:#14532d; }
    .controls { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; align-items:center; }
    .pill { background:#1e293b; border-radius:8px; padding:6px 10px; border:1px solid #334155; font-size:12px; color:#e2e8f0; }
    button.pill { cursor:pointer; }
    .meta-small { color:#94a3b8; font-size:11px; }
    #filtersPanel { display:none; margin-top:8px; border:1px solid #334155; border-radius:10px; background:#0b1326; padding:10px; }
    #filtersPanel .filters-grid { display:grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap:8px; }
    .turns { margin-top:12px; display:grid; gap:10px; }
    .turn-card { border:1px solid #1e293b; border-radius:12px; background:#0b1326; padding:10px; }
    .dialog-only { border:1px solid #334155; border-radius:12px; background:#0b1326; padding:10px; margin-top:10px; }
    .dialog-item { padding:10px 0; border-bottom:1px solid #1e293b; }
    .dialog-item:last-child { border-bottom:none; }
    .turn-head { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
    .nodes { margin-top:8px; display:grid; gap:8px; }
    .node { border:1px solid #334155; border-radius:10px; padding:8px; background:#0f172a; }
    .summary-strip { margin-top:8px; display:grid; grid-template-columns:repeat(4, minmax(180px, 1fr)); gap:8px; }
    .summary-box { border:1px solid #334155; border-radius:10px; padding:8px; background:#0f172a; cursor:pointer; }
    .summary-box.active { border-color:#38bdf8; }
    .summary-box .t { font-size:11px; color:#cbd5e1; }
    .summary-box .m { font-size:12px; color:#93c5fd; margin-top:4px; display:flex; justify-content:space-between; }
    .s-ok { color:#86efac; }
    .s-error { color:#fca5a5; }
    .s-skipped { color:#fcd34d; }
    .s-missing { color:#94a3b8; }
    .row { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:#93c5fd; }
    .io { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:8px; }
    .box { border:1px solid #334155; border-radius:10px; background:#020617; }
    .box h4 { margin:0; padding:8px; border-bottom:1px solid #1e293b; font-size:12px; color:#93c5fd; }
    pre { margin:0; padding:10px; white-space:pre-wrap; word-break:break-word; max-height:28vh; overflow:auto; font-size:12px; }
    @media (max-width: 1280px) { .summary-strip { grid-template-columns:repeat(2, minmax(220px, 1fr)); } }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h2 style="margin:0">LiveTrace2 v1</h2>
      <div class="meta-small">Listado acumulado de turnos, filtros por nodo y control de despliegue global/local.</div>
    </div>
    <div>
      <span id="conn" class="badge">conectando...</span>
      <span id="total" class="badge">0 turnos</span>
    </div>
  </div>

  <div class="controls">
    <button id="expandAllBtn" class="pill">Desplegar todo</button>
    <button id="filtersBtn" class="pill">Filtros</button>
    <label id="skippedWrap" class="pill" style="display:flex;align-items:center;gap:6px;"><input id="toggleSkipped" type="checkbox" checked /> Show skipped/not captured</label>
    <button id="dialogBtn" class="pill">dialogo</button>
  </div>

  <div id="filtersPanel">
    <div class="meta-small" style="margin-bottom:8px;">Filtra nodos por nombre (afecta a cards de resumen y detalle).</div>
    <div id="filtersGrid" class="filters-grid"></div>
  </div>

  <div id="turnsList" class="turns"><div class="meta-small">Aún no hay turnos recibidos.</div></div>
</div>

<script>
const HIDDEN_TRACE_NODES = new Set([
  'world_gate',
  'belief_gate',
  'world_extractor_llm',
  'belief_llm',
]);
const FILTER_NODE_ORDER = [
  'advisor_llm',
  'world_judge_llm',
  'planner_gate',
  'planner_llm',
  'executor_llm',
  'finalizer_llm',
];
const SUMMARY_NODE_ORDER = FILTER_NODE_ORDER;

const conn = document.getElementById('conn');
const total = document.getElementById('total');
const turnsList = document.getElementById('turnsList');
const expandAllBtn = document.getElementById('expandAllBtn');
const filtersBtn = document.getElementById('filtersBtn');
const filtersPanel = document.getElementById('filtersPanel');
const filtersGrid = document.getElementById('filtersGrid');
const toggleSkipped = document.getElementById('toggleSkipped');
const skippedWrap = document.getElementById('skippedWrap');
const dialogBtn = document.getElementById('dialogBtn');

const turns = [];
const turnIndexById = new Map();
const localExpanded = new Set();
const activeFilters = new Set(FILTER_NODE_ORDER);
const expandedNodeByTurn = new Map();
let expandAll = false;
let dialogMode = false;

function pretty(v){ try{return JSON.stringify(v ?? {}, null, 2);}catch{return String(v ?? '');} }
function ts(v){
  if(v === null || v === undefined || v === '') return 'NO TIMESTAMPS';
  const normalized = (typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 1e12) ? v * 1000 : v;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? 'NO TIMESTAMPS' : d.toISOString();
}
function escapeHtml(v){ return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }

function turnId(evt){
  const session = String(evt.session_id || evt?.header?.event_identity?.session_id || 'session');
  return `${session}::${Number(evt.turn_idx || 0)}::${Number(evt.trace_index || 0)}`;
}

function detail(node){
  const input = node.input_prompt_rendered || (node.input_payload_raw == null ? 'NOT_CAPTURED' : pretty(node.input_payload_raw));
  const output = node.output_text_raw || node.output_text_rendered || (node.output_payload_parsed == null && node.output_payload_raw == null ? 'NOT_CAPTURED' : pretty(node.output_payload_parsed ?? node.output_payload_raw));
  const gateExtra = node.node_type === 'gate' ? `<div class="io"><div class="box"><h4>Gate inputs</h4><pre>${escapeHtml(pretty(node.gate_inputs))}</pre></div><div class="box"><h4>Gate decision</h4><pre>${escapeHtml(node.gate_decision || '—')}
${escapeHtml((node.gate_reason_codes||[]).join(', ') || node.gate_reason || '—')}</pre></div></div>` : '';
  return `<div class="row"><strong>${escapeHtml(node.node_name)}</strong><span>${escapeHtml(node.node_type)} · ${escapeHtml(node.status || 'missing')}</span></div><div class="row"><span>${node.latency_ms ?? '—'} ms</span><span>${ts(node.started_at)} → ${ts(node.ended_at)}</span></div><div class="io"><div class="box"><h4>Entrada</h4><pre>${escapeHtml(input)}</pre></div><div class="box"><h4>Salida</h4><pre>${escapeHtml(output)}</pre></div></div>${gateExtra}`;
}

function statusClass(status){
  const s = String(status || '').toLowerCase();
  if(s === 'ok') return 's-ok';
  if(s === 'error') return 's-error';
  if(s === 'skipped') return 's-skipped';
  return 's-missing';
}

function renderFilters(){
  filtersGrid.innerHTML = FILTER_NODE_ORDER.map((name)=>{
    const checked = activeFilters.has(name) ? 'checked' : '';
    return `<label class="pill" style="display:flex;align-items:center;gap:6px;"><input class="filterItem" type="checkbox" data-name="${name}" ${checked} />${name}</label>`;
  }).join('');
  for(const el of filtersGrid.querySelectorAll('.filterItem')){
    el.onchange = (event) => {
      const name = String(event.target?.getAttribute('data-name') || '');
      if(!name) return;
      if(event.target.checked) activeFilters.add(name);
      else activeFilters.delete(name);
      for(const [tid, nodeName] of expandedNodeByTurn.entries()){
        if(nodeName === name && !activeFilters.has(nodeName)) expandedNodeByTurn.set(tid, null);
      }
      renderTurns();
    };
  }
}

function isNodeVisible(node){
  const name = String(node.node_name || '');
  if(!activeFilters.has(name)) return false;
  if(toggleSkipped.checked) return true;
  const skipped = String(node.status||'') === 'skipped';
  const notCaptured = String(node.input_capture_state||'') === 'not_captured' && String(node.output_capture_state||'') === 'not_captured';
  return !(skipped || notCaptured);
}
function escapeHtml(v){ return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }

function buildSummaryNodes(allNodes){
  const byName = new Map();
  for(const node of allNodes){
    const name = String(node.node_name || '');
    if(!name || byName.has(name)) continue;
    byName.set(name, node);
  }

  const ordered = [];
  for(const name of SUMMARY_NODE_ORDER){
    if(byName.has(name)) ordered.push(byName.get(name));
  }

  for(const [name, node] of byName.entries()){
    if(!SUMMARY_NODE_ORDER.includes(name)) ordered.push(node);
  }
  return ordered;
}


function pickUserText(evt){
  return String(evt.input_message || evt.user_message || evt.message || (evt.payload||{}).user_message || '').trim() || '—';
}

function pickIaText(evt){
  return String(evt.assistant_message || evt.final_reply || evt.output_text || evt.reply || (((evt.payload||{}).executor_output||{}).response_text) || '').trim() || '—';
}

function renderDialogOnly(){
  const orderedTurns = [...turns].sort((a,b)=>{
    const sa = String(a.session_id || '');
    const sb = String(b.session_id || '');
    if(sa !== sb) return sa.localeCompare(sb);
    const ta = Number(a.turn_idx || 0);
    const tb = Number(b.turn_idx || 0);
    if(ta !== tb) return ta - tb;
    return Number(a.trace_index || 0) - Number(b.trace_index || 0);
  });
  if(!orderedTurns.length){
    turnsList.innerHTML = '<div class="meta-small">Aún no hay turnos recibidos.</div>';
    return;
  }
  turnsList.innerHTML = `<div class="dialog-only">${orderedTurns.map((evt)=>`<div class="dialog-item"><div><strong>User:</strong> ${escapeHtml(pickUserText(evt))}</div><div style="margin-top:6px"><strong>IA:</strong> ${escapeHtml(pickIaText(evt))}</div></div>`).join('')}</div>`;
}


function orderNodesForDisplay(nodes){
  const prio = new Map(SUMMARY_NODE_ORDER.map((name, idx)=>[name, idx]));
  return [...nodes].sort((a,b)=>{
    const pa = prio.has(String(a.node_name || '')) ? prio.get(String(a.node_name || '')) : 999;
    const pb = prio.has(String(b.node_name || '')) ? prio.get(String(b.node_name || '')) : 999;
    if(pa !== pb) return pa - pb;
    return Number(a.sequence_index || 0) - Number(b.sequence_index || 0);
  });
}

function renderTurns(){
  total.textContent = `${turns.length} turnos`;
  if(dialogMode){
    renderDialogOnly();
    return;
  }
  if(!turns.length){
    turnsList.innerHTML = '<div class="meta-small">Aún no hay turnos recibidos.</div>';
    return;
  }
  turnsList.innerHTML = turns.map((evt)=>{
    const id = turnId(evt);
    const allNodes = Array.isArray(evt.nodes) ? evt.nodes : [];
    const renderableNodes = allNodes.filter((node)=>!HIDDEN_TRACE_NODES.has(String(node.node_name || '')));
    const visibleNodes = orderNodesForDisplay(renderableNodes.filter(isNodeVisible));
    const expanded = expandAll || localExpanded.has(id);
    const selectedNodeName = expandedNodeByTurn.get(id) || null;

    const details = expanded
      ? (visibleNodes.length
          ? `<div class="nodes">${visibleNodes.map((node)=>`<div class="node">${detail(node)}</div>`).join('')}</div>`
          : '<div class="meta-small" style="margin-top:8px;">No hay nodos visibles con los filtros actuales.</div>')
      : (()=>{
          const summaryNodes = buildSummaryNodes(renderableNodes).filter((node)=>isNodeVisible(node));
          const strip = summaryNodes.length
            ? `<div class="summary-strip">${summaryNodes.map((node)=>`<div class="summary-box ${selectedNodeName===node.node_name?'active':''}" data-turn-id="${id}" data-node-name="${node.node_name}"><div class="t">${escapeHtml(node.node_name)}</div><div class="m"><span>${escapeHtml(String(node.latency_ms ?? '—'))} ms</span><span class="${statusClass(node.status)}">${escapeHtml(String(node.status || 'missing'))}</span></div></div>`).join('')}</div>`
            : '<div class="meta-small" style="margin-top:8px;">No hay nodos visibles con los filtros actuales.</div>';
          const selectedNode = summaryNodes.find((n)=>String(n.node_name)===String(selectedNodeName)) || null;
          const oneNodeDetail = selectedNode ? `<div class="node" style="margin-top:8px">${detail(selectedNode)}</div>` : '';
          return strip + oneNodeDetail;
        })();

    const localBtn = expandAll
      ? '<button class="pill" disabled title="Desactiva Desplegar todo para usarlo">Desplegar</button>'
      : `<button class="pill local-toggle" data-turn-id="${id}">${localExpanded.has(id) ? 'Ocultar' : 'Desplegar'}</button>`;

    return `<div class="turn-card"><div class="turn-head"><div><strong>Turno ${Number(evt.turn_idx || 0)}</strong> · session=${escapeHtml(evt.session_id || 'n/a')} · trace=${Number(evt.trace_index || 0)}<div class="meta-small">${ts(evt.started_at)} → ${ts(evt.ended_at)} · visibles=${visibleNodes.length}/${renderableNodes.length} · latencia=${evt.total_latency_ms ?? '-'} ms</div><div class="meta-small" style="margin-top:4px"><strong>User:</strong> ${escapeHtml(pickUserText(evt))}</div><div class="meta-small" style="margin-top:2px"><strong>IA:</strong> ${escapeHtml(pickIaText(evt))}</div></div><div>${localBtn}</div></div>${details}</div>`;
  }).join('');

  for(const btn of turnsList.querySelectorAll('.local-toggle')){
    btn.onclick = (event) => {
      const id = String(event.target?.getAttribute('data-turn-id') || '');
      if(!id) return;
      if(localExpanded.has(id)) localExpanded.delete(id);
      else localExpanded.add(id);
      renderTurns();
    };
  }

  for(const box of turnsList.querySelectorAll('.summary-box')){
    box.onclick = (event) => {
      const tid = String(event.currentTarget?.getAttribute('data-turn-id') || '');
      const nodeName = String(event.currentTarget?.getAttribute('data-node-name') || '');
      if(!tid || !nodeName) return;
      const current = expandedNodeByTurn.get(tid) || null;
      expandedNodeByTurn.set(tid, current === nodeName ? null : nodeName);
      renderTurns();
    };
  }
}

function upsertTurn(evt){
  const id = turnId(evt);
  if(turnIndexById.has(id)){
    const idx = turnIndexById.get(id);
    turns[idx] = evt;
    return;
  }
  turnIndexById.set(id, turns.length);
  turns.push(evt);
}

expandAllBtn.onclick = () => {
  expandAll = !expandAll;
  expandAllBtn.textContent = expandAll ? 'Contraer todo' : 'Desplegar todo';
  renderTurns();
};

filtersBtn.onclick = () => {
  const isOpen = filtersPanel.style.display === 'block';
  filtersPanel.style.display = isOpen ? 'none' : 'block';
};

toggleSkipped.onchange = () => renderTurns();

dialogBtn.onclick = () => {
  dialogMode = !dialogMode;
  dialogBtn.textContent = dialogMode ? 'dialogo ✓' : 'dialogo';
  filtersPanel.style.display = dialogMode ? 'none' : filtersPanel.style.display;
  skippedWrap.style.display = dialogMode ? 'none' : 'flex';
  renderTurns();
};


renderFilters();
renderTurns();

const es = new EventSource('/negociacion/livetrace2/stream');
es.addEventListener('open', () => { conn.textContent='conectado'; conn.className='badge ok'; });
es.addEventListener('error', () => { conn.textContent='reconectando'; conn.className='badge'; });
es.addEventListener('trace2', (event) => {
  const evt = JSON.parse(event.data);
  upsertTurn(evt);
  renderTurns();
});

window.__livetrace2_ingest = (evt) => { upsertTurn(evt); renderTurns(); };
</script>
</body>
</html>
"""

@app.get("/negociacion/trazas", response_class=HTMLResponse)
def negotiation_trace_panel():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Panel LiveTrace - Negociación</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: Inter, system-ui, sans-serif; margin: 0; background: #020617; color: #e2e8f0; }
    .wrap { max-width: 1320px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    .hint { color: #94a3b8; margin-bottom: 14px; }
    .status { margin-bottom: 12px; font-size: 14px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; }
    .ok { background: #14532d; color: #bbf7d0; }
    .warn { background: #7c2d12; color: #fed7aa; }
    .controls { display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
    .controls input { background:#0f172a; border:1px solid #334155; color:#e2e8f0; border-radius:8px; padding:8px 10px; }
    .list { display: grid; gap: 12px; }
    .item { border: 1px solid #1e293b; border-radius: 12px; padding: 12px; background: #0b1326; }
    .head { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
    .meta { color: #93c5fd; font-size: 13px; }
    .row { margin-top: 7px; font-size: 13px; }
    .grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; margin-top: 8px; }
    .pill { background:#1e293b; border:1px solid #334155; border-radius:8px; padding:6px 8px; font-size:12px; }
    .kv { display:grid; grid-template-columns: 220px 1fr; gap:8px; font-size:12px; margin-top:6px; }
    .k { color:#94a3b8; }
    .v { color:#cbd5e1; word-break: break-word; }
    details { margin-top:8px; border:1px solid #1e293b; border-radius:8px; padding:6px 10px; background:#0f172a; }
    summary { cursor:pointer; color:#93c5fd; }
    pre { margin:8px 0 0; white-space:pre-wrap; word-break:break-word; font-size:12px; color:#cbd5e1; }
    code { color: #c4b5fd; }
    .err { color: #fca5a5; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>LiveTrace Negociación</h1>
    <div class="hint">Abre siempre esta URL para ver todo en directo (todas las sesiones). Incluye respuesta final, gates, estado base/nuevo y razonamiento.</div>
    <div class="status">
      <span>Conexión SSE:</span> <span id="conn" class="badge warn">conectando...</span>
      <span class="badge" id="total">0 eventos</span>
    </div>
    <div class="controls">
      <input id="sessionFilter" placeholder="Filtrar por session_id o user_id" />
      <input id="textFilter" placeholder="Filtrar por policy/fase/respuesta" />
    </div>
    <div id="events" class="list"></div>
  </div>

  <script>
    const connEl = document.getElementById('conn');
    const eventsEl = document.getElementById('events');
    const totalEl = document.getElementById('total');
    const sessionFilter = document.getElementById('sessionFilter');
    const textFilter = document.getElementById('textFilter');
    const store = [];

    function pretty(obj) { return JSON.stringify(obj || {}, null, 2); }
    function joinOrDash(arr) { return (arr && arr.length) ? arr.join(', ') : '—'; }

    function matchesFilters(evt) {
      const sf = sessionFilter.value.trim().toLowerCase();
      const tf = textFilter.value.trim().toLowerCase();
      if (sf) {
        const identity = `${evt.user_id} ${evt.session_id}`.toLowerCase();
        if (!identity.includes(sf)) return false;
      }
      if (tf) {
        const haystack = `${evt.policy || ''} ${evt.phase || ''} ${evt.final_reply || ''}`.toLowerCase();
        if (!haystack.includes(tf)) return false;
      }
      return true;
    }

    function durationMs(timing) {
      const total = timing?.turn_total_ms;
      if (typeof total === 'number' && Number.isFinite(total) && total >= 0) {
        return Number.isInteger(total) ? `${total} ms` : `${total.toFixed(1)} ms`;
      }
      const start = Number(timing?.timeline?.t_turn_start || 0);
      const end = Number(timing?.timeline?.t_after_graph || 0);
      if (!start || !end || end < start) return 'n/a';
      const ms = (end - start) * 1000;
      return Number.isInteger(ms) ? `${ms} ms` : `${ms.toFixed(1)} ms`;
    }

    function renderAll() {
      eventsEl.innerHTML = '';
      const visible = store.filter(matchesFilters);
      for (const evt of visible) {
        const plannerFail = evt.planner_failed || evt.belief_update_failed;
        const card = document.createElement('div');
        card.className = 'item';
        const when = new Date(evt.updated_at).toLocaleTimeString();
        const gateChoices = (evt.gate_choices || []).map(g => `${g.gate}: enabled=${g.gate_enabled ? 'true' : 'false'} · decision=${g.gate_decision}${g.gate_reason ? ` · reason=${g.gate_reason}` : ''}`).join(' | ') || 'sin gates booleanos';
        card.innerHTML = `
          <div class="head">
            <strong>${plannerFail ? '⚠️' : '✅'} turno ${evt.turn} · ${evt.policy || 'policy:n/a'}</strong>
            <span class="meta">${evt.user_id} / ${evt.session_id} · ${when}</span>
          </div>
          <div class="row">fase: <code>${evt.phase || 'n/a'}</code> · duración: <code>${durationMs(evt.timing)}</code> · fallback planner: <code>${evt.planner_fallback_used ? 'sí' : 'no'}</code></div>
          <div class="row">mensaje usuario: <code>${(evt.input_message || '').replaceAll('<','&lt;')}</code></div>
          <div class="row">respuesta final agente: <code>${(evt.final_reply || '').replaceAll('<','&lt;')}</code></div>

          <div class="grid">
            <div class="pill"><strong>Policies permitidas:</strong> ${joinOrDash(evt.allowed_policy_ids)}</div>
            <div class="pill"><strong>Gate elegido:</strong> ${gateChoices}</div>
            <div class="pill"><strong>world changed:</strong> ${joinOrDash(evt.world_changed_keys)} </div>
            <div class="pill"><strong>world unchanged:</strong> ${joinOrDash(evt.world_unchanged_keys)} </div>
            <div class="pill"><strong>belief changed:</strong> ${joinOrDash(evt.belief_changed_keys)} </div>
            <div class="pill"><strong>belief unchanged:</strong> ${joinOrDash(evt.belief_unchanged_keys)} </div>
          </div>

          <div class="kv"><span class="k">extractor</span><span class="v">used=${evt.extractor_used ? 'sí' : 'no'} · reasons=${joinOrDash(evt.extractor_reasons)} · patch_keys=${joinOrDash(evt.extractor_world_patch_keys)}</span></div>
          <div class="kv"><span class="k">evidencia top</span><span class="v">${(evt.top_evidence_v2 || []).map(r => `${r.path}=${r.value}(${r.confidence})`).join(' | ') || '—'}</span></div>
          <div class="kv"><span class="k">errores</span><span class="v ${plannerFail ? 'err' : ''}">planner=${evt.planner_error || '—'} · belief=${evt.belief_update_error || '—'}</span></div>

          <details><summary>Estado base vs nuevo (world)</summary><pre>${pretty({base: evt.world_base, new: evt.world_new, diff: evt.world_diff})}</pre></details>
          <details><summary>Estado base vs nuevo (belief)</summary><pre>${pretty({base: evt.belief_base, new: evt.belief_new, diff: evt.belief_diff})}</pre></details>
          <details><summary>Decisión y planificación</summary><pre>${pretty({policy_plan_judgement: evt.policy_plan_judgement, policy_decision: evt.policy_decision, policy_pre_repair: evt.policy_pre_repair, policy_post_repair: evt.policy_post_repair, executed_policy: evt.executed_policy, phase_candidate: evt.phase_candidate, phase_effective: evt.phase_effective, planner_reason: evt.planner_reason, planner_meta: evt.planner_meta, planner_debug: evt.planner_debug, progress_debug: evt.progress_debug, gates: evt.gates})}</pre></details>
          <details><summary>Validación, memoria y modelo</summary><pre>${pretty({validation_issues: evt.validation_issues, memory_meta: evt.memory_meta, refresh_meta: evt.refresh_meta, summary_enqueue_meta: evt.summary_enqueue_meta, model_params: evt.model_params, timing: evt.timing})}</pre></details>
        `;
        eventsEl.appendChild(card);
      }
      totalEl.textContent = `${visible.length} eventos visibles / ${store.length} total`;
    }

    [sessionFilter, textFilter].forEach(el => el.addEventListener('input', renderAll));

    const es = new EventSource('/negociacion/trazas/stream');
    es.addEventListener('open', () => {
      connEl.textContent = 'conectado';
      connEl.className = 'badge ok';
    });
    es.addEventListener('error', () => {
      connEl.textContent = 'reconectando';
      connEl.className = 'badge warn';
    });
    es.addEventListener('trace', (event) => {
      const data = JSON.parse(event.data);
      store.unshift(data);
      if (store.length > 250) store.pop();
      renderAll();
    });
  </script>
</body>
</html>
"""

@app.get("/demo", response_class=HTMLResponse)
def demo_page():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>Demo Agente Humano</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 0;
      background: #0f172a;
      color: #e5e7eb;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
    }
    .chat-container {
      background: #020617;
      border-radius: 16px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
      width: 100%;
      max-width: 900px;
      height: 80vh;
      display: flex;
      flex-direction: column;
      padding: 16px;
      box-sizing: border-box;
    }
    .chat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .chat-header h1 {
      font-size: 18px;
      margin: 0;
    }
    .mode-selector {
      font-size: 13px;
      color: #9ca3af;
    }
    .mode-selector label {
      margin-right: 12px;
      cursor: pointer;
    }
    .session-info {
      display: flex;
      gap: 8px;
      margin-bottom: 8px;
    }
    .session-info input {
      flex: 1;
      padding: 6px 8px;
      border-radius: 8px;
      border: 1px solid #1f2937;
      background: #020617;
      color: #e5e7eb;
      font-size: 12px;
    }
    .messages {
      flex: 1;
      border-radius: 12px;
      border: 1px solid #1f2937;
      background: radial-gradient(circle at top left, #0f172a, #020617);
      padding: 12px;
      overflow-y: auto;
      font-size: 14px;
    }
    .msg {
      margin-bottom: 8px;
      line-height: 1.4;
      max-width: 80%;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    .msg-user {
      text-align: right;
      margin-left: auto;
      background: #1d4ed8;
      border-radius: 12px 12px 0 12px;
      padding: 6px 10px;
      color: #e5e7eb;
    }
    .msg-assistant {
      text-align: left;
      background: #020617;
      border-radius: 12px 12px 12px 0;
      padding: 6px 10px;
      border: 1px solid #1f2937;
    }
    .chat-input {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }
    .chat-input textarea {
      flex: 1;
      resize: none;
      border-radius: 10px;
      border: 1px solid #1f2937;
      padding: 8px;
      font-size: 14px;
      background: #020617;
      color: #e5e7eb;
      height: 60px;
    }
    .chat-input button {
      width: 110px;
      border-radius: 10px;
      border: none;
      background: #22c55e;
      color: #020617;
      font-weight: 600;
      cursor: pointer;
      font-size: 14px;
    }
    .chat-input button:disabled {
      opacity: 0.6;
      cursor: default;
    }
    .status {
      font-size: 12px;
      color: #9ca3af;
      margin-top: 4px;
      height: 16px;
    }
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="chat-header">
  <h1>Demo Agente Humano</h1>
  <div style="display: flex; align-items: center; gap: 8px;">
    <button id="openAvatarBtn" style="font-size: 12px; padding: 4px 8px;">
      Ver en avatar
    </button>
    <div class="mode-selector">
      <label>
        <input type="radio" name="mode" value="chat" checked />
        Chat normal (/chat)
      </label>
      <label>
        <input type="radio" name="mode" value="negociar" />
        Negociador (/negociar)
      </label>
    </div>
  </div>
</div>

    <div class="session-info">
      <input id="userId" placeholder="user_id" value="test_user" />
      <input id="sessionId" placeholder="session_id" value="sesion_1" />
    </div>

    <div id="messages" class="messages"></div>

    <div class="chat-input">
      <textarea id="input" placeholder="Escribe tu mensaje y pulsa Enter o clic en Enviar..."></textarea>
      <button id="sendBtn">Enviar</button>
    </div>
    <div id="status" class="status"></div>
  </div>

  <script>
    const messagesEl = document.getElementById("messages");
    const inputEl = document.getElementById("input");
    const sendBtn = document.getElementById("sendBtn");
    const statusEl = document.getElementById("status");
    const userIdEl = document.getElementById("userId");
    const sessionIdEl = document.getElementById("sessionId");

    function appendMessage(text, who) {
      const div = document.createElement("div");
      div.classList.add("msg");
      if (who === "user") {
        div.classList.add("msg-user");
      } else {
        div.classList.add("msg-assistant");
      }
      div.textContent = text;
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
      const text = inputEl.value.trim();
      if (!text) return;

      const mode = document.querySelector('input[name="mode"]:checked').value;
      const endpoint = mode === "negociar" ? "/negociar" : "/chat";

      const user_id = userIdEl.value.trim() || "anon";
      const session_id = sessionIdEl.value.trim() || "sesion_1";

      appendMessage(text, "user");
      inputEl.value = "";
      inputEl.focus();

      sendBtn.disabled = true;
      statusEl.textContent = "Pensando...";

      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            user_id,
            session_id,
            message: text
          })
        });

        if (!res.ok) {
          const errText = await res.text();
          appendMessage("Error " + res.status + ": " + errText, "assistant");
        } else {
          const data = await res.json();
          appendMessage(data.reply, "assistant");
        }
      } catch (err) {
        appendMessage("Error de red: " + err, "assistant");
      } finally {
        sendBtn.disabled = false;
        statusEl.textContent = "";
      }
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    
    const openAvatarBtn = document.getElementById("openAvatarBtn");
    openAvatarBtn.addEventListener("click", () => {
      window.location.href = "/avatar/";
    });

  </script>
</body>
</html>
    """

@app.post("/stt_google")
async def stt_google(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Archivo de audio vacío.")

    if speech_client is not None:
        try:
            audio = speech.RecognitionAudio(content=audio_bytes)
            response = speech_client.recognize(
                config=stt_config,
                audio=audio
            )

            text = ""
            for result in response.results:
                text += result.alternatives[0].transcript + " "

            return {"text": text.strip()}
        except Exception as exc:
            logger.warning("google_stt_runtime_error=%s", exc)

    if openai_client is not None:
        try:
            transcription = openai_client.audio.transcriptions.create(
                model=OPENAI_STT_MODEL,
                file=(_guess_transcription_filename(file), audio_bytes),
                language=GOOGLE_STT_LANGUAGE.split("-")[0],
            )
            text = (getattr(transcription, "text", "") or "").strip()
            if not text:
                raise ValueError("Transcripción vacía")
            return {"text": text}
        except Exception as exc:
            logger.warning("openai_stt_runtime_error=%s", exc)

    raise HTTPException(
        status_code=503,
        detail="No hay proveedor STT disponible (Google/OpenAI).",
    )

@app.post("/tts_openai")
async def tts_openai(payload: TTSRequest):
    if openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="OpenAI TTS no está configurado en este entorno.",
        )

    try:
        voice = payload.voice or DEFAULT_VOICE
        fmt = DEFAULT_FORMAT
        if payload.format and payload.format != DEFAULT_FORMAT:
            logger.info(
                "Formato solicitado ignorado; usando formato TTS por defecto",
                extra={"requested_format": payload.format, "default_format": DEFAULT_FORMAT},
            )

        print(f"[TTS_OPENAI] Texto: {payload.text!r}")
        print(f"[TTS_OPENAI] model={TTS_MODEL}, voice={voice}, response_format={fmt}")

        audio_resp = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=payload.text,
            response_format=fmt,
            speed=DEFAULT_SPEED,
            instructions=TTS_IDENTITY_INSTRUCTIONS,
        )

        audio_bytes = audio_resp.read()  # <--- aquí también
        print(f"[TTS_OPENAI] audio_bytes len={len(audio_bytes)}")

        media_type = (
            "audio/mpeg" if fmt == "mp3"
            else "audio/ogg" if fmt == "opus"
            else "audio/wav"
        )

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type=media_type,
        )

    except Exception as e:
        import traceback
        print("ERROR en /tts_openai:")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error en OpenAI TTS: {e}",
        )


    
@app.post("/tts", response_model=TTSAudioResponse)
async def tts(payload: TTSRequest):
    if openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="OpenAI TTS no está configurado en este entorno.",
        )

    try:
        t_tts_request_start = time.perf_counter()
        voice = payload.voice or DEFAULT_VOICE
        fmt = DEFAULT_FORMAT
        if payload.format and payload.format != DEFAULT_FORMAT:
            logger.info(
                "Formato solicitado ignorado; usando formato TTS por defecto",
                extra={"requested_format": payload.format, "default_format": DEFAULT_FORMAT},
            )
        if fmt not in {"mp3", "opus", "wav"}:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de audio no soportado: {fmt}",
            )

        if deferred_summary_enabled() and payload.user_id and payload.session_id:
            state = get_session_state(payload.user_id, payload.session_id)
            enqueued = SUMMARY_JOBS.enqueue(
                make_turn_job(
                    state,
                    context_limit_turns=DEFAULT_CONTEXT_LIMIT_TURNS,
                    keep_last_n_turns=DEFAULT_KEEP_LAST_TURNS,
                )
            )
            logger.info(
                "summary_job_enqueue_from_tts",
                extra={
                    "user_id": payload.user_id,
                    "session_id": payload.session_id,
                    "turn_id": state.turn_count,
                    "enqueued": enqueued,
                    "t_tts_request_start": t_tts_request_start,
                    "t_summary_enqueued_from_tts": time.perf_counter(),
                },
            )

        print(f">>> /tts llamado. Texto: {payload.text!r}")
        print(f">>> model={TTS_MODEL}, voice={voice}, response_format={fmt}")

        media_type = (
            "audio/mpeg" if fmt == "mp3" else "audio/ogg" if fmt == "opus" else "audio/wav"
        )
        audio = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=payload.text,
            response_format=fmt,
            speed=DEFAULT_SPEED,
            instructions=TTS_IDENTITY_INSTRUCTIONS,
        )

        audio_bytes = audio.content
        print(
            f">>> /tts: audio_bytes len={len(audio_bytes)}, media_type={media_type}"
        )
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        logger.info(
            "Enviando audio TTS base64",
            extra={
                "tts_format": fmt,
                "audio_mime_type": media_type,
                "audio_base64_len": len(audio_b64),
            },
        )

        return TTSAudioResponse(
            audio_base64=audio_b64,
            audio_mime_type=media_type,
        )

    except Exception as e:
        print("ERROR en /tts:", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en TTS: {e}",
        )
