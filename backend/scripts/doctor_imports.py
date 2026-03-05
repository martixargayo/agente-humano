#!/usr/bin/env python3
"""Diagnóstico rápido de entorno para errores de importación en app.py/engine.py."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


MODULES = [
    "fastapi",
    "fastapi.responses",
    "fastapi.staticfiles",
    "fastapi.middleware.cors",
    "pydantic",
    "openai",
    "google.oauth2",
    "google.cloud.speech",
]


def main() -> int:
    print(f"Python ejecutándose en: {sys.executable}")
    print(f"Versión: {sys.version.split()[0]}")

    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    print(f"Repo root detectado: {root}")
    print(f"Backend path existe: {backend.exists()} ({backend})")

    failed = False
    for mod in MODULES:
        try:
            importlib.import_module(mod)
            print(f"[OK] {mod}")
        except Exception as exc:  # noqa: BLE001
            failed = True
            print(f"[FAIL] {mod}: {exc}")

    try:
        import openai  # type: ignore

        has_client = hasattr(openai, "OpenAI")
        print(f"openai.OpenAI disponible: {has_client}")
        if not has_client:
            failed = True
            print("[FAIL] Tu versión de openai parece antigua para este código (falta OpenAI()).")
    except Exception:
        pass

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
