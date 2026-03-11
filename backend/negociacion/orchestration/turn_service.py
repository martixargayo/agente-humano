from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sessions.state import SessionState

from ..state.shared_types import NegotiationChannel, NegotiationExecutionProfile
from ..traces.models import TurnTrace
from .flow_config import NegotiationTurnConfig, run_negotiation_cognitive_turn_detailed


@dataclass
class CanonicalNegotiationTurnResult:
    reply: str
    updated_state: SessionState
    turn_trace: TurnTrace
    effective_config: dict[str, Any]
    effective_config_hash: str
    execution_profile: NegotiationExecutionProfile
    channel: NegotiationChannel
    prompts_dir_effective: str
    finish_button_armed: bool


_ALLOWED_PROFILES_BY_CHANNEL: dict[NegotiationChannel, set[NegotiationExecutionProfile]] = {
    NegotiationChannel.avatar: {NegotiationExecutionProfile.canonical_negotiation},
    NegotiationChannel.optimizer: {
        NegotiationExecutionProfile.canonical_negotiation,
        NegotiationExecutionProfile.experimental_negotiation,
    },
}


def _hash_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_channel_profile(channel: NegotiationChannel, execution_profile: NegotiationExecutionProfile) -> None:
    allowed = _ALLOWED_PROFILES_BY_CHANNEL.get(channel, set())
    if execution_profile not in allowed:
        raise ValueError(f"execution_profile={execution_profile.value} no permitido para channel={channel.value}")


def run_negotiation_turn_canonical(
    *,
    state: SessionState,
    user_message: str,
    config: NegotiationTurnConfig,
    channel: NegotiationChannel,
    execution_profile: NegotiationExecutionProfile,
) -> CanonicalNegotiationTurnResult:
    _validate_channel_profile(channel, execution_profile)

    effective_config = config.model_dump(mode="json")
    effective_config_hash = _hash_json(effective_config)

    details = run_negotiation_cognitive_turn_detailed(
        state,
        user_message,
        config,
        channel=channel,
        execution_profile=execution_profile,
        effective_config=effective_config,
        effective_config_hash=effective_config_hash,
    )

    return CanonicalNegotiationTurnResult(
        reply=details.reply,
        updated_state=details.updated_state,
        turn_trace=details.turn_trace,
        effective_config=effective_config,
        effective_config_hash=effective_config_hash,
        execution_profile=execution_profile,
        channel=channel,
        prompts_dir_effective=str(config.prompts_dir),
        finish_button_armed=details.finish_button_armed,
    )
