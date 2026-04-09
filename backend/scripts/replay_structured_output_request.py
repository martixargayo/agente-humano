from __future__ import annotations

import argparse
import json
import os
from typing import Any

import httpx
import openai


def _load_payload(path: str) -> dict[str, Any]:
    raw = json.loads(open(path, "r", encoding="utf-8").read())
    if isinstance(raw.get("request_payload"), dict):
        return raw["request_payload"]
    if isinstance(raw, dict):
        return raw
    raise ValueError("invalid_payload_json")


def replay_with_sdk(payload: dict[str, Any], *, api_key: str, base_url: str | None = None) -> dict[str, Any]:
    client = openai.OpenAI(api_key=api_key, base_url=base_url) if base_url else openai.OpenAI(api_key=api_key)
    try:
        response = client.responses.create(**payload)
        return {
            "ok": True,
            "status_code": 200,
            "response_id": getattr(response, "id", None),
            "output_text": getattr(response, "output_text", None),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "status_code": getattr(exc, "status_code", None),
            "code": getattr(exc, "code", None),
            "message": str(exc),
        }


def replay_raw_http(payload: dict[str, Any], *, api_key: str, base_url: str | None = None) -> dict[str, Any]:
    endpoint_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{endpoint_base}/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    body: dict[str, Any] | str
    try:
        body = response.json()
    except Exception:
        body = response.text
    error = body.get("error") if isinstance(body, dict) else None
    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "error_code": error.get("code") if isinstance(error, dict) else None,
        "error_message": error.get("message") if isinstance(error, dict) else None,
        "body": body,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay captured Structured Outputs payload via SDK and raw HTTP.")
    parser.add_argument("--payload", required=True, help="Path to JSON payload or wrapper with request_payload.")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for replay")

    payload = _load_payload(args.payload)
    report = {
        "payload_hash": hash(json.dumps(payload, sort_keys=True, ensure_ascii=False)),
        "sdk": replay_with_sdk(payload, api_key=api_key, base_url=args.base_url),
        "raw_http": replay_raw_http(payload, api_key=api_key, base_url=args.base_url),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
