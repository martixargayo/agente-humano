from pydantic import BaseModel, ConfigDict, Field, conlist
from typing import Literal


class PlannerSemanticV1DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["planner_semantic_v1"] = "planner_semantic_v1"
    phase: Literal[
        "clima_humano",
        "descubrimiento_y_comprension",
        "propuesta_creativa",
        "concesiones_y_ajuste_final",
        "formalizacion_del_acuerdo",
    ]
    style: str = Field(default="", max_length=260)
    next_move_hint: str = Field(default="", max_length=320)
    what_not_to_repeat: conlist(str, max_length=8) = Field(default_factory=list)
