"""Utility helpers for reading technical pattern evidence in strategies."""

from __future__ import annotations

from typing import Any

from src.trading.technical_analysis.models import PatternEvidence, TechnicalAnalysisResult


def is_pattern_enabled(config: dict[str, Any]) -> bool:
    return bool((config.get("pattern_evidence") or {}).get("enabled", False))


def _evidence_rows(technical_analysis: TechnicalAnalysisResult | None, pattern_type: str) -> list[PatternEvidence]:
    if technical_analysis is None:
        return []
    return [e for e in (technical_analysis.pattern_evidence or []) if e.pattern_type == pattern_type]


def has_pattern_status(
    technical_analysis: TechnicalAnalysisResult | None,
    pattern_type: str,
    allowed_status: set[str],
) -> bool:
    for evidence in _evidence_rows(technical_analysis, pattern_type):
        status = str((evidence.details or {}).get("status", ""))
        if status in allowed_status:
            return True
    return False


def count_fvg(
    technical_analysis: TechnicalAnalysisResult | None,
    fvg_type: str,
    statuses: set[str],
) -> int:
    count = 0
    for evidence in _evidence_rows(technical_analysis, "FVG"):
        for fvg in evidence.fvgs:
            if fvg.type == fvg_type and fvg.status in statuses:
                count += 1
    return count
