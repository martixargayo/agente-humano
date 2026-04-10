from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Type

import openai
from pydantic import BaseModel

from infra.openai.structured_outputs import normalize_schema_for_strict_json_schema


def load_prompt_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _client() -> openai.OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return openai.OpenAI()
    except Exception:
        return None


def run_structured(
    *,
    model: str,
    developer_prompt: str,
    user_payload: dict[str, Any],
    output_model: Type[BaseModel],
    schema_name: str,
) -> dict[str, Any] | None:
    client = _client()
    if client is None:
        return None

    user_message = f"BEGIN_INPUT_JSON\n{json.dumps(user_payload, ensure_ascii=False)}\nEND_INPUT_JSON"
    schema = normalize_schema_for_strict_json_schema(output_model.model_json_schema())

    response = client.responses.create(
        model=model,
        input=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_message},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
        store=False,
        reasoning={"effort": "medium"},
    )
    output = getattr(response, "output_text", "") or "{}"
    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        raise ValueError("runner_output_not_object")
    return parsed
