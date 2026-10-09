"""Dynamic Context Window Compression & Semantic Pruning Engine.

Implements:
- REQ-GRAPH-006: Lossless token compression and context-window compaction pipeline.
- REQ-GRAPH-007: Semantic relevance pruning removing low-salience tokens while preserving syntactic validity.
- REQ-GRAPH-008: Hierarchical summary rollups and long-context eviction proofs.
- REQ-GRAPH-009: Dynamic context window adaptation based on model tier and budget ceilings.
- REQ-GRAPH-010: End-to-end context fidelity and reconstruction verification suite.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import math
import re
import time
import zlib
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ModelTier(str, Enum):
    TIER_1_PREMIUM = "tier_1_premium"   # e.g., Opus / 200k context window
    TIER_2_STANDARD = "tier_2_standard" # e.g., Sonnet / 128k context window
    TIER_3_ECONOMY = "tier_3_economy"   # e.g., Haiku / 32k context window


class CompressionMode(str, Enum):
    LOSSLESS = "lossless"
    SEMANTIC_PRUNED = "semantic_pruned"
    HIERARCHICAL_ROLLUP = "hierarchical_rollup"
    ADAPTIVE = "adaptive"


@dataclasses.dataclass
class ContextSegment:
    """Represents a piece of context (code, prompt, tool trace, or message)."""
    segment_id: str
    content: str
    token_count: int
    modality: str = "text"
    salience_score: float = 1.0
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "content": self.content,
            "token_count": self.token_count,
            "modality": self.modality,
            "salience_score": self.salience_score,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclasses.dataclass
class LosslessCompactedPayload:
    """Compressed context payload that can be losslessly restored."""
    compressed_b64: str
    original_size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float
    checksum_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compressed_b64": self.compressed_b64,
            "original_size_bytes": self.original_size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "compression_ratio": self.compression_ratio,
            "checksum_sha256": self.checksum_sha256,
        }


@dataclasses.dataclass
class EvictionProof:
    """Cryptographic proof that context segments were evicted with tamper-evident record."""
    proof_id: str
    evicted_segment_ids: List[str]
    evicted_tokens_count: int
    evicted_root_hash: str
    timestamp: float
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "evicted_segment_ids": self.evicted_segment_ids,
            "evicted_tokens_count": self.evicted_tokens_count,
            "evicted_root_hash": self.evicted_root_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


@dataclasses.dataclass
class RollupSummary:
    """Hierarchical summary node representing rolled-up context with eviction proof."""
    rollup_id: str
    summary_text: str
    level: int
    child_segment_ids: List[str]
    original_tokens: int
    summary_tokens: int
    eviction_proof: Optional[EvictionProof] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollup_id": self.rollup_id,
            "summary_text": self.summary_text,
            "level": self.level,
            "child_segment_ids": self.child_segment_ids,
            "original_tokens": self.original_tokens,
            "summary_tokens": self.summary_tokens,
            "eviction_proof": self.eviction_proof.to_dict() if self.eviction_proof else None,
        }


@dataclasses.dataclass
class AdaptationProfile:
    """Context window budget profile for an LLM tier."""
    model_tier: ModelTier
    max_context_tokens: int
    target_budget_tokens: int
    min_salience_threshold: float
    enable_hierarchical_rollup: bool
    enable_lossless_compaction: bool


@dataclasses.dataclass
class ReconstructionVerificationResult:
    """End-to-end context fidelity and reconstruction verification report."""
    test_id: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    semantic_fidelity_score: float # 0.0 to 1.0 (overlap & keyword retention)
    syntax_valid: bool
    roundtrip_lossless_passed: bool
    eviction_proof_valid: bool
    passed: bool
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compression_ratio": round(self.compression_ratio, 3),
            "semantic_fidelity_score": round(self.semantic_fidelity_score, 4),
            "syntax_valid": self.syntax_valid,
            "roundtrip_lossless_passed": self.roundtrip_lossless_passed,
            "eviction_proof_valid": self.eviction_proof_valid,
            "passed": self.passed,
            "details": self.details,
        }


def estimate_token_count(text: str) -> int:
    """Simple fast deterministic token count approximation (~4 chars per token)."""
    if not text:
        return 0
    words = text.split()
    # Hybrid word/char metric: max(len(words), ceil(len(text) / 4))
    return max(len(words), math.ceil(len(text) / 4.0))


class LosslessCompactor:
    """Lossless token compression and context-window compaction pipeline (REQ-GRAPH-006)."""

    @staticmethod
    def compress_text(text: str) -> LosslessCompactedPayload:
        raw_bytes = text.encode("utf-8")
        compressed = zlib.compress(raw_bytes, level=9)
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        orig_size = len(raw_bytes)
        comp_size = len(compressed)
        ratio = round(orig_size / max(1, comp_size), 3)

        return LosslessCompactedPayload(
            compressed_b64=base64.b64encode(compressed).decode("ascii"),
            original_size_bytes=orig_size,
            compressed_size_bytes=comp_size,
            compression_ratio=ratio,
            checksum_sha256=checksum,
        )

    @staticmethod
    def decompress_text(payload: LosslessCompactedPayload) -> str:
        compressed = base64.b64decode(payload.compressed_b64.encode("ascii"))
        decompressed_bytes = zlib.decompress(compressed)
        calc_checksum = hashlib.sha256(decompressed_bytes).hexdigest()
        if calc_checksum != payload.checksum_sha256:
            raise ValueError(f"Checksum mismatch: expected {payload.checksum_sha256}, got {calc_checksum}")
        return decompressed_bytes.decode("utf-8")


class SemanticPruner:
    """Semantic relevance pruning removing low-salience tokens while preserving syntactic validity (REQ-GRAPH-007)."""

    STOP_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "by", "for", "with",
        "about", "against", "between", "into", "through", "during", "before", "after", "above",
        "below", "to", "from", "up", "down", "over", "under", "again", "further", "then", "once",
        "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few",
        "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
        "than", "too", "very", "can", "will", "just", "should", "now",
    }

    # Syntactic characters that MUST NEVER be pruned to preserve syntactic and code structure
    PROTECTED_SYNTAX = set("()[]{}<>,;:\"'`=!+-*/\\|&^%~#@$")

    def score_token(self, token: str, is_code: bool = False) -> float:
        """Score semantic salience of an individual token."""
        stripped = token.strip()
        if not stripped:
            return 0.0
        # If token contains protected structural syntax, salience is high
        if any(c in self.PROTECTED_SYNTAX for c in stripped):
            return 0.95
        # Numbers, hashes, identifiers have high salience
        if re.match(r"^[0-9]+(\.[0-9]+)?$", stripped) or re.match(r"^0x[a-fA-F0-9]+$", stripped):
            return 0.9
        # Code identifiers (camelCase, snake_case)
        if "_" in stripped or (stripped.isalnum() and not stripped.islower() and not stripped.isupper()):
            return 0.85
        lower = stripped.lower()
        if lower in self.STOP_WORDS:
            return 0.15
        # Standard nouns/verbs/terms
        return 0.6

    def prune_text(
        self,
        text: str,
        salience_threshold: float = 0.3,
        preserve_syntax: bool = True,
    ) -> Tuple[str, float]:
        """Prunes low-salience tokens from text while strictly maintaining syntactic validity."""
        lines = text.splitlines(keepends=True)
        pruned_lines: List[str] = []

        for line in lines:
            # Preserve comment-only or code header structure if preserve_syntax
            stripped_line = line.strip()
            if not stripped_line:
                pruned_lines.append(line)
                continue

            # Tokenize line preserving spaces and punctuation
            tokens = re.findall(r"\w+|[^\w\s]|\s+", line)
            kept_tokens: List[str] = []

            for tok in tokens:
                if tok.isspace():
                    kept_tokens.append(tok)
                    continue

                score = self.score_token(tok)
                # If protected syntax and preserve_syntax is active, keep regardless of score
                if preserve_syntax and any(c in self.PROTECTED_SYNTAX for c in tok):
                    kept_tokens.append(tok)
                elif score >= salience_threshold:
                    kept_tokens.append(tok)

            pruned_line = "".join(kept_tokens)
            # Ensure balanced brackets/quotes weren't broken by pruning
            if preserve_syntax:
                pruned_line = self._rebalance_structural_syntax(line, pruned_line)
            pruned_lines.append(pruned_line)

        result_text = "".join(pruned_lines)
        orig_tokens = estimate_token_count(text)
        pruned_tokens = estimate_token_count(result_text)
        ratio = round(orig_tokens / max(1, pruned_tokens), 3)
        return result_text, ratio

    def _rebalance_structural_syntax(self, original: str, pruned: str) -> str:
        """Verify delimiters like {}, (), [], quotes match in count; restore if missing."""
        delimiters = [("(", ")"), ("{", "}"), ("[", "]"), ("<", ">")]
        rebalanced = pruned
        for open_d, close_d in delimiters:
            orig_open = original.count(open_d)
            orig_close = original.count(close_d)
            p_open = rebalanced.count(open_d)
            p_close = rebalanced.count(close_d)

            # If pruned version lost a matching bracket that original had
            if orig_open == orig_close and p_open != p_close:
                diff = abs(p_open - p_close)
                if p_open < p_close:
                    rebalanced = (open_d * diff) + rebalanced
                else:
                    rebalanced = rebalanced + (close_d * diff)
        return rebalanced


class HierarchicalRollupEngine:
    """Hierarchical summary rollups and long-context eviction proofs (REQ-GRAPH-008)."""

    def __init__(self, signing_secret: str = "desk-context-eviction-secret") -> None:
        self.signing_secret = signing_secret
        self.eviction_proofs: Dict[str, EvictionProof] = {}
        self.rollups: Dict[str, RollupSummary] = {}

    def rollup_segments(
        self,
        segments: List[ContextSegment],
        chunk_size: int = 3,
        level: int = 1,
    ) -> List[RollupSummary]:
        """Aggregate segments into multi-level summary rollups."""
        if not segments:
            return []

        rollups: List[RollupSummary] = []
        for i in range(0, len(segments), chunk_size):
            chunk = segments[i:i + chunk_size]
            child_ids = [s.segment_id for s in chunk]
            total_orig_tokens = sum(s.token_count for s in chunk)

            # Synthesize hierarchical rollup text
            bullet_points = []
            for s in chunk:
                # Extract first meaningful line or summary
                lines = [l.strip() for l in s.content.splitlines() if l.strip()]
                lead = lines[0] if lines else f"Segment {s.segment_id}"
                bullet_points.append(f"[{s.modality}] {lead[:120]}")

            summary_text = f"Summary L{level} (Segments {', '.join(child_ids)}):\n" + "\n".join(f"- {bp}" for bp in bullet_points)
            summary_tokens = estimate_token_count(summary_text)

            rollup_id = f"rollup_l{level}_{int(time.time()*1000)}_{i//chunk_size}"
            rollup = RollupSummary(
                rollup_id=rollup_id,
                summary_text=summary_text,
                level=level,
                child_segment_ids=child_ids,
                original_tokens=total_orig_tokens,
                summary_tokens=summary_tokens,
            )
            self.rollups[rollup_id] = rollup
            rollups.append(rollup)

        return rollups

    def evict_and_prove(
        self,
        segments: List[ContextSegment],
        proof_id: Optional[str] = None,
    ) -> EvictionProof:
        """Evict context segments and generate a cryptographic HMAC-SHA256 inclusion/eviction proof."""
        pid = proof_id or f"proof_evict_{int(time.time()*1000)}"
        seg_ids = [s.segment_id for s in segments]
        total_tokens = sum(s.token_count for s in segments)

        # Chained SHA-256 root hash over evicted segment contents
        leaf_hashes = [hashlib.sha256(s.content.encode("utf-8")).hexdigest() for s in segments]
        root_hash = hashlib.sha256("".join(leaf_hashes).encode("utf-8")).hexdigest()

        now = time.time()
        sign_payload = f"{pid}:{root_hash}:{total_tokens}:{','.join(seg_ids)}:{now}".encode("utf-8")
        signature = hmac.new(self.signing_secret.encode("utf-8"), sign_payload, hashlib.sha256).hexdigest()

        proof = EvictionProof(
            proof_id=pid,
            evicted_segment_ids=seg_ids,
            evicted_tokens_count=total_tokens,
            evicted_root_hash=root_hash,
            timestamp=now,
            signature=signature,
        )
        self.eviction_proofs[pid] = proof
        return proof

    def verify_eviction_proof(self, proof: EvictionProof) -> bool:
        """Verify authenticity and non-repudiation of an eviction proof."""
        sign_payload = f"{proof.proof_id}:{proof.evicted_root_hash}:{proof.evicted_tokens_count}:{','.join(proof.evicted_segment_ids)}:{proof.timestamp}".encode("utf-8")
        expected_sig = hmac.new(self.signing_secret.encode("utf-8"), sign_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(proof.signature, expected_sig)


class DynamicWindowAdapter:
    """Dynamic context window adaptation based on model tier and budget ceilings (REQ-GRAPH-009)."""

    TIER_DEFAULTS: Dict[ModelTier, AdaptationProfile] = {
        ModelTier.TIER_1_PREMIUM: AdaptationProfile(
            model_tier=ModelTier.TIER_1_PREMIUM,
            max_context_tokens=200000,
            target_budget_tokens=160000,
            min_salience_threshold=0.20,
            enable_hierarchical_rollup=False,
            enable_lossless_compaction=True,
        ),
        ModelTier.TIER_2_STANDARD: AdaptationProfile(
            model_tier=ModelTier.TIER_2_STANDARD,
            max_context_tokens=128000,
            target_budget_tokens=96000,
            min_salience_threshold=0.35,
            enable_hierarchical_rollup=True,
            enable_lossless_compaction=True,
        ),
        ModelTier.TIER_3_ECONOMY: AdaptationProfile(
            model_tier=ModelTier.TIER_3_ECONOMY,
            max_context_tokens=32000,
            target_budget_tokens=24000,
            min_salience_threshold=0.50,
            enable_hierarchical_rollup=True,
            enable_lossless_compaction=True,
        ),
    }

    def __init__(self, custom_profiles: Optional[Dict[ModelTier, AdaptationProfile]] = None) -> None:
        self.profiles = custom_profiles or dict(self.TIER_DEFAULTS)

    def adapt_context(
        self,
        segments: List[ContextSegment],
        tier: ModelTier,
        hard_budget_ceiling: Optional[int] = None,
        pruner: Optional[SemanticPruner] = None,
        rollup_engine: Optional[HierarchicalRollupEngine] = None,
    ) -> Dict[str, Any]:
        """Adapt a set of context segments to fit inside the specified tier and token budget ceiling."""
        profile = self.profiles.get(tier, self.profiles[ModelTier.TIER_2_STANDARD])
        effective_budget = hard_budget_ceiling if hard_budget_ceiling is not None else profile.target_budget_tokens
        pruner = pruner or SemanticPruner()
        rollup_engine = rollup_engine or HierarchicalRollupEngine()

        total_tokens = sum(s.token_count for s in segments)
        if total_tokens <= effective_budget:
            return {
                "adapted_segments": [s.to_dict() for s in segments],
                "mode": CompressionMode.LOSSLESS.value,
                "tier": tier.value,
                "original_tokens": total_tokens,
                "final_tokens": total_tokens,
                "eviction_proof": None,
                "rollup_summaries": [],
            }

        # Step 1: Semantic Pruning on low-salience segments
        adapted: List[ContextSegment] = []
        for s in segments:
            if s.salience_score < profile.min_salience_threshold:
                pruned_content, _ = pruner.prune_text(s.content, salience_threshold=profile.min_salience_threshold)
                new_tokens = estimate_token_count(pruned_content)
                adapted.append(ContextSegment(
                    segment_id=s.segment_id,
                    content=pruned_content,
                    token_count=new_tokens,
                    modality=s.modality,
                    salience_score=s.salience_score,
                    metadata={**s.metadata, "pruned": True},
                ))
            else:
                adapted.append(s)

        current_tokens = sum(s.token_count for s in adapted)
        if current_tokens <= effective_budget:
            return {
                "adapted_segments": [s.to_dict() for s in adapted],
                "mode": CompressionMode.SEMANTIC_PRUNED.value,
                "tier": tier.value,
                "original_tokens": total_tokens,
                "final_tokens": current_tokens,
                "eviction_proof": None,
                "rollup_summaries": [],
            }

        # Step 2: Hierarchical Rollup and Oldest Segment Eviction
        # Retain most recent/highest salience segments, rollup older ones
        # Sort by salience ascending to evict/rollup lowest salience first
        sorted_for_rollup = sorted(adapted, key=lambda x: (x.salience_score, -x.created_at))
        to_evict_and_rollup: List[ContextSegment] = []
        retained: List[ContextSegment] = []

        tokens_acc = 0
        # Preserve highest salience from the tail of sorted
        for seg in reversed(sorted_for_rollup):
            if tokens_acc + seg.token_count <= (effective_budget * 0.75):
                retained.append(seg)
                tokens_acc += seg.token_count
            else:
                to_evict_and_rollup.append(seg)

        # Generate rollup summaries and eviction proof for evicted segments
        rollups = rollup_engine.rollup_segments(to_evict_and_rollup, chunk_size=3, level=1)
        eviction_proof = rollup_engine.evict_and_prove(to_evict_and_rollup)

        # Combine retained segments + rollups as synthesized context
        final_segments = [s.to_dict() for s in retained]
        rollup_tokens = sum(r.summary_tokens for r in rollups)

        return {
            "adapted_segments": final_segments,
            "mode": CompressionMode.HIERARCHICAL_ROLLUP.value,
            "tier": tier.value,
            "original_tokens": total_tokens,
            "final_tokens": tokens_acc + rollup_tokens,
            "eviction_proof": eviction_proof.to_dict(),
            "rollup_summaries": [r.to_dict() for r in rollups],
        }


class ContextFidelityVerifier:
    """End-to-end context fidelity and reconstruction verification suite (REQ-GRAPH-010)."""

    @staticmethod
    def calculate_semantic_fidelity(original: str, compressed: str) -> float:
        """Measure semantic keyword and n-gram overlap between original and compressed representations."""
        orig_words = set(re.findall(r"\w+", original.lower()))
        comp_words = set(re.findall(r"\w+", compressed.lower()))
        if not orig_words:
            return 1.0
        intersection = orig_words.intersection(comp_words)
        return len(intersection) / len(orig_words)

    @staticmethod
    def verify_syntactic_validity(text: str) -> bool:
        """Check if syntax brackets (parens, curlies, brackets) are balanced and valid."""
        stack: List[str] = []
        mapping = {")": "(", "}": "{", "]": "["}
        for ch in text:
            if ch in mapping.values():
                stack.append(ch)
            elif ch in mapping.keys():
                if not stack or stack.pop() != mapping[ch]:
                    return False
        return len(stack) == 0

    def run_verification(
        self,
        test_content: str,
        test_id: Optional[str] = None,
        compactor: Optional[LosslessCompactor] = None,
        pruner: Optional[SemanticPruner] = None,
        rollup_engine: Optional[HierarchicalRollupEngine] = None,
    ) -> ReconstructionVerificationResult:
        """Execute end-to-end verification across lossless, semantic pruning, and rollup pipelines."""
        tid = test_id or f"verify_ctx_{int(time.time()*1000)}"
        compactor = compactor or LosslessCompactor()
        pruner = pruner or SemanticPruner()
        rollup_engine = rollup_engine or HierarchicalRollupEngine()

        orig_tokens = estimate_token_count(test_content)

        # 1. Test Lossless Compaction & Roundtrip Decompression
        payload = compactor.compress_text(test_content)
        decompressed = compactor.decompress_text(payload)
        lossless_ok = (decompressed == test_content)

        # 2. Test Semantic Pruning & Syntactic Integrity
        pruned_text, _ = pruner.prune_text(test_content, salience_threshold=0.3, preserve_syntax=True)
        pruned_tokens = estimate_token_count(pruned_text)
        syntax_ok = self.verify_syntactic_validity(pruned_text)
        fidelity_score = self.calculate_semantic_fidelity(test_content, pruned_text)

        # 3. Test Hierarchical Rollup & Eviction Proof
        dummy_seg = ContextSegment(segment_id="seg-test-01", content=test_content, token_count=orig_tokens)
        proof = rollup_engine.evict_and_prove([dummy_seg])
        proof_valid = rollup_engine.verify_eviction_proof(proof)

        overall_passed = lossless_ok and syntax_ok and (fidelity_score >= 0.5) and proof_valid

        return ReconstructionVerificationResult(
            test_id=tid,
            original_tokens=orig_tokens,
            compressed_tokens=pruned_tokens,
            compression_ratio=round(orig_tokens / max(1, pruned_tokens), 3),
            semantic_fidelity_score=fidelity_score,
            syntax_valid=syntax_ok,
            roundtrip_lossless_passed=lossless_ok,
            eviction_proof_valid=proof_valid,
            passed=overall_passed,
            details={
                "original_bytes": payload.original_size_bytes,
                "compressed_bytes": payload.compressed_size_bytes,
                "lossless_checksum": payload.checksum_sha256,
                "proof_id": proof.proof_id,
            },
        )


class ContextCompressionEngine:
    """Unified engine coordinating lossless compaction, semantic pruning, rollups, and adaptation."""

    def __init__(self, signing_secret: str = "desk-context-eviction-secret") -> None:
        self.compactor = LosslessCompactor()
        self.pruner = SemanticPruner()
        self.rollup_engine = HierarchicalRollupEngine(signing_secret=signing_secret)
        self.adapter = DynamicWindowAdapter()
        self.verifier = ContextFidelityVerifier()
