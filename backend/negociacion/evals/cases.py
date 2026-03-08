from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVALS_ROOT = Path(__file__).resolve().parent
DATASETS_DIR = EVALS_ROOT / "datasets"


def load_jsonl_cases(filename: str) -> list[dict[str, Any]]:
    path = DATASETS_DIR / filename
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dataset_path(filename: str) -> Path:
    return DATASETS_DIR / filename
