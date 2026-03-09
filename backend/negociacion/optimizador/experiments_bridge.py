from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..orchestration.flow_config import NegotiationTurnConfig
from .models import OverrideEntry
from .prompts_bridge import PROMPT_FILES, PROMPTS_DIR

_ALLOWED_CONFIG_FIELDS: dict[str, type] = {
    "model_memory": str,
    "model_phase_classifier": str,
    "model_planner": str,
    "model_executor": str,
    "reasoning_effort_planner": str,
    "feature_input_guardrails": bool,
    "feature_output_guardrails": bool,
    "feature_moderation": bool,
    "max_recent_messages": int,
    "max_executor_recent_turns": int,
}

_ALLOWED_CONTEXTUAL_KEYS = {"phase_cards", "persona"}

_OVERRIDE_STORE: dict[str, dict[str, Any]] = {}
_DEFAULT_STATE = {"mode": "mirror", "entries": [], "workspace_version": 1, "committed_entries": []}


def get_state(optimizer_session_id: str) -> dict[str, Any]:
    state = _OVERRIDE_STORE.setdefault(optimizer_session_id, deepcopy(_DEFAULT_STATE))
    return deepcopy(state)


def reset_state(optimizer_session_id: str) -> dict[str, Any]:
    _OVERRIDE_STORE[optimizer_session_id] = deepcopy(_DEFAULT_STATE)
    return deepcopy(_OVERRIDE_STORE[optimizer_session_id])


def update_state(optimizer_session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    state = _OVERRIDE_STORE.setdefault(optimizer_session_id, deepcopy(_DEFAULT_STATE))
    if "mode" in patch:
        if patch["mode"] not in {"mirror", "sandbox"}:
            raise ValueError("mode inválido")
        state["mode"] = patch["mode"]

    entries = patch.get("entries")
    if entries is not None:
        validated: list[dict[str, Any]] = []
        for raw in entries:
            entry = OverrideEntry.model_validate(raw)
            _validate_entry(entry)
            validated.append(entry.model_dump(mode="json"))
        state["entries"] = validated
    return deepcopy(state)



def confirm_state(optimizer_session_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    state = _OVERRIDE_STORE.setdefault(optimizer_session_id, deepcopy(_DEFAULT_STATE))
    validated: list[dict[str, Any]] = []
    for raw in entries:
        entry = OverrideEntry.model_validate(raw)
        _validate_entry(entry)
        validated.append(entry.model_dump(mode="json"))
    state["entries"] = validated
    state["committed_entries"] = deepcopy(validated)
    state["mode"] = "sandbox"
    state["workspace_version"] = int(state.get("workspace_version") or 1) + 1
    return deepcopy(state)

def resolve_entries(
    *,
    optimizer_session_id: str,
    conversation_id: str | None,
    turn_id: str | None,
) -> list[dict[str, Any]]:
    state = get_state(optimizer_session_id)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for scope in ["this_optimizer_session", "this_conversation", "this_turn"]:
        for entry in state.get("entries", []):
            if entry.get("scope") != scope:
                continue
            if scope == "this_conversation" and entry.get("conversation_id") != conversation_id:
                continue
            if scope == "this_turn" and entry.get("turn_id") != turn_id:
                continue
            by_key[(entry["category"], entry["key"])] = entry
    return list(by_key.values())


def apply_overrides(
    base_config: NegotiationTurnConfig,
    entries: list[dict[str, Any]],
) -> tuple[NegotiationTurnConfig, TemporaryDirectory | None]:
    config_patch: dict[str, Any] = {}
    for entry in entries:
        if entry["category"] == "config":
            config_patch[entry["key"]] = entry["value"]
    config = base_config.model_copy(update=config_patch)

    prompt_entries = [entry for entry in entries if entry["category"] == "prompt"]
    contextual_entries = [entry for entry in entries if entry["category"] == "contextual"]
    if not prompt_entries and not contextual_entries:
        return config, None

    tempdir = TemporaryDirectory(prefix="optimizador_prompts_")
    tmp_dir = Path(tempdir.name)

    _copy_base_prompt_bundle(tmp_dir)

    for entry in prompt_entries:
        file_name = PROMPT_FILES.get(entry["key"])
        if file_name:
            (tmp_dir / file_name).write_text(str(entry["value"]), encoding="utf-8")

    for entry in contextual_entries:
        if entry["key"] == "phase_cards":
            (tmp_dir / "phase_cards.json").write_text(_json_string(entry["value"]), encoding="utf-8")
        elif entry["key"] == "persona":
            (tmp_dir / "persona.json").write_text(_json_string(entry["value"]), encoding="utf-8")

    config = config.model_copy(update={"prompts_dir": str(tmp_dir)})
    return config, tempdir


def describe_effective_overrides(entries: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = {"prompt": {}, "config": {}, "contextual": {}}
    for entry in entries:
        grouped[entry["category"]][entry["key"]] = {
            "scope": entry["scope"],
            "value": entry["value"],
            "conversation_id": entry.get("conversation_id"),
            "turn_id": entry.get("turn_id"),
        }
    return grouped


def _copy_base_prompt_bundle(tmp_dir: Path) -> None:
    for file_name in list(PROMPT_FILES.values()) + ["phase_cards.json", "persona.json"]:
        source = PROMPTS_DIR / file_name
        if source.exists():
            (tmp_dir / file_name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _json_string(value: Any) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            raise ValueError("contextual override debe ser JSON válido")
    return json.dumps(value, ensure_ascii=False, indent=2)


def _validate_contextual_value(key: str, value: Any) -> None:
    if key == "phase_cards":
        if not isinstance(value, dict):
            raise ValueError("phase_cards override debe ser objeto JSON")
    elif key == "persona":
        if not isinstance(value, dict):
            raise ValueError("persona override debe ser objeto JSON")
        policy = value.get("policy")
        expressive = value.get("expressive")
        if not isinstance(policy, dict) or not isinstance(expressive, dict):
            raise ValueError("persona override requiere policy y expressive")


def _validate_entry(entry: OverrideEntry) -> None:
    if entry.category == "prompt":
        if entry.key not in PROMPT_FILES:
            raise ValueError(f"prompt override no soportado: {entry.key}")
    elif entry.category == "config":
        expected = _ALLOWED_CONFIG_FIELDS.get(entry.key)
        if expected is None:
            raise ValueError(f"config override no soportado: {entry.key}")
        if not isinstance(entry.value, expected):
            raise ValueError(f"config override inválido para {entry.key}")
    elif entry.category == "contextual":
        if entry.key not in _ALLOWED_CONTEXTUAL_KEYS:
            raise ValueError(f"contextual override no soportado: {entry.key}")
        _validate_contextual_value(entry.key, entry.value)

    if entry.scope == "this_conversation" and not entry.conversation_id:
        raise ValueError("scope this_conversation requiere conversation_id")
    if entry.scope == "this_turn" and not entry.turn_id:
        raise ValueError("scope this_turn requiere turn_id")
