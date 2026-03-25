from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BoundCommunicationContext(BaseModel):
    model_config = ConfigDict(extra='forbid')

    flow_id: str
    context_id: str
    context_version: str


class ResolvedCommunicationContext(BaseModel):
    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

    flow_id: str
    context_id: str
    context_version: str
    public_slug: str
    context_dir: Path
    presentation_dir: Path
    assets_dir: Path
    manifest_path: Path
    resolution_source: str
