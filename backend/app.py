# backend/app.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import os
from google.cloud import speech
from google.oauth2 import service_account

import io  # arriba del archivo
from fastapi.responses import StreamingResponse
from openai import OpenAI

import base64

import pathlib
from fastapi.staticfiles import StaticFiles

from state import get_session_state
from agent import run_agent

from negotiation.negotiation_graph import run_negotiation_agent

from dotenv import load_dotenv
load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

from websockets.asyncio.client import connect as ws_connect  # pip install websockets

import asyncio
import json
import wave

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

BASE_DIR = pathlib.Path(__file__).resolve().parent
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

credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_CREDENTIALS_PATH
)

speech_client = speech.SpeechClient(credentials=credentials)

# Google STT config desde .env
GOOGLE_STT_MODEL = os.getenv("GOOGLE_STT_MODEL", "latest_long")
GOOGLE_STT_LANGUAGE = os.getenv("GOOGLE_STT_LANGUAGE", "es-ES")
GOOGLE_STT_PUNCT = os.getenv("GOOGLE_STT_PUNCTUATION", "true").lower() == "true"
GOOGLE_STT_ENCODING = os.getenv("GOOGLE_STT_ENCODING", "WEBM_OPUS")

stt_config = speech.RecognitionConfig(
    language_code=GOOGLE_STT_LANGUAGE,
    enable_automatic_punctuation=GOOGLE_STT_PUNCT,
    model=GOOGLE_STT_MODEL,
    encoding=getattr(speech.RecognitionConfig.AudioEncoding, GOOGLE_STT_ENCODING),
)

# --- OpenAI Text-to-Speech (salida de audio) ---

openai_client = OpenAI()  # usa OPENAI_API_KEY del entorno

TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_VOICE = os.getenv("OPENAI_TTS_VOICE", "onyx")
DEFAULT_FORMAT = os.getenv("OPENAI_TTS_FORMAT", "mp3")
SPANISH_EU_VOICE_INSTRUCTIONS = """
Language: Spanish (es-ES).
Accent: European Spanish (Spain), not Latin American.
Pronunciation: Use standard peninsular Spanish; avoid Latin American intonation and seseo typical of Latin America.
Intonation: neutral and slightly descending at sentence endings, avoid sing-song or overly melodic patterns.
Tone: masculine, calm, confident, and natural.
Style: conversational and close, like an adult from Spain speaking directly to the listener.
"""
# --- Config OpenAI Realtime TTS (voz tipo ChatGPT) ---

REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
REALTIME_VOICE_DEFAULT = os.getenv("OPENAI_REALTIME_VOICE", "alloy")

# URL WebSocket del Realtime API
REALTIME_WS_URL = os.getenv(
    "OPENAI_REALTIME_WS_URL",
    f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}",
)

@app.on_event("startup")
async def warmup_tts():
    """
    Llamada de calentamiento para que el primer TTS
    no tenga el coste de arranque del modelo.
    """
    try:
        # Texto corto y neutro, solo para que el modelo cargue.
        resp = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=DEFAULT_VOICE,
            input="Calibración de voz.",
            response_format=DEFAULT_FORMAT,
            instructions=SPANISH_EU_VOICE_INSTRUCTIONS,
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

class TTSRequest(BaseModel):
    text: str
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
        return ChatResponse(reply=reply)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente de negociación: {e}",
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
    try:
        audio_bytes = await file.read()
        audio = speech.RecognitionAudio(content=audio_bytes)

        response = speech_client.recognize(
            config=stt_config,
            audio=audio
        )

        text = ""
        for result in response.results:
            text += result.alternatives[0].transcript + " "

        return {"text": text.strip()}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en Google STT: {e}",
        )

@app.post("/tts_openai")
async def tts_openai(payload: TTSRequest):
    try:
        voice = payload.voice or DEFAULT_VOICE
        fmt = payload.format or DEFAULT_FORMAT

        print(f"[TTS_OPENAI] Texto: {payload.text!r}")
        print(f"[TTS_OPENAI] model={TTS_MODEL}, voice={voice}, response_format={fmt}")

        audio_resp = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=payload.text,
            response_format=fmt,
            instructions=SPANISH_EU_VOICE_INSTRUCTIONS,
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
    try:
        voice = payload.voice or DEFAULT_VOICE
        fmt = payload.format or DEFAULT_FORMAT

        if fmt not in {"mp3", "opus", "wav"}:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de audio no soportado: {fmt}",
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
            instructions=SPANISH_EU_VOICE_INSTRUCTIONS,
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

async def tts_realtime_generate_wav(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """
    Usa el modelo Realtime (gpt-realtime / gpt-4o-realtime...) para leer en voz alta
    el texto dado y devuelve un WAV (audio_bytes, mime_type).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada para Realtime")

    voice_name = (voice or REALTIME_VOICE_DEFAULT).strip() or REALTIME_VOICE_DEFAULT

    # Conectamos al WebSocket Realtime (firmando cabeceras en formato lista de tuplas)
    headers = [
        ("Authorization", f"Bearer {api_key}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]

    async with ws_connect(
        REALTIME_WS_URL,
        additional_headers=headers,
    ) as ws:
        # 1) Actualizamos sesión: solo audio de salida + instrucciones de "lector literal"
        session_update = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": REALTIME_MODEL,
                "output_modalities": ["audio"],
                "instructions": (
                    "Eres un motor de LOCUCIÓN. "
                    "Tu única tarea es LEER EN VOZ ALTA, literalmente, el texto "
                    "que el usuario proporcione. No añadas ni quites palabras."
                ),
                "audio": {
                    "output": {
                        "format": {
                            "type": "audio/pcm",
                        },
                        "voice": voice_name,
                    }
                },
            },
        }
        await ws.send(json.dumps(session_update))

        # 2) Creamos item de conversación con el texto a leer
        conv_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            },
        }
        await ws.send(json.dumps(conv_item))

        # 3) Pedimos respuesta SOLO audio
        resp_create = {
            "type": "response.create",
            "response": {
                "output_modalities": ["audio"],
                "instructions": "Lee literalmente el contenido del último mensaje del usuario.",
            },
        }
        await ws.send(json.dumps(resp_create))

        # 4) Recogemos chunks de audio PCM16 (base64) y los juntamos
        pcm_chunks: list[bytes] = []
        sample_rate = 24000  # típico en Realtime para audio/pcm

        while True:
            raw_msg = await ws.recv()
            try:
                event = json.loads(raw_msg)
            except Exception:
                continue

            etype = event.get("type")

            if etype == "response.audio.delta":
                b64 = event.get("delta") or ""
                if b64:
                    pcm_chunks.append(base64.b64decode(b64))

            elif etype == "response.audio.done":
                # nada especial, esperamos a response.done
                continue

            elif etype == "response.done":
                break

            elif etype == "error":
                raise RuntimeError(f"Realtime error: {event}")

        if not pcm_chunks:
            raise RuntimeError("Realtime no devolvió audio (pcm_chunks vacío)")

        pcm_data = b"".join(pcm_chunks)

        # 5) Empaquetamos PCM16 en WAV
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)      # mono
            wf.setsampwidth(2)      # 16 bits
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        wav_bytes = buf.getvalue()

        return wav_bytes, "audio/wav"


@app.post("/tts_realtime", response_model=TTSAudioResponse)
async def tts_realtime(payload: TTSRequest):
    """
    TTS usando el modelo Realtime (voz tipo ChatGPT).
    Recibe texto y devuelve audio_base64 + audio_mime_type (WAV).
    """
    try:
        # Usamos la voz que venga en el payload o la por defecto de Realtime
        wav_bytes, mime_type = await tts_realtime_generate_wav(
            text=payload.text,
            voice=payload.voice,
        )

        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

        return TTSAudioResponse(
            audio_base64=audio_b64,
            audio_mime_type=mime_type,
        )

    except Exception as e:
        print("ERROR en /tts_realtime:", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en TTS Realtime: {e}",
        )
