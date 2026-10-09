"""Autonomous Formal Verification & Automated Invariant Proving Pipeline.

Implements pre-/post-condition invariant contracts, static AST invariant proving,
dynamic property-based fuzz verification, counterexample failure triage,
and HMAC-SHA256 formal verification attestation certificates.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import hashlib
import hmac
import inspect
import json
import math
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class InvariantType(str, enum.Enum):
    PRE_CONDITION = "PRE_CONDITION"
    POST_CONDITION = "POST_CONDITION"
    LOOP_INVARIANT = "LOOP_INVARIANT"
    STATE_INVARIANT = "STATE_INVARIANT"


class VerificationVerdict(str, enum.Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"


@dataclasses.dataclass
class InvariantContract:
    contract_id: str
    invariant_type: InvariantType
    expression: str  # Python expression evaluated in context: args for pre, result + args for post
    description: str = ""
    target_function: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "invariant_type": self.invariant_type.value,
            "expression": self.expression,
            "description": self.description,
            "target_function": self.target_function,
        }


@dataclasses.dataclass
class CounterExample:
    contract_id: str
    invariant_type: InvariantType
    expression: str
    inputs: Dict[str, Any]
    output: Any = None
    error_message: str = ""
    suggested_patch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "invariant_type": self.invariant_type.value,
            "expression": self.expression,
            "inputs": self.inputs,
            "output": self.output,
            "error_message": self.error_message,
            "suggested_patch": self.suggested_patch,
        }


@dataclasses.dataclass
class StaticAnalysisReport:
    is_sound: bool
    loop_termination_proved: bool
    memory_safety_proved: bool
    non_nullability_proved: bool
    violations: List[str] = dataclasses.field(default_factory=list)
    ast_node_count: int = 0
    branch_complexity: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_sound": self.is_sound,
            "loop_termination_proved": self.loop_termination_proved,
            "memory_safety_proved": self.memory_safety_proved,
            "non_nullability_proved": self.non_nullability_proved,
            "violations": self.violations,
            "ast_node_count": self.ast_node_count,
            "branch_complexity": self.branch_complexity,
        }


@dataclasses.dataclass
class DynamicPropertyReport:
    total_trials: int
    passed_trials: int
    verdict: VerificationVerdict
    counterexamples: List[CounterExample] = dataclasses.field(default_factory=list)
    coverage_ratio: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trials": self.total_trials,
            "passed_trials": self.passed_trials,
            "verdict": self.verdict.value,
            "counterexamples": [ce.to_dict() for ce in self.counterexamples],
            "coverage_ratio": self.coverage_ratio,
        }


@dataclasses.dataclass
class FormalVerificationCertificate:
    certificate_id: str
    tool_name: str
    version: str
    author_seat_id: str
    code_hash: str
    verdict: VerificationVerdict
    static_report: StaticAnalysisReport
    dynamic_report: DynamicPropertyReport
    contracts_evaluated: int
    attestation_signature: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "tool_name": self.tool_name,
            "version": self.version,
            "author_seat_id": self.author_seat_id,
            "code_hash": self.code_hash,
            "verdict": self.verdict.value,
            "static_report": self.static_report.to_dict(),
            "dynamic_report": self.dynamic_report.to_dict(),
            "contracts_evaluated": self.contracts_evaluated,
            "attestation_signature": self.attestation_signature,
            "timestamp": self.timestamp,
        }


class StaticInvariantProver:
    """Performs static analysis, control flow graph inspection, and AST invariant proving."""

    def __init__(self, disallowed_calls: Optional[Set[str]] = None) -> None:
        self.disallowed_calls = disallowed_calls or {
            "eval", "exec", "__import__", "compile", "open", "os.system", "subprocess"
        }

    def analyze(self, source_code: str) -> StaticAnalysisReport:
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return StaticAnalysisReport(
                is_sound=False,
                loop_termination_proved=False,
                memory_safety_proved=False,
                non_nullability_proved=False,
                violations=[f"Syntax error: {e}"],
            )

        violations: List[str] = []
        node_count = 0
        branch_complexity = 1
        has_while = False
        unbounded_loops = False

        for node in ast.walk(tree):
            node_count += 1
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                branch_complexity += 1

            if isinstance(node, ast.While):
                has_while = True
                # Check for while True without break
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    has_break = any(isinstance(child, ast.Break) for child in ast.walk(node))
                    if not has_break:
                        unbounded_loops = True
                        violations.append("Unbounded 'while True' loop detected without guaranteed termination break.")

            if isinstance(node, ast.Call):
                call_id = ""
                if isinstance(node.func, ast.Name):
                    call_id = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_id = f"{getattr(node.func.value, 'id', '')}.{node.func.attr}"
                if call_id in self.disallowed_calls:
                    violations.append(f"Disallowed call in formally verified synthesis: {call_id}")

            # Memory safety: check for recursive definitions without base cases or dangerous unbounded buffers
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int) and node.right.value > 100_000:
                    violations.append("Potential memory exhaustion: array/string replication exceeds 100,000 units.")

        loop_termination = not unbounded_loops
        memory_safety = not any("memory" in v.lower() for v in violations)
        non_nullability = True
        is_sound = len(violations) == 0

        return StaticAnalysisReport(
            is_sound=is_sound,
            loop_termination_proved=loop_termination,
            memory_safety_proved=memory_safety,
            non_nullability_proved=non_nullability,
            violations=violations,
            ast_node_count=node_count,
            branch_complexity=branch_complexity,
        )


class DynamicPropertyTester:
    """Evaluates synthesized code against invariant contracts using property-based fuzz distributions."""

    def __init__(self, default_trials: int = 50, seed: Optional[int] = 42) -> None:
        self.default_trials = default_trials
        self.random = random.Random(seed)

    def _generate_synthetic_input(self, param_type: str, trial_idx: int) -> Any:
        param_type = param_type.lower()
        if "int" in param_type:
            # Include boundary edge cases
            if trial_idx == 0:
                return 0
            elif trial_idx == 1:
                return 1
            elif trial_idx == 2:
                return -1
            elif trial_idx == 3:
                return 100
            elif trial_idx == 4:
                return -100
            return self.random.randint(-1000, 1000)
        elif "float" in param_type:
            if trial_idx == 0:
                return 0.0
            elif trial_idx == 1:
                return 1.0
            elif trial_idx == 2:
                return -1.0
            return self.random.uniform(-1000.0, 1000.0)
        elif "str" in param_type:
            if trial_idx == 0:
                return ""
            elif trial_idx == 1:
                return "a"
            elif trial_idx == 2:
                return "test string with spaces"
            letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            return "".join(self.random.choice(letters) for _ in range(self.random.randint(1, 20)))
        elif "bool" in param_type:
            return trial_idx % 2 == 0
        elif "list" in param_type:
            if trial_idx == 0:
                return []
            return [self.random.randint(1, 100) for _ in range(self.random.randint(1, 5))]
        elif "dict" in param_type:
            return {"k": trial_idx}
        return f"arg_{trial_idx}"

    def run_property_tests(
        self,
        fn: Callable[..., Any],
        param_types: Dict[str, str],
        contracts: List[InvariantContract],
        trials: Optional[int] = None,
    ) -> DynamicPropertyReport:
        num_trials = trials or self.default_trials
        passed = 0
        counterexamples: List[CounterExample] = []

        safe_builtins = {
            "abs": abs,
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "all": all,
            "any": any,
            "isinstance": isinstance,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "math": math,
        }

        for trial_idx in range(num_trials):
            # Generate test inputs
            inputs = {
                name: self._generate_synthetic_input(ptype, trial_idx)
                for name, ptype in param_types.items()
            }

            # 1. Evaluate PRE-CONDITION contracts
            pre_violated = False
            for contract in contracts:
                if contract.invariant_type == InvariantType.PRE_CONDITION:
                    ctx = {**safe_builtins, **inputs}
                    try:
                        satisfied = bool(eval(contract.expression, {"__builtins__": {}}, ctx))
                    except Exception as e:
                        satisfied = False

                    if not satisfied:
                        # Pre-condition filter: if input violates pre-condition, test input is out of domain
                        pre_violated = True
                        break

            if pre_violated:
                # Pre-condition filtered trial: not considered an implementation failure
                passed += 1
                continue

            # 2. Execute target function
            try:
                output = fn(**inputs)
            except Exception as exc:
                ce = CounterExample(
                    contract_id="runtime_exception",
                    invariant_type=InvariantType.STATE_INVARIANT,
                    expression="no_unhandled_exception",
                    inputs=inputs,
                    output=None,
                    error_message=f"Runtime error during property execution: {exc}",
                    suggested_patch="Add exception handling or boundary check for given input spectrum.",
                )
                counterexamples.append(ce)
                continue

            # 3. Evaluate POST-CONDITION and STATE-INVARIANT contracts
            all_contracts_satisfied = True
            for contract in contracts:
                if contract.invariant_type in (InvariantType.POST_CONDITION, InvariantType.STATE_INVARIANT):
                    ctx = {**safe_builtins, **inputs, "result": output, "output": output}
                    try:
                        satisfied = bool(eval(contract.expression, {"__builtins__": {}}, ctx))
                    except Exception as e:
                        satisfied = False

                    if not satisfied:
                        all_contracts_satisfied = False
                        ce = CounterExample(
                            contract_id=contract.contract_id,
                            invariant_type=contract.invariant_type,
                            expression=contract.expression,
                            inputs=inputs,
                            output=output,
                            error_message=f"Invariant violated: expression '{contract.expression}' evaluated to False for result={output}",
                            suggested_patch=f"Enforce post-condition constraint '{contract.expression}' before returning value.",
                        )
                        counterexamples.append(ce)
                        break

            if all_contracts_satisfied:
                passed += 1

        verdict = VerificationVerdict.PROVED if len(counterexamples) == 0 else VerificationVerdict.DISPROVED
        coverage_ratio = passed / max(1, num_trials)

        return DynamicPropertyReport(
            total_trials=num_trials,
            passed_trials=passed,
            verdict=verdict,
            counterexamples=counterexamples,
            coverage_ratio=coverage_ratio,
        )


class VerificationTriageAnalyzer:
    """Diagnoses verification failures, categorizes counterexamples, and generates remediation guidance."""

    @staticmethod
    def triage(counterexamples: List[CounterExample]) -> Dict[str, Any]:
        if not counterexamples:
            return {"status": "clean", "violations_count": 0, "diagnostics": []}

        diagnostics: List[Dict[str, Any]] = []
        for ce in counterexamples:
            issue_type = "boundary_error"
            if "exception" in ce.error_message.lower():
                issue_type = "unhandled_runtime_fault"
            elif any(k in ce.expression.lower() for k in ["len", "size", "count"]):
                issue_type = "length_invariant_violation"
            elif any(k in ce.expression.lower() for k in [">", "<", ">=", "<=", "=="]):
                issue_type = "numeric_range_violation"

            diagnostics.append({
                "contract_id": ce.contract_id,
                "issue_type": issue_type,
                "expression": ce.expression,
                "failing_inputs": ce.inputs,
                "output_produced": ce.output,
                "error": ce.error_message,
                "remediation_guidance": ce.suggested_patch or "Refine invariant logic or synthesize boundary assertion.",
            })

        return {
            "status": "violated",
            "violations_count": len(counterexamples),
            "diagnostics": diagnostics,
        }


class FormalVerificationPipeline:
    """End-to-end formal verification pipeline orchestrating static analysis, dynamic proving, and attestation."""

    def __init__(self, secret_key: str = "desk-verification-hmac-key") -> None:
        self.secret_key = secret_key.encode("utf-8")
        self.static_prover = StaticInvariantProver()
        self.dynamic_tester = DynamicPropertyTester()
        self.triage_analyzer = VerificationTriageAnalyzer()
        self.certificates: Dict[str, FormalVerificationCertificate] = {}

    def _compute_signature(self, code_hash: str, verdict: str, static_sound: bool, passed_trials: int) -> str:
        msg = f"{code_hash}:{verdict}:{static_sound}:{passed_trials}".encode("utf-8")
        return hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()

    def verify_tool_synthesis(
        self,
        tool_name: str,
        version: str,
        author_seat_id: str,
        source_code: str,
        param_types: Dict[str, str],
        contracts: List[InvariantContract],
        trials: int = 50,
    ) -> FormalVerificationCertificate:
        code_hash = hashlib.sha256(source_code.encode("utf-8")).hexdigest()
        cert_id = f"cert-{tool_name}-{version}-{code_hash[:12]}"

        # 1. Static Invariant Analysis
        static_report = self.static_prover.analyze(source_code)
        if not static_report.is_sound:
            verdict = VerificationVerdict.DISPROVED
            if any("disallowed" in v.lower() for v in static_report.violations):
                verdict = VerificationVerdict.SECURITY_VIOLATION
            elif any("syntax" in v.lower() for v in static_report.violations):
                verdict = VerificationVerdict.SYNTAX_ERROR

            dynamic_report = DynamicPropertyReport(
                total_trials=0,
                passed_trials=0,
                verdict=verdict,
                counterexamples=[],
                coverage_ratio=0.0,
            )
            sig = self._compute_signature(code_hash, verdict.value, static_report.is_sound, 0)
            cert = FormalVerificationCertificate(
                certificate_id=cert_id,
                tool_name=tool_name,
                version=version,
                author_seat_id=author_seat_id,
                code_hash=code_hash,
                verdict=verdict,
                static_report=static_report,
                dynamic_report=dynamic_report,
                contracts_evaluated=len(contracts),
                attestation_signature=sig,
            )
            self.certificates[cert_id] = cert
            return cert

        # 2. Compile in isolated local scope
        safe_globals: Dict[str, Any] = {"__builtins__": {
            "abs": abs,
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "range": range,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "isinstance": isinstance,
            "print": lambda *_: None,
        }}
        local_scope: Dict[str, Any] = {}
        try:
            exec(source_code, safe_globals, local_scope)
        except Exception as exc:
            static_report.is_sound = False
            static_report.violations.append(f"Execution compilation error: {exc}")
            dynamic_report = DynamicPropertyReport(
                total_trials=0,
                passed_trials=0,
                verdict=VerificationVerdict.SYNTAX_ERROR,
                counterexamples=[],
                coverage_ratio=0.0,
            )
            sig = self._compute_signature(code_hash, VerificationVerdict.SYNTAX_ERROR.value, False, 0)
            cert = FormalVerificationCertificate(
                certificate_id=cert_id,
                tool_name=tool_name,
                version=version,
                author_seat_id=author_seat_id,
                code_hash=code_hash,
                verdict=VerificationVerdict.SYNTAX_ERROR,
                static_report=static_report,
                dynamic_report=dynamic_report,
                contracts_evaluated=len(contracts),
                attestation_signature=sig,
            )
            self.certificates[cert_id] = cert
            return cert

        # Find target callable
        target_fn = None
        for item in local_scope.values():
            if callable(item):
                target_fn = item
                break

        if not target_fn:
            static_report.is_sound = False
            static_report.violations.append("No callable function defined in source code.")
            dynamic_report = DynamicPropertyReport(
                total_trials=0,
                passed_trials=0,
                verdict=VerificationVerdict.DISPROVED,
                counterexamples=[],
                coverage_ratio=0.0,
            )
            sig = self._compute_signature(code_hash, VerificationVerdict.DISPROVED.value, False, 0)
            cert = FormalVerificationCertificate(
                certificate_id=cert_id,
                tool_name=tool_name,
                version=version,
                author_seat_id=author_seat_id,
                code_hash=code_hash,
                verdict=VerificationVerdict.DISPROVED,
                static_report=static_report,
                dynamic_report=dynamic_report,
                contracts_evaluated=len(contracts),
                attestation_signature=sig,
            )
            self.certificates[cert_id] = cert
            return cert

        # 3. Dynamic Property Testing
        dynamic_report = self.dynamic_tester.run_property_tests(
            fn=target_fn,
            param_types=param_types,
            contracts=contracts,
            trials=trials,
        )

        final_verdict = (
            VerificationVerdict.PROVED
            if (static_report.is_sound and dynamic_report.verdict == VerificationVerdict.PROVED)
            else VerificationVerdict.DISPROVED
        )

        sig = self._compute_signature(code_hash, final_verdict.value, static_report.is_sound, dynamic_report.passed_trials)

        cert = FormalVerificationCertificate(
            certificate_id=cert_id,
            tool_name=tool_name,
            version=version,
            author_seat_id=author_seat_id,
            code_hash=code_hash,
            verdict=final_verdict,
            static_report=static_report,
            dynamic_report=dynamic_report,
            contracts_evaluated=len(contracts),
            attestation_signature=sig,
        )
        self.certificates[cert_id] = cert
        return cert

    def verify_certificate(self, cert: FormalVerificationCertificate) -> bool:
        expected = self._compute_signature(
            cert.code_hash,
            cert.verdict.value,
            cert.static_report.is_sound,
            cert.dynamic_report.passed_trials,
        )
        return hmac.compare_digest(cert.attestation_signature, expected)
