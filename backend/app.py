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

from state import get_session_state
from agent import run_agent

from negotiation.negotiation_graph import run_negotiation_agent

app = FastAPI(title="Agente Humano - MVP")

# --- Google Cloud Speech-to-Text (entrada de audio) ---

# Ruta absoluta al JSON dentro del Codespace
GOOGLE_CREDENTIALS_PATH = "/workspaces/agente-humano/backend/keys/google-stt.json"

credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_CREDENTIALS_PATH
)

speech_client = speech.SpeechClient(credentials=credentials)

stt_config = speech.RecognitionConfig(
    language_code="es-ES",
    enable_automatic_punctuation=True,
    model="latest_long",
    encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
)

# --- OpenAI Text-to-Speech (salida de audio) ---

openai_client = OpenAI()  # usa OPENAI_API_KEY del entorno

TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "alloy"
DEFAULT_FORMAT = "mp3"  # también puedes usar "opus" o "wav"


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
  </script>
</body>
</html>
    """

@app.post("/tts_openai")
async def tts_openai(payload: TTSRequest):
    try:
        voice = payload.voice or DEFAULT_VOICE
        fmt = payload.format or DEFAULT_FORMAT

        audio = openai_client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=payload.text,
            format=fmt,
        )

        audio_bytes = audio  # el SDK ya devuelve bytes

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
        raise HTTPException(
            status_code=500,
            detail=f"Error en OpenAI TTS: {e}",
        )