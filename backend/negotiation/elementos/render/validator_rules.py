from __future__ import annotations

import re
from typing import Dict, List, Tuple


_INTERNAL_ACCESS_PATTERNS = [
    re.compile(r"\b(acceso|acceder|entrar)\s+(a|al|a la)\s+(tu|su)?\s*(cuenta|sistema|base de datos|panel|crm)\b", re.IGNORECASE),
    re.compile(r"\b(he|ya)\s+accedido\s+a\s+tu\s+(cuenta|sistema|panel)\b", re.IGNORECASE),
]

_PHYSICAL_ACTION_PATTERNS = [
    re.compile(r"\b(he|ya)\s+(enviado|entregado|llamado|contactado|reservado|comprado)\b", re.IGNORECASE),
]

_PRIVACY_LEAK_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bapi[_-]?key\b", re.IGNORECASE),
    re.compile(r"\btoken\b\s*[:=]\s*\w+", re.IGNORECASE),
]

_DANGEROUS_INSTRUCTION_PATTERNS = [
    re.compile(r"\b(fabricar|construir)\s+(bomba|explosivo)\b", re.IGNORECASE),
    re.compile(r"\b(hackear|piratear)\b", re.IGNORECASE),
]


def _match_any(patterns: List[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def evaluate_critical_violations(text: str) -> Tuple[List[Dict[str, str]], bool]:
    violations: List[Dict[str, str]] = []
    if _match_any(_INTERNAL_ACCESS_PATTERNS, text):
        violations.append(
            {
                "code": "claims_internal_access",
                "severity": "critical",
                "evidence": "internal_access_phrase",
            }
        )
    if _match_any(_PHYSICAL_ACTION_PATTERNS, text):
        violations.append(
            {
                "code": "claims_physical_action_done",
                "severity": "critical",
                "evidence": "physical_action_phrase",
            }
        )
    if _match_any(_PRIVACY_LEAK_PATTERNS, text):
        violations.append(
            {"code": "privacy_leak", "severity": "critical", "evidence": "secret_pattern"}
        )
    if _match_any(_DANGEROUS_INSTRUCTION_PATTERNS, text):
        violations.append(
            {
                "code": "dangerous_instruction",
                "severity": "critical",
                "evidence": "dangerous_instruction_pattern",
            }
        )
    critical = bool(violations)
    return violations, critical
