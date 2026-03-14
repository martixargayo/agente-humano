"""Legacy mock report module intentionally disabled.

This file used to contain phase-2 mock structures that no longer match
`evaluacion.contracts.models`. It is kept only as an explicit tombstone to
avoid accidental imports of stale code during debugging.
"""

from __future__ import annotations


class MockReportDeprecatedError(RuntimeError):
    """Raised when deprecated mock report helpers are requested."""


def build_mock_ui_report(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise MockReportDeprecatedError(
        "mock_report.py is deprecated and intentionally disabled; "
        "use the real evaluation pipeline in evaluacion.engine.service"
    )
