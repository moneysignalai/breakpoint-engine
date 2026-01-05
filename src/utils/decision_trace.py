from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GateTrace:
    name: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionTrace:
    symbol: str
    strategy: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    computed: Dict[str, Any] = field(default_factory=dict)
    gates: List[GateTrace] = field(default_factory=list)
    skip_reason: Optional[str] = None
    skip_details: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def add_input(self, key: str, value: Any) -> None:
        self.inputs[key] = value

    def add_inputs(self, data: Dict[str, Any]) -> None:
        self.inputs.update(data)

    def add_computed(self, key: str, value: Any) -> None:
        self.computed[key] = value

    def add_computeds(self, data: Dict[str, Any]) -> None:
        self.computed.update(data)

    def record_gate(self, name: str, passed: bool, details: Dict[str, Any] | None = None) -> None:
        gate_details = details or {}
        self.gates.append(GateTrace(name=name, passed=passed, details=gate_details))
        if not passed and not self.skip_reason:
            self.skip_reason = name
            self.skip_details = gate_details

    def mark_skip(self, reason: str, details: Dict[str, Any] | None = None) -> None:
        self.skip_reason = reason
        self.skip_details = details or {}
        if not any(g.name == reason for g in self.gates):
            self.gates.append(GateTrace(name=reason, passed=False, details=self.skip_details))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "inputs": self.inputs,
            "computed": self.computed,
            "gates": [
                {"name": g.name, "passed": g.passed, "details": g.details} for g in self.gates
            ],
            "skip_reason": self.skip_reason,
            "skip_details": self.skip_details,
            "notes": self.notes,
        }

    def failed_gates(self) -> List[Dict[str, Any]]:
        return [
            {"name": gate.name, "details": gate.details}
            for gate in self.gates
            if not gate.passed
        ]

    def summary(self) -> Dict[str, Any]:
        return {
            "skip_reason": self.skip_reason,
            "gates": [{"name": g.name, "passed": g.passed} for g in self.gates],
            "inputs": self.inputs,
            "computed": self.computed,
        }
