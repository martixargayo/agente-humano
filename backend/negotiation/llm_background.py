from __future__ import annotations

from copy import deepcopy
import re

from .elementos.render import resolve_render_profiles
from .elementos.render.carlos_buyer_preset import get_carlos_constraints_struct, is_carlos_buyer_render_ids
from .schemas import default_constraints_struct


def infer_speaker_of_user_message(user_message: str, *, fallback: str = "unknown") -> str:
    raw = str(user_message or "").strip().lower()
    if not raw:
        return fallback
    if raw.startswith(("vendedor:", "don joaquín:", "don joaquin:", "seller:")):
        return "seller"
    if raw.startswith(("comprador:", "carlos:", "buyer:")):
        return "buyer"
    return fallback


def build_background_context(progress_state: dict | None) -> tuple[dict, dict, dict, dict]:
    progress = progress_state if isinstance(progress_state, dict) else {}
    render_state = progress.get("render_state") if isinstance(progress.get("render_state"), dict) else {}
    persona_profile, scene_profile, style_contract = resolve_render_profiles(render_state)

    constraints_struct = progress.get("render_constraints_struct")
    if not isinstance(constraints_struct, dict):
        if is_carlos_buyer_render_ids(
            persona_profile.get("persona_id"),
            scene_profile.get("scene_id"),
            style_contract.get("style_id"),
        ):
            constraints_struct = get_carlos_constraints_struct()
        else:
            constraints_struct = default_constraints_struct()
    return (
        deepcopy(persona_profile),
        deepcopy(scene_profile),
        deepcopy(style_contract),
        deepcopy(constraints_struct),
    )


def _compact_spaces(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _strip_digits(value: str) -> str:
    text = _compact_spaces(value)
    return re.sub(r"\d+", "", text).strip()


def _to_bool_text(value: object) -> str:
    return "true" if bool(value) else "false"


def build_background_public_block(
    persona_profile: dict,
    scene_profile: dict,
    style_contract: dict,
    constraints_struct: dict,
    *,
    language: str,
    task_type: str,
    domain: str,
    participants: dict,
    speaker_of_user_message: str,
) -> str:
    role_card = persona_profile.get("role_card") if isinstance(persona_profile.get("role_card"), dict) else {}
    persona_id = _compact_spaces(persona_profile.get("persona_id", "buyer_mustang67_v1")) or "buyer_mustang67_v1"
    persona_name = _compact_spaces(role_card.get("name", "Carlos")) or "Carlos"
    # Campo allowlist: role + anchors + experience sin cifras.
    role_public = "comprador joven interesado en Mustang 1967"
    anchors = persona_profile.get("persona_anchors")
    if not isinstance(anchors, list) or not anchors:
        anchors = ["excited but cautious", "wants clarity and low risk", "polite, non-aggressive negotiator"]
    anchors_public = [str(item).strip() for item in anchors if str(item).strip()][:3]
    if len(anchors_public) == 0:
        anchors_public = ["excited but cautious", "wants clarity and low risk", "polite, non-aggressive negotiator"]

    scene_id = _compact_spaces(scene_profile.get("scene_id", "mustang67_in_person_viewing")) or "mustang67_in_person_viewing"
    partner_name = _compact_spaces(scene_profile.get("partner_name", "Don Joaquín")) or "Don Joaquín"

    style_id = _compact_spaces(style_contract.get("style_id", "psyplay_compact")) or "psyplay_compact"
    max_questions = int(style_contract.get("max_questions", 1) or 1)
    markdown_allowed = _to_bool_text(style_contract.get("markdown_allowed", False))

    forbid_behaviors = constraints_struct.get("forbid_behaviors") if isinstance(constraints_struct.get("forbid_behaviors"), list) else []
    forbid_set = {str(item).strip() for item in forbid_behaviors if str(item).strip()}
    constraints_lines = ["- No revelar presupuesto máximo ni BATNA", "- No amenazar ni presionar", "- Mantener tono respetuoso"]
    if "revealing_max_budget_or_BATNA" not in forbid_set:
        constraints_lines = [line for line in constraints_lines if "BATNA" not in line]
    if "aggressive_pressure_or_threats" not in forbid_set:
        constraints_lines = [line for line in constraints_lines if "amenazar" not in line and "presionar" not in line]
    if len(constraints_lines) == 0:
        constraints_lines = ["- Mantener tono respetuoso"]

    participants_json = '{"buyer":"Carlos","seller":"Don Joaquín"}'
    if isinstance(participants, dict) and participants:
        buyer = _compact_spaces(participants.get("buyer", "Carlos")) or "Carlos"
        seller = _compact_spaces(participants.get("seller", "Don Joaquín")) or "Don Joaquín"
        participants_json = f'{{"buyer":"{buyer}","seller":"{seller}"}}'

    speaker = str(speaker_of_user_message or "unknown").strip().lower()
    if speaker not in {"seller", "buyer", "unknown"}:
        speaker = "unknown"

    _ = _strip_digits(str(persona_profile.get("experience", "")))

    lines = [
        "BACKGROUND_CONTEXT:",
        f"language: {str(language or 'es').strip() or 'es'}",
        f"task_type: {str(task_type or 'negotiation').strip() or 'negotiation'}",
        f"domain: {str(domain or 'mustang67_car_purchase').strip() or 'mustang67_car_purchase'}",
        f"participants: {participants_json}",
        f"speaker_of_user_message: {speaker}",
        "",
        "PERSONA_PUBLIC:",
        f"persona_id: {persona_id}",
        f"name: {persona_name}",
        f"role: {role_public}",
        f"persona_anchors: {anchors_public}",
        "",
        "SCENE_PUBLIC:",
        f"scene_id: {scene_id}",
        "setting: roleplay compra coche clásico en persona",
        f"partner_name: {partner_name}",
        "turn_topic: negociación compra Mustang 1967, foco fiabilidad y papeles",
        "",
        "STYLE_PUBLIC:",
        f"style_id: {style_id}",
        "target_length: very_short",
        f"max_questions: {max_questions}",
        f"markdown_allowed: {markdown_allowed}",
        "",
        "CONSTRAINTS_PUBLIC:",
        *constraints_lines,
    ]
    return "\n".join(lines).strip()
