"""Unit tests for Neuromorphic Spiking Neural Mesh & Event-Driven Synaptic Attestation (Phase 61)."""

import pytest

from desk_gateway.neuromorphic_mesh import (
    EventSpikeRouter,
    HardwareNeuromorphicDrillSimulator,
    NeuromorphicAnchorExporter,
    NeuromorphicMesh,
    SpikeEvent,
    SpikingNeuron,
    SynapticAttestationLedger,
    SynapticConnection,
    SynapticProofReceipt,
)


def test_spiking_neuron_lif_dynamics():
    neuron = SpikingNeuron(neuron_id="test_lif", layer_id="hidden")
    assert neuron.membrane_potential == -70.0

    # Step decay towards resting
    neuron.membrane_potential = -60.0
    neuron.step_decay(elapsed_us=5.0)
    assert neuron.membrane_potential < -60.0

    # Integrate sub-threshold spike
    fired = neuron.integrate_spike(synaptic_weight=0.2, current_time_us=10.0)
    assert fired is False

    # Integrate strong spike that exceeds threshold (-55.0 mV)
    fired_super = neuron.integrate_spike(synaptic_weight=1.5, current_time_us=11.0)
    assert fired_super is True
    assert neuron.membrane_potential == neuron.reset_potential
    assert neuron.total_spikes_fired == 1


def test_synaptic_connection_stdp_learning():
    syn = SynapticConnection(source_id="n1", target_id="n2", weight=0.3)

    # 1. Long-Term Potentiation (Pre fires at 10us, Post fires at 15us -> causal)
    new_w_ltp = syn.apply_stdp(pre_time_us=10.0, post_time_us=15.0)
    assert new_w_ltp > 0.3

    # 2. Long-Term Depression (Post fires at 15us, Pre fires at 20us -> non-causal)
    new_w_ltd = syn.apply_stdp(pre_time_us=20.0, post_time_us=15.0)
    assert new_w_ltd < new_w_ltp


def test_event_spike_router_priority_order():
    router = EventSpikeRouter()
    evt2 = SpikeEvent(event_id="e2", source_neuron_id="n1", target_neuron_id="n2", timestamp_us=15.0)
    evt1 = SpikeEvent(event_id="e1", source_neuron_id="n1", target_neuron_id="n2", timestamp_us=5.0)

    router.enqueue_spike(evt2)
    router.enqueue_spike(evt1)
    assert router.pending_count == 2

    # Pop due at 10.0 us -> only evt1 should pop
    due = router.pop_due_spikes(current_time_us=10.0)
    assert len(due) == 1
    assert due[0].event_id == "e1"
    assert router.pending_count == 1


def test_neuromorphic_mesh_simulation_and_fingerprint():
    mesh = NeuromorphicMesh(mesh_id="test-mesh-01")
    initial_fp = mesh.compute_synaptic_fingerprint()
    assert len(initial_fp) == 64

    # Inject stimulus into input neurons
    injected = mesh.inject_spikes([("in_0", 1.5), ("in_1", 1.2)])
    assert injected == 2

    step_info = mesh.step_simulation(duration_us=20.0, step_dt_us=1.0)
    assert step_info["simulated_time_us"] == 20.0
    assert step_info["spikes_fired_in_step"] > 0
    assert step_info["total_mesh_spikes"] > 0

    post_fp = mesh.compute_synaptic_fingerprint()
    # Fingerprint should mutate if STDP adapted weights
    assert post_fp != initial_fp


def test_synaptic_attestation_ledger_and_anchor():
    ledger = SynapticAttestationLedger()
    rcpt = ledger.append_receipt(
        mesh_id="mesh-01",
        receipt_type="SYNAPTIC_WEIGHT_UPDATE",
        simulated_time_us=100.0,
        total_spikes=45,
        synaptic_fingerprint="abc123hash",
        payload={"sparsity": 0.85},
    )
    assert isinstance(rcpt, SynapticProofReceipt)
    assert len(rcpt.hmac_signature) == 64
    assert len(ledger.receipts) == 1

    merkle_root = ledger.compute_merkle_root()
    assert len(merkle_root) == 64

    exporter = NeuromorphicAnchorExporter()
    anchor = exporter.export_commitment(ledger.receipts)
    assert anchor["status"] == "CONFIRMED"
    assert anchor["merkle_root"] == merkle_root
    assert anchor["receipts_anchored"] == 1
    assert anchor["transaction_signature"].startswith("sol-nm-")


def test_hardware_neuromorphic_drill_simulator():
    drill = HardwareNeuromorphicDrillSimulator.run_drill()
    assert drill["drill_status"] == "ALL_CHECKS_PASSED"
    assert drill["kernel_compilation"]["status"] == "PASSED"
    assert drill["workload_dispatch"]["status"] == "PASSED"
    assert drill["lif_spike_propagation"]["status"] == "PASSED"
    assert drill["stdp_synaptic_adaptation"]["status"] == "PASSED"
    assert drill["synaptic_attestation_and_anchoring"]["status"] == "PASSED"
