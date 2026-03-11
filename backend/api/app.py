# backend/api/app.py
from __future__ import annotations

import os
import pathlib
import sys
import asyncio

from dotenv import load_dotenv
from pathlib import Path

# cargar variables del .env (en backend/.env)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from google.cloud import speech
from google.oauth2 import service_account

import io  # arriba del archivo
import time
from fastapi.responses import StreamingResponse
import openai

import base64
from typing import Any, Literal, cast

from fastapi.staticfiles import StaticFiles

BASE_DIR = pathlib.Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sessions.state import get_session_state
from agent import run_agent
from negociacion import run_negotiation_agent
from negociacion.orchestration.flow_config import set_tts_prefetch_hook
from negociacion.optimizador import router as optimizador_router

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

AVATAR_DIR = BACKEND_DIR / "avatar_app"  # carpeta que has creado

if AVATAR_DIR.exists():
    app.mount(
        "/avatar",
        StaticFiles(directory=str(AVATAR_DIR), html=True),
        name="avatar",
    )

OPTIMIZADOR_DIR = AVATAR_DIR / "optimizador"
if OPTIMIZADOR_DIR.exists():
    app.mount(
        "/optimizador",
        StaticFiles(directory=str(OPTIMIZADOR_DIR), html=True),
        name="optimizador",
    )

app.include_router(optimizador_router)

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
        _ = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH
        )
        return speech.SpeechClient.from_service_account_file(GOOGLE_CREDENTIALS_PATH)
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

def _build_openai_client():
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("openai_api_key_missing_tts_disabled=true")
        return None

    try:
        return openai.OpenAI()  # usa OPENAI_API_KEY del entorno
    except Exception as exc:
        logger.warning("openai_tts_client_init_error=%s", exc)
        return None


openai_client = _build_openai_client()

TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_VOICE = os.getenv("OPENAI_TTS_VOICE", "cedar")
DEFAULT_FORMAT = os.getenv("OPENAI_TTS_FORMAT", "wav")
DEFAULT_SPEED = float(os.getenv("OPENAI_TTS_SPEED", "1.10"))
_ALLOWED_TTS_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
TTSAudioFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]

_tts_audio_cache: dict[str, bytes] = {}
_tts_inflight_tasks: dict[str, asyncio.Future[Any]] = {}
_main_event_loop: asyncio.AbstractEventLoop | None = None

def _resolved_tts_format(requested: str | None = None) -> TTSAudioFormat:
    value = (requested or DEFAULT_FORMAT or "wav").strip().lower()
    if value not in _ALLOWED_TTS_FORMATS:
        value = "wav"
    return cast(TTSAudioFormat, value)

TTS_IDENTITY_INSTRUCTIONS = os.getenv(
    "OPENAI_TTS_INSTRUCTIONS",
    (
        "Hombre de Madrid de 35 años. Acento castellano peninsular puro. "
        "Aplica una distinción fonética estricta entre la 'S' y la 'Z/C' "
        "(ceceo/seseo español). Tono de voz seco, directo y sin variaciones "
        "melódicas. Evita cualquier entonación rítmica o cantada."
    ),
)


def _tts_media_type(fmt: TTSAudioFormat) -> str:
    return (
        "audio/mpeg" if fmt == "mp3" else "audio/ogg" if fmt == "opus" else "audio/wav"
    )


def _sync_generate_tts_audio(text: str, voice: str, fmt: TTSAudioFormat) -> bytes:
    audio_resp = openai_client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
        response_format=fmt,
        speed=DEFAULT_SPEED,
        instructions=TTS_IDENTITY_INSTRUCTIONS,
    )
    return getattr(audio_resp, "content", None) or audio_resp.read()


async def pre_generate_tts(text: str):
    if openai_client is None:
        return

    normalized_text = text.strip()
    if not normalized_text:
        return

    if normalized_text in _tts_audio_cache:
        return

    logger.info("pre_generate_tts_started text_len=%s", len(normalized_text))
    try:
        audio_bytes = await run_in_threadpool(
            _sync_generate_tts_audio,
            normalized_text,
            "cedar",
            _resolved_tts_format(),
        )
        _tts_audio_cache[normalized_text] = audio_bytes
        logger.info("pre_generate_tts_generated text_len=%s audio_bytes=%s", len(normalized_text), len(audio_bytes))
    except Exception as exc:
        logger.warning("pre_generate_tts_error=%s", exc)
    finally:
        _tts_inflight_tasks.pop(normalized_text, None)


def _schedule_tts_prefetch(text: str) -> None:
    normalized_text = text.strip()
    if not normalized_text or normalized_text in _tts_audio_cache:
        return
    if normalized_text in _tts_inflight_tasks and not _tts_inflight_tasks[normalized_text].done():
        return

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(pre_generate_tts(normalized_text))
    except RuntimeError:
        if _main_event_loop is None:
            logger.warning("pre_generate_tts_skipped no_event_loop=true")
            return
        future = asyncio.run_coroutine_threadsafe(pre_generate_tts(normalized_text), _main_event_loop)
        task = asyncio.wrap_future(future, loop=_main_event_loop)

    _tts_inflight_tasks[normalized_text] = task
    logger.info("pre_generate_tts_task_launched text_len=%s", len(normalized_text))


set_tts_prefetch_hook(_schedule_tts_prefetch)

@app.on_event("startup")
async def warmup_tts():
    """
    Llamada de calentamiento para que el primer TTS
    no tenga el coste de arranque del modelo.
    """
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()

    if openai_client is None:
        logger.warning("warmup_tts_skipped client_unavailable=true")
        return

    try:
        # Texto corto y neutro, solo para que el modelo cargue.
        resp = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=DEFAULT_VOICE,
            input="Calibración de voz.",
            response_format=_resolved_tts_format(),
            speed=DEFAULT_SPEED,
            instructions=TTS_IDENTITY_INSTRUCTIONS,
        )
        # Forzamos a materializar los bytes (según formato)
        audio_bytes = getattr(resp, "content", None) or resp.read()
        print(f"[warmup] TTS precalentado. bytes={len(audio_bytes)}")
    except Exception as e:
        print("[warmup] Falló warmup TTS:", repr(e))




class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    finish_button_armed: bool = False

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
        return ChatResponse(reply=reply, finish_button_armed=False)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente: {e}",
        )

@app.post("/negociar", response_model=ChatResponse)
def negociar_endpoint(payload: ChatRequest):
    try:
        state = get_session_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

        reply, updated_state = run_negotiation_agent(state, payload.message)
        finish_button_armed = False
        negotiation_canonical = updated_state.world_state.get("negotiation_canonical", {}) if isinstance(updated_state.world_state, dict) else {}
        if isinstance(negotiation_canonical, dict):
            ui_state = negotiation_canonical.get("ui_state", {})
            if isinstance(ui_state, dict):
                finish_button_armed = bool(ui_state.get("finish_button_armed", False))
        return ChatResponse(reply=reply, finish_button_armed=finish_button_armed)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en negociación: {e}",
        )

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
    <div class="mode-selector">Solo chat (/chat)</div>
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

      const endpoint = "/chat";

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
        fmt = _resolved_tts_format(payload.format)
        
        print(f"[TTS_OPENAI] Texto: {payload.text!r}")
        print(f"[TTS_OPENAI] model={TTS_MODEL}, voice={voice}, response_format={fmt}")

        audio_bytes = await run_in_threadpool(
            _sync_generate_tts_audio,
            payload.text,
            voice,
            fmt,
        )
        print(f"[TTS_OPENAI] audio_bytes len={len(audio_bytes)}")

        media_type = _tts_media_type(fmt)

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
        voice = payload.voice or DEFAULT_VOICE
        fmt = _resolved_tts_format(payload.format)
        print(f">>> /tts llamado. Texto: {payload.text!r}")
        print(f">>> model={TTS_MODEL}, voice={voice}, response_format={fmt}")

        media_type = _tts_media_type(fmt)
        normalized_text = payload.text.strip()

        if normalized_text in _tts_audio_cache:
            audio_bytes = _tts_audio_cache[normalized_text]
            logger.info("tts_cache_hit text_len=%s", len(normalized_text))
        else:
            in_flight = _tts_inflight_tasks.get(normalized_text)
            if in_flight is not None and not in_flight.done():
                logger.info("tts_waiting_for_inflight text_len=%s", len(normalized_text))
                await in_flight

            if normalized_text in _tts_audio_cache:
                audio_bytes = _tts_audio_cache[normalized_text]
                logger.info("tts_cache_hit_after_wait text_len=%s", len(normalized_text))
            else:
                audio_bytes = await run_in_threadpool(
                    _sync_generate_tts_audio,
                    payload.text,
                    voice,
                    fmt,
                )
                _tts_audio_cache[normalized_text] = audio_bytes
                logger.info("tts_generated_sync text_len=%s audio_bytes=%s", len(normalized_text), len(audio_bytes))

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
