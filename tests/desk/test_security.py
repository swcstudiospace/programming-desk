"""Tests for PolicySandbox and BoundarySecurityError."""

from pathlib import Path
import tempfile
import pytest

from src.desk.security import BoundarySecurityError, PolicySandbox


def test_sanitize_tokens() -> None:
    sandbox = PolicySandbox()

    gh_token = "ghp_" + "a" * 36
    oa_token = "sk-" + "b" * 25
    bearer_token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    aws_token = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret (redaction test fixture)
    git_sha = "c95916fd0c98836e32210686c3aca8ff188c49f6"
    safe_text = "Standard log message with commit: " + git_sha

    raw_text = f"Pushing with {gh_token} and {oa_token} and header {bearer_token} and aws {aws_token}. {safe_text}"
    sanitized = sandbox.sanitize(raw_text)

    assert gh_token not in sanitized
    assert oa_token not in sanitized
    assert bearer_token not in sanitized
    assert aws_token not in sanitized
    assert git_sha in sanitized
    assert "[REDACTED]" in sanitized

    fine_grained = "github_pat_" + ("ab" * 16)
    slack = "xoxb-" + ("1" * 12)
    anthropic = "sk-ant-" + ("c" * 24)
    private_key = "-----BEGIN " + "PRIVATE KEY-----"
    extra = sandbox.sanitize(f"{fine_grained} {slack} {anthropic} {private_key}")
    assert fine_grained not in extra
    assert slack not in extra
    assert anthropic not in extra
    assert "BEGIN PRIVATE KEY" not in extra

    header = "-----BEGIN " + "PRIVATE KEY-----"
    footer = "-----END " + "PRIVATE KEY-----"
    body = "bm90LWEtcmVhbC1rZXk="
    pem = f"note {header}\n{body}\n{footer}\n tail"
    redacted = sandbox.sanitize(pem)
    assert body not in redacted
    assert "BEGIN" not in redacted
    assert "END" not in redacted
    assert "tail" in redacted


def test_sanitize_env() -> None:
    sandbox = PolicySandbox()
    env = {
        "WORKSPACE": "/root/workspace",
        "GITHUB_TOKEN": "ghp_" + "x" * 36,
        "DATABASE_PASSWORD": "supersecretpassword",
        "PUBLIC_URL": "https://example.com/api?token=sk-" + "y" * 22,
    }
    sanitized = sandbox.sanitize_env(env)

    assert sanitized["WORKSPACE"] == "/root/workspace"
    assert sanitized["GITHUB_TOKEN"] == "[REDACTED]"
    assert sanitized["DATABASE_PASSWORD"] == "[REDACTED]"
    assert "sk-" not in sanitized["PUBLIC_URL"]
    assert "[REDACTED]" in sanitized["PUBLIC_URL"]


def test_validate_path_within_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir).resolve()
        sub_dir = root / "sub" / "folder"
        sub_dir.mkdir(parents=True)
        file_path = sub_dir / "target.txt"
        file_path.touch()

        sandbox = PolicySandbox(workspace_root=root)
        validated = sandbox.validate_path(file_path)
        assert validated == file_path.resolve()

        rel_validated = sandbox.validate_path("sub/folder/target.txt")
        assert rel_validated == file_path.resolve()


def test_validate_path_traversal_rejection() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir).resolve()
        sandbox = PolicySandbox(workspace_root=root)

        with pytest.raises(BoundarySecurityError) as exc_info:
            sandbox.validate_path("../../etc/shadow")
        assert "Path traversal violation" in str(exc_info.value)


def test_validate_path_rejects_symlink_escape() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir).resolve()
        outside = Path(tempfile.mkdtemp(prefix="desk-outside-"))
        try:
            secret = outside / "secret.txt"
            secret.write_text("hidden", encoding="utf-8")
            link = root / "alias"
            link.symlink_to(secret)

            sandbox = PolicySandbox(workspace_root=root)
            with pytest.raises(BoundarySecurityError) as exc_info:
                sandbox.validate_path(link)
            assert "Symlink rejected" in str(exc_info.value)

            nested = root / "sub"
            nested.mkdir()
            inner = nested / "jump"
            inner.symlink_to(outside)
            with pytest.raises(BoundarySecurityError):
                sandbox.validate_path(inner / "secret.txt")
        finally:
            secret.unlink(missing_ok=True)
            outside.rmdir()


def test_validate_path_rejects_null_byte() -> None:
    sandbox = PolicySandbox()
    with pytest.raises(BoundarySecurityError):
        sandbox.validate_path("safe\x00.txt")


def test_validate_command() -> None:
    sandbox = PolicySandbox()

    valid_cmd = ["python3", "-m", "desk.cli", "--help"]
    assert sandbox.validate_command(valid_cmd) == valid_cmd

    # Literal pipe in arguments (e.g. git log formatting) is safe and valid
    git_cmd = ["git", "log", "--format=%H|%s"]
    assert sandbox.validate_command(git_cmd) == git_cmd

    # Inline python code with bitwise OR and semicolons is safe and valid
    py_inline_cmd = ["python3", "-c", "x = 1 | 2; print(x)"]
    assert sandbox.validate_command(py_inline_cmd) == py_inline_cmd

    with pytest.raises(BoundarySecurityError):
        sandbox.validate_command([])

    with pytest.raises(BoundarySecurityError):
        sandbox.validate_command(["curl", "http://evil.com; rm -rf /"])

    with pytest.raises(BoundarySecurityError):
        sandbox.validate_command(["cat", "file && echo hacked"])

    with pytest.raises(BoundarySecurityError):
        sandbox.validate_command(["python3", "test.py"], allowed_executables=["git", "node"])
