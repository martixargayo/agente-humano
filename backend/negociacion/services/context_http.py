from __future__ import annotations

from fastapi import HTTPException

from ..orchestration.context_errors import (
    ContextContractError,
    ContextMismatchError,
    ImplicitContextForbiddenError,
    InvalidConfigContextError,
    MissingTurnContextError,
    SessionContextConflictError,
    StatefulContextRequiredError,
)


def raise_http_from_context_error(exc: Exception) -> None:
    if isinstance(exc, SessionContextConflictError):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "session_context_conflict",
                "session_id": exc.entrypoint,
                "existing_context_id": exc.expected,
                "requested_context_id": exc.actual,
            },
        ) from exc
    if isinstance(exc, ContextMismatchError):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "context_mismatch",
                "reason_code": exc.reason_code,
                "expected": exc.expected,
                "actual": exc.actual,
            },
        ) from exc
    if isinstance(exc, (MissingTurnContextError, StatefulContextRequiredError, ImplicitContextForbiddenError)):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_turn_context",
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, InvalidConfigContextError):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "invalid_config_context",
                "reason_code": exc.reason_code,
                "message": str(exc),
                "expected": exc.expected,
                "actual": exc.actual,
            },
        ) from exc
    if isinstance(exc, ContextContractError):
        raise HTTPException(status_code=400, detail={"error": "context_contract_error", "reason_code": exc.reason_code}) from exc
