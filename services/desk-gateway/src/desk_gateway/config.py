"""Settings read from the environment (/etc/desk-gateway/gateway.env on the VPS)."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
# docs_search spends these inside the tool deadline: 4s lookup + 10s retrieval = 14s.
DOCS_LOOKUP_BUDGET_SEC = 4.0
DOCS_RETRIEVAL_BUDGET_SEC = 10.0
RECALL_BANK_TIMEOUT_SEC = 6.0
RAGFLOW_DATASET_TTL_SEC = 600.0
DEFAULT_RAGFLOW_DATASETS = ("programming-desk", "agent-substrate")
MAX_LIVE_TOOLS = 20
PACK_MAX_TOOLS = 5


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _float_env(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    return float(raw)

# Operator-owned quantum simulator-node topology (phase 68). These values are
# read from the environment at startup only: no request may register nodes or
# override endpoint URLs / credentials, and the values are never logged or
# publicly serialized (repr is disabled on the Settings fields below).
_QUANTUM_NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_QUANTUM_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _quantum_node_id(node: object, *, name: str) -> str:
    if not isinstance(node, str) or not node or len(node) > 64:
        raise ValueError(f"{name} must be a 1..64 char string")
    if _QUANTUM_NODE_RE.fullmatch(node) is None:
        raise ValueError(f"{name} holds illegal characters")
    return node


def _quantum_endpoint(node: str, url: object) -> str:
    """Validate one operator-configured node URL (parity with transport rules)."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"node {node!r} endpoint must be a non-empty URL string")
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError(f"node {node!r} has an unparsable endpoint") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"node {node!r} endpoint must be an http(s) URL")
    if parts.username or parts.password:
        raise ValueError(f"node {node!r} endpoint must not embed credentials")
    host = parts.hostname.lower()
    # Literal loopback may run plaintext for local process evidence; every
    # other host requires verified TLS (https). The transport enforces the
    # same distinction per command.
    if parts.scheme == "http" and host not in _QUANTUM_LOOPBACK_HOSTS:
        raise ValueError(f"node {node!r} plaintext HTTP is loopback-only")
    path = parts.path.rstrip("/")
    if path not in ("", "/"):
        raise ValueError(f"node {node!r} endpoint must not carry a path")
    return url.strip()


def _json_object_env(name: str) -> dict[str, Any]:
    raw = _env(name)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed


def _json_links_env(name: str) -> list[Any]:
    raw = _env(name)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"{name} must be a JSON list of [node, node] pairs")
    return parsed


def _validate_quantum_topology(
    endpoints: dict[str, Any],
    tokens: dict[str, Any],
    links: list[Any],
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str]]]:
    """Fail-closed validation of the operator quantum topology.

    Rejects malformed shapes, unknown topology references, self-links,
    duplicate undirected links, missing per-node credentials, and
    permissive silent drops (a bare CSV string is not JSON and is
    rejected, never partially accepted). Empty topology is valid and
    means the gateway runs without a remote worker plane.
    """
    if not isinstance(endpoints, dict):
        raise ValueError("quantum_node_endpoints must be a node->URL mapping")
    if not isinstance(tokens, dict):
        raise ValueError("quantum_node_tokens must be a node->token mapping")
    clean_endpoints: dict[str, str] = {}
    for node, url in endpoints.items():
        _quantum_node_id(node, name="endpoint node")
        clean_endpoints[node] = _quantum_endpoint(node, url)
    clean_tokens: dict[str, str] = {}
    if not isinstance(tokens, dict):
        raise ValueError("quantum_node_tokens must be a node->token mapping")
    for node, token in tokens.items():
        _quantum_node_id(node, name="token node")
        if node not in clean_endpoints:
            raise ValueError(f"quantum token for unknown node {node!r}")
        if not isinstance(token, str) or not token:
            raise ValueError(f"quantum token for node {node!r} must be non-empty")
        clean_tokens[node] = token
    for node in clean_endpoints:
        if node not in clean_tokens:
            raise ValueError(f"node {node!r} has an endpoint but no configured token")
    if not isinstance(links, list):
        raise ValueError("quantum_node_links must be a list of [node, node] pairs")
    seen: set[frozenset[str]] = set()
    clean_links: list[tuple[str, str]] = []
    for pos, entry in enumerate(links):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(f"quantum_node_links[{pos}] must be a [node, node] pair")
        node_a, node_b = entry
        _quantum_node_id(node_a, name=f"quantum_node_links[{pos}][0]")
        _quantum_node_id(node_b, name=f"quantum_node_links[{pos}][1]")
        if node_a == node_b:
            raise ValueError(f"quantum_node_links[{pos}] must link distinct nodes")
        if node_a not in clean_endpoints or node_b not in clean_endpoints:
            raise ValueError(f"quantum_node_links[{pos}] references unknown node")
        key = frozenset((node_a, node_b))
        if key in seen:
            raise ValueError(f"quantum_node_links[{pos}] duplicates an earlier link")
        seen.add(key)
        clean_links.append((node_a, node_b))
    return clean_endpoints, clean_tokens, clean_links


def _validate_solana_rpc(url: str) -> str:
    """Accept an empty publisher URL or a bare https endpoint."""
    if not isinstance(url, str):
        raise ValueError("QUANTUM_SOLANA_RPC_URL must be a string")
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("QUANTUM_SOLANA_RPC_URL must be an https URL without userinfo, path, or query")
    return url


@dataclass
class Settings:
    public_host: str = "desk.swcstudio.space"
    host: str = "127.0.0.1"
    port: int = 8791
    data_dir: Path = Path("/var/lib/desk-gateway")
    repo_dir: Path = Path("/root/src/repos/programming-desk")
    repo_remote: str = "origin"
    repo_branch: str = "main"
    # Account the gate subprocesses are dropped to. Empty means they inherit the gateway's own
    # (root on the VPS): the gates only ever read the export, but a gate is still a program
    # reading attacker-supplied data, so a deployment that can spare an account should name one.
    gate_user: str = ""
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
    # Paid once at startup. A seat request never waits on this connect.
    dragonfly_connect_timeout_ms: int = 500
    # Warm command budget. Measured commands are about 240 ms.
    dragonfly_command_timeout_ms: int = 250
    # Hard cap on one rate-limit check. The local bucket answers when it expires.
    dragonfly_rate_limit_budget_ms: int = 150
    dragonfly_health_check_interval_sec: int = 30
    dragonfly_socket_keepalive: bool = True
    dragonfly_breaker_failures: int = 3
    dragonfly_breaker_recovery_sec: float = 30.0
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
    intake_queue_max_depth: int = 100
    intake_rate_limit_per_minute: int = 60
    webhook_secrets: dict[str, str] = field(default_factory=dict)
    idempotency_window_sec: float = 300.0
    intake_max_retries: int = 3
    federation_enabled: bool = False
    federation_peer_keys: dict[str, str] = field(default_factory=dict)
    federation_peers: dict[str, str] = field(default_factory=dict)
    cutover_enabled: bool = False
    canary_percentage: int = 100
    isolated_seats: list[str] = field(default_factory=list)
    alert_webhook_url: str = ""
    slo_latency_p99_max_ms: float = 500.0
    slo_intake_success_min_pct: float = 99.9
    dlq_alert_threshold: int = 10
    edge_default_region: str = "us-east"
    edge_latency_threshold_ms: float = 400.0
    edge_rate_limit_per_minute: int = 60
    edge_burst_capacity: int = 120
    ragflow_datasets: list[str] = field(default_factory=lambda: list(DEFAULT_RAGFLOW_DATASETS))
    ragflow_dataset_ttl_sec: float = RAGFLOW_DATASET_TTL_SEC
    docs_lookup_budget_sec: float = DOCS_LOOKUP_BUDGET_SEC
    docs_retrieval_budget_sec: float = DOCS_RETRIEVAL_BUDGET_SEC
    recall_bank_timeout_sec: float = RECALL_BANK_TIMEOUT_SEC
    # Operator-owned quantum simulator-node topology (phase 68).
    #
    # QUANTUM_NODE_ENDPOINTS is a JSON object mapping node ID to base URL,
    # QUANTUM_NODE_TOKENS a JSON object mapping node ID to scoped credential,
    # QUANTUM_NODE_LINKS a JSON list of undirected [node, node] pairs.
    # Empty topology is valid (no remote worker plane). Any configured node
    # needs an endpoint and a token; links may only reference known nodes.
    # Plaintext http is accepted for literal loopback process evidence only;
    # all other hosts require https. Values are validated at construction,
    # never logged, and never honored from request data.
    quantum_node_endpoints: dict[str, str] = field(default_factory=dict, repr=False)
    quantum_node_tokens: dict[str, str] = field(default_factory=dict, repr=False)
    quantum_node_links: list[tuple[str, str]] = field(default_factory=list, repr=False)
    # In-process test hooks only (a LocalNodeTransport, RNG, and/or event
    # sink). Never populated from the environment; production always builds
    # the lifespan-owned RemoteNodeTransport from the operator topology.
    quantum_transport_override: Any = field(default=None, repr=False, compare=False)
    quantum_rng_override: Any = field(default=None, repr=False, compare=False)
    quantum_sink_override: Any = field(default=None, repr=False, compare=False)
    quantum_rpc_client_override: Any = field(default=None, repr=False, compare=False)
    # Dedicated Devnet publisher. Empty means unconfigured (export returns 503).
    # The signer file is not opened here.
    quantum_solana_rpc_url: str = ""
    quantum_solana_signer_path: str = ""

    def __post_init__(self) -> None:
        endpoints, tokens, links = _validate_quantum_topology(
            dict(self.quantum_node_endpoints),
            dict(self.quantum_node_tokens),
            list(self.quantum_node_links),
        )
        self.quantum_node_endpoints = endpoints
        self.quantum_node_tokens = tokens
        self.quantum_node_links = links
        self.quantum_solana_rpc_url = _validate_solana_rpc(self.quantum_solana_rpc_url)
        if not isinstance(self.quantum_solana_signer_path, str):
            raise ValueError("QUANTUM_SOLANA_SIGNER_PATH must be a string")

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

    def webhook_secret_for_origin(self, origin: str) -> str | None:
        return self.webhook_secrets.get(origin)

    @classmethod
    def from_env(cls) -> Settings:
        passphrases = {seat: _env(f"SEAT_PASSPHRASE_{seat.upper()}") for seat in SEATS}
        intake: dict[str, str] = {}
        for pair in _csv(_env("INTAKE_TOKENS")):
            origin, _, token = pair.partition(":")
            if origin and token:
                intake[origin.strip()] = token.strip()
        webhook_sec: dict[str, str] = {}
        for pair in _csv(_env("WEBHOOK_SECRETS")):
            origin, _, sec = pair.partition(":")
            if origin and sec:
                webhook_sec[origin.strip()] = sec.strip()
        projects = {
            "ultrathink": _env("RAILWAY_PROJECT_ULTRATHINK"),
            "agent-substrate": _env("RAILWAY_PROJECT_AGENT_SUBSTRATE"),
        }
        packs = {
            "kanbanos": _env("PACK_KANBANOS_API_BASE"),
            "desklanes": _env("PACK_DESKLANES_API_BASE"),
            "clippyos": _env("PACK_CLIPPYOS_API_BASE"),
        }
        fed_peers: dict[str, str] = {}
        for pair in _csv(_env("FEDERATION_PEERS")):
            desk_id, _, peer_url = pair.partition(":")
            if desk_id and peer_url:
                fed_peers[desk_id.strip()] = peer_url.strip()
        fed_keys: dict[str, str] = {}
        for pair in _csv(_env("FEDERATION_PEER_KEYS")):
            key_id, _, key_pem = pair.partition(":")
            if key_id and key_pem:
                fed_keys[key_id.strip()] = key_pem.strip().replace("\\n", "\n")
        return cls(
            public_host=_env("PUBLIC_HOST", "desk.swcstudio.space"),
            host=_env("HOST", "127.0.0.1"),
            port=int(_env("PORT", "8791")),
            data_dir=Path(_env("DATA_DIR", "/var/lib/desk-gateway")),
            repo_dir=Path(_env("DESK_REPO_DIR", "/root/src/repos/programming-desk")),
            repo_remote=_env("DESK_REPO_REMOTE", "origin"),
            repo_branch=_env("DESK_REPO_BRANCH", "main"),
            gate_user=_env("DESK_GATE_USER"),
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
            dragonfly_connect_timeout_ms=int(_env("DRAGONFLY_CONNECT_TIMEOUT_MS", "500")),
            dragonfly_command_timeout_ms=int(_env("DRAGONFLY_COMMAND_TIMEOUT_MS", "250")),
            dragonfly_rate_limit_budget_ms=int(_env("DRAGONFLY_RATE_LIMIT_BUDGET_MS", "150")),
            dragonfly_health_check_interval_sec=int(_env("DRAGONFLY_HEALTH_CHECK_INTERVAL_SEC", "30")),
            dragonfly_socket_keepalive=_env("DRAGONFLY_SOCKET_KEEPALIVE", "true").lower() in ("true", "1", "yes"),
            dragonfly_breaker_failures=int(_env("DRAGONFLY_BREAKER_FAILURES", "3")),
            dragonfly_breaker_recovery_sec=float(_env("DRAGONFLY_BREAKER_RECOVERY_SEC", "30")),
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
            intake_queue_max_depth=int(_env("INTAKE_QUEUE_MAX_DEPTH", "100")),
            intake_rate_limit_per_minute=int(_env("INTAKE_RATE_LIMIT_PER_MINUTE", "60")),
            webhook_secrets=webhook_sec,
            idempotency_window_sec=float(_env("IDEMPOTENCY_WINDOW_SEC", "300.0")),
            intake_max_retries=int(_env("INTAKE_MAX_RETRIES", "3")),
            federation_enabled=_env("FEDERATION_ENABLED", "false").lower() in ("true", "1", "yes"),
            federation_peer_keys=fed_keys,
            federation_peers=fed_peers,
            cutover_enabled=_env("CUTOVER_ENABLED", "false").lower() in ("true", "1", "yes"),
            canary_percentage=int(_env("CANARY_PERCENTAGE", "100")),
            isolated_seats=_csv(_env("ISOLATED_SEATS", "")),
            alert_webhook_url=_env("ALERT_WEBHOOK_URL"),
            slo_latency_p99_max_ms=float(_env("SLO_LATENCY_P99_MAX_MS", "500.0")),
            slo_intake_success_min_pct=float(_env("SLO_INTAKE_SUCCESS_MIN_PCT", "99.9")),
            dlq_alert_threshold=int(_env("DLQ_ALERT_THRESHOLD", "10")),
            edge_default_region=_env("EDGE_DEFAULT_REGION", "us-east"),
            edge_latency_threshold_ms=float(_env("EDGE_LATENCY_THRESHOLD_MS", "400.0")),
            edge_rate_limit_per_minute=int(_env("EDGE_RATE_LIMIT_PER_MINUTE", "60")),
            edge_burst_capacity=int(_env("EDGE_BURST_CAPACITY", "120")),
            ragflow_datasets=_csv(_env("RAGFLOW_DATASETS")) or list(DEFAULT_RAGFLOW_DATASETS),
            ragflow_dataset_ttl_sec=_float_env("RAGFLOW_DATASET_TTL_SEC", RAGFLOW_DATASET_TTL_SEC),
            docs_lookup_budget_sec=_float_env("DOCS_LOOKUP_BUDGET_SEC", DOCS_LOOKUP_BUDGET_SEC),
            docs_retrieval_budget_sec=_float_env("DOCS_RETRIEVAL_BUDGET_SEC", DOCS_RETRIEVAL_BUDGET_SEC),
            recall_bank_timeout_sec=_float_env("RECALL_BANK_TIMEOUT_SEC", RECALL_BANK_TIMEOUT_SEC),
            quantum_node_endpoints=_json_object_env("QUANTUM_NODE_ENDPOINTS"),
            quantum_node_tokens=_json_object_env("QUANTUM_NODE_TOKENS"),
            quantum_node_links=_json_links_env("QUANTUM_NODE_LINKS"),
            quantum_solana_rpc_url=_env("QUANTUM_SOLANA_RPC_URL"),
            quantum_solana_signer_path=_env("QUANTUM_SOLANA_SIGNER_PATH"),
        )
