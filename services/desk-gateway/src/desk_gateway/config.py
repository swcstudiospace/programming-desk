"""Settings read from the environment (/etc/desk-gateway/gateway.env on the VPS)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SEATS: dict[str, str] = {
    "lead": "bot-00-programming-lead",
    "systems": "bot-01-systems-backend",
    "web": "bot-02-web-edge",
    "android": "bot-03-android",
    "ios": "bot-04-ios",
    "infra": "bot-05-infrastructure",
    "quality": "bot-06-quality-security",
}
SEAT_BY_BOT: dict[str, str] = {v: k for k, v in SEATS.items()}
SEAT_LABEL: dict[str, str] = {
    "lead": "LEAD",
    "systems": "SYSTEMS",
    "web": "WEB",
    "android": "ANDROID",
    "ios": "IOS",
    "infra": "INFRA",
    "quality": "QUALITY",
}
TOOL_DEADLINE_SEC = 20.0
MAX_LIVE_TOOLS = 20
PACK_MAX_TOOLS = 5


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    public_host: str = "desk.swcstudio.space"
    host: str = "127.0.0.1"
    port: int = 8791
    data_dir: Path = Path("/var/lib/desk-gateway")
    repo_dir: Path = Path("/root/src/repos/programming-desk")
    repo_remote: str = "origin"
    repo_branch: str = "main"
    log_level: str = "INFO"
    seat_passphrases: dict[str, str] = field(default_factory=dict)
    intake_tokens: dict[str, str] = field(default_factory=dict)
    substrate_url: str = "http://127.0.0.1:7410"
    substrate_token: str = ""
    agent_bus_url: str = "http://127.0.0.1:8790"
    agent_bus_token: str = ""
    greptime_url: str = ""
    greptime_user: str = ""
    greptime_password: str = ""
    greptime_db: str = "public"
    pg_url: str = ""
    dragonfly_url: str = ""
    hindsight_url: str = ""
    hindsight_api_key: str = ""
    ragflow_url: str = ""
    ragflow_api_key: str = ""
    railway_api_token: str = ""
    railway_projects: dict[str, str] = field(default_factory=dict)
    vercel_token: str = ""
    vercel_team_id: str = ""
    vercel_projects: list[str] = field(default_factory=list)
    greptile_api_key: str = ""
    greptile_github_token: str = ""
    github_token: str = ""
    play_access_token: str = ""
    asc_key_id: str = ""
    asc_issuer_id: str = ""
    asc_private_key_path: str = ""
    pack_api_bases: dict[str, str] = field(default_factory=dict)
    extra_allowed_origins: list[str] = field(default_factory=list)
    view_passphrase: str = ""
    view_secret: str = ""

    @property
    def issuer_url(self) -> str:
        return f"https://{self.public_host}"

    @property
    def resource_url(self) -> str:
        return f"https://{self.public_host}/mcp"

    @property
    def gateway_url(self) -> str:
        return self.issuer_url

    def seat_for_passphrase(self, passphrase: str) -> str | None:
        import secrets

        if not passphrase:
            return None
        for seat, expected in self.seat_passphrases.items():
            if expected and secrets.compare_digest(passphrase.encode(), expected.encode()):
                return seat
        return None

    def origin_for_intake_token(self, token: str) -> str | None:
        import secrets

        if not token:
            return None
        for origin, expected in self.intake_tokens.items():
            if expected and secrets.compare_digest(token.encode(), expected.encode()):
                return origin
        return None

    @classmethod
    def from_env(cls) -> Settings:
        passphrases = {seat: _env(f"SEAT_PASSPHRASE_{seat.upper()}") for seat in SEATS}
        intake: dict[str, str] = {}
        for pair in _csv(_env("INTAKE_TOKENS")):
            origin, _, token = pair.partition(":")
            if origin and token:
                intake[origin.strip()] = token.strip()
        projects = {
            "ultrathink": _env("RAILWAY_PROJECT_ULTRATHINK"),
            "agent-substrate": _env("RAILWAY_PROJECT_AGENT_SUBSTRATE"),
        }
        packs = {
            "kanbanos": _env("PACK_KANBANOS_API_BASE"),
            "desklanes": _env("PACK_DESKLANES_API_BASE"),
            "clippyos": _env("PACK_CLIPPYOS_API_BASE"),
        }
        return cls(
            public_host=_env("PUBLIC_HOST", "desk.swcstudio.space"),
            host=_env("HOST", "127.0.0.1"),
            port=int(_env("PORT", "8791")),
            data_dir=Path(_env("DATA_DIR", "/var/lib/desk-gateway")),
            repo_dir=Path(_env("DESK_REPO_DIR", "/root/src/repos/programming-desk")),
            repo_remote=_env("DESK_REPO_REMOTE", "origin"),
            repo_branch=_env("DESK_REPO_BRANCH", "main"),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            seat_passphrases={k: v for k, v in passphrases.items() if v},
            intake_tokens=intake,
            substrate_url=_env("SUBSTRATE_URL", "http://127.0.0.1:7410").rstrip("/"),
            substrate_token=_env("SUBSTRATE_TOKEN"),
            agent_bus_url=_env("AGENT_BUS_URL", "http://127.0.0.1:8790").rstrip("/"),
            agent_bus_token=_env("AGENT_BUS_TOKEN"),
            greptime_url=_env("GREPTIME_URL").rstrip("/"),
            greptime_user=_env("GREPTIME_USER"),
            greptime_password=_env("GREPTIME_PASSWORD"),
            greptime_db=_env("GREPTIME_DB", "public"),
            pg_url=_env("SUBSTRATE_PG_URL"),
            dragonfly_url=_env("DRAGONFLY_URL"),
            hindsight_url=_env("HINDSIGHT_URL").rstrip("/"),
            hindsight_api_key=_env("HINDSIGHT_API_KEY"),
            ragflow_url=_env("RAGFLOW_URL").rstrip("/"),
            ragflow_api_key=_env("RAGFLOW_API_KEY"),
            railway_api_token=_env("RAILWAY_API_TOKEN"),
            railway_projects={k: v for k, v in projects.items() if v},
            vercel_token=_env("VERCEL_TOKEN"),
            vercel_team_id=_env("VERCEL_TEAM_ID"),
            vercel_projects=_csv(_env("VERCEL_PROJECTS")),
            greptile_api_key=_env("GREPTILE_API_KEY"),
            greptile_github_token=_env("GREPTILE_GITHUB_TOKEN"),  # pragma: allowlist secret (env var name)
            github_token=_env("GITHUB_TOKEN"),
            play_access_token=_env("PLAY_ACCESS_TOKEN"),
            asc_key_id=_env("ASC_KEY_ID"),
            asc_issuer_id=_env("ASC_ISSUER_ID"),
            asc_private_key_path=_env("ASC_PRIVATE_KEY_PATH"),  # pragma: allowlist secret (env var name)
            pack_api_bases={k: v.rstrip("/") for k, v in packs.items() if v},
            extra_allowed_origins=_csv(_env("EXTRA_ALLOWED_ORIGINS")),
            view_passphrase=_env("DESK_VIEW_PASSPHRASE"),
            view_secret=_env("DESK_VIEW_SECRET"),
        )
