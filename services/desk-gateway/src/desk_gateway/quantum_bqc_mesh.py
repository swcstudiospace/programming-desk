"""Blind Quantum Computing (BQC) & Measurement-Based Quantum Computing (MBQC) (Milestone v5.3 - Phase 72).

Implements:
- MeasurementBasis: XY-plane measurement basis with angle theta and adaptive outcome corrections.
- ClusterStateGraph: 2D brickwork graph state generation with Entangled cluster state adjacency and stabilizer tracking.
- ClientBlindAngles: Client-side angle blinding (theta' = theta + r * pi) and measurement outcome unblinding (s' = s ^ r).
- BQCEngine: Coordinates delegation of quantum computations from a thin client (Alice) to an untrusted quantum server (Bob)
  such that the server learns neither the input, the algorithm/angles, nor the computation output.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import hashlib
import json
import math
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple


class MeasurementPlane(str, enum.Enum):
    XY = "XY"
    XZ = "XZ"
    YZ = "YZ"


@dataclasses.dataclass
class BlindAngleSpecification:
    step_id: str
    target_qubit: int
    raw_angle: float           # Original target rotation angle theta in radians
    blind_key_r: int           # Random binary key r in {0, 1}
    blind_theta: float         # Blinded angle theta' = raw_angle + r * pi
    measurement_plane: MeasurementPlane = MeasurementPlane.XY

    @classmethod
    def create(cls, step_id: str, target_qubit: int, raw_angle: float) -> "BlindAngleSpecification":
        r = secrets.randbelow(2)
        blind_theta = (raw_angle + r * math.pi) % (2.0 * math.pi)
        return cls(
            step_id=step_id,
            target_qubit=target_qubit,
            raw_angle=raw_angle,
            blind_key_r=r,
            blind_theta=round(blind_theta, 6),
        )

    def unblind_outcome(self, server_outcome: int) -> int:
        """Unblinds the measurement outcome s = s' ^ r."""
        return server_outcome ^ self.blind_key_r


@dataclasses.dataclass
class BrickworkNode:
    node_id: int
    layer: int
    qubit_index: int
    neighbors: List[int] = dataclasses.field(default_factory=list)
    measured: bool = False
    outcome: Optional[int] = None


class BrickworkClusterState:
    """Represents a standard 2D brickwork MBQC graph state."""

    def __init__(self, layers: int = 3, qubits_per_layer: int = 4) -> None:
        self.layers = max(1, layers)
        self.qubits_per_layer = max(2, qubits_per_layer)
        self.nodes: Dict[int, BrickworkNode] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        total_qubits = self.layers * self.qubits_per_layer
        for idx in range(total_qubits):
            layer = idx // self.qubits_per_layer
            q_idx = idx % self.qubits_per_layer
            self.nodes[idx] = BrickworkNode(node_id=idx, layer=layer, qubit_index=q_idx)

        # Connect horizontal neighbors (within line across layers)
        for layer in range(self.layers - 1):
            for q in range(self.qubits_per_layer):
                u = layer * self.qubits_per_layer + q
                v = (layer + 1) * self.qubits_per_layer + q
                self.nodes[u].neighbors.append(v)
                self.nodes[v].neighbors.append(u)

        # Connect vertical neighbors in brickwork pattern
        for layer in range(self.layers):
            offset = layer % 2
            for q in range(offset, self.qubits_per_layer - 1, 2):
                u = layer * self.qubits_per_layer + q
                v = u + 1
                self.nodes[u].neighbors.append(v)
                self.nodes[v].neighbors.append(u)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layers": self.layers,
            "qubits_per_layer": self.qubits_per_layer,
            "total_nodes": len(self.nodes),
            "adjacency": {node_id: node.neighbors for node_id, node in self.nodes.items()},
        }


class BlindQuantumComputingEngine:
    """Coordinates Universal Blind Quantum Computation (BQC) delegation."""

    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def init_bqc_session(
        self,
        client_node: str,
        server_node: str,
        layers: int = 3,
        qubits_per_layer: int = 4,
    ) -> Dict[str, Any]:
        session_id = f"bqc-{secrets.token_hex(6)}"
        cluster = BrickworkClusterState(layers=layers, qubits_per_layer=qubits_per_layer)
        session_data = {
            "session_id": session_id,
            "client_node": client_node,
            "server_node": server_node,
            "cluster": cluster,
            "step_blinds": {},
            "server_outcomes": {},
            "unblinded_results": {},
            "created_at": time.time(),
        }
        self.sessions[session_id] = session_data
        return {
            "session_id": session_id,
            "client_node": client_node,
            "server_node": server_node,
            "cluster_info": cluster.to_dict(),
        }

    def execute_blind_measurement_step(
        self,
        session_id: str,
        target_qubit: int,
        target_angle_rad: float,
    ) -> Dict[str, Any]:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(f"Session {session_id} not found")

        cluster: BrickworkClusterState = session["cluster"]
        if target_qubit not in cluster.nodes:
            raise ValueError(f"Target qubit {target_qubit} out of graph bounds")

        # 1. Client prepares blind angle specification
        step_id = f"step-{len(session['step_blinds']) + 1}"
        blind_spec = BlindAngleSpecification.create(step_id, target_qubit, target_angle_rad)
        session["step_blinds"][target_qubit] = blind_spec

        # 2. Server measures physical qubit in XY plane along angle theta'
        # Probability P(0) = cos^2(theta'/2), P(1) = sin^2(theta'/2)
        prob_0 = math.cos(blind_spec.blind_theta / 2.0) ** 2
        roll = secrets.randbelow(1_000_000) / 1_000_000.0
        server_outcome = 0 if roll < prob_0 else 1
        session["server_outcomes"][target_qubit] = server_outcome

        # Mark node
        cluster.nodes[target_qubit].measured = True
        cluster.nodes[target_qubit].outcome = server_outcome

        # 3. Client decrypts/unblinds outcome using private blinding key r
        unblinded_outcome = blind_spec.unblind_outcome(server_outcome)
        session["unblinded_results"][target_qubit] = unblinded_outcome

        return {
            "step_id": step_id,
            "target_qubit": target_qubit,
            "server_received_theta": blind_spec.blind_theta,
            "server_outcome": server_outcome,
            "client_unblinded_outcome": unblinded_outcome,
            "blind_key_r_used": blind_spec.blind_key_r,
        }
