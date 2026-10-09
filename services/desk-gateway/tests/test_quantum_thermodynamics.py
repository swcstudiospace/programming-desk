"""Tests for Quantum Thermodynamic Resource Theories, Maxwell's Demon & Landauer Erasure Ledger (Milestone v6.6 - Phases 98 & 99)."""

import math
import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_thermodynamics_mesh import (
    K_B,
    LandauerErasureEngine,
    MaxwellQuantumDemon,
    QuantumHeatEngineCycle,
    QuantumThermalReservoir,
    QuantumThermodynamicMesh,
    QuantumWorkExtractionEngine,
)
from desk_gateway.quantum_thermodynamics_anchoring import (
    QuantumThermodynamicMerkleLedger,
    QuantumThermodynamicReceipt,
    QuantumThermodynamicSolanaAnchorExporter,
    QuantumThermodynamicVerificationDrill,
)
from desk_gateway.server import build_app


def test_thermal_reservoir_gibbs_state() -> None:
    res = QuantumThermalReservoir(temperature=1.0)
    energy_levels = [0.0, 1.0, 2.0]
    th = res.compute_thermal_state(energy_levels)

    assert len(th.probabilities) == 3
    assert abs(sum(th.probabilities) - 1.0) < 1e-6
    # Gibbs distribution: probabilities decrease strictly with energy
    assert th.probabilities[0] > th.probabilities[1] > th.probabilities[2]
    assert th.von_neumann_entropy > 0.0
    assert th.free_energy <= th.mean_energy


def test_ergotropy_and_passivity() -> None:
    energy_levels = [0.0, 1.0, 2.0]

    # Passive state (ordered descending in population)
    passive_probs = [0.6, 0.3, 0.1]
    res_pass = QuantumWorkExtractionEngine.calculate_ergotropy(energy_levels, passive_probs)
    assert res_pass.is_passive
    assert res_pass.extractable_ergotropy < 1e-7

    # Active state (inverted population)
    active_probs = [0.1, 0.2, 0.7]
    res_act = QuantumWorkExtractionEngine.calculate_ergotropy(energy_levels, active_probs, reservoir_temperature=1.0)
    assert not res_act.is_passive
    assert res_act.extractable_ergotropy > 0.0
    assert res_act.bound_free_energy_work >= res_act.extractable_ergotropy


def test_maxwell_demon_and_landauer_erasure() -> None:
    demon = MaxwellQuantumDemon(measurement_fidelity=1.0)
    demon_res = demon.measure_and_extract_work((0.9, 0.1), energy_gap=1.0, temperature=1.0)

    assert demon_res.mutual_information_bits > 0.0
    assert demon_res.work_extracted > 0.0
    assert demon_res.demon_memory_bits == 1.0

    # Landauer erasure of the 1 bit of memory acquired by demon
    erasure_res = LandauerErasureEngine.erase_memory(bits_to_erase=1.0, reservoir_temperature=1.0, dissipation_efficiency=1.05)
    assert erasure_res.landauer_bound_satisfied
    assert erasure_res.actual_heat_dissipated >= erasure_res.theoretical_minimum_heat
    # Landauer limit at T=1: Q_min = k_B * T * ln(2)
    assert abs(erasure_res.theoretical_minimum_heat - math.log(2)) < 1e-6


def test_quantum_otto_heat_engine() -> None:
    engine = QuantumHeatEngineCycle(th_cold=1.0, th_hot=4.0, omega_cold=1.0, omega_hot=2.0)
    res = engine.execute_cycle()

    assert res.second_law_satisfied
    # Otto efficiency = 1 - omega_cold / omega_hot = 1 - 1/2 = 0.5
    assert abs(res.otto_efficiency - 0.5) < 1e-5
    # Carnot limit = 1 - T_c / T_h = 1 - 1/4 = 0.75
    assert abs(res.carnot_limit - 0.75) < 1e-5
    assert res.otto_efficiency <= res.carnot_limit
    assert res.net_work_extracted >= 0.0


def test_thermodynamic_merkle_ledger_and_anchor() -> None:
    ledger = QuantumThermodynamicMerkleLedger()
    rcpt1 = QuantumThermodynamicReceipt(
        receipt_id="rcpt-test-1",
        cycle_type="OTTO_CYCLE",
        temperature=300.0,
        work_extracted=12.5,
        heat_dissipated=25.0,
        entropy_delta=0.01,
        efficiency=0.33,
        second_law_satisfied=True,
        landauer_bound_satisfied=True,
    )
    rcpt2 = QuantumThermodynamicReceipt(
        receipt_id="rcpt-test-2",
        cycle_type="DEMON_ERASURE",
        temperature=300.0,
        work_extracted=0.693,
        heat_dissipated=0.750,
        entropy_delta=0.002,
        efficiency=0.924,
        second_law_satisfied=True,
        landauer_bound_satisfied=True,
    )

    ledger.add_receipt(rcpt1)
    ledger.add_receipt(rcpt2)

    root = ledger.get_merkle_root()
    assert len(root) == 64
    assert ledger.verify_ledger_integrity()

    payload = QuantumThermodynamicSolanaAnchorExporter.generate_instruction_payload(
        merkle_root=root,
        num_receipts=len(ledger.receipts),
        mean_temperature=300.0,
        total_work_extracted=13.193,
        total_heat_dissipated=25.750,
    )
    assert payload["program_id"] == QuantumThermodynamicSolanaAnchorExporter.ANCHOR_PROGRAM_ID
    assert payload["data"]["merkle_root"] == root
    assert "anchor_thermodynamic_landauer_root" in payload["instruction"]

    program = QuantumThermodynamicSolanaAnchorExporter.export_anchor_program()
    assert "declare_id!" in program
    assert "total_heat_dissipated_scaled" in program


def test_thermodynamic_verification_drill() -> None:
    drill = QuantumThermodynamicVerificationDrill(default_temperature=1.0)
    drill_res = drill.run_drill()

    assert drill_res["all_passed"]
    assert len(drill_res["stages"]) == 5
    for stage_key, stage_info in drill_res["stages"].items():
        assert stage_info["passed"], f"Stage {stage_key} failed: {stage_info}"
    assert len(drill_res["merkle_root"]) == 64


def test_thermo_api_endpoints() -> None:
    app, _ = build_app()
    client = TestClient(app)

    # 1. Thermalize
    resp = client.post("/v1/quantum/thermo/thermalize", json={"energy_levels": [0.0, 1.0, 2.0], "temperature": 1.5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert len(data["thermal_state"]["probabilities"]) == 3

    # 2. Ergotropy extract
    resp = client.post(
        "/v1/quantum/thermo/ergotropy/extract",
        json={"energy_levels": [0.0, 1.0, 2.0], "probabilities": [0.1, 0.2, 0.7], "temperature": 1.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["ergotropy"]["extractable_ergotropy"] > 0
    assert len(data["merkle_root"]) == 64

    # 3. Demon cycle
    resp = client.post("/v1/quantum/thermo/demon/cycle", json={"p0": 0.85, "p1": 0.15, "temperature": 1.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["demon"]["work_extracted"] > 0
    assert data["erasure"]["landauer_bound_satisfied"]

    # 4. Heat engine cycle
    resp = client.post(
        "/v1/quantum/thermo/heat_engine/cycle",
        json={"th_cold": 1.0, "th_hot": 4.0, "omega_cold": 1.0, "omega_hot": 2.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["cycle"]["second_law_satisfied"]
    assert data["cycle"]["otto_efficiency"] <= data["cycle"]["carnot_limit"]

    # 5. Anchor export
    resp = client.post("/v1/quantum/thermo/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert "anchor" in data
    assert "program" in data

    # 6. Verification drill simulate
    resp = client.post("/v1/quantum/thermo/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["drill"]["all_passed"]
