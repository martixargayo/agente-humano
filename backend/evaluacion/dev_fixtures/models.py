from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DemoFixtureTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_index: int
    turn_id: str
    user_text: str
    assistant_text: str


class DemoFixtureConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turns: list[DemoFixtureTurn] = Field(default_factory=list)


class DemoFixtureStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: int | None = None


class DemoFixtureDomainContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final_phase: str | None = None
    finish_button_was_armed: bool = False


class DemoFixtureDerivedFactsOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_turn_indexes: list[int] | None = None
    close_signals_count: int | None = None
    offer_signals_count: int | None = None
    blocker_signals_count: int | None = None


class DemoFixtureTraceDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_count: int = 0
    guardrail_events_count: int = 0


class FeedbackDemoFixtureV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["feedback_demo_fixture.v1"]
    fixture_id: str
    title: str
    domain: Literal["negociacion"]
    conversation: DemoFixtureConversation
    conversation_stats: DemoFixtureStats = Field(default_factory=DemoFixtureStats)
    domain_context: DemoFixtureDomainContext = Field(default_factory=DemoFixtureDomainContext)
    derived_facts_overrides: DemoFixtureDerivedFactsOverrides | None = None
    trace_digest: DemoFixtureTraceDigest | None = None
