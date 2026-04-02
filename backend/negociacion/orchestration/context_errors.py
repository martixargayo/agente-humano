from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextContractError(RuntimeError):
    reason_code: str
    message: str
    expected: str | None = None
    actual: str | None = None
    entry_surface: str | None = None
    entrypoint: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class MissingTurnContextError(ContextContractError):
    def __init__(self, message: str = "turn_context_required", **kwargs: str | None) -> None:
        super().__init__(reason_code="ctx_missing_turn_context", message=message, **kwargs)


class ImplicitContextForbiddenError(ContextContractError):
    def __init__(self, message: str = "implicit_context_forbidden", **kwargs: str | None) -> None:
        super().__init__(reason_code="ctx_implicit_forbidden", message=message, **kwargs)


class ContextMismatchError(ContextContractError):
    def __init__(self, message: str = "context_mismatch", **kwargs: str | None) -> None:
        super().__init__(reason_code="ctx_bound_effective_mismatch", message=message, **kwargs)


class InvalidConfigContextError(ContextContractError):
    def __init__(self, message: str = "invalid_config_context", **kwargs: str | None) -> None:
        super().__init__(reason_code="ctx_config_effective_mismatch", message=message, **kwargs)


class StatefulContextRequiredError(ContextContractError):
    def __init__(self, message: str = "stateful_context_required", **kwargs: str | None) -> None:
        super().__init__(reason_code="ctx_stateful_requires_explicit", message=message, **kwargs)


class SessionContextConflictError(ContextMismatchError):
    def __init__(self, *, session_id: str, existing_context_id: str, requested_context_id: str) -> None:
        super().__init__(
            message="session_context_conflict",
            expected=existing_context_id,
            actual=requested_context_id,
            entrypoint=session_id,
        )
