from __future__ import annotations

from sessions.state import SessionState

from evaluacion.contracts.models import FeedbackInputBundleV1

from .extractor import build_feedback_input_bundle_v1


class NegotiationEvaluationAdapter:
    flow_id = 'negociacion'

    def build_feedback_input_bundle_v1(self, *, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1:
        return build_feedback_input_bundle_v1(state=state, evaluation_id=evaluation_id)
