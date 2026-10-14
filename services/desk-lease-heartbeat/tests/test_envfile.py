from desk_lease_heartbeat.envfile import EnvFileError, parse_env_file
import pytest


def test_env_file_does_not_expand_dollar_or_backticks() -> None:
    parsed = parse_env_file(
        "\n".join(
            [
                "# comment",
                "",
                "LEASE_ENDPOINT_TOKEN=pa$$word`id`",
                'LEASE_ENDPOINT_URL="http://127.0.0.1:7410/mcp"',
                "LEASE_HOLDER_ID='host-$HOME'",
                "LEASE_TTL_S=",
            ]
        )
    )
    assert parsed["LEASE_ENDPOINT_TOKEN"] == "pa$$word`id`"
    assert parsed["LEASE_ENDPOINT_URL"] == "http://127.0.0.1:7410/mcp"
    assert parsed["LEASE_HOLDER_ID"] == "host-$HOME"
    assert parsed["LEASE_TTL_S"] == ""


def test_env_file_rejects_shell_export_and_unclosed_quotes() -> None:
    with pytest.raises(EnvFileError):
        parse_env_file("export LEASE_SEAT=bot-01-systems-backend\n")
    with pytest.raises(EnvFileError):
        parse_env_file('LEASE_ENDPOINT_TOKEN="unterminated\n')
