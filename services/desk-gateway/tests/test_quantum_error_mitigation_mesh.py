"""Unit and integration tests for Quantum Error Mitigation (QEM) mesh (Milestone v6.1 - Phases 88 & 89)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_error_mitigation_mesh import (
    ExtrapolationModel,
    NoiseScalePoint,
    ProbabilisticErrorCanceller,
    ReadoutErrorMitigator,
    ZeroNoiseExtrapolator,
)
from desk_gateway.quantum_error_mitigation_anchoring import (
    QEMMerkleLedger,
    QEMReceipt,
    QEMSolanaAnchorExporter,
    QEMVerificationDrillSimulator,
)
from desk_gateway.server import build_app


def test_zero_noise_extrapolator_richardson():
    scale_points = [
        NoiseScalePoint(scale_factor=1.0, measured_expectation=0.80),
        NoiseScalePoint(scale_factor=2.0, measured_expectation=0.70),
        NoiseScalePoint(scale_factor=3.0, measured_expectation=0.62),
    ]
    res = ZeroNoiseExtrapolator.extrapolate(
        scale_points=scale_points,
        model=ExtrapolationModel.RICHARDSON,
        ideal_target=0.92,
    )
    assert res.mitigated_zero_noise_value > res.unmitigated_value
    assert res.error_reduction_pct > 0.0
    d = res.to_dict()
    assert d["extrapolation_model"] == "RICHARDSON"


def test_zero_noise_extrapolator_linear():
    scale_points = [
        NoiseScalePoint(scale_factor=1.0, measured_expectation=0.80),
        NoiseScalePoint(scale_factor=2.0, measured_expectation=0.70),
    ]
    res = ZeroNoiseExtrapolator.extrapolate(
        scale_points=scale_points,
        model=ExtrapolationModel.LINEAR,
    )
    assert abs(res.mitigated_zero_noise_value - 0.90) < 1e-5


def test_readout_error_mitigator():
    mitigator = ReadoutErrorMitigator(p0_given_1=0.04, p1_given_0=0.02)
    raw_counts = {"0": 850, "1": 150}
    res = mitigator.mitigate_readout_counts(raw_counts)
    assert "p0" in res and "p1" in res
    assert abs(res["p0"] + res["p1"] - 1.0) < 1e-4
    assert res["p0"] > (850 / 1000)


def test_probabilistic_error_canceller():
    pec = ProbabilisticErrorCanceller(depolarizing_rate=0.04)
    mitigated, gamma = pec.cancel_error(0.80)
    assert gamma > 1.0
    assert mitigated > 0.80


def test_qem_merkle_ledger_and_anchor():
    ledger = QEMMerkleLedger()
    r1 = QEMReceipt.create("c1", "ZNE", 0.80, 0.91, 13.0)
    r2 = QEMReceipt.create("c2", "READOUT", 0.85, 0.89, 5.0)
    ledger.append_receipt(r1)
    ledger.append_receipt(r2)
    root = ledger.get_root_hash()
    assert len(root) == 64

    export = QEMSolanaAnchorExporter.export(ledger)
    assert export["status"] == "ANCHOR_PAYLOAD_GENERATED"
    assert export["merkle_root"] == root
    assert export["total_receipts"] == 2


def test_qem_verification_drill():
    drill = QEMVerificationDrillSimulator.run_drill()
    assert drill["passed"] is True
    assert len(drill["stages"]) == 5
    for stage_name, stage_data in drill["stages"].items():
        assert stage_data["passed"] is True


def test_qem_gateway_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. ZNE route
    resp = client.post(
        "/v1/quantum/mitigation/zne",
        json={
            "circuit_id": "test-bell-circuit",
            "model": "RICHARDSON",
            "ideal_target": 0.95,
            "scale_points": [
                {"scale_factor": 1.0, "measured_expectation": 0.81},
                {"scale_factor": 2.0, "measured_expectation": 0.70},
                {"scale_factor": 3.0, "measured_expectation": 0.61},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "result" in data
    assert "receipt" in data

    # 2. Readout route
    resp2 = client.post(
        "/v1/quantum/mitigation/readout",
        json={
            "circuit_id": "test-readout-circuit",
            "raw_counts": {"0": 920, "1": 80},
            "p0_given_1": 0.05,
            "p1_given_0": 0.02,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ok"] is True
    assert "mitigated_counts" in data2

    # 3. PEC route
    resp3 = client.post(
        "/v1/quantum/mitigation/pec",
        json={
            "circuit_id": "test-pec-circuit",
            "measured_expectation": 0.84,
            "depolarizing_rate": 0.03,
        },
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["ok"] is True
    assert data3["mitigated_expectation"] > 0.84

    # 4. Anchor Export route
    resp4 = client.post("/v1/quantum/mitigation/anchor/export")
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert data4["ok"] is True
    assert data4["anchor"]["total_receipts"] >= 3

    # 5. Verification Drill route
    resp5 = client.post("/v1/quantum/mitigation/drill/simulate")
    assert resp5.status_code == 200
    data5 = resp5.json()
    assert data5["ok"] is True
    assert data5["drill"]["passed"] is True
