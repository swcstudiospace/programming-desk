"""Unit tests for Autonomous Space-Air-Ground Integrated Network (SAGIN) & Delay-Tolerant Satellite Swarm Mesh (Phase 64)."""

import time
import pytest

from desk_gateway.sagin_orbital_mesh import (
    BundlePriority,
    ContactGraphRouter,
    ContactPlanEntry,
    CustodialStorageManager,
    CustodyStatus,
    DelayTolerantBundle,
    DopplerTelemetryTracker,
    OrbitalEphemeris,
)


def test_orbital_ephemeris_and_contact_window():
    ephem = OrbitalEphemeris(
        satellite_id="sat-starlink-test-1",
        constellation="Starlink-Gen2",
        altitude_km=550.0,
        inclination_deg=53.0,
        true_anomaly_deg=45.0,
    )
    # Ground station in Svalbard
    win = ephem.calculate_contact_window(78.22, 15.65)
    assert "is_visible" in win
    assert win["slant_range_km"] > 0
    assert win["carrier_frequency_ghz"] == 28.5
    assert ephem.to_dict()["constellation"] == "Starlink-Gen2"


def test_doppler_telemetry_tracker():
    carrier_ghz = 28.5
    rel_vel = 7.2  # km/s
    res = DopplerTelemetryTracker.compute_doppler_shift(carrier_ghz, rel_vel)
    assert res["nominal_carrier_ghz"] == 28.5
    assert res["relative_velocity_km_s"] == 7.2
    assert res["doppler_shift_khz"] > 0
    assert res["link_snr_margin_db"] >= 0.0
    assert "telemetry_lock_healthy" in res


def test_delay_tolerant_bundle_creation_and_expiration():
    bundle = DelayTolerantBundle(
        bundle_id="b-test-01",
        source_eid="dtn://sat-1",
        destination_eid="dtn://gs-1",
        payload_raw="EARTH_OBSERVATION_DATA",
        priority=BundlePriority.EXPEDITED,
        ttl_seconds=0.01,
    )
    assert bundle.priority == BundlePriority.EXPEDITED
    assert len(bundle.digest_sha256) == 64
    assert not bundle.is_expired()

    time.sleep(0.02)
    assert bundle.is_expired()


def test_contact_graph_router():
    router = ContactGraphRouter(local_eid="dtn://sat-1")
    now = time.time()
    # Contact from sat-1 to sat-2
    router.add_contact(ContactPlanEntry("c-12", "dtn://sat-1", "dtn://sat-2", now, now + 500, 10000))
    # Contact from sat-2 to ground-1
    router.add_contact(ContactPlanEntry("c-2g", "dtn://sat-2", "dtn://gs-1", now + 10, now + 600, 20000))

    bundle = DelayTolerantBundle(
        bundle_id="b-cgr-1",
        source_eid="dtn://sat-1",
        destination_eid="dtn://gs-1",
        payload_raw="WEATHER_SCAN",
    )
    route_res = router.route_bundle(bundle, current_time=now)
    assert route_res["status"] == "FORWARDED"
    assert route_res["next_hop"] == "dtn://sat-2"
    assert route_res["full_path"] == ["dtn://sat-1", "dtn://sat-2", "dtn://gs-1"]


def test_custodial_storage_manager():
    mgr = CustodialStorageManager(custodian_eid="dtn://sat-1", max_capacity_bytes=10000)
    bundle = DelayTolerantBundle(
        bundle_id="b-custody-1",
        source_eid="dtn://sensor-0",
        destination_eid="dtn://gs-1",
        payload_raw="ATMOSPHERIC_CO2_TELEMETRY",
    )
    receipt = mgr.accept_custody(bundle)
    assert receipt["accepted"] is True
    assert "custody_sig" in receipt
    assert bundle.bundle_id in mgr.store
    assert bundle.custody_status == CustodyStatus.ACCEPTED

    # Release custody
    released = mgr.release_custody(bundle.bundle_id, "DELIVERED")
    assert released is True
    assert bundle.bundle_id not in mgr.store
    assert bundle.custody_status == CustodyStatus.DELIVERED
