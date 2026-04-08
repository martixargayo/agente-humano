from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversationSimpleContextError(RuntimeError):
    reason_code: str
    message: str
    expected: str | None = None
    actual: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class ConversationSimpleSessionContextConflictError(ConversationSimpleContextError):
    def __init__(self, *, session_id: str, existing_context_id: str, requested_context_id: str) -> None:
        super().__init__(
            reason_code="cs_ctx_session_conflict",
            message="session_context_conflict",
            expected=existing_context_id,
            actual=requested_context_id,
        )
        self.session_id = session_id
