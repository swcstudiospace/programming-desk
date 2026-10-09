"""Integration tests for Space-Air-Ground Integrated Network (SAGIN) REST endpoints (Milestone v4.9)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_sagin_ephemeris_and_doppler_routes(client):
    # 1. POST /v1/sagin/ephemeris/contact_window
    r1 = client.post(
        "/v1/sagin/ephemeris/contact_window",
        json={
            "satellite_id": "sat-starlink-test",
            "constellation": "Starlink-Gen2",
            "altitude_km": 550.0,
            "inclination_deg": 53.0,
            "station_latitude": 78.22,
            "station_longitude": 15.65,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "contact_window" in r1.json()
    assert r1.json()["contact_window"]["carrier_frequency_ghz"] == 28.5

    # 2. POST /v1/sagin/doppler/shift
    r2 = client.post(
        "/v1/sagin/doppler/shift",
        json={"carrier_frequency_ghz": 28.5, "relative_velocity_km_s": 7.1},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["doppler"]["relative_velocity_km_s"] == 7.1
    assert r2.json()["doppler"]["telemetry_lock_healthy"] is True


def test_sagin_bundle_and_custody_routes(client):
    # 1. POST /v1/sagin/bundle/route
    r1 = client.post(
        "/v1/sagin/bundle/route",
        json={
            "bundle_id": "b-test-gw-01",
            "source_eid": "dtn://gateway-orbital-0",
            "destination_eid": "dtn://gs-svalbard-01",
            "payload_raw": "SAR_SCAN_CHUNK_42",
            "priority": "expedited",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["bundle"]["priority"] == "expedited"

    # 2. POST /v1/sagin/custody/accept
    r2 = client.post(
        "/v1/sagin/custody/accept",
        json={
            "bundle_id": "b-test-gw-02",
            "source_eid": "dtn://sensor-orbital-1",
            "destination_eid": "dtn://gs-svalbard-01",
            "payload_raw": "IONOSPHERIC_DENSITY_MEASUREMENT",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["custody_receipt"]["accepted"] is True


def test_sagin_downlink_and_consensus_routes(client):
    # 1. POST /v1/sagin/downlink/session
    r1 = client.post(
        "/v1/sagin/downlink/session",
        json={
            "station_id": "gs-svalbard-01",
            "satellite_id": "sat-starlink-leo-01",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["downlink_session"]["station_id"] == "gs-svalbard-01"

    # 2. POST /v1/sagin/consensus/propose
    r2 = client.post(
        "/v1/sagin/consensus/propose",
        json={
            "batch_id": "batch-sagin-test-1",
            "satellite_id": "sat-starlink-leo-01",
            "state_root": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "downlink_digests": ["0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
            "proposer_station": "gs-svalbard-01",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["batch"]["batch_id"] == "batch-sagin-test-1"

    # 3. POST /v1/sagin/consensus/ballot
    r3 = client.post(
        "/v1/sagin/consensus/ballot",
        json={
            "batch_id": "batch-sagin-test-1",
            "station_id": "gs-singapore-01",
            "vote": "APPROVE",
        },
    )
    assert r3.status_code == 200
    assert r3.json()["ok"] is True


def test_sagin_anchor_and_drill_routes(client):
    # 1. POST /v1/sagin/anchor/export
    r1 = client.post("/v1/sagin/anchor/export")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["anchor"]["status"] == "CONFIRMED_ON_SOLANA_DEVNET"

    # 2. POST /v1/sagin/drill/simulate
    r2 = client.post("/v1/sagin/drill/simulate")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["drill"]["drill_status"] == "ALL_CHECKS_PASSED"
