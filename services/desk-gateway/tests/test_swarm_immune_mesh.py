"""Unit tests for Autonomous Multi-Agent Self-Evolving Immune & Swarm Anti-Fragility Mesh (Phase 62)."""

import pytest

from desk_gateway.swarm_immune_mesh import (
    GeneticAntibodyMutator,
    ImmuneAntibody,
    MitigationAction,
    MultiSeatAntibodyDistributor,
    RuntimeReconstitutionSupervisor,
    SwarmAntiFragilityEngine,
    ThreatPattern,
    ThreatSeverity,
    ThreatVectorType,
)


def test_antibody_creation_and_signature_verification():
    distributor = MultiSeatAntibodyDistributor(seat_id="bot-06-quality-security")
    ab = distributor.create_and_sign(
        vector_type=ThreatVectorType.BYZANTINE_INJECTION,
        indicator_pattern="DROP_TABLE_OR_ESCAPE",
        mitigation=MitigationAction.QUARANTINE_ISOLATE,
        severity=ThreatSeverity.CRITICAL,
    )
    assert ab.antibody_id.startswith("ab-")
    assert ab.generation == 0
    assert ab.issuer_seat == "bot-06-quality-security"
    assert distributor._verify_signature(ab) is True

    # Tamper with signature
    tampered = ImmuneAntibody(
        antibody_id=ab.antibody_id,
        target_vector=ab.target_vector,
        pattern=ab.pattern,
        mitigation=ab.mitigation,
        severity=ab.severity,
        generation=ab.generation,
        fitness_score=ab.fitness_score,
        issuer_seat=ab.issuer_seat,
        signature="invalid-fake-sig",
    )
    assert distributor.register_antibody(tampered) is False


def test_peer_sync_and_catalog_digest():
    d1 = MultiSeatAntibodyDistributor(seat_id="bot-06-quality-security")
    ab1 = d1.create_and_sign(
        vector_type=ThreatVectorType.AST_ESCAPE,
        indicator_pattern="__import__('os').system",
    )

    d2 = MultiSeatAntibodyDistributor(seat_id="bot-01-systems-backend")
    sync_result = d2.sync_with_peer("bot-06-quality-security", [ab1])

    assert sync_result["accepted_count"] == 1
    assert sync_result["rejected_count"] == 0
    assert ab1.antibody_id in d2.antibodies
    assert sync_result["catalog_digest"] == d2.compute_local_catalog_digest()


def test_genetic_antibody_mutator():
    mutator = GeneticAntibodyMutator(mutation_rate=0.8)
    distributor = MultiSeatAntibodyDistributor(seat_id="bot-06-quality-security")
    parent = distributor.create_and_sign(
        vector_type=ThreatVectorType.LATENCY_POISONING,
        indicator_pattern="SLOW_LORIS",
    )

    child = mutator.mutate(parent, distributor.hmac_key)
    assert child.generation == parent.generation + 1
    assert child.target_vector == parent.target_vector
    assert distributor._verify_signature(child) is True


def test_antifragility_perturbation_and_evolution():
    distributor = MultiSeatAntibodyDistributor(seat_id="bot-06-quality-security")
    engine = SwarmAntiFragilityEngine(distributor)

    # Initial probe with no existing matching antibody -> triggers synthesis and evolution
    res1 = engine.inject_chaos_perturbation(
        target_seat="bot-02-web-edge",
        vector_type=ThreatVectorType.ENTROPY_BURST,
        attack_payload="ENTROPY_OVERLOAD_ATTACK",
        simulated_entropy=0.95,
    )
    assert res1["outcome"] == "EVOLVED_IMMUNITY_GAINED"
    assert res1["evolved_antibody_id"] is not None

    # Repeated probe with existing matching antibody -> intercepted & neutralized
    res2 = engine.inject_chaos_perturbation(
        target_seat="bot-02-web-edge",
        vector_type=ThreatVectorType.ENTROPY_BURST,
        attack_payload="ENTROPY_OVERLOAD_ATTACK",
        simulated_entropy=0.95,
    )
    assert res2["is_blocked"] is True
    assert res2["outcome"] == "NEUTRALIZED_BY_EXISTING_ANTIBODY"


def test_runtime_reconstitution_and_rehabilitation():
    distributor = MultiSeatAntibodyDistributor(seat_id="bot-06-quality-security")
    engine = SwarmAntiFragilityEngine(distributor)
    supervisor = RuntimeReconstitutionSupervisor(engine)

    snap_id = supervisor.capture_golden_snapshot("bot-03-android", {"state": "clean", "cache_size": 128})
    assert snap_id.startswith("snap-")

    # Reconstitute
    recon = supervisor.reconstitute_seat("bot-03-android")
    assert recon["new_state"] == "REHABILITATING"
    assert engine.seat_states["bot-03-android"] == "REHABILITATING"

    # Graduate rehabilitation
    grad = supervisor.graduate_rehabilitation("bot-03-android", drill_score=0.92)
    assert grad["final_status"] == "HEALTHY"
    assert grad["outcome"] == "GRADUATED_HEALTHY"
