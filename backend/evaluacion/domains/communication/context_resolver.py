from __future__ import annotations

from comunicacion.contexts import resolve_communication_context
from comunicacion.storage.models import AttemptRecord
from evaluacion.contracts.communication_models import CommunicationDomainContext


def resolve_communication_evaluation_context_from_attempt(*, attempt: AttemptRecord) -> CommunicationDomainContext:
    resolved = resolve_communication_context(attempt.context_id)
    return CommunicationDomainContext(
        domain='comunicacion',
        flow_id='comunicacion',
        context_id=resolved.context_id,
        context_version=resolved.context_version,
    )
