from __future__ import annotations

import json
import unittest
from pathlib import Path

from interfaz_usuario import router as interfaz_usuario_router

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
BASELINE_DIR = BACKEND_DIR / "negociacion" / "contexts" / "baseline_current"

PROMPT_PAIRS = {
    "planner_prompt.txt": (
        BACKEND_DIR / "negociacion" / "prompts" / "planner_prompt.txt",
        BASELINE_DIR / "prompts" / "planner_prompt.txt",
    ),
    "executor_prompt.txt": (
        BACKEND_DIR / "negociacion" / "prompts" / "executor_prompt.txt",
        BASELINE_DIR / "prompts" / "executor_prompt.txt",
    ),
    "summarizer_prompt.txt": (
        BACKEND_DIR / "negociacion" / "prompts" / "summarizer_prompt.txt",
        BASELINE_DIR / "prompts" / "summarizer_prompt.txt",
    ),
    "phase_classifier_prompt.txt": (
        BACKEND_DIR / "negociacion" / "prompts" / "phase_classifier_prompt.txt",
        BASELINE_DIR / "prompts" / "phase_classifier_prompt.txt",
    ),
    "core_evaluator_prompt.txt": (
        BACKEND_DIR / "evaluacion" / "prompts" / "core_evaluator_prompt.txt",
        BASELINE_DIR / "evaluation" / "core_evaluator_prompt.txt",
    ),
    "trajectory_evaluator_prompt.txt": (
        BACKEND_DIR / "evaluacion" / "prompts" / "trajectory_evaluator_prompt.txt",
        BASELINE_DIR / "evaluation" / "trajectory_evaluator_prompt.txt",
    ),
}

JSON_PAIRS = {
    "persona.json": (
        BACKEND_DIR / "negociacion" / "prompts" / "persona.json",
        BASELINE_DIR / "assets" / "persona.json",
    ),
    "negotiation_brief.json": (
        BACKEND_DIR / "negociacion" / "prompts" / "negotiation_brief.json",
        BASELINE_DIR / "assets" / "negotiation_brief.json",
    ),
    "phase_cards.json": (
        BACKEND_DIR / "negociacion" / "prompts" / "phase_cards.json",
        BASELINE_DIR / "assets" / "phase_cards.json",
    ),
    "phase_classifier_card.json": (
        BACKEND_DIR / "negociacion" / "prompts" / "phase_classifier_card.json",
        BASELINE_DIR / "assets" / "phase_classifier_card.json",
    ),
    "rubric.json": (
        BACKEND_DIR / "evaluacion" / "domains" / "negotiation" / "rubrics" / "negotiation_rubric_v1.json",
        BASELINE_DIR / "evaluation" / "rubric.json",
    ),
}

PRODUCTIVE_FILES_THAT_MUST_NOT_BE_REWIRED = [
    BACKEND_DIR / "negociacion" / "pipeline.py",
    BACKEND_DIR / "negociacion" / "orchestration" / "flow_config.py",
    BACKEND_DIR / "negociacion" / "state" / "canonical_state.py",
    BACKEND_DIR / "evaluacion" / "engine" / "service.py",
    BACKEND_DIR / "evaluacion" / "domains" / "negotiation" / "extractor.py",
    BACKEND_DIR / "interfaz_usuario" / "services.py",
    BACKEND_DIR / "interfaz_usuario" / "models.py",
    BACKEND_DIR / "interfaz_usuario" / "__init__.py",
    BACKEND_DIR / "interfaz_usuario_app" / "app.js",
    BACKEND_DIR / "interfaz_usuario_app" / "index.html",
    BACKEND_DIR / "negociacion" / "optimizador" / "services.py",
]


class Phase1BaselineContextTests(unittest.TestCase):
    def test_baseline_root_and_subdirectories_exist(self) -> None:
        self.assertTrue(BASELINE_DIR.exists())
        self.assertTrue((BASELINE_DIR / "prompts").is_dir())
        self.assertTrue((BASELINE_DIR / "assets").is_dir())
        self.assertTrue((BASELINE_DIR / "evaluation").is_dir())

    def test_manifest_exists_and_parses(self) -> None:
        manifest_path = BASELINE_DIR / "manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["flow_id"], "negociacion")
        self.assertEqual(manifest["context_id"], "baseline_current")
        self.assertEqual(manifest["public_slug"], "negociacion")
        self.assertIn("bundle", manifest)
        self.assertIn("files", manifest)

    def test_reflected_prompts_are_textually_identical_to_legacy(self) -> None:
        for name, (legacy_path, baseline_path) in PROMPT_PAIRS.items():
            with self.subTest(name=name):
                self.assertEqual(
                    legacy_path.read_text(encoding="utf-8"),
                    baseline_path.read_text(encoding="utf-8"),
                )

    def test_reflected_json_assets_are_structurally_identical_to_legacy(self) -> None:
        for name, (legacy_path, baseline_path) in JSON_PAIRS.items():
            with self.subTest(name=name):
                self.assertEqual(
                    json.loads(legacy_path.read_text(encoding="utf-8")),
                    json.loads(baseline_path.read_text(encoding="utf-8")),
                )

    def test_productive_files_have_not_been_rewired_to_baseline_context_root(self) -> None:
        forbidden_markers = [
            "contexts/baseline_current",
            "baseline_current/prompts",
            "baseline_current/assets",
            "baseline_current/evaluation",
        ]
        for path in PRODUCTIVE_FILES_THAT_MUST_NOT_BE_REWIRED:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                content = path.read_text(encoding="utf-8")
                for marker in forbidden_markers:
                    self.assertNotIn(marker, content)

    def test_public_interfaz_routes_still_exist(self) -> None:
        paths = {route.path for route in interfaz_usuario_router.routes}
        self.assertIn("/api/interfaz_usuario/sessions/bootstrap", paths)
        self.assertIn("/api/interfaz_usuario/negociacion/new_conversation", paths)
        self.assertIn("/api/interfaz_usuario/negociacion/turn", paths)


if __name__ == "__main__":
    unittest.main()
