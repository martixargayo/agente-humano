from __future__ import annotations

"""Backward-compatible alias for mock/integration end-to-end evals."""

from .run_end_to_end_mock_evals import run


if __name__ == "__main__":
    raise SystemExit(run())
