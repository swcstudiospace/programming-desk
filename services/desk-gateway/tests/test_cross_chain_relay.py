import hashlib
import hmac
import pytest
from desk_gateway.cross_chain_relay import (
    ChainType,
    BlockHeader,
    CrossChainMessage,
    StateTrieVerifier,
    RelayerStakingRegistry,
    CrossChainRelayEngine,
)

def test_state_trie_verifier():
    verifier = StateTrieVerifier()
    key = "account:0x1234"
    value = {"balance": 1000}
    leaf_hash = verifier.compute_leaf_hash(key, value)
    
    # Compute simple 1-step proof
    sibling = "sibling_hash_abc"
    state_root = hashlib.sha3_256((leaf_hash + sibling).encode("utf-8")).hexdigest()
    proof = [sibling]

    assert verifier.verify_proof(state_root, key, value, proof) is True
    # Tampered value
    assert verifier.verify_proof(state_root, key, {"balance": 9999}, proof) is False
    # Empty proof
    assert verifier.verify_proof(state_root, key, value, []) is False


def test_relayer_staking_registry():
    registry = RelayerStakingRegistry(min_bond=50.0)
    assert registry.is_authorized("relayer-primary") is True
    assert registry.is_authorized("relayer-unknown") is False

    # Slashing
    registry.slash("relayer-primary", penalty=60.0)
    assert registry.is_authorized("relayer-primary") is False

    # Reward
    registry.reward("relayer-secondary", amount=15.0)
    assert registry.bonds["relayer-secondary"] == 95.0


def test_cross_chain_relay_engine_header_continuity_and_slashing():
    registry = RelayerStakingRegistry(min_bond=50.0)
    engine = CrossChainRelayEngine(staking_registry=registry)

    # Relay Genesis Block
    h0 = BlockHeader(
        chain=ChainType.EVM,
        height=0,
        block_hash="hash0",
        parent_hash="0x0",
        state_root="root0",
        receipts_root="rr0",
    )
    res0 = engine.relay_header("relayer-primary", h0)
    assert res0.height == 0

    # Relay Block 1
    h1 = BlockHeader(
        chain=ChainType.EVM,
        height=1,
        block_hash="hash1",
        parent_hash="hash0",
        state_root="root1",
        receipts_root="rr1",
    )
    res1 = engine.relay_header("relayer-primary", h1)
    assert res1.height == 1

    # Malicious Block 2 with invalid parent_hash
    h2_bad = BlockHeader(
        chain=ChainType.EVM,
        height=2,
        block_hash="hash2",
        parent_hash="wrong_parent",
        state_root="root2",
        receipts_root="rr2",
    )
    with pytest.raises(ValueError, match="Parent hash mismatch"):
        engine.relay_header("relayer-primary", h2_bad)

    # Relayer should now be slashed
    assert registry.is_authorized("relayer-primary") is False


def test_cross_chain_message_dispatch_and_replay_prevention():
    engine = CrossChainRelayEngine()

    payload = {"intent": "transfer", "amount": 500}
    sig_payload = "msg-1:EVM:SOLANA:1".encode("utf-8")
    sig = hmac.new(engine.signing_secret, sig_payload, hashlib.sha256).hexdigest()

    msg = CrossChainMessage(
        message_id="msg-1",
        source_chain=ChainType.EVM,
        target_chain=ChainType.SOLANA,
        sender_address="0xAlice",
        recipient_address="SolanaBob",
        payload=payload,
        nonce=1,
        proof="dummy-proof",
        signature=sig,
    )

    res = engine.dispatch_message("relayer-primary", msg, [])
    assert res["status"] == "DISPATCHED"
    assert res["message_id"] == "msg-1"

    # Replay attempt with same nonce
    with pytest.raises(ValueError, match="Replay attack detected"):
        engine.dispatch_message("relayer-primary", msg, [])
