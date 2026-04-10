from __future__ import annotations

import json
import os
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from conversacion_simple.orchestration import pipeline as cs_pipeline
from interfaz_usuario import services as iu_services
from sessions.state import reset_session_store

REPORT_PATH = Path("backend/docs/forensics_interfaz_usuario_conversacion_simple_latency_run.json")
TARGET_CONTEXT = "negociacion_sala_reuniones"


@dataclass
class TurnTiming:
    label: str
    message: str
    http_total_ms: float
    backend_total_ms: float | None
    pre_openai_ms: float | None
    openai_ms: float | None
    post_openai_ms: float | None
    parse_json_ms: float | None
    pydantic_validate_ms: float | None
    apply_patch_ms: float | None
    save_state_ms: float | None
    append_trace_ms: float | None
    response_status: int
    response_reply_len: int
    surface_total_ms: float | None = None
    pipeline_turn_total_ms: float | None = None
    stage_breakdown: dict[str, float] | None = None


def _safe_ms(start: float, end: float) -> float:
    return round((end - start) * 1000.0, 3)


@contextmanager
def _instrument_pipeline(per_turn: list[dict[str, float | str | int]], *, fake_openai: bool, disable_persistence: bool) -> Any:
    base_call = _fake_structured_call if fake_openai else cs_pipeline._call_brain_structured
    base_parse = cs_pipeline._parse_brain_output_strict
    base_apply = cs_pipeline.apply_brain_output_to_state
    base_save = cs_pipeline.save_session_state
    base_append = cs_pipeline.ConversationSimpleStateRepository.append_trace

    active: dict[str, float | str | int] = {}

    def wrap_call(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        out = base_call(*args, **kwargs)
        t1 = time.perf_counter()
        active["openai_ms"] = _safe_ms(t0, t1)
        active["openai_response_id"] = out.response_id or ""
        return out

    def wrap_parse(*args: Any, **kwargs: Any) -> Any:
        payload = kwargs.get("payload") if "payload" in kwargs else (args[0] if args else None)
        t_json0 = time.perf_counter()
        # _parse_brain_output_strict already receives parsed dict, so json parse lives in _call_brain_structured
        t_json1 = time.perf_counter()
        out = base_parse(*args, **kwargs)
        t_json2 = time.perf_counter()
        active["parse_json_ms"] = _safe_ms(t_json0, t_json1)
        # includes pydantic + normalize
        active["pydantic_validate_ms"] = _safe_ms(t_json1, t_json2) if isinstance(payload, dict) else 0.0
        return out

    def wrap_apply(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        out = base_apply(*args, **kwargs)
        t1 = time.perf_counter()
        active["apply_patch_ms"] = _safe_ms(t0, t1)
        return out

    def wrap_save(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        if disable_persistence:
            out = None
        else:
            out = base_save(*args, **kwargs)
        t1 = time.perf_counter()
        active["save_state_ms"] = _safe_ms(t0, t1)
        return out

    def wrap_append(self: Any, session_state: Any, trace: Any) -> Any:
        t0 = time.perf_counter()
        if disable_persistence:
            out = None
        else:
            out = base_append(self, session_state, trace)
        t1 = time.perf_counter()
        active["append_trace_ms"] = _safe_ms(t0, t1)
        return out

    orig_run = iu_services.run_conversacion_simple_turn

    def wrap_run(*args: Any, **kwargs: Any) -> Any:
        active.clear()
        t0 = time.perf_counter()
        out = orig_run(*args, **kwargs)
        t1 = time.perf_counter()
        active["backend_total_ms"] = _safe_ms(t0, t1)
        pre = active.get("backend_total_ms", 0.0) - active.get("openai_ms", 0.0) - active.get("parse_json_ms", 0.0) - active.get("pydantic_validate_ms", 0.0) - active.get("apply_patch_ms", 0.0) - active.get("save_state_ms", 0.0) - active.get("append_trace_ms", 0.0)
        active["pre_openai_ms"] = round(max(pre, 0.0), 3)
        post = active.get("backend_total_ms", 0.0) - active.get("pre_openai_ms", 0.0) - active.get("openai_ms", 0.0)
        active["post_openai_ms"] = round(max(post, 0.0), 3)
        per_turn.append(dict(active))
        return out

    with patch.object(cs_pipeline, "_call_brain_structured", wrap_call), \
        patch.object(cs_pipeline, "_parse_brain_output_strict", wrap_parse), \
        patch.object(cs_pipeline, "apply_brain_output_to_state", wrap_apply), \
        patch.object(cs_pipeline, "save_session_state", wrap_save), \
        patch.object(cs_pipeline.ConversationSimpleStateRepository, "append_trace", wrap_append), \
        patch.object(iu_services, "run_conversacion_simple_turn", wrap_run):
        yield


def _fake_structured_call(*, client: Any, model: str, messages: list[dict[str, str]], max_output_tokens: int | None = None) -> cs_pipeline.StructuredBrainCall:
    _ = (client, model, messages, max_output_tokens)
    time.sleep(0.12)
    return cs_pipeline.StructuredBrainCall(
        source="model",
        parsed_json={
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "Respuesta simulada de baja latencia."},
            "state_patch": {
                "conversation_state": {
                    "phase": "avance",
                    "status": "active",
                    "current_turn_goal": "responder",
                    "closure_readiness": "not_ready",
                },
                "memory_working": {
                    "current_topic": "simulacion",
                    "pending_question": None,
                    "last_turn_summary": "respuesta fake",
                },
                "memory_episodic_append": [],
            },
        },
        response=object(),
        response_id="resp_fake_123",
        schema_observability={"schema_name": "BrainOutput", "validation": {"valid": True}, "openai_subset_validation": {"valid": True}},
        fallback_reason_code=None,
        model_attempted=True,
        model_succeeded=True,
    )


def _bootstrap_cs(client: TestClient, user_id: str, session_id: str) -> None:
    r = client.post(
        "/api/interfaz_usuario/sessions/bootstrap",
        json={"user_id": user_id, "session_id": session_id, "context_id": TARGET_CONTEXT},
    )
    assert r.status_code == 200, r.text


def _run_sequence(client: TestClient, label: str, messages: list[str], *, fake_openai: bool, forensic: bool, disable_persistence: bool = False) -> dict[str, Any]:
    reset_session_store()
    os.environ["CONVERSACION_SIMPLE_TRACE_FORENSIC"] = "1" if forensic else "0"

    session_suffix = f"{label}_{'fake' if fake_openai else 'real'}_{'for' if forensic else 'std'}"
    user_id = f"u_{session_suffix}"
    session_id = f"s_{session_suffix}"
    _bootstrap_cs(client, user_id=user_id, session_id=session_id)

    timings: list[TurnTiming] = []
    per_turn_internal: list[dict[str, float | str | int]] = []

    with _instrument_pipeline(per_turn_internal, fake_openai=fake_openai, disable_persistence=disable_persistence):
            for idx, message in enumerate(messages, start=1):
                t0 = time.perf_counter()
                r = client.post(
                    "/api/interfaz_usuario/negociacion/turn",
                    json={
                        "user_id": user_id,
                        "session_id": session_id,
                        "message": message,
                        "new_conversation": False,
                    },
                )
                t1 = time.perf_counter()
                payload = r.json()
                internal = per_turn_internal[-1] if per_turn_internal else {}
                latency_breakdown = payload.get("latency_breakdown_ms", {}) if isinstance(payload, dict) else {}
                surface_precise = latency_breakdown.get("surface_stage_timings_precise_ms", {}) if isinstance(latency_breakdown, dict) else {}
                pipeline_precise = latency_breakdown.get("pipeline_stage_timings_precise_ms", {}) if isinstance(latency_breakdown, dict) else {}
                merged_stage_breakdown: dict[str, float] = {}
                if isinstance(surface_precise, dict):
                    merged_stage_breakdown.update({f"surface::{k}": float(v) for k, v in surface_precise.items() if isinstance(v, (int, float))})
                if isinstance(pipeline_precise, dict):
                    merged_stage_breakdown.update({f"pipeline::{k}": float(v) for k, v in pipeline_precise.items() if isinstance(v, (int, float))})
                timings.append(
                    TurnTiming(
                        label=f"{label}_t{idx}",
                        message=message,
                        http_total_ms=_safe_ms(t0, t1),
                        backend_total_ms=float(internal.get("backend_total_ms")) if internal.get("backend_total_ms") is not None else None,
                        pre_openai_ms=float(internal.get("pre_openai_ms")) if internal.get("pre_openai_ms") is not None else None,
                        openai_ms=float(internal.get("openai_ms")) if internal.get("openai_ms") is not None else None,
                        post_openai_ms=float(internal.get("post_openai_ms")) if internal.get("post_openai_ms") is not None else None,
                        parse_json_ms=float(internal.get("parse_json_ms")) if internal.get("parse_json_ms") is not None else None,
                        pydantic_validate_ms=float(internal.get("pydantic_validate_ms")) if internal.get("pydantic_validate_ms") is not None else None,
                        apply_patch_ms=float(internal.get("apply_patch_ms")) if internal.get("apply_patch_ms") is not None else None,
                        save_state_ms=float(internal.get("save_state_ms")) if internal.get("save_state_ms") is not None else None,
                        append_trace_ms=float(internal.get("append_trace_ms")) if internal.get("append_trace_ms") is not None else None,
                        response_status=r.status_code,
                        response_reply_len=len(payload.get("reply", "")) if isinstance(payload, dict) else 0,
                        surface_total_ms=float(latency_breakdown.get("surface_total_precise_ms")) if isinstance(latency_breakdown.get("surface_total_precise_ms"), (int, float)) else None,
                        pipeline_turn_total_ms=float(pipeline_precise.get("turn_total")) if isinstance(pipeline_precise.get("turn_total"), (int, float)) else None,
                        stage_breakdown=merged_stage_breakdown,
                    )
                )

    def _aggregate(key: str) -> dict[str, float | None]:
        values = [getattr(item, key) for item in timings if getattr(item, key) is not None]
        if not values:
            return {"avg": None, "p50": None, "p95": None}
        return {
            "avg": round(statistics.fmean(values), 3),
            "p50": round(statistics.median(values), 3),
            "p95": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 3),
        }

    return {
        "label": label,
        "fake_openai": fake_openai,
        "forensic": forensic,
        "disable_persistence": disable_persistence,
        "turns": [asdict(t) for t in timings],
        "aggregates_ms": {
            "http_total_ms": _aggregate("http_total_ms"),
            "backend_total_ms": _aggregate("backend_total_ms"),
            "pre_openai_ms": _aggregate("pre_openai_ms"),
            "openai_ms": _aggregate("openai_ms"),
            "post_openai_ms": _aggregate("post_openai_ms"),
            "parse_json_ms": _aggregate("parse_json_ms"),
            "pydantic_validate_ms": _aggregate("pydantic_validate_ms"),
            "apply_patch_ms": _aggregate("apply_patch_ms"),
            "save_state_ms": _aggregate("save_state_ms"),
            "append_trace_ms": _aggregate("append_trace_ms"),
            "surface_total_ms": _aggregate("surface_total_ms"),
            "pipeline_turn_total_ms": _aggregate("pipeline_turn_total_ms"),
        },
        "stage_aggregates_ms": _aggregate_stage_breakdown(timings),
    }


def _aggregate_stage_breakdown(timings: list[TurnTiming]) -> dict[str, dict[str, float]]:
    by_stage: dict[str, list[float]] = {}
    for item in timings:
        if not isinstance(item.stage_breakdown, dict):
            continue
        for key, value in item.stage_breakdown.items():
            by_stage.setdefault(key, []).append(float(value))
    aggregated: dict[str, dict[str, float]] = {}
    for key, values in by_stage.items():
        if not values:
            continue
        ordered = sorted(values)
        aggregated[key] = {
            "avg": round(statistics.fmean(values), 3),
            "p50": round(statistics.median(values), 3),
            "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        }
    return aggregated


def build_report() -> dict[str, Any]:
    client = TestClient(app)

    experiments: list[dict[str, Any]] = []

    experiments.append(
        _run_sequence(
            client,
            label="single_short",
            messages=["hola"],
            fake_openai=True,
            forensic=False,
        )
    )
    experiments.append(
        _run_sequence(
            client,
            label="cold_vs_warm_short",
            messages=["hola"] * 6,
            fake_openai=True,
            forensic=False,
        )
    )
    experiments.append(
        _run_sequence(
            client,
            label="multi_turn",
            messages=[
                "hola",
                "quiero reservar la sala de reuniones para mañana",
                "somos 8 personas y necesitamos proyector",
                "presupuesto limitado, ¿qué opciones hay?",
            ],
            fake_openai=True,
            forensic=False,
        )
    )
    experiments.append(
        _run_sequence(
            client,
            label="rich_context_forensic_on",
            messages=[
                "Necesito cerrar una negociación de alquiler de sala con catering, pantalla, y acceso desde las 8:00 a 18:00 para 12 personas.",
                "Incluye requerimientos de confidencialidad y posibilidad de ampliar horario sin penalización alta.",
            ],
            fake_openai=True,
            forensic=True,
        )
    )

    experiments.append(
        _run_sequence(
            client,
            label="multi_turn_no_persistence",
            messages=["hola", "segunda", "tercera", "cuarta"],
            fake_openai=True,
            forensic=False,
            disable_persistence=True,
        )
    )

    openai_key_present = bool(os.getenv("OPENAI_API_KEY"))
    real_experiment: dict[str, Any] | None = None
    if openai_key_present:
        real_experiment = _run_sequence(
            client,
            label="single_short_real_openai",
            messages=["hola"],
            fake_openai=False,
            forensic=False,
        )

    report = {
        "report_name": "forensics_interfaz_usuario_conversacion_simple_latency",
        "context_id": TARGET_CONTEXT,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "openai_key_present": openai_key_present,
        "experiments": experiments,
        "real_openai_experiment": real_experiment,
        "notes": [
            "Los tiempos miden ruta HTTP TestClient -> FastAPI -> servicio real sin red frontend.",
            "openai_ms representa el coste observado alrededor de _call_brain_structured.",
            "La métrica parse_json_ms en esta campaña mide parse residual en _parse_brain_output_strict; el json.loads principal ocurre dentro de _call_brain_structured.",
        ],
    }
    return report


if __name__ == "__main__":
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report_path": str(REPORT_PATH)}, ensure_ascii=False))
