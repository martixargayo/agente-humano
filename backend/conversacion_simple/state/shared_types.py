from __future__ import annotations

from enum import Enum


class ConversationSimplePhase(str, Enum):
    apertura = "apertura"
    desarrollo = "desarrollo"
    cierre = "cierre"
