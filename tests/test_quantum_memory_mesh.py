"""Unit and integration tests for Quantum Memory Node Storage and CV Optical Routing (Phase 70)."""

import math
import pytest

from desk_gateway.quantum_memory_mesh import (
    CVHomodyneMeasurementType,
    CVOpticalRouter,
    CVSqueezedState,
    QuantumMemoryBufferType,
    QuantumMemoryCell,
    QuantumMemoryNode,
)


def test_quantum_memory_cell_lifecycle_and_decay():
    state_payload = {"qubit": "alpha_0", "fidelity": 0.98}
    node = QuantumMemoryNode("desk-alpha", QuantumMemoryBufferType.AFC)

    cell = node.store_state(
        state_repr=state_payload,
        buffer_type=QuantumMemoryBufferType.AFC,
        t1_relaxation_us=10000.0,
        t2_dephasing_us=4000.0,
        peak_efficiency=0.95,
    )
    assert cell.cell_id.startswith("qmem-desk-alpha-")
    assert not cell.retrieved
    assert cell.calculate_coherence() > 0.90

    # Retrieve state
    ok, fid, retrieved = node.retrieve_state(cell.cell_id)
    assert ok is True
    assert fid > 0.85
    assert retrieved["qubit"] == "alpha_0"
    assert cell.retrieved is True

    # Retrieve again should fail
    ok_second, fid_second, err = node.retrieve_state(cell.cell_id)
    assert ok_second is False
    assert fid_second == 0.0


def test_quantum_memory_cells_listing():
    node = QuantumMemoryNode("desk-beta", QuantumMemoryBufferType.EIT)
    c1 = node.store_state({"id": 1, "fidelity": 0.99})
    c2 = node.store_state({"id": 2, "fidelity": 0.95})

    active = node.list_cells(include_retrieved=False)
    assert len(active) == 2

    node.retrieve_state(c1.cell_id)
    active_after = node.list_cells(include_retrieved=False)
    assert len(active_after) == 1
    assert active_after[0]["cell_id"] == c2.cell_id

    all_cells = node.list_cells(include_retrieved=True)
    assert len(all_cells) == 2


def test_continuous_variable_squeezed_state():
    router = CVOpticalRouter()
    # 1.0 squeezing param gives ~8.69 dB squeezing
    sqz = router.generate_squeezed_state("desk-alpha", squeezing_r=1.0, squeezing_phi=0.0)
    assert sqz.squeezing_db == pytest.approx(8.69, rel=1e-2)
    # Variance q is squeezed below 0.5 vacuum level
    assert sqz.variance_q < 0.5
    # Variance p is anti-squeezed above 0.5 vacuum level
    assert sqz.variance_p > 0.5
    # Uncertainty product Var(q)*Var(p) == (1/2)^2 == 0.25 (minimum uncertainty state)
    assert sqz.variance_q * sqz.variance_p == pytest.approx(0.25, rel=1e-5)


def test_cv_beam_splitter_symplectic_mixing():
    router = CVOpticalRouter()
    s1 = router.generate_squeezed_state("desk-alpha", squeezing_r=1.0, squeezing_phi=0.0, mean_q=1.0, mean_p=0.0)
    s2 = router.generate_squeezed_state("desk-alpha", squeezing_r=1.0, squeezing_phi=0.0, mean_q=-1.0, mean_p=0.0)

    # 50:50 beam splitter
    out1, out2 = router.beam_splitter(s1, s2, transmissivity=0.5)
    # q_out1 = sqrt(0.5)*(1) + sqrt(0.5)*(-1) = 0
    assert out1.mean_q == pytest.approx(0.0, abs=1e-5)
    # q_out2 = -sqrt(0.5)*(1) + sqrt(0.5)*(-1) = -2*sqrt(0.5) = -sqrt(2)
    assert out2.mean_q == pytest.approx(-math.sqrt(2.0), abs=1e-5)


def test_cv_homodyne_measurement():
    router = CVOpticalRouter()
    s = router.generate_squeezed_state("desk-alpha", squeezing_r=0.8, squeezing_phi=0.0)

    m_q = router.measure_homodyne(s, CVHomodyneMeasurementType.POSITION, detector_efficiency=0.99)
    assert m_q["measured_quadrature"] == "q"
    assert "value" in m_q
    assert m_q["variance"] < 0.5

    m_p = router.measure_homodyne(s, CVHomodyneMeasurementType.MOMENTUM, detector_efficiency=0.99)
    assert m_p["measured_quadrature"] == "p"
    assert "value" in m_p
    assert m_p["variance"] > 0.5

    m_joint = router.measure_homodyne(s, CVHomodyneMeasurementType.HETERODYNE, detector_efficiency=0.95)
    assert m_joint["measured_quadrature"] == "joint_qp"
    assert "value_q" in m_joint
    assert "value_p" in m_joint
