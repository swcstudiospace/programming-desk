"""Unit and integration tests for Dynamic Skill & Tool Synthesis (Phase 36).

Validates AST security filtering, sandbox verification, dynamic tool deployment,
HMAC attestation signing, invocation telemetry, and lifecycle pruning.
"""

import pytest
import hmac
import hashlib
from desk_gateway.skill_synthesis import (
    ASTSecurityValidator,
    SyntheticSandboxHarness,
    ToolLifecycleManager,
    SkillSynthesisEngine,
    SkillSpecification,
    ToolParameterSchema,
    SyntheticTestCase,
    ToolLifecycleState,
    SecurityViolationError,
    SandboxExecutionError,
)


def test_ast_security_validator_blocks_malicious_code():
    validator = ASTSecurityValidator()

    # Disallowed os import
    malicious_import = """
import os

def malicious_tool(path: str):
    return os.listdir(path)
"""
    with pytest.raises(SecurityViolationError, match="Prohibited import detected"):
        validator.validate_source(malicious_import)

    # Disallowed subprocess
    malicious_subp = """
from subprocess import check_output

def run_cmd(cmd: str):
    return check_output(cmd)
"""
    with pytest.raises(SecurityViolationError, match="Prohibited import-from detected"):
        validator.validate_source(malicious_subp)

    # Disallowed eval call
    malicious_eval = """
def sneaky_eval(code_str: str):
    return eval(code_str)
"""
    with pytest.raises(SecurityViolationError, match="Prohibited built-in call"):
        validator.validate_source(malicious_eval)

    # Disallowed dunder access
    malicious_dunder = """
def dunder_breakout():
    return ().__class__.__subclasses__()
"""
    with pytest.raises(SecurityViolationError, match="Prohibited dunder access"):
        validator.validate_source(malicious_dunder)


def test_ast_security_validator_allows_safe_code():
    validator = ASTSecurityValidator()
    safe_code = """
import json
import math

def calculate_stats(numbers_json: str):
    nums = json.loads(numbers_json)
    if not nums:
        return {"count": 0, "mean": 0.0}
    total = sum(nums)
    avg = total / len(nums)
    return {"count": len(nums), "mean": avg, "sqrt_count": math.sqrt(len(nums))}
"""
    # Should validate without error
    validator.validate_source(safe_code)


def test_synthetic_sandbox_harness_execution():
    harness = SyntheticSandboxHarness()
    spec = SkillSpecification(
        tool_name="add_numbers",
        version="1.0.0",
        description="Adds two integers together",
        parameters=[
            ToolParameterSchema(name="a", type_name="int", description="first"),
            ToolParameterSchema(name="b", type_name="int", description="second"),
        ],
        return_type="int",
        required_permissions={"compute:basic"},
        author_seat_id="systems",
        python_source="""
def add_numbers(a: int, b: int) -> int:
    return a + b
""",
        test_cases=[
            SyntheticTestCase(input_args={"a": 2, "b": 3}, expected_output=5),
            SyntheticTestCase(input_args={"a": -1, "b": 1}, expected_output=0),
        ],
    )

    fn = harness.compile_tool(spec)
    harness.execute_test_cases(spec, fn)
    assert fn(a=10, b=20) == 30

    # Test with failing assertion
    failing_spec = SkillSpecification(
        tool_name="failing_tool",
        version="1.0.0",
        description="Fails expected output",
        parameters=[],
        return_type="int",
        required_permissions=set(),
        author_seat_id="systems",
        python_source="""
def failing_tool() -> int:
    return 42
""",
        test_cases=[
            SyntheticTestCase(input_args={}, expected_output=99),
        ],
    )
    fail_fn = harness.compile_tool(failing_spec)
    with pytest.raises(SandboxExecutionError, match="output mismatch"):
        harness.execute_test_cases(failing_spec, fail_fn)


def test_skill_synthesis_engine_lifecycle_and_invocation():
    secret_key = b"test-secret-synthesis-key"
    engine = SkillSynthesisEngine(signing_key=secret_key)

    source = """
def word_counter(text: str) -> int:
    return len(text.split())
"""
    spec = SkillSpecification(
        tool_name="word_counter",
        version="1.0.0",
        description="Counts words in input string",
        parameters=[ToolParameterSchema(name="text", type_name="str", description="text to count")],
        return_type="int",
        required_permissions={"text:analyze"},
        author_seat_id="lead",
        python_source=source,
        test_cases=[
            SyntheticTestCase(input_args={"text": "hello world"}, expected_output=2),
            SyntheticTestCase(input_args={"text": "desk gateway autonomous swarm"}, expected_output=4),
        ],
    )

    receipt = engine.verify_and_deploy_skill(spec)
    assert receipt.tool_name == "word_counter"
    assert receipt.lifecycle_state == ToolLifecycleState.ACTIVE

    # Verify signature
    code_hash = engine.compute_source_hash(source)
    expected_sig = hmac.new(secret_key, f"word_counter:1.0.0:{code_hash}".encode("utf-8"), hashlib.sha256).hexdigest()
    assert receipt.attestation_signature == expected_sig

    # Invoke tool
    result = engine.invoke_synthetic_tool("word_counter", text="the quick brown fox")
    assert result == 4

    # Check metrics
    metrics = engine.lifecycle.get_metrics("word_counter")
    assert metrics is not None
    assert metrics["total_calls"] == 1
    assert metrics["failed_calls"] == 0

    # Deprecate and Retire
    engine.deprecate_tool("word_counter")
    assert engine.lifecycle.get_state("word_counter") == ToolLifecycleState.DEPRECATED

    engine.retire_tool("word_counter")
    assert engine.lifecycle.get_state("word_counter") == ToolLifecycleState.RETIRED

    with pytest.raises(RuntimeError, match="has been retired"):
        engine.invoke_synthetic_tool("word_counter", text="fail")


def test_tool_lifecycle_manager_automatic_deprecation():
    mgr = ToolLifecycleManager(max_error_rate=0.3, min_calls_for_deprecation=5)
    mgr.register_tool("flaky_tool")

    # 3 successes, 3 failures -> 50% error rate > 30% threshold
    for _ in range(3):
        mgr.record_execution("flaky_tool", duration_sec=0.01, success=True)
    for _ in range(3):
        mgr.record_execution("flaky_tool", duration_sec=0.01, success=False)

    assert mgr.get_state("flaky_tool") == ToolLifecycleState.DEPRECATED
    m = mgr.get_metrics("flaky_tool")
    assert m["error_rate"] == 0.5
