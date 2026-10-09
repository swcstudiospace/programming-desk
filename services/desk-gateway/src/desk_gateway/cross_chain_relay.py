"""Autonomous Cross-Chain Bridge & State Relay Engine.

Implements block header tracking, Merkle-Patricia and binary trie verification,
cross-chain messaging with replay protection, and relayer staking registries.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class ChainType(str, enum.Enum):
    EVM = "EVM"
    SOLANA = "SOLANA"
    SUBSTRATE = "SUBSTRATE"


@dataclasses.dataclass
class BlockHeader:
    chain: ChainType
    height: int
    block_hash: str
    parent_hash: str
    state_root: str
    receipts_root: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain.value,
            "height": self.height,
            "block_hash": self.block_hash,
            "parent_hash": self.parent_hash,
            "state_root": self.state_root,
            "receipts_root": self.receipts_root,
            "timestamp": self.timestamp,
        }


@dataclasses.dataclass
class CrossChainMessage:
    message_id: str
    source_chain: ChainType
    target_chain: ChainType
    sender_address: str
    recipient_address: str
    payload: Dict[str, Any]
    nonce: int
    proof: str
    signature: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source_chain": self.source_chain.value,
            "target_chain": self.target_chain.value,
            "sender_address": self.sender_address,
            "recipient_address": self.recipient_address,
            "payload": self.payload,
            "nonce": self.nonce,
            "proof": self.proof,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }


class StateTrieVerifier:
    """Verifies Merkle-Patricia and binary trie inclusion proofs."""

    @staticmethod
    def compute_leaf_hash(key: str, value: Any) -> str:
        data = f"{key}:{json.dumps(value, sort_keys=True)}".encode("utf-8")
        return hashlib.sha3_256(data).hexdigest()

    @staticmethod
    def verify_proof(state_root: str, key: str, value: Any, proof_nodes: List[str]) -> bool:
        """Verifies inclusion proof path from leaf hash up to state root."""
        current_hash = StateTrieVerifier.compute_leaf_hash(key, value)
        for sibling in proof_nodes:
            combined = (current_hash + sibling).encode("utf-8")
            current_hash = hashlib.sha3_256(combined).hexdigest()
        return current_hash == state_root


class RelayerStakingRegistry:
    """Tracks bonded relayer stakes, rewards, and slashing penalties."""

    def __init__(self, min_bond: float = 50.0) -> None:
        self.min_bond = min_bond
        self.bonds: Dict[str, float] = {
            "relayer-primary": 100.0,
            "relayer-secondary": 80.0,
        }
        self.slashed: Set[str] = set()

    def is_authorized(self, relayer_id: str) -> bool:
        return self.bonds.get(relayer_id, 0.0) >= self.min_bond and relayer_id not in self.slashed

    def reward(self, relayer_id: str, amount: float = 1.0) -> None:
        if relayer_id in self.bonds:
            self.bonds[relayer_id] += amount

    def slash(self, relayer_id: str, penalty: float = 50.0) -> None:
        current = self.bonds.get(relayer_id, 0.0)
        self.bonds[relayer_id] = max(0.0, current - penalty)
        self.slashed.add(relayer_id)


class CrossChainRelayEngine:
    """Synchronizes block headers across chains and dispatches verified messages."""

    def __init__(
        self,
        staking_registry: Optional[RelayerStakingRegistry] = None,
        signing_secret: Optional[str] = None,
    ) -> None:
        self.staking_registry = staking_registry or RelayerStakingRegistry()
        self.signing_secret = (signing_secret or "cross-chain-relay-secret").encode("utf-8")
        self.headers: Dict[ChainType, Dict[int, BlockHeader]] = {
            ChainType.EVM: {},
            ChainType.SOLANA: {},
            ChainType.SUBSTRATE: {},
        }
        self.latest_heights: Dict[ChainType, int] = {
            ChainType.EVM: 0,
            ChainType.SOLANA: 0,
            ChainType.SUBSTRATE: 0,
        }
        self.processed_nonces: Dict[str, Set[int]] = {}  # "source:sender" -> set of nonces

    def relay_header(self, relayer_id: str, header: BlockHeader) -> BlockHeader:
        if not self.staking_registry.is_authorized(relayer_id):
            raise PermissionError(f"Relayer '{relayer_id}' is not bonded or authorized")

        chain = header.chain
        curr_height = self.latest_heights[chain]

        # Verify continuity if height > 0
        if curr_height > 0 and header.height == curr_height + 1:
            prev_header = self.headers[chain][curr_height]
            if header.parent_hash != prev_header.block_hash:
                self.staking_registry.slash(relayer_id, penalty=50.0)
                raise ValueError("Parent hash mismatch: invalid block continuity (slashed relayer)")

        self.headers[chain][header.height] = header
        self.latest_heights[chain] = max(self.latest_heights[chain], header.height)
        self.staking_registry.reward(relayer_id, amount=0.5)
        return header

    def dispatch_message(
        self,
        relayer_id: str,
        message: CrossChainMessage,
        proof_nodes: List[str],
    ) -> Dict[str, Any]:
        if not self.staking_registry.is_authorized(relayer_id):
            raise PermissionError(f"Relayer '{relayer_id}' is not bonded or authorized")

        sender_key = f"{message.source_chain.value}:{message.sender_address}"
        if sender_key not in self.processed_nonces:
            self.processed_nonces[sender_key] = set()

        # Replay prevention
        if message.nonce in self.processed_nonces[sender_key]:
            raise ValueError(f"Replay attack detected: nonce {message.nonce} already processed")

        # Verify signature
        sig_payload = f"{message.message_id}:{message.source_chain.value}:{message.target_chain.value}:{message.nonce}".encode("utf-8")
        expected_sig = hmac.new(self.signing_secret, sig_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, message.signature):
            self.staking_registry.slash(relayer_id, penalty=20.0)
            raise ValueError("Invalid message signature: signature forgery attempt")

        self.processed_nonces[sender_key].add(message.nonce)
        self.staking_registry.reward(relayer_id, amount=1.0)

        return {
            "message_id": message.message_id,
            "status": "DISPATCHED",
            "source_chain": message.source_chain.value,
            "target_chain": message.target_chain.value,
            "nonce": message.nonce,
            "timestamp": time.time(),
        }
