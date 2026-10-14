"""One renewal tick. The timer owns the 60s cadence; this process does not sleep."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from desk_lease_heartbeat.envfile import EnvFileError, load_env_file
from desk_lease_heartbeat.mcp import EXIT_FOR, CallOutcome, call_graph_heartbeat
from desk_lease_heartbeat.redact import public_url, redact
from desk_lease_heartbeat.state import HeldLease, StateError, load_held, load_misses, save_held, save_misses, write_last_renewal

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_CONFIG = 6

_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
_FAILURE_PRIORITY = ("unreachable", "http", "unparseable", "tool")


@dataclass(frozen=True)
class Settings:
    seat: str
    holder_id: str
    endpoint_url: str
    endpoint_token: str
    ttl_seconds: int | None
    interval_s: int | None
    jitter_s: int | None
    timeout_s: float
    max_missed: int | None
    state_dir: Path | None
    held_file: Path | None
    log_level: str
    log_bytes: int

    @property
    def configured(self) -> bool:
        return bool(self.endpoint_url and self.endpoint_token)

    def held_path(self) -> Path | None:
        if self.held_file is not None:
            return self.held_file
        if self.state_dir is not None:
            return self.state_dir / "held.json"
        return None

    def misses_path(self) -> Path | None:
        if self.state_dir is not None:
            return self.state_dir / "misses.json"
        held = self.held_path()
        if held is not None:
            return held.parent / "misses.json"
        return None

    def renewal_path(self) -> Path | None:
        if self.state_dir is not None:
            return self.state_dir / "last-renewal"
        held = self.held_path()
        if held is not None:
            return held.parent / "last-renewal"
        return None


class ConfigError(Exception):
    pass


def run_renew(env_file: Path | None = None, environ: dict[str, str] | None = None) -> int:
    base = dict(os.environ if environ is None else environ)
    try:
        if env_file is not None:
            # The file is the cron path's only source of truth, so it wins.
            base.update(load_env_file(env_file))
        settings = settings_from_env(base)
    except (EnvFileError, ConfigError) as exc:
        _emit("error", str(exc), secrets=[], threshold="info")
        return EXIT_CONFIG

    secrets = [settings.endpoint_token]
    try:
        held_path = settings.held_path()
        leases = load_held(held_path) if held_path is not None else []
    except StateError as exc:
        _emit("error", str(exc), secrets=secrets, threshold=settings.log_level)
        return EXIT_CONFIG

    mine = [lease for lease in leases if _for_this_seat(lease, settings.seat)]
    secrets = [settings.endpoint_token, *[lease.lease_id for lease in mine]]

    if not mine:
        _emit("info", "nothing held", secrets=secrets, threshold=settings.log_level)
        return EXIT_OK
    if not settings.configured:
        _emit(
            "info",
            "upstream not configured (LEASE_ENDPOINT_URL or LEASE_ENDPOINT_TOKEN unset); skipping renew",
            secrets=secrets,
            threshold=settings.log_level,
        )
        return EXIT_OK

    misses_path = settings.misses_path()
    misses = load_misses(misses_path) if misses_path is not None else {}
    renewed: list[HeldLease] = []
    dropped: list[HeldLease] = []
    failures: list[CallOutcome] = []
    # LEASE_TIMEOUT_S is the wall-clock budget for every call in this tick.
    # systemd TimeoutStartSec is the same number, so a second full timeout
    # per lease would outlive the unit and the TTL margin.
    deadline = time.monotonic() + settings.timeout_s

    for lease in mine:
        ttl = lease.ttl_seconds if lease.ttl_seconds is not None else settings.ttl_seconds
        arguments: dict[str, object] = {
            "graph_id": lease.graph_id,
            "node_id": lease.node_id,
            "lease_id": lease.lease_id,
        }
        if ttl is not None:
            arguments["ttl_seconds"] = ttl
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome = CallOutcome("unreachable", "overall timeout")
        else:
            outcome = call_graph_heartbeat(
                url=settings.endpoint_url,
                token=settings.endpoint_token,
                arguments=arguments,
                timeout_s=remaining,
                log_bytes=settings.log_bytes,
                secrets=secrets,
            )
        where = f"{lease.graph_id}/{lease.node_id}"
        if outcome.kind == "renewed":
            misses.pop(lease.key(), None)
            renewed.append(lease)
            _emit("info", f"renewed {where}", secrets=secrets, threshold=settings.log_level)
        elif outcome.kind == "rejected":
            misses.pop(lease.key(), None)
            dropped.append(lease)
            _emit(
                "warning",
                f"lease rejected {where} reason={outcome.reason}; dropping it",
                secrets=secrets,
                threshold=settings.log_level,
            )
        else:
            failures.append(outcome)
            count = misses.get(lease.key(), 0) + 1
            give_up = settings.max_missed is not None and count >= settings.max_missed
            if give_up:
                misses.pop(lease.key(), None)
                dropped.append(lease)
                _emit(
                    "error",
                    f"renew failed {where} ({outcome.kind}, miss {count}/{settings.max_missed}); dropping it",
                    secrets=secrets,
                    threshold=settings.log_level,
                )
            else:
                misses[lease.key()] = count
                _emit(
                    "error",
                    f"renew failed {where} ({outcome.kind}) at {public_url(settings.endpoint_url)}: {_safe_reason(outcome, secrets)}",
                    secrets=secrets,
                    threshold=settings.log_level,
                )

    if dropped:
        _persist_held(held_path, leases, dropped)
    if misses_path is not None:
        save_misses(misses_path, misses)

    if failures and renewed:
        return EXIT_PARTIAL
    if failures:
        return _failure_exit(failures)

    if renewed:
        renewal_path = settings.renewal_path()
        if renewal_path is not None:
            write_last_renewal(renewal_path, int(time.time()))
        holder = f" holder={settings.holder_id}" if settings.holder_id else ""
        seat = f" seat={settings.seat}" if settings.seat else ""
        _emit(
            "info",
            f"renewed {len(renewed)} lease(s){seat}{holder}",
            secrets=secrets,
            threshold=settings.log_level,
        )
    elif dropped:
        _emit(
            "info",
            f"nothing held after dropping {len(dropped)} lease(s)",
            secrets=secrets,
            threshold=settings.log_level,
        )
    return EXIT_OK


def settings_from_env(env: dict[str, str]) -> Settings:
    ttl = _optional_int(env, "LEASE_TTL_S", minimum=30, maximum=86400)
    interval = _optional_int(env, "LEASE_INTERVAL_S", minimum=1, maximum=86400)
    jitter = _optional_int(env, "LEASE_JITTER_S", minimum=0, maximum=86400)
    timeout = _optional_int(env, "LEASE_TIMEOUT_S", minimum=1, maximum=86400)
    max_missed = _optional_int(env, "LEASE_MAX_MISSED", minimum=1, maximum=1000)
    log_bytes = _optional_int(env, "LEASE_LOG_BYTES", minimum=0, maximum=1_000_000)
    level = env.get("LEASE_LOG_LEVEL", "").strip().lower() or "info"
    if level not in _LEVELS:
        raise ConfigError("LEASE_LOG_LEVEL must be debug, info, warning, or error")
    timeout_s = timeout if timeout is not None else 10
    _check_cadence(ttl, interval, jitter, timeout_s, timeout_set=timeout is not None)
    state_raw = env.get("LEASE_STATE_DIR", "").strip()
    held_raw = env.get("LEASE_HELD_FILE", "").strip()
    return Settings(
        seat=env.get("LEASE_SEAT", "").strip(),
        holder_id=env.get("LEASE_HOLDER_ID", "").strip(),
        endpoint_url=env.get("LEASE_ENDPOINT_URL", "").strip(),
        endpoint_token=env.get("LEASE_ENDPOINT_TOKEN", "").strip(),
        ttl_seconds=ttl,
        interval_s=interval,
        jitter_s=jitter,
        timeout_s=float(timeout_s),
        max_missed=max_missed,
        state_dir=Path(state_raw) if state_raw else None,
        held_file=Path(held_raw) if held_raw else None,
        log_level=level,
        log_bytes=log_bytes if log_bytes is not None else 2000,
    )


def _check_cadence(
    ttl: int | None,
    interval: int | None,
    jitter: int | None,
    timeout_s: int,
    *,
    timeout_set: bool,
) -> None:
    """INTERVAL + JITTER + TIMEOUT <= TTL/3, and TIMEOUT < INTERVAL.

    Checked only for the terms that are actually set, so a manual run that
    leaves the timer's cadence empty still renews. When all four are set, a
    budget that can outlive the lease margin is exit 6, not a green tick.
    """
    if interval is not None and timeout_set and timeout_s >= interval:
        raise ConfigError(
            f"LEASE_TIMEOUT_S ({timeout_s}) must be < LEASE_INTERVAL_S ({interval})"
        )
    if ttl is None or interval is None or jitter is None or not timeout_set:
        return
    total = interval + jitter + timeout_s
    if total * 3 > ttl:
        raise ConfigError(
            "LEASE_INTERVAL_S + LEASE_JITTER_S + LEASE_TIMEOUT_S "
            f"({interval}+{jitter}+{timeout_s}={total}) must be <= LEASE_TTL_S/3 ({ttl}/3)"
        )


def _for_this_seat(lease: HeldLease, seat: str) -> bool:
    if lease.seat is None or not seat:
        return True
    return lease.seat == seat


def _persist_held(path: Path | None, original: list[HeldLease], dropped: list[HeldLease]) -> None:
    if path is None:
        return
    dropped_ids = {id(lease) for lease in dropped}
    save_held(path, [lease for lease in original if id(lease) not in dropped_ids])


def _failure_exit(failed: list[CallOutcome]) -> int:
    kinds = {outcome.kind for outcome in failed}
    for kind in _FAILURE_PRIORITY:
        if kind in kinds:
            return EXIT_FOR[kind]
    return EXIT_FOR["tool"]


def _safe_reason(outcome: CallOutcome, secrets: list[str]) -> str:
    return redact(outcome.reason, secrets)[:300]


def _optional_int(env: dict[str, str], name: str, *, minimum: int, maximum: int) -> int | None:
    raw = env.get(name, "").strip()
    if not raw:
        return None
    if not raw.isascii() or not raw.isdigit():
        raise ConfigError(f"{name} must be an integer {minimum}..{maximum}")
    value = int(raw)
    if value < minimum or value > maximum:
        raise ConfigError(f"{name} must be an integer {minimum}..{maximum}")
    return value


def _emit(level: str, message: str, *, secrets: list[str], threshold: str) -> None:
    if _LEVELS[level] < _LEVELS[threshold]:
        return
    print(f"desk-lease-heartbeat: {redact(message, secrets)}", file=sys.stderr)
