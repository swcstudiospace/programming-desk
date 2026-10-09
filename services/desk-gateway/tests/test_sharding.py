"""Unit tests for Phase 42: Dynamic Partition Sharding & Multi-Master Geo-Replication."""

import pytest
from desk_gateway.sharding import (
    ConsistentHashRing,
    ShardNode,
    CRDTStore,
    LWWRegister,
    PNCounter,
    ORSet,
    GeoReplicationEngine,
    ShardRouter,
    ConsistencyLevel,
)


def test_consistent_hash_ring_partitioning():
    ring = ConsistentHashRing(vnodes_per_node=32)

    node1 = ShardNode("node-1", "us-east")
    node2 = ShardNode("node-2", "us-west")
    node3 = ShardNode("node-3", "eu-central")

    ring.add_node(node1)
    ring.add_node(node2)
    ring.add_node(node3)

    assert len(ring.nodes) == 3
    assert len(ring._ring) == 32 * 3

    # Determinism: same key routes to same primary node
    key = "user-profile-9876"
    primary = ring.get_primary_node(key)
    assert primary is not None
    assert ring.get_primary_node(key).node_id == primary.node_id

    # Replica lookup: returns distinct nodes
    replicas = ring.get_replica_nodes(key, replica_factor=3)
    assert len(replicas) == 3
    replica_ids = [r.node_id for r in replicas]
    assert len(set(replica_ids)) == 3

    # Remove node
    assert ring.remove_node("node-2") is True
    assert len(ring.nodes) == 2
    assert ring.get_primary_node(key) is not None


def test_crdt_lww_register_convergence():
    reg1 = LWWRegister(value="first", timestamp=100.0, writer_node_id="node-a")
    reg2 = LWWRegister(value="second", timestamp=105.0, writer_node_id="node-b")

    # Merge reg2 into reg1 -> reg2 wins
    reg1.merge(reg2)
    assert reg1.value == "second"
    assert reg1.timestamp == 105.0

    # Earlier timestamp cannot overwrite
    reg_early = LWWRegister(value="old", timestamp=90.0, writer_node_id="node-c")
    reg1.merge(reg_early)
    assert reg1.value == "second"


def test_crdt_pn_counter_convergence():
    c1 = PNCounter()
    c2 = PNCounter()

    c1.increment("node-1", 10)
    c1.decrement("node-1", 2)  # value = 8

    c2.increment("node-2", 5)
    c2.decrement("node-2", 1)  # value = 4

    # Merge
    c1.merge(c2)
    assert c1.value == 12

    c2.merge(c1)
    assert c2.value == 12


def test_crdt_or_set_add_wins():
    s1 = ORSet()
    s2 = ORSet()

    tag1 = s1.add("item-A")
    s2.merge(s1)
    assert s2.read() == {"item-A"}

    # Remove item in s1
    s1.remove("item-A")
    assert s1.read() == set()

    # Concurrently add item-A again in s2
    tag2 = s2.add("item-A")

    # Merge s1 into s2: Add-wins semantics
    s2.merge(s1)
    assert "item-A" in s2.read()


def test_geo_replication_and_router():
    ring = ConsistentHashRing()
    node_a = ShardNode("node-a", "us-east")
    node_b = ShardNode("node-b", "us-west")
    ring.add_node(node_a)
    ring.add_node(node_b)

    store = CRDTStore("us-east", "node-a")
    replicator = GeoReplicationEngine("us-east", "test-secret-key")
    router = ShardRouter(ring, store, replicator)

    res_write = router.write_lww("session-key-42", {"token": "xyz123"}, ConsistencyLevel.QUORUM)
    assert res_write["ok"] is True
    assert res_write["delta_id"].startswith("delta-us-east-")

    res_read = router.read_lww("session-key-42")
    assert res_read["ok"] is True
    assert res_read["value"] == {"token": "xyz123"}

    res_counter = router.update_counter("view_counter", delta=3)
    assert res_counter["value"] == 3
    read_cnt = router.read_counter("view_counter")
    assert read_cnt["value"] == 3

    # Verify replication delta signature
    delta = replicator.replication_log[0]
    assert replicator.verify_delta(delta) is True
