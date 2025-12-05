# backend/lipsync_bfa.py
from __future__ import annotations

import json
import os
import tempfile
from typing import List, Dict

from bournemouth_aligner import PhonemeTimestampAligner


# --- 1) Inicializar BFA una sola vez (import-time) ---

# Para español usamos el preset "es" (usa espeak-es por debajo)
# duration_max lo fijamos a 20 s (más que suficiente para tu caso).
ALIGNER = PhonemeTimestampAligner(
    preset="es",        # español
    duration_max=20,
    device="cpu",       # en VPS sin GPU
)


# --- 2) Mapeo fonema IPA -> visema lógico (versión "industrial" para tu rig CC) ---


"""
Set de visemas que usaremos en todo el sistema:

- AA  : /a/ abierta ("casa")
- AE  : /a/ más cerrada o /e/ abierta ("mesa", transiciones a /a/)
- EE  : /e/ e /i/ muy abierta/sonriente ("sí", "tiene")
- IH  : /i/ más relajada / media
- OH  : /o/ media ("cosa")
- OO  : /u/ / "oo" redondeada ("tú", "uno")

- MBP : bilabiales (m, b, p)
- FV  : labiodentales (f, v)
- TH  : dentales con lengua visible (θ, ð) – en ES se puede usar en "za, ce, ci..."
- L   : laterales /L/ ("la", "el") y nasales suaves
- S   : sibilantes ("s", "z") y muchas consonantes fricativas / oclusivas "planas"
- CH  : africadas / post-alveolares ("ch", "sh", etc.)
- KG  : velares posteriores ("k", "g", "x")
- R   : /r/ y /ɾ/

- SIL : silencio / reposo (boca neutra)
"""

PHONEME_TO_VISEME: Dict[str, str] = {
    # --- Vocales principales ---
    # a abierta
    "a": "AA",
    "aː": "AA",

    # e algo más abierta → AE
    "ɛ": "AE",
    "e": "AE",
    "eː": "AE",

    # i, vocal muy anterior → EE / IH según intensidad
    "i": "EE",
    "iː": "EE",

    # o → OH
    "o": "OH",
    "oː": "OH",

    # u → OO
    "u": "OO",
    "uː": "OO",

    # --- Diptongos frecuentes (mandamos a vocal dominante) ---
    "ai": "AE",
    "au": "AA",
    "ei": "EE",
    "oi": "OH",
    "ou": "OH",
    "ia": "EE",
    "ie": "EE",
    "io": "EE",
    "ua": "OO",
    "ue": "OO",
    "uo": "OO",

    # --- Bilabiales / labiales → MBP ---
    "p": "MBP",
    "b": "MBP",
    "m": "MBP",

    # --- Labiodentales → FV ---
    "f": "FV",
    "v": "FV",  # en ES suena más a /b/ pero nos interesa el gesto labiodental

    # --- Dentales fricativas (θ, ð) → TH (lengua entre dientes) ---
    "θ": "TH",
    "ð": "TH",

    # --- Africadas / fricativas palatales → CH ---
    "t͡ʃ": "CH",
    "ʃ": "CH",
    "ʒ": "CH",
    "d͡ʒ": "CH",

    # --- Sibilantes / fricativas alveolares → S ---
    "s": "S",
    "z": "S",

    # --- Oclusivas / consonantes "planas" → S (boca en posición media) ---
    "t": "S",
    "d": "S",
    "n": "S",
    "ɲ": "S",   # ñ
    "ç": "S",
    "x": "KG",  # /x/ tipo "jamón" -> posterior, lo mando a KG

    # --- Laterales /L/ y nasales suaves → L ---
    "l": "L",

    # --- Róticas /R/ ---
    "r": "R",
    "ɾ": "R",

    # --- Velares /K,G/ ---
    "k": "KG",
    "g": "KG",

    # Aproximantes / semivocales → las acerco a OO (labios algo redondeados)
    "w": "OO",
    "ɥ": "OO",
}


def phoneme_to_viseme(phoneme: str) -> str:
    """
    Convierte un fonema IPA (BFA/espeak) en uno de los visemas lógicos:

    {AA, AE, EE, IH, OH, OO, MBP, FV, TH, L, S, CH, KG, R, SIL}

    Si no lo conoce, devuelve SIL (boca en reposo).
    """
    phoneme = (phoneme or "").strip().lower()
    if not phoneme:
        return "SIL"

    # Normalizar pequeñas variaciones: alargadas, etc.
    replacements = {
        "aː": "a",
        "eː": "e",
        "iː": "i",
        "oː": "o",
        "uː": "u",
    }
    phoneme = replacements.get(phoneme, phoneme)

    return PHONEME_TO_VISEME.get(phoneme, "SIL")


# --- 3) Función central: audio_bytes (WAV) + texto -> timeline de visemas ---


def build_viseme_timeline_from_bfa(
    text: str,
    audio_bytes_wav: bytes,
) -> List[Dict]:
    """
    Usa BFA para alinear audio + texto y devuelve
    un timeline de visemas listo para tu frontend:

    [
      { "start": 0.00, "end": 0.08, "viseme": "MBP" },
      ...
    ]

    Donde "viseme" es uno de:
    {AA, AE, EE, IH, OH, OO, MBP, FV, TH, L, S, CH, KG, R, SIL}
    """

    if not audio_bytes_wav:
        return []

    # BFA espera ruta de archivo, así que usamos un temporal .wav
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes_wav)
        tmp_path = tmp.name

    try:
        # 1) Cargar audio
        audio_wav = ALIGNER.load_audio(tmp_path)

        # 2) Procesar frase completa (BFA espera `text`, no `text_sentence`)
        ts = ALIGNER.process_sentence(
            text,              # o text=text
            audio_wav,         # audio cargado con ALIGNER.load_audio
            ts_out_path=None,
            extract_embeddings=False,
            vspt_path=None,
            do_groups=True,
            debug=False,
        )

        # 3) Traducir JSON de BFA a timeline de visemas
        viseme_timeline: List[Dict] = []

        segments = ts.get("segments", [])
        for seg in segments:
            for ph in seg.get("phoneme_ts", []):
                label = ph.get("phoneme_label")
                start_ms = ph.get("start_ms")
                end_ms = ph.get("end_ms")

                if label is None or start_ms is None or end_ms is None:
                    continue

                viseme = phoneme_to_viseme(str(label))
                start_s = float(start_ms) / 1000.0
                end_s = float(end_ms) / 1000.0

                # DEBUG: ver fonema → visema
                print(
                    f"[BFA] phoneme={label!r} -> viseme={viseme}, "
                    f"{start_s:.3f}-{end_s:.3f}s"
                )

                viseme_timeline.append(
                    {
                        "start": start_s,
                        "end": end_s,
                        "viseme": viseme,
                    }
                )


        # 4) Fusionar fonemas consecutivos con el mismo visema (suaviza timeline)
        merged: List[Dict] = []
        for seg in viseme_timeline:
            if not merged:
                merged.append(seg)
                continue

            last = merged[-1]
            if seg["viseme"] == last["viseme"] and abs(seg["start"] - last["end"]) < 0.02:
                # pegamos segmentos casi contiguos del mismo visema
                last["end"] = seg["end"]
            else:
                merged.append(seg)

        print(f"[BFA] timeline visemas: {len(merged)} segmentos")
        for seg in merged:
            print(f"[BFA] VISEME_SEG: {seg['viseme']} {seg['start']:.3f}-{seg['end']:.3f}s")

        return merged

    finally:
        # Limpieza del temporal
        try:
            os.remove(tmp_path)
        except OSError:
            pass
