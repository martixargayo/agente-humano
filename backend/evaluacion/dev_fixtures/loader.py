from __future__ import annotations

import json
from pathlib import Path

from evaluacion.dev_fixtures.models import FeedbackDemoFixtureV1

FIXTURES_DIR = Path(__file__).resolve().parent


def list_fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def load_fixture(path: Path) -> FeedbackDemoFixtureV1:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return FeedbackDemoFixtureV1.model_validate(raw)


def list_fixtures() -> list[FeedbackDemoFixtureV1]:
    return [load_fixture(p) for p in list_fixture_files()]


def get_fixture_by_id(fixture_id: str) -> FeedbackDemoFixtureV1 | None:
    for fixture in list_fixtures():
        if fixture.fixture_id == fixture_id:
            return fixture
    return None
