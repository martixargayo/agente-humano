from __future__ import annotations

from dataclasses import asdict, dataclass

from evaluacion.engine.communication_llm_config import parse_env_bool

_POLICY_VERSION = 'communication_activation_policy.v1'
_FORCE_SAFE_MODE_ENV = 'COMMUNICATION_FORCE_SAFE_MODE'


@dataclass(frozen=True)
class CommunicationActivationPolicy:
    content_mode: str
    delivery_mode: str
    visual_mode: str
    global_synthesis_mode: str
    policy_source: str = 'code'
    policy_version: str = _POLICY_VERSION

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _base_policy() -> CommunicationActivationPolicy:
    return CommunicationActivationPolicy(
        content_mode='llm',
        delivery_mode='llm',
        visual_mode='llm_v1',
        global_synthesis_mode='llm',
    )


def _safe_mode_policy() -> CommunicationActivationPolicy:
    return CommunicationActivationPolicy(
        content_mode='fallback',
        delivery_mode='fallback',
        visual_mode='metadata',
        global_synthesis_mode='fallback',
    )


def is_force_safe_mode_enabled() -> bool:
    return parse_env_bool(_FORCE_SAFE_MODE_ENV, default=False)


def get_communication_activation_policy() -> CommunicationActivationPolicy:
    if is_force_safe_mode_enabled():
        return _safe_mode_policy()
    return _base_policy()
