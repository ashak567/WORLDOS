"""Future capabilities stay behind contracts until deterministic facts support them."""
from __future__ import annotations

from typing import Protocol


class ScenarioEngine(Protocol):
    def validate_constraints(self, scenario: dict) -> list[str]: ...


class PredictionEngine(Protocol):
    def predict(self, target: str, evidence_ids: list[str]) -> dict: ...


class SimulationEngine(Protocol):
    def run(self, scenario: dict) -> dict: ...


class AnomalyEngine(Protocol):
    def detect(self, series: list[float]) -> list[int]: ...


class EvidenceBoundReasoner(Protocol):
    """An AI layer may explain query results but must return cited evidence IDs."""

    def answer(self, question: str, deterministic_result: dict, evidence_ids: list[str]) -> dict: ...

