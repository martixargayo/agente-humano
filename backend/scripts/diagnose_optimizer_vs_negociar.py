from __future__ import annotations

# Backward-compatible entrypoint.
# Canonical diagnostic now lives in diagnose_parity_safe_surfaces.py
from pathlib import Path
import runpy

if __name__ == "__main__":
    target = Path(__file__).with_name("diagnose_parity_safe_surfaces.py")
    runpy.run_path(str(target), run_name="__main__")
