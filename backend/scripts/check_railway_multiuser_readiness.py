from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from evaluacion.storage import REPOSITORY
from interfaz_usuario.models import SessionBootstrapRequest
from negociacion.optimizador import experiments_bridge
from sessions.state import SESSIONS, get_session_state

PATTERNS = {
    "global_session_store": re.compile(r"^SESSIONS\s*:?.*=", re.MULTILINE),
    "in_memory_eval_repo": re.compile(r"REPOSITORY\s*=\s*InMemoryFeedbackRepository\("),
    "optimizer_override_store": re.compile(r"_OVERRIDE_STORE\s*:\s*dict"),
    "default_public_identity": re.compile(r'user_id:\s*str\s*=\s*"u_interfaz"|session_id:\s*str\s*=\s*"interfaz-main"'),
    "temporary_directory": re.compile(r"TemporaryDirectory\("),
}

FILES = [
    BACKEND / "sessions" / "state.py",
    BACKEND / "evaluacion" / "storage" / "in_memory_repository.py",
    BACKEND / "negociacion" / "optimizador" / "experiments_bridge.py",
    BACKEND / "interfaz_usuario" / "models.py",
    BACKEND / "interfaz_usuario_app" / "index.html",
    BACKEND / "avatar_app" / "optimizador" / "app.js",
]


def scan_patterns() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                findings.append({"file": str(path.relative_to(ROOT)), "line": line, "pattern": label, "match": match.group(0)[:120]})
    return findings


def runtime_probes() -> dict[str, object]:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()
    REPOSITORY._reports.clear()
    experiments_bridge._OVERRIDE_STORE.clear()

    default_bootstrap = SessionBootstrapRequest().model_dump(mode="json")

    state = get_session_state("probe-user", "probe-session")
    state.world_state["probe"] = {"alive": True}
    sessions_before = len(SESSIONS)
    SESSIONS.clear()
    restarted = get_session_state("probe-user", "probe-session")

    experiments_bridge.update_state("probe-optimizer", {"mode": "sandbox", "entries": []})
    overrides_before = experiments_bridge.get_state("probe-optimizer")
    experiments_bridge._OVERRIDE_STORE.clear()
    overrides_after = experiments_bridge.get_state("probe-optimizer")

    return {
        "default_bootstrap": default_bootstrap,
        "session_store": {
            "sessions_before_restart": sessions_before,
            "state_survives_clear": "probe" in restarted.world_state,
        },
        "optimizer_overrides": {
            "before_clear": overrides_before,
            "after_clear": overrides_after,
        },
        "evaluation_repository_type": type(REPOSITORY).__name__,
    }


def classify_risks(findings: list[dict[str, object]], probes: dict[str, object]) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if any(item["pattern"] == "global_session_store" for item in findings):
        risks.append({"severity": "high", "title": "Estado conversacional en RAM del proceso", "evidence": "SESSIONS global detectado y el probe confirma pérdida tras clear/restart."})
    if any(item["pattern"] == "in_memory_eval_repo" for item in findings):
        risks.append({"severity": "high", "title": "Evaluación sin persistencia durable", "evidence": "REPOSITORY usa InMemoryFeedbackRepository."})
    if any(item["pattern"] == "optimizer_override_store" for item in findings):
        risks.append({"severity": "high", "title": "Overrides del optimizer solo en memoria local", "evidence": "_OVERRIDE_STORE global detectado."})
    default_bootstrap = probes.get("default_bootstrap", {})
    if default_bootstrap.get("user_id") == "u_interfaz" and default_bootstrap.get("session_id") == "interfaz-main":
        risks.append({"severity": "critical", "title": "Identidad pública por defecto compartida", "evidence": "bootstrap público usa user_id/session_id constantes."})
    return risks


def main() -> None:
    findings = scan_patterns()
    probes = runtime_probes()
    payload = {
        "summary": {
            "pattern_findings": len(findings),
            "high_or_worse_risks": len(classify_risks(findings, probes)),
        },
        "findings": findings,
        "runtime_probes": probes,
        "risks": classify_risks(findings, probes),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
