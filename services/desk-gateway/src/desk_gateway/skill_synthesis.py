"""Dynamic Skill & Tool Synthesis Engine.

Implements autonomous skill and tool generation, Python AST static security vetting,
isolated ephemeral sandbox verification, dynamic tool mesh registry hot-reloading,
and tool capability lifecycle management with automated deprecation.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import hashlib
import hmac
import inspect
import json
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class ToolLifecycleState(str, enum.Enum):
    PROPOSED = "PROPOSED"
    VALIDATING = "VALIDATING"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class SecurityViolationError(Exception):
    """Raised when synthesized tool code violates AST security policies."""
    pass


class SandboxExecutionError(Exception):
    """Raised when sandbox execution fails assertion or runtime constraints."""
    pass


@dataclasses.dataclass
class ToolParameterSchema:
    name: str
    type_name: str
    description: str
    required: bool = True
    default: Optional[Any] = None


@dataclasses.dataclass
class SyntheticTestCase:
    input_args: Dict[str, Any]
    expected_output: Any
    description: str = ""


@dataclasses.dataclass
class SkillSpecification:
    tool_name: str
    version: str
    description: str
    parameters: List[ToolParameterSchema]
    return_type: str
    required_permissions: Set[str]
    author_seat_id: str
    python_source: str
    test_cases: List[SyntheticTestCase] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ToolExecutionReceipt:
    tool_name: str
    version: str
    author_seat_id: str
    code_hash: str
    attestation_signature: str
    timestamp: float
    lifecycle_state: ToolLifecycleState


class ASTSecurityValidator:
    """Static AST analyzer verifying safety of dynamically synthesized tool code."""

    PROHIBITED_IMPORTS: Set[str] = {
        "os", "sys", "subprocess", "socket", "shutil", "posix", "pty",
        "requests", "urllib", "http", "ftplib", "builtins", "__builtin__",
        "pickle", "shelve", "ctypes", "marshal", "importlib"
    }

    PROHIBITED_FUNCTIONS: Set[str] = {
        "eval", "exec", "compile", "open", "__import__", "globals",
        "locals", "getattr", "setattr", "delattr", "system", "spawn"
    }

    ALLOWED_MODULES: Set[str] = {
        "math", "re", "json", "time", "datetime", "hashlib",
        "dataclasses", "typing", "collections", "itertools", "string"
    }

    def __init__(
        self,
        max_lines: int = 150,
        max_ast_nodes: int = 400,
        prohibited_imports: Optional[Set[str]] = None,
        prohibited_functions: Optional[Set[str]] = None,
    ):
        self.max_lines = max_lines
        self.max_ast_nodes = max_ast_nodes
        self.prohibited_imports = prohibited_imports or self.PROHIBITED_IMPORTS
        self.prohibited_functions = prohibited_functions or self.PROHIBITED_FUNCTIONS

    def validate_source(self, code: str) -> None:
        """Parse and inspect Python source code for security violations."""
        lines = code.strip().splitlines()
        if len(lines) > self.max_lines:
            raise SecurityViolationError(
                f"Source code exceeds maximum line limit: {len(lines)} > {self.max_lines}"
            )

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SecurityViolationError(f"Synthesized code syntax error: {e}") from e

        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > self.max_ast_nodes:
            raise SecurityViolationError(
                f"AST complexity exceeds node limit: {node_count} > {self.max_ast_nodes}"
            )

        for node in ast.walk(tree):
            # Check import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in self.prohibited_imports or root_mod not in self.ALLOWED_MODULES:
                        raise SecurityViolationError(f"Prohibited import detected: '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in self.prohibited_imports or root_mod not in self.ALLOWED_MODULES:
                        raise SecurityViolationError(f"Prohibited import-from detected: '{node.module}'")

            # Check function calls
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in self.prohibited_functions:
                    raise SecurityViolationError(f"Prohibited built-in call: '{func.id}'")
                elif isinstance(func, ast.Attribute) and func.attr in self.prohibited_functions:
                    raise SecurityViolationError(f"Prohibited attribute call: '{func.attr}'")

            # Block private/dunder attribute accesses like __subclasses__
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__"):
                    raise SecurityViolationError(f"Prohibited dunder access: '{node.attr}'")


class SyntheticSandboxHarness:
    """Ephemeral in-process sandbox executing synthesized tools with safety bounds."""

    def __init__(self, execution_timeout_sec: float = 2.0):
        self.execution_timeout_sec = execution_timeout_sec

    def compile_tool(self, spec: SkillSpecification) -> Callable[..., Any]:
        """Safely compile source and extract the main entrypoint function."""
        # Clean restricted globals
        safe_globals: Dict[str, Any] = {
            "__builtins__": {
                "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
                "enumerate": enumerate, "zip": zip, "range": range, "filter": filter,
                "map": map, "int": int, "float": float, "str": str, "bool": bool,
                "list": list, "dict": dict, "set": set, "tuple": tuple,
                "isinstance": isinstance, "Exception": Exception, "ValueError": ValueError,
            }
        }
        local_scope: Dict[str, Any] = {}
        compiled = compile(spec.python_source, filename=f"<synthetic_{spec.tool_name}>", mode="exec")
        exec(compiled, safe_globals, local_scope)

        if spec.tool_name not in local_scope or not callable(local_scope[spec.tool_name]):
            raise SandboxExecutionError(
                f"Synthesized tool entrypoint function '{spec.tool_name}' not defined in module."
            )
        return local_scope[spec.tool_name]

    def execute_test_cases(self, spec: SkillSpecification, tool_fn: Callable[..., Any]) -> None:
        """Run all test cases against compiled tool function."""
        if not spec.test_cases:
            raise SandboxExecutionError("Tool specification must provide at least 1 test case assertion.")

        for idx, tc in enumerate(spec.test_cases):
            start = time.perf_counter()
            try:
                result = tool_fn(**tc.input_args)
            except Exception as e:
                raise SandboxExecutionError(f"Test case {idx} failed with error: {e}") from e
            elapsed = time.perf_counter() - start

            if elapsed > self.execution_timeout_sec:
                raise SandboxExecutionError(
                    f"Test case {idx} exceeded execution timeout ({elapsed:.3f}s > {self.execution_timeout_sec}s)"
                )

            if result != tc.expected_output:
                raise SandboxExecutionError(
                    f"Test case {idx} output mismatch: got {result!r}, expected {tc.expected_output!r}"
                )


class ToolLifecycleManager:
    """Tracks invocation metrics, error rates, and lifecycle transitions for tools."""

    def __init__(
        self,
        max_error_rate: float = 0.25,
        min_calls_for_deprecation: int = 10,
        deprecation_cooloff_sec: float = 86400.0,
    ):
        self.max_error_rate = max_error_rate
        self.min_calls_for_deprecation = min_calls_for_deprecation
        self.deprecation_cooloff_sec = deprecation_cooloff_sec
        # tool_name -> metrics dict
        self._metrics: Dict[str, Dict[str, Any]] = {}
        # tool_name -> state
        self._states: Dict[str, ToolLifecycleState] = {}

    def register_tool(self, tool_name: str, initial_state: ToolLifecycleState = ToolLifecycleState.ACTIVE) -> None:
        self._states[tool_name] = initial_state
        self._metrics[tool_name] = {
            "total_calls": 0,
            "failed_calls": 0,
            "total_duration_sec": 0.0,
            "registered_at": time.time(),
            "last_used_at": 0.0,
        }

    def record_execution(self, tool_name: str, duration_sec: float, success: bool) -> None:
        if tool_name not in self._metrics:
            self.register_tool(tool_name)
        
        m = self._metrics[tool_name]
        m["total_calls"] += 1
        if not success:
            m["failed_calls"] += 1
        m["total_duration_sec"] += duration_sec
        m["last_used_at"] = time.time()

        # Check for degradation
        if m["total_calls"] >= self.min_calls_for_deprecation:
            error_rate = m["failed_calls"] / m["total_calls"]
            if error_rate > self.max_error_rate and self._states.get(tool_name) == ToolLifecycleState.ACTIVE:
                self._states[tool_name] = ToolLifecycleState.DEPRECATED

    def get_state(self, tool_name: str) -> Optional[ToolLifecycleState]:
        return self._states.get(tool_name)

    def set_state(self, tool_name: str, state: ToolLifecycleState) -> None:
        self._states[tool_name] = state

    def get_metrics(self, tool_name: str) -> Optional[Dict[str, Any]]:
        if tool_name not in self._metrics:
            return None
        m = self._metrics[tool_name]
        total = m["total_calls"]
        error_rate = (m["failed_calls"] / total) if total > 0 else 0.0
        avg_latency = (m["total_duration_sec"] / total) if total > 0 else 0.0
        return {
            "total_calls": total,
            "failed_calls": m["failed_calls"],
            "error_rate": error_rate,
            "avg_latency_sec": avg_latency,
            "lifecycle_state": self._states.get(tool_name, ToolLifecycleState.PROPOSED).value,
            "last_used_at": m["last_used_at"],
        }


class SkillSynthesisEngine:
    """Orchestrates dynamic tool creation, vetting, attestation signing, and live invocation."""

    def __init__(
        self,
        signing_key: bytes,
        ast_validator: Optional[ASTSecurityValidator] = None,
        sandbox_harness: Optional[SyntheticSandboxHarness] = None,
        lifecycle_mgr: Optional[ToolLifecycleManager] = None,
    ):
        self.signing_key = signing_key
        self.validator = ast_validator or ASTSecurityValidator()
        self.sandbox = sandbox_harness or SyntheticSandboxHarness()
        self.lifecycle = lifecycle_mgr or ToolLifecycleManager()
        # Active compiled tools: tool_name -> callable
        self._active_tools: Dict[str, Callable[..., Any]] = {}
        # Registered specs: tool_name -> SkillSpecification
        self._specs: Dict[str, SkillSpecification] = {}
        # Attestation receipts: tool_name -> ToolExecutionReceipt
        self._receipts: Dict[str, ToolExecutionReceipt] = {}

    def compute_source_hash(self, source: str) -> str:
        return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()

    def generate_attestation_signature(self, tool_name: str, version: str, code_hash: str) -> str:
        msg = f"{tool_name}:{version}:{code_hash}".encode("utf-8")
        return hmac.new(self.signing_key, msg, hashlib.sha256).hexdigest()

    def verify_and_deploy_skill(self, spec: SkillSpecification) -> ToolExecutionReceipt:
        """Validates AST safety, executes test assertions in sandbox, signs attestation, and deploys tool."""
        # 1. AST static analysis
        self.validator.validate_source(spec.python_source)

        # 2. Compile and test in sandbox
        tool_fn = self.sandbox.compile_tool(spec)
        self.sandbox.execute_test_cases(spec, tool_fn)

        # 3. Create attestation receipt
        code_hash = self.compute_source_hash(spec.python_source)
        sig = self.generate_attestation_signature(spec.tool_name, spec.version, code_hash)
        now = time.time()

        receipt = ToolExecutionReceipt(
            tool_name=spec.tool_name,
            version=spec.version,
            author_seat_id=spec.author_seat_id,
            code_hash=code_hash,
            attestation_signature=sig,
            timestamp=now,
            lifecycle_state=ToolLifecycleState.ACTIVE,
        )

        # 4. Deploy into active mesh
        self._active_tools[spec.tool_name] = tool_fn
        self._specs[spec.tool_name] = spec
        self._receipts[spec.tool_name] = receipt
        self.lifecycle.register_tool(spec.tool_name, ToolLifecycleState.ACTIVE)

        return receipt

    def invoke_synthetic_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Invoke a deployed synthetic tool with lifecycle telemetry recording."""
        if tool_name not in self._specs:
            raise KeyError(f"Synthetic tool '{tool_name}' is not registered.")

        state = self.lifecycle.get_state(tool_name)
        if state == ToolLifecycleState.RETIRED:
            raise RuntimeError(f"Synthetic tool '{tool_name}' has been retired.")

        if tool_name not in self._active_tools:
            raise KeyError(f"Synthetic tool '{tool_name}' is not active.")

        if state == ToolLifecycleState.DEPRECATED:
            # Still callable, but degraded state warning can be noted
            pass

        tool_fn = self._active_tools[tool_name]
        start = time.perf_counter()
        success = False
        try:
            result = tool_fn(**kwargs)
            success = True
            return result
        finally:
            duration = time.perf_counter() - start
            self.lifecycle.record_execution(tool_name, duration, success)

    def deprecate_tool(self, tool_name: str) -> None:
        if tool_name not in self._specs:
            raise KeyError(f"Tool '{tool_name}' not found.")
        self.lifecycle.set_state(tool_name, ToolLifecycleState.DEPRECATED)
        if tool_name in self._receipts:
            self._receipts[tool_name].lifecycle_state = ToolLifecycleState.DEPRECATED

    def retire_tool(self, tool_name: str) -> None:
        if tool_name not in self._specs:
            raise KeyError(f"Tool '{tool_name}' not found.")
        self.lifecycle.set_state(tool_name, ToolLifecycleState.RETIRED)
        if tool_name in self._receipts:
            self._receipts[tool_name].lifecycle_state = ToolLifecycleState.RETIRED
        self._active_tools.pop(tool_name, None)

    def list_active_tools(self) -> List[Dict[str, Any]]:
        results = []
        for name, spec in self._specs.items():
            state = self.lifecycle.get_state(name)
            metrics = self.lifecycle.get_metrics(name)
            results.append({
                "tool_name": name,
                "version": spec.version,
                "description": spec.description,
                "required_permissions": sorted(list(spec.required_permissions)),
                "lifecycle_state": state.value if state else ToolLifecycleState.PROPOSED.value,
                "metrics": metrics,
            })
        return results

    def get_receipt(self, tool_name: str) -> Optional[ToolExecutionReceipt]:
        return self._receipts.get(tool_name)
