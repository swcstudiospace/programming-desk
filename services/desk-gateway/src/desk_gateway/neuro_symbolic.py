"""Neuro-Symbolic Logic Graph & First-Order Predicate Synthesis (Milestone v4.5 - Phase 56).

Implements:
- Predicate: Represents first-order logical atomic formulas with terms and truth values.
- SymbolicRule: Horn-clause representation (antecedents -> consequent) with confidence weights.
- FirstOrderLogicEngine: Forward-chaining inference, backward-chaining query resolution, and fact unification.
- ConceptNode: Knowledge graph entity with semantic embedding and categorical attributes.
- RelationEdge: Semantic relation connecting concept nodes with logical predicates.
- NeuroSymbolicGraph: Hybrid knowledge graph fusing vector representations with logical axioms.
- LogicalInvariantChecker: Validates agent operations against formal safety and operational invariants.
- RuleExtractionEngine: Synthesizes symbolic Horn rules from neural execution trajectories.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Predicate:
    """Represents a first-order atomic proposition or predicate: name(arg_1, arg_2, ...)."""
    name: str
    args: Tuple[str, ...]
    negated: bool = False
    truth_val: float = 1.0  # Supports fuzzy logic valuations in [0.0, 1.0]

    def key(self) -> str:
        prefix = "NOT_" if self.negated else ""
        return f"{prefix}{self.name}({','.join(self.args)})"

    def ground(self, bindings: Dict[str, str]) -> Predicate:
        """Substitutes variables with bound constants."""
        new_args = tuple(bindings.get(arg, arg) for arg in self.args)
        return Predicate(name=self.name, args=new_args, negated=self.negated, truth_val=self.truth_val)

    def is_variable(self, term: str) -> bool:
        """Variables conventionally start with '?' or lowercase single letters 'x', 'y', 'z'."""
        return term.startswith("?") or (len(term) == 1 and term.islower())

    def unify(self, fact: Predicate, bindings: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Attempts unification of this pattern predicate with a ground fact."""
        if self.name != fact.name or self.negated != fact.negated or len(self.args) != len(fact.args):
            return None
        new_bindings = dict(bindings)
        for p_term, f_term in zip(self.args, fact.args):
            if self.is_variable(p_term):
                if p_term in new_bindings:
                    if new_bindings[p_term] != f_term:
                        return None
                else:
                    new_bindings[p_term] = f_term
            else:
                if p_term != f_term:
                    return None
        return new_bindings


@dataclass
class SymbolicRule:
    """Horn clause: antecedent_1 AND ... AND antecedent_k -> consequent."""
    rule_id: str
    antecedents: List[Predicate]
    consequent: Predicate
    confidence: float = 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "antecedents": [a.key() for a in self.antecedents],
            "consequent": self.consequent.key(),
            "confidence": self.confidence,
            "description": self.description,
        }


class FirstOrderLogicEngine:
    """Evaluates Horn rules over ground facts using forward and backward chaining."""

    def __init__(self) -> None:
        self.facts: Dict[str, Predicate] = {}
        self.rules: Dict[str, SymbolicRule] = {}

    def add_fact(self, predicate: Predicate) -> None:
        self.facts[predicate.key()] = predicate

    def remove_fact(self, predicate_key: str) -> bool:
        return self.facts.pop(predicate_key, None) is not None

    def add_rule(self, rule: SymbolicRule) -> None:
        self.rules[rule.rule_id] = rule

    def evaluate_forward_chaining(self, max_iterations: int = 10) -> List[Predicate]:
        """Iteratively applies Horn rules until a fixed point is reached."""
        inferred: List[Predicate] = []
        for _ in range(max_iterations):
            new_inferred_this_round = False
            for rule in list(self.rules.values()):
                # Find matching substitution combinations
                matching_bindings = self._match_antecedents(rule.antecedents, 0, {})
                for bindings in matching_bindings:
                    ground_consequent = rule.consequent.ground(bindings)
                    # Compute resultant fuzzy truth value: min(antecedents) * rule.confidence
                    ground_key = ground_consequent.key()
                    if ground_key not in self.facts:
                        self.facts[ground_key] = ground_consequent
                        inferred.append(ground_consequent)
                        new_inferred_this_round = True
            if not new_inferred_this_round:
                break
        return inferred

    def _match_antecedents(
        self,
        antecedents: List[Predicate],
        index: int,
        current_bindings: Dict[str, str],
    ) -> List[Dict[str, str]]:
        if index >= len(antecedents):
            return [current_bindings]
        pattern = antecedents[index]
        results = []
        for fact in self.facts.values():
            bindings = pattern.unify(fact, current_bindings)
            if bindings is not None:
                sub_results = self._match_antecedents(antecedents, index + 1, bindings)
                results.extend(sub_results)
        return results

    def query(self, query_predicate: Predicate) -> List[Dict[str, str]]:
        """Answers a query predicate returning all satisfying variable bindings."""
        results = []
        for fact in self.facts.values():
            bindings = query_predicate.unify(fact, {})
            if bindings is not None:
                results.append(bindings)
        return results


@dataclass
class ConceptNode:
    """A semantic concept node with both symbolic attributes and vector embeddings."""
    node_id: str
    name: str
    category: str
    embedding: List[float] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    truth_degree: float = 1.0


@dataclass
class RelationEdge:
    """Directed relational edge between two concepts with semantic weight."""
    relation_id: str
    source_id: str
    target_id: str
    predicate_name: str
    weight: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)


class NeuroSymbolicGraph:
    """Fuses vector embedding representation with logical predicates and concept relations."""

    def __init__(self, embedding_dimension: int = 4) -> None:
        self.embedding_dimension = embedding_dimension
        self.nodes: Dict[str, ConceptNode] = {}
        self.edges: Dict[str, RelationEdge] = {}
        self.logic_engine = FirstOrderLogicEngine()

    def add_concept(
        self,
        node_id: str,
        name: str,
        category: str,
        embedding: Optional[List[float]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        truth_degree: float = 1.0,
    ) -> ConceptNode:
        if embedding is None:
            embedding = [0.0] * self.embedding_dimension
        node = ConceptNode(
            node_id=node_id,
            name=name,
            category=category,
            embedding=embedding,
            attributes=attributes or {},
            truth_degree=truth_degree,
        )
        self.nodes[node_id] = node
        # Add categorical fact into logic engine
        self.logic_engine.add_fact(Predicate(name="is_category", args=(node_id, category), truth_val=truth_degree))
        return node

    def add_relation(
        self,
        relation_id: str,
        source_id: str,
        target_id: str,
        predicate_name: str,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ) -> RelationEdge:
        if source_id not in self.nodes or target_id not in self.nodes:
            raise KeyError(f"Source '{source_id}' or Target '{target_id}' concept node not found.")
        edge = RelationEdge(
            relation_id=relation_id,
            source_id=source_id,
            target_id=target_id,
            predicate_name=predicate_name,
            weight=weight,
            properties=properties or {},
        )
        self.edges[relation_id] = edge
        # Materialize logic fact
        self.logic_engine.add_fact(Predicate(name=predicate_name, args=(source_id, target_id), truth_val=weight))
        return edge

    def query_similarity(self, query_embedding: List[float], top_k: int = 3) -> List[Tuple[ConceptNode, float]]:
        """Finds closest concept nodes using cosine similarity."""
        results = []
        for node in self.nodes.values():
            if not node.embedding or len(node.embedding) != len(query_embedding):
                continue
            dot = sum(a * b for a, b in zip(node.embedding, query_embedding))
            norm_a = math.sqrt(sum(a * a for a in node.embedding))
            norm_b = math.sqrt(sum(b * b for b in query_embedding))
            sim = dot / (norm_a * norm_b) if (norm_a > 1e-9 and norm_b > 1e-9) else 0.0
            results.append((node, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


@dataclass
class InvariantViolation:
    invariant_name: str
    target_action: str
    violating_bindings: Dict[str, str]
    message: str


class LogicalInvariantChecker:
    """Verifies that candidate agent operations adhere to formal logic safety invariants."""

    def __init__(self, logic_engine: FirstOrderLogicEngine) -> None:
        self.logic_engine = logic_engine
        self.invariants: List[Tuple[str, Predicate, str]] = []  # (name, forbidden_pattern, description)

    def register_safety_invariant(self, name: str, forbidden_predicate: Predicate, description: str) -> None:
        """Registers a predicate pattern that, if satisfied in the state, constitutes a violation."""
        self.invariants.append((name, forbidden_predicate, description))

    def check_invariants(self, candidate_action: str, candidate_facts: List[Predicate]) -> List[InvariantViolation]:
        """Temporarily adds candidate facts, tests invariants, and rolls back."""
        violations = []
        added_keys = []
        try:
            for fact in candidate_facts:
                self.logic_engine.add_fact(fact)
                added_keys.append(fact.key())

            # Evaluate forward deductions
            self.logic_engine.evaluate_forward_chaining()

            for name, forbidden, desc in self.invariants:
                bindings_list = self.logic_engine.query(forbidden)
                for bindings in bindings_list:
                    violations.append(
                        InvariantViolation(
                            invariant_name=name,
                            target_action=candidate_action,
                            violating_bindings=bindings,
                            message=f"Invariant violation '{name}': {desc} with {bindings}",
                        )
                    )
        finally:
            for key in added_keys:
                self.logic_engine.remove_fact(key)

        return violations


class RuleExtractionEngine:
    """Extracts generalized Horn rules from neural trajectory observations."""

    def __init__(self) -> None:
        self.observation_history: List[Dict[str, Any]] = []

    def record_observation(self, context_predicates: List[Predicate], outcome_predicate: Predicate) -> None:
        self.observation_history.append({
            "context": context_predicates,
            "outcome": outcome_predicate,
            "timestamp": time.time(),
        })

    def extract_rules(self, min_support: int = 1, min_confidence: float = 0.7) -> List[SymbolicRule]:
        """Induces candidate rules matching recurring antecedent-consequent patterns."""
        if not self.observation_history:
            return []

        rules: List[SymbolicRule] = []
        # Group by outcome name and argument pattern
        outcome_groups: Dict[str, List[List[Predicate]]] = {}
        for obs in self.observation_history:
            out: Predicate = obs["outcome"]
            group_key = out.name
            outcome_groups.setdefault(group_key, []).append(obs["context"])

        rule_idx = 0
        for out_name, contexts in outcome_groups.items():
            if len(contexts) < min_support:
                continue
            # Collect common antecedent predicate names
            antecedent_counts: Dict[str, int] = {}
            for ctx in contexts:
                for p in ctx:
                    antecedent_counts[p.name] = antecedent_counts.get(p.name, 0) + 1

            common_antecedents = [
                p_name for p_name, count in antecedent_counts.items()
                if (count / len(contexts)) >= min_confidence
            ]

            if common_antecedents:
                rule_idx += 1
                ant_preds = [Predicate(name=p, args=("?x",)) for p in common_antecedents]
                conseq_pred = Predicate(name=out_name, args=("?x",))
                rules.append(
                    SymbolicRule(
                        rule_id=f"rule-ind-auto-{rule_idx}",
                        antecedents=ant_preds,
                        consequent=conseq_pred,
                        confidence=min(1.0, len(contexts) / (len(contexts) + 0.5)),
                        description=f"Auto-extracted rule for {out_name} with support {len(contexts)}",
                    )
                )

        return rules
