from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RUNNERS = {
    "run_fixture_evals": "negociacion.evals.runners.run_all_evals",
    "run_live_evals": "negociacion.evals.runners.run_all_live_evals",
    "run_e2e_mock": "negociacion.evals.runners.run_end_to_end_mock_evals",
    "run_e2e_live": "negociacion.evals.runners.run_end_to_end_live_evals",
    "run_all": "negociacion.evals.runners.run_all_evals",
    "run_all_live": "negociacion.evals.runners.run_all_live_evals",
}


def run_eval(action: str) -> dict:
    module = RUNNERS.get(action)
    if not module:
        raise ValueError(f"Acción desconocida: {action}")
    backend_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "action": action,
        "module": module,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
    }
