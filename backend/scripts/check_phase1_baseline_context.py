from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
BASELINE_DIR = BACKEND_DIR / "negociacion" / "contexts" / "baseline_current"

PROMPT_PAIRS = [
    (BACKEND_DIR / "negociacion" / "prompts" / "planner_prompt.txt", BASELINE_DIR / "prompts" / "planner_prompt.txt"),
    (BACKEND_DIR / "negociacion" / "prompts" / "executor_prompt.txt", BASELINE_DIR / "prompts" / "executor_prompt.txt"),
    (BACKEND_DIR / "negociacion" / "prompts" / "summarizer_prompt.txt", BASELINE_DIR / "prompts" / "summarizer_prompt.txt"),
    (BACKEND_DIR / "negociacion" / "prompts" / "phase_classifier_prompt.txt", BASELINE_DIR / "prompts" / "phase_classifier_prompt.txt"),
    (BACKEND_DIR / "evaluacion" / "prompts" / "core_evaluator_prompt.txt", BASELINE_DIR / "evaluation" / "core_evaluator_prompt.txt"),
    (BACKEND_DIR / "evaluacion" / "prompts" / "trajectory_evaluator_prompt.txt", BASELINE_DIR / "evaluation" / "trajectory_evaluator_prompt.txt"),
]

JSON_PAIRS = [
    (BACKEND_DIR / "negociacion" / "prompts" / "persona.json", BASELINE_DIR / "assets" / "persona.json"),
    (BACKEND_DIR / "negociacion" / "prompts" / "negotiation_brief.json", BASELINE_DIR / "assets" / "negotiation_brief.json"),
    (BACKEND_DIR / "negociacion" / "prompts" / "phase_cards.json", BASELINE_DIR / "assets" / "phase_cards.json"),
    (BACKEND_DIR / "negociacion" / "prompts" / "phase_classifier_card.json", BASELINE_DIR / "assets" / "phase_classifier_card.json"),
    (BACKEND_DIR / "evaluacion" / "domains" / "negotiation" / "rubrics" / "negotiation_rubric_v1.json", BASELINE_DIR / "evaluation" / "rubric.json"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    print(f"baseline_dir={BASELINE_DIR}")
    if not BASELINE_DIR.exists():
        raise SystemExit("baseline_current no existe")

    print("\n[prompts]")
    for legacy, baseline in PROMPT_PAIRS:
        same = legacy.read_text(encoding="utf-8") == baseline.read_text(encoding="utf-8")
        print(f"- {legacy.relative_to(REPO_ROOT)} == {baseline.relative_to(REPO_ROOT)} -> {same} sha={sha256(legacy)}")
        if not same:
            raise SystemExit("prompt mismatch")

    print("\n[json]")
    for legacy, baseline in JSON_PAIRS:
        same = json.loads(legacy.read_text(encoding="utf-8")) == json.loads(baseline.read_text(encoding="utf-8"))
        print(f"- {legacy.relative_to(REPO_ROOT)} == {baseline.relative_to(REPO_ROOT)} -> {same} sha={sha256(legacy)}")
        if not same:
            raise SystemExit("json mismatch")

    print("\nresultado=ok")


if __name__ == "__main__":
    main()
