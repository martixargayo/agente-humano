"""Migraciones de compatibilidad para estado de sesión.

En esta versión simplificada del repositorio no existen módulos de negociación
externos, así que mantenemos funciones locales que normalizan estructuras
básicas y evitan errores de import al arrancar el backend.
"""

from __future__ import annotations

from typing import Any


def _ensure_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def migrate_belief_state_to_v3(belief_state: Any) -> dict:
    """Devuelve un belief_state compatible con v3.

    Si entra un valor no-dict, se reemplaza por un dict vacío.
    """
    return _ensure_dict(belief_state)


def migrate_world_state_to_v3(world_state: Any) -> dict:
    """Devuelve un world_state compatible con v3.

    Si entra un valor no-dict, se reemplaza por un dict vacío.
    """
    return _ensure_dict(world_state)
