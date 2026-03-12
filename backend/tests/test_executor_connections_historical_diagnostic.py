from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "a1939b2"


def _git_show(rev: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git show failed for {rev}:{path}\nSTDERR:\n{result.stderr}")
    return result.stdout


def _exists_in_rev(rev: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{rev}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_core_executor_surrounding_backend_stack_is_byte_identical_vs_a1939b2() -> None:
    # Si esto se mantiene, no hubo cambio de wiring backend real del executor
    # entre a1939b2 y HEAD en la ruta cognitiva/guards/nodes auditada.
    critical_files = [
        "backend/negociacion/guards/policy.py",
        "backend/negociacion/pipeline.py",
        "backend/negociacion/optimizador/__init__.py",
        "backend/negociacion/optimizador/services.py",
        "backend/negociacion/nodes/executor_node.py",
        "backend/negociacion/nodes/planner_node.py",
        "backend/negociacion/nodes/memory_node.py",
    ]

    for relpath in critical_files:
        baseline = _git_show(BASELINE, relpath)
        current = (REPO_ROOT / relpath).read_text(encoding="utf-8")
        assert current == baseline, f"Unexpected drift since {BASELINE} in {relpath}"


def test_avatar_negotiation_endpoint_contract_matches_a1939b2() -> None:
    relpath = "backend/avatar_app/app.js"
    baseline = _git_show(BASELINE, relpath)
    current = (REPO_ROOT / relpath).read_text(encoding="utf-8")

    marker = "const endpoint = mode === AgentMode.NEGOTIATION ? '/negociar' : '/chat';"
    assert marker in baseline
    assert marker in current


def test_frontend_unification_added_interfaz_and_shared_runtime_after_a1939b2() -> None:
    shared_runtime = "backend/avatar_app/shared/chat_runtime.js"
    interfaz_app = "backend/avatar_app/interfaz_usuario/app.js"

    assert _exists_in_rev("HEAD", shared_runtime)
    assert _exists_in_rev("HEAD", interfaz_app)

    assert not _exists_in_rev(BASELINE, shared_runtime)
    assert not _exists_in_rev(BASELINE, interfaz_app)


def test_optimizer_chat_path_semantics_preserved_through_runtime_extraction() -> None:
    relpath = "backend/avatar_app/optimizador/app.js"
    baseline = _git_show(BASELINE, relpath)
    current = (REPO_ROOT / relpath).read_text(encoding="utf-8")

    # Baseline (inline implementation) ya enviaba por sandbox/turn con scope_turn_id.
    assert 'api("/sandbox/turn"' in baseline
    assert "scope_turn_id: state.selectedTurnId || null" in baseline

    # HEAD (runtime compartido) mantiene el mismo endpoint útil y scope_turn_id.
    runtime = (REPO_ROOT / "backend/avatar_app/shared/chat_runtime.js").read_text(encoding="utf-8")
    assert 'api("/sandbox/turn"' in runtime
    assert "scope_turn_id: state.selectedTurnId || null" in runtime


def test_api_mount_and_route_expansion_since_a1939b2_is_ui_surface_not_executor_core() -> None:
    relpath = "backend/api/app.py"
    baseline = _git_show(BASELINE, relpath)
    current = (REPO_ROOT / relpath).read_text(encoding="utf-8")

    # Cambio posterior: nueva superficie estática /interfaz_usuario.
    assert '"/interfaz_usuario"' not in baseline
    assert '"/interfaz_usuario"' in current

    # Sin cambio en endpoint útil de negociación /negociar.
    negociar_decl = '@app.post("/negociar", response_model=ChatResponse)'
    assert negociar_decl in baseline
    assert negociar_decl in current



def test_executor_core_files_intentionally_drifted_since_baseline() -> None:
    # This diagnostic guards against accidental rollback of the contract fix.
    for relpath in (
        "backend/negociacion/orchestration/flow_config.py",
        "backend/negociacion/guards/output.py",
    ):
        baseline = _git_show(BASELINE, relpath)
        current = (REPO_ROOT / relpath).read_text(encoding="utf-8")
        assert current != baseline
