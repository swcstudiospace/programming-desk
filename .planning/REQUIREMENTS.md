# Requirements: Milestone v4.5 — Autonomous Multi-Agent Neuro-Symbolic Reasoning & Causal Inference Mesh

This document defines the requirements for Milestone v4.5 of Programming Desk.

## 1. Neuro-Symbolic Logic Graph & First-Order Predicate Synthesis (Phase 56)

- [x] **REQ-NS-001**: First-Order Predicate & Horn Clause Rule Engine (`FirstOrderLogicEngine`, `SymbolicRule`, `Predicate`) supporting forward-chaining deduction, backward-chaining queries, and automated resolution refutation over grounded facts.
- [x] **REQ-NS-002**: Neuro-Symbolic Knowledge Graph (`NeuroSymbolicGraph`, `ConceptNode`, `RelationEdge`) binding vector embeddings with discrete logical entities, supporting fuzzy truth valuations in \([0.0, 1.0]\) and semantic similarity retrieval.
- [x] **REQ-NS-003**: Swarm Logical Invariant Checker (`LogicalInvariantChecker`) verifying execution invariants and safety policies against proposed tool invocations and state mutations, aborting invalid state transitions.
- [x] **REQ-NS-004**: Neural-to-Symbolic Rule Extractor (`RuleExtractionEngine`) translating observed agent execution traces and neural completions into formalized first-order Horn rules with confidence scores.
- [x] **REQ-NS-005**: Neuro-Symbolic REST API endpoints under `/v1/neuro-symbolic/*` exposing rule registration, deduction forward-chaining, concept graph indexing, and invariant evaluation.

## 2. Causal DAG Discovery, Do-Calculus Interventions & Counterfactual Mesh (Phase 57)

- [x] **REQ-NS-006**: Causal Directed Acyclic Graph (DAG) Representation (`CausalDAG`, `CausalVariable`, `CausalEdge`) with topological cycle rejection and d-separation path conditional independence analysis.
- [x] **REQ-NS-007**: Constraint-Based Causal Discovery Engine (`ConstraintCausalDiscovery`) inferring causal skeletons and edge orientations from observational data matrix traces using conditional independence tests.
- [x] **REQ-NS-008**: Pearl's Do-Calculus Interventional Engine (`DoCalculusEngine`) simulating causal interventions \(P(Y | do(X = x))\) via graph mutilation, backdoor adjustment set identification, and interventional expectation computation.
- [x] **REQ-NS-009**: Counterfactual Reasoning Simulator (`CounterfactualSimulator`) implementing structural causal model (SCM) abduction, action, and prediction for hypothetical counterfactual queries ("What if action A was taken instead of B?").
- [x] **REQ-NS-010**: Causal Anchor & Proof Exporter (`CausalAnchorExporter`) producing HMAC-SHA256 causal receipts, constructing Merkle proof roots, and exporting anchors to Solana devnet targets.
- [x] **REQ-NS-011**: End-to-End Neuro-Symbolic & Causal Mesh Drill Simulator (`NeuroSymbolicCausalDrillSimulator`) verifying Horn deduction, invariant enforcement, d-separation, do-calculus adjustment, counterfactual simulation, and Solana devnet anchoring.
- [x] **REQ-NS-012**: Causal REST API endpoints under `/v1/causal/*` and `/v1/neuro-symbolic/drill/simulate` exposing DAG compilation, causal discovery, interventional evaluation, counterfactual queries, and drill executions.
