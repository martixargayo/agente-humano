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


# --- 2) Mapeo fonema IPA -> visema lógico (para tu rig CC4) ---

# Esto es una primera versión razonable para español.
# Más adelante se puede afinar / extender.
PHONEME_TO_VISEME: Dict[str, str] = {
    # Vocales
    "a": "AA",
    "aː": "AA",
    "e": "E",
    "eː": "E",
    "i": "I",
    "iː": "I",
    "o": "O",
    "oː": "O",
    "u": "U",
    "uː": "U",

    # Diptongos frecuentes (los mandamos a vocal dominante)
    "ai": "AA",
    "au": "AA",
    "ei": "E",
    "oi": "O",
    "ou": "O",
    "ia": "I",
    "ie": "I",
    "io": "I",
    "ua": "U",
    "ue": "U",
    "uo": "U",

    # Bilabiales / labiales → cierre MBP
    "p": "MBP",
    "b": "MBP",
    "m": "MBP",

    # Labiodentales → FV
    "f": "FV",
    "v": "FV",

    # Africadas / fricativas palatales → CH
    "t͡ʃ": "CH",
    "ʃ": "CH",
    "ʒ": "CH",
    "d͡ʒ": "CH",

    # Aproximantes / semivocales → W (redondeo suave)
    "w": "W",
    "ɥ": "W",

    # Resto de consonantes que mueven algo la boca
    # (ligera apertura tipo "E")
    "s": "E",
    "z": "E",
    "θ": "E",
    "ð": "E",
    "t": "E",
    "d": "E",
    "n": "E",
    "ɲ": "E",
    "l": "E",
    "r": "E",
    "ɾ": "E",
    "k": "E",
    "g": "E",
    "x": "E",
}


def phoneme_to_viseme(phoneme: str) -> str:
    """
    Convierte un fonema IPA (BFA/espeak) en uno de tus visemas lógicos.
    Si no lo conoce, devuelve REST (boca neutra).
    """
    phoneme = (phoneme or "").strip().lower()
    if not phoneme:
        return "REST"

    # Normalizar pequeñas variaciones (ejemplo)
    replacements = {
        "aː": "a",
        "eː": "e",
        "iː": "i",
        "oː": "o",
        "uː": "u",
    }
    phoneme = replacements.get(phoneme, phoneme)

    return PHONEME_TO_VISEME.get(phoneme, "REST")


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

                viseme_timeline.append(
                    {
                        "start": start_s,
                        "end": end_s,
                        "viseme": viseme,
                    }
                )

        # Opcional: fusionar fonemas consecutivos con el mismo visema
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

        # LOG para comprobar que hay timeline
        print(f"[BFA] timeline visemas: {len(merged)} segmentos")

        return merged

    finally:
        # Limpieza del temporal
        try:
            os.remove(tmp_path)
        except OSError:
            pass
