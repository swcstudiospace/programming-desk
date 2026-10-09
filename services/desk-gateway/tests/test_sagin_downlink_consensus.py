"""Unit tests for Ground Station Downlink Consensus & Multi-Constellation State Anchoring (Phase 65)."""

import pytest

from desk_gateway.sagin_downlink_consensus import (
    GroundStationNode,
    IntermittentGroundConsensusEngine,
    MultiConstellationDownlinkManager,
    SAGINAnchorExporter,
    SAGINOrbitalVerificationDrillSimulator,
    SatelliteMerkleReceiptLedger,
)
from desk_gateway.sagin_orbital_mesh import OrbitalEphemeris


def test_multi_constellation_downlink_manager():
    mgr = MultiConstellationDownlinkManager()
    assert len(mgr.ground_stations) >= 4

    ephem = OrbitalEphemeris(
        satellite_id="sat-kuiper-101",
        constellation="Kuiper",
        altitude_km=630.0,
        inclination_deg=51.9,
    )
    sess = mgr.initiate_downlink_session("gs-svalbard-01", ephem)
    assert sess["satellite_id"] == "sat-kuiper-101"
    assert "contact_window" in sess
    assert "doppler_compensation" in sess


def test_intermittent_ground_consensus():
    engine = IntermittentGroundConsensusEngine(ground_station_quorum_threshold=0.5)
    batch = engine.propose_orbital_batch(
        batch_id="batch-001",
        satellite_id="sat-starlink-42",
        state_root="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
        downlink_digests=["abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234"],
        proposer_station="gs-svalbard-01",
    )
    assert batch["batch_id"] == "batch-001"
    assert batch["status"] == "PROPOSED"

    # Add second vote to satisfy 50% threshold on 4 stations (2 approvals)
    res = engine.submit_ballot("batch-001", "gs-hawaii-01", "APPROVE", total_active_stations=4)
    assert res["is_committed"] is True
    assert res["approvals"] == 2
    assert "batch-001" in engine.committed_batches


def test_satellite_merkle_receipt_ledger_and_anchor():
    ledger = SatelliteMerkleReceiptLedger()
    r1 = ledger.append_event("DOWNLINK_INGEST", "sat-1", "gs-svalbard-01", {"frames": 10})
    r2 = ledger.append_event("DOWNLINK_INGEST", "sat-2", "gs-singapore-01", {"frames": 20})

    root = ledger.compute_merkle_root()
    assert len(root) == 64
    assert len(ledger.receipts) == 2
    assert r1.signature != ""

    exporter = SAGINAnchorExporter()
    commitment = exporter.export_commitment(ledger)
    assert commitment["status"] == "CONFIRMED_ON_SOLANA_DEVNET"
    assert commitment["merkle_root"] == root
    assert commitment["leaf_count"] == 2
    assert commitment["transaction_signature"].startswith("5SAGIN")


def test_sagin_orbital_verification_drill():
    drill = SAGINOrbitalVerificationDrillSimulator.run_drill()
    assert drill["drill_status"] == "ALL_CHECKS_PASSED"
    assert drill["orbital_ephemeris_and_doppler"]["status"] == "PASSED"
    assert drill["contact_graph_routing"]["status"] == "PASSED"
    assert drill["dt_bundle_custody"]["status"] == "PASSED"
    assert drill["downlink_and_ground_consensus"]["status"] == "PASSED"
    assert drill["sagin_solana_anchoring"]["status"] == "PASSED"
