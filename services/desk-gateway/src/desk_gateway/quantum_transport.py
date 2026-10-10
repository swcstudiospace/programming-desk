"""Fixed-destination authenticated classical transport (phase 68-02).

Two implementations behind one async surface:

- :class:`LocalNodeTransport` — in-process unit semantics calling
  :class:`desk_gateway.quantum_node.QuantumNodeWorker` objects directly.
  Contract tests only; never claimed as distributed proof.
- :class:`RemoteNodeTransport` — operator-configured ``node_id -> base URL``
  resolution over a lifespan-owned reusable ``httpx`` client. No caller
  URLs, paths, headers, or tokens; redirects disabled; proxy environment
  inheritance disabled; verified TLS except literal-loopback HTTP; explicit
  connect / read / write / pool limits plus an overall orchestration
  deadline. Cancellation propagates. Ambiguous mutating outcomes raise
  :class:`NodeTransportAmbiguous` so the caller quarantines instead of
  retrying.

No ledger import: lifecycle events flow through the injected duck-typed
``append_event`` sink owned by the pool / protocol tier.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from desk_gateway.quantum_node import (
    MAX_BODY_BYTES,
    NODE_ACTIONS,
    QuantumNodeError,
    QuantumNodeWorker,
)

__all__ = [
    "LOOPBACK_HOSTS",
    "MAX_BODY_BYTES",
    "NODE_PATHS",
    "NodeCommandFailed",
    "NodeTransportAmbiguous",
    "NodeTransportDeadline",
    "NodeTransportError",
    "NodeTransportUnavailable",
    "RemoteNodeTransport",
    "LocalNodeTransport",
]

#: Hostnames allowed to use plaintext HTTP (literal loopback only).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: Fixed worker command paths. The coordinator names node IDs only.
NODE_PATHS = {action: f"/v1/node/{action}" for action in NODE_ACTIONS}


class NodeTransportError(Exception):
    """Base class for transport failures."""


class NodeCommandFailed(NodeTransportError):
    """Definitive worker refusal: safe to report, never ambiguous."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


class NodeTransportUnavailable(NodeTransportError):
    """Definitive pre-send failure (DNS / connect / config): nothing applied."""


class NodeTransportDeadline(NodeTransportError):
    """Overall orchestration deadline exceeded (also used for read timeouts)."""


class NodeTransportAmbiguous(NodeTransportError):
    """The command may have applied: caller MUST quarantine, never retry."""


def _encode_body(body: Mapping[str, Any]) -> bytes:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BODY_BYTES:
        raise NodeCommandFailed(413, "body_too_large", "transport body exceeds 64 KiB")
    return raw


def _normalize_endpoint(node_id: str, raw_url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(raw_url.strip())
    except ValueError as exc:
        raise ValueError(f"node {node_id!r} has an unparsable endpoint") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"node {node_id!r} endpoint must be an http(s) URL")
    if parts.username or parts.password:
        raise ValueError(f"node {node_id!r} endpoint must not embed credentials")
    host = parts.hostname.lower()
    if parts.scheme == "http" and host not in LOOPBACK_HOSTS:
        raise ValueError(f"node {node_id!r} plaintext HTTP is loopback-only")
    path = parts.path.rstrip("/")
    if path not in ("", "/"):
        raise ValueError(f"node {node_id!r} endpoint must not carry a path")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


@dataclass
class _CallRecord:
    node_id: str
    action: str
    operation_id: str | None
    acknowledged: bool


class LocalNodeTransport:
    """In-process transport: same method shapes, direct worker calls.

    ``instances`` / ``tokens`` scope every command exactly like the remote
    path; when omitted they are filled from the bound worker objects so
    unit tests exercise ownership without hardcoding secrets.
    """

    def __init__(
        self,
        workers: Mapping[str, QuantumNodeWorker],
        *,
        tokens: Mapping[str, str] | None = None,
    ) -> None:
        if not workers:
            raise ValueError("LocalNodeTransport needs at least one worker")
        self._workers = dict(workers)
        self._tokens = dict(tokens or {})
        self.calls: list[_CallRecord] = []

    def _scope(self, node_id: str) -> tuple[QuantumNodeWorker, str, str]:
        try:
            worker = self._workers[node_id]
        except KeyError as exc:
            raise NodeTransportUnavailable(f"unknown node {node_id!r}") from exc
        token = self._tokens.get(node_id, worker._token)  # noqa: SLF001 - same-process test scope
        return worker, token, worker.instance_id

    def _note(self, node_id: str, action: str, operation_id: str | None, response: Mapping[str, Any]) -> None:
        acknowledged = bool(response.get("acknowledgement", response.get("ok", False)))
        self.calls.append(_CallRecord(node_id, action, operation_id, acknowledged))

    @staticmethod
    def _failed(exc: QuantumNodeError) -> NodeCommandFailed:
        return NodeCommandFailed(exc.status, exc.code, exc.detail)

    async def reserve(self, node_id: str, *, operation_id: str, resource_id: str, count: int,
                      session_id: str | None = None, instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.reserve(
                operation_id=operation_id, resource_id=resource_id, count=count,
                session_id=session_id, token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "reserve", operation_id, response)
        return response

    async def apply_circuit(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                            operations: Sequence[Mapping[str, Any]], instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.apply_circuit(
                operation_id=operation_id, lease_ids=lease_ids, operations=operations,
                token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "apply_circuit", operation_id, response)
        return response

    async def measure(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                      branch_probabilities: Sequence[float] | None = None,
                      branch_bits: Sequence[Sequence[int]] | None = None,
                      instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.measure(
                operation_id=operation_id, lease_ids=lease_ids, token=token, node=node_id,
                instance=default_instance if instance is None else instance,
                branch_probabilities=branch_probabilities, branch_bits=branch_bits,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "measure", operation_id, response)
        return response

    async def stage_conditional_state(self, node_id: str, *, operation_id: str, lease_id: str,
                                      session_id: str, rho_matrix: object,
                                      instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.stage_conditional_state(
                operation_id=operation_id, lease_id=lease_id, session_id=session_id,
                rho_matrix=rho_matrix, token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "stage_conditional_state", operation_id, response)
        return response

    async def correct(self, node_id: str, *, operation_id: str, lease_id: str, session_id: str,
                      bsm_x: int, bsm_z: int, frame_x: int, frame_z: int,
                      instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.correct(
                operation_id=operation_id, lease_id=lease_id, session_id=session_id,
                bsm_x=bsm_x, bsm_z=bsm_z, frame_x=frame_x, frame_z=frame_z,
                token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "correct", operation_id, response)
        return response

    async def transfer(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                       from_resource: str, to_resource: str,
                       instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.transfer(
                operation_id=operation_id, lease_ids=lease_ids,
                from_resource=from_resource, to_resource=to_resource,
                token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "transfer", operation_id, response)
        return response

    async def release(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                      instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            response = await worker.release(
                operation_id=operation_id, lease_ids=lease_ids, token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "release", operation_id, response)
        return response

    async def inspect(self, node_id: str, *, instance: str | None = None) -> dict[str, Any]:
        worker, token, default_instance = self._scope(node_id)
        try:
            return await worker.inspect(
                token=token, node=node_id,
                instance=default_instance if instance is None else instance,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc

    async def aclose(self) -> None:
        self.calls.clear()


class RemoteNodeTransport:
    """Operator-configured remote transport over one reusable httpx client.

    ``endpoints`` maps node IDs to exact base URLs; ``tokens`` maps node
    IDs to scoped credentials. Both are operator configuration — never
    caller request data. The client is created lazily, reused across
    commands, and closed via :meth:`aclose` (lifespan owner).
    """

    def __init__(
        self,
        endpoints: Mapping[str, str],
        tokens: Mapping[str, str],
        *,
        connect_timeout: float = 2.0,
        read_timeout: float = 5.0,
        write_timeout: float = 5.0,
        pool_timeout: float = 2.0,
        deadline: float = 20.0,
        max_connections: int = 32,
        client: Any | None = None,
    ) -> None:
        if not endpoints:
            raise ValueError("RemoteNodeTransport needs at least one endpoint")
        self._endpoints = {node: _normalize_endpoint(node, url) for node, url in endpoints.items()}
        self._tokens = dict(tokens)
        for node in self._endpoints:
            if not self._tokens.get(node):
                raise ValueError(f"node {node!r} has no configured token")
        import httpx

        self._timeout = httpx.Timeout(
            connect=connect_timeout, read=read_timeout, write=write_timeout, pool=pool_timeout
        )
        self._limits = httpx.Limits(max_connections=max_connections)
        self.deadline = float(deadline)
        self._client = client
        self._owned = client is None
        self._instances: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @property
    def client(self) -> Any | None:
        return self._client

    async def _acquire(self) -> Any:
        async with self._lock:
            if self._client is None:
                import httpx

                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    limits=self._limits,
                    trust_env=False,
                    follow_redirects=False,
                )
            return self._client

    async def aclose(self) -> None:
        async with self._lock:
            client, self._client = self._client, None
        if client is not None and self._owned:
            await client.aclose()

    async def _post(
        self,
        node_id: str,
        action: str,
        body: Mapping[str, Any],
        *,
        operation_id: str | None,
        readonly: bool,
    ) -> dict[str, Any]:
        import httpx

        try:
            base = self._endpoints[node_id]
        except KeyError as exc:
            raise NodeTransportUnavailable(f"unknown node {node_id!r}") from exc
        token = self._tokens[node_id]
        raw = _encode_body(body)
        url = base + NODE_PATHS[action]
        client = await self._acquire()
        try:
            response = await asyncio.wait_for(
                client.post(
                    url,
                    content=raw,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                ),
                timeout=self.deadline,
            )
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, TimeoutError) as exc:
            if readonly:
                raise NodeTransportDeadline(f"node {node_id!r} {action} exceeded the deadline") from exc
            raise NodeTransportAmbiguous(
                f"node {node_id!r} {action} timed out and may have applied"
            ) from exc
        except httpx.TimeoutException as exc:
            if readonly:
                raise NodeTransportDeadline(f"node {node_id!r} {action} timed out") from exc
            raise NodeTransportAmbiguous(
                f"node {node_id!r} {action} timed out and may have applied"
            ) from exc
        except httpx.NetworkError as exc:
            raise NodeTransportUnavailable(f"node {node_id!r} unreachable: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise NodeTransportAmbiguous(
                f"node {node_id!r} {action} failed ambiguously: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 500:
            if readonly:
                raise NodeTransportUnavailable(f"node {node_id!r} {action} failed with {response.status_code}")
            raise NodeTransportAmbiguous(
                f"node {node_id!r} {action} failed with {response.status_code} and may have applied"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NodeTransportAmbiguous(f"node {node_id!r} {action} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise NodeTransportAmbiguous(f"node {node_id!r} {action} returned a non-object payload")
        if response.status_code >= 400 or payload.get("ok") is False:
            raise NodeCommandFailed(
                response.status_code,
                str(payload.get("error", "remote_refused")),
                str(payload.get("detail", "worker refused the command")),
            )
        return payload

    def _instance(self, node_id: str, instance: str | None) -> str:
        if instance is not None:
            return instance
        try:
            return self._instances[node_id]
        except KeyError as exc:
            raise NodeTransportUnavailable(
                f"node {node_id!r} instance unknown: inspect the worker first"
            ) from exc

    async def inspect(self, node_id: str, *, instance: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"node": node_id, "instance": instance or ""}
        # Unscoped probe: the worker still enforces auth + instance binding.
        probe_token_instance = self._instances.get(node_id, "")
        body["instance"] = probe_token_instance if instance is None else instance
        payload = await self._post(node_id, "inspect", body, operation_id=None, readonly=True)
        if isinstance(payload.get("instance_id"), str):
            self._instances[node_id] = payload["instance_id"]
        return payload

    async def _mutate(self, node_id: str, action: str, fields: Mapping[str, Any],
                      *, operation_id: str, instance: str | None) -> dict[str, Any]:
        body = {"node": node_id, "instance": self._instance(node_id, instance),
                "operation_id": operation_id, **dict(fields)}
        return await self._post(node_id, action, body, operation_id=operation_id, readonly=False)

    async def reserve(self, node_id: str, *, operation_id: str, resource_id: str, count: int,
                      session_id: str | None = None, instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "reserve", {"resource_id": resource_id, "count": count,
                                                       "session_id": session_id},
                                  operation_id=operation_id, instance=instance)

    async def apply_circuit(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                            operations: Sequence[Mapping[str, Any]], instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "apply_circuit", {"lease_ids": list(lease_ids),
                                                             "operations": list(operations)},
                                  operation_id=operation_id, instance=instance)

    async def measure(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                      branch_probabilities: Sequence[float] | None = None,
                      branch_bits: Sequence[Sequence[int]] | None = None,
                      instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "measure", {"lease_ids": list(lease_ids),
                                                       "branch_probabilities": branch_probabilities,
                                                       "branch_bits": branch_bits},
                                  operation_id=operation_id, instance=instance)

    async def stage_conditional_state(self, node_id: str, *, operation_id: str, lease_id: str,
                                      session_id: str, rho_matrix: object,
                                      instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "stage_conditional_state", {"lease_id": lease_id,
                                                                       "session_id": session_id,
                                                                       "rho_matrix": rho_matrix},
                                  operation_id=operation_id, instance=instance)

    async def correct(self, node_id: str, *, operation_id: str, lease_id: str, session_id: str,
                      bsm_x: int, bsm_z: int, frame_x: int, frame_z: int,
                      instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "correct", {"lease_id": lease_id, "session_id": session_id,
                                                       "bsm_x": bsm_x, "bsm_z": bsm_z,
                                                       "frame_x": frame_x, "frame_z": frame_z},
                                  operation_id=operation_id, instance=instance)

    async def transfer(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                       from_resource: str, to_resource: str,
                       instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "transfer", {"lease_ids": list(lease_ids),
                                                        "from_resource": from_resource,
                                                        "to_resource": to_resource},
                                  operation_id=operation_id, instance=instance)

    async def release(self, node_id: str, *, operation_id: str, lease_ids: Sequence[str],
                      instance: str | None = None) -> dict[str, Any]:
        return await self._mutate(node_id, "release", {"lease_ids": list(lease_ids)},
                                  operation_id=operation_id, instance=instance)
