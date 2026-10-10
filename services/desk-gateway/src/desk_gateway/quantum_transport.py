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
    host_part = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{host_part}{port}"


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

    async def inspect(self, node_id: str, *, instance: str | None = None,
                      lease_offset: int = 0, lease_limit: int = 64,
                      resource_ids: list[str] | None = None) -> dict[str, Any]:
        worker, token, _ = self._scope(node_id)
        try:
            return await worker.inspect(
                token=token, node=node_id, instance=instance,
                lease_offset=lease_offset, lease_limit=lease_limit,
                resource_ids=resource_ids,
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc

    def _qkd_envelope(self, node_id: str, *, operation_id: str, session_id: str,
                      action: str, payload: Mapping[str, Any],
                      instance: str | None) -> tuple[QuantumNodeWorker, str, dict[str, Any]]:
        """Build one QKD envelope through the exact wire codec.

        The envelope is serialized and measured exactly as the remote path
        sends it (64 KiB actual-bytes admission, JSON normalization), then
        dispatched to the worker; there is no in-process validation bypass.
        """
        if not isinstance(action, str):
            raise ValueError("qkd action must be a string")
        if not isinstance(payload, Mapping):
            raise ValueError("qkd payload must be a mapping of wire DTOs")
        worker, token, default_instance = self._scope(node_id)
        envelope = {
            "node": node_id,
            "instance": default_instance if instance is None else instance,
            "operation_id": operation_id,
            "session_id": session_id,
            "action": action,
            "payload": dict(payload),
        }
        wire = json.loads(_encode_body(envelope).decode("utf-8"))
        return worker, token, wire

    async def qkd_step(self, node_id: str, *, operation_id: str, session_id: str,
                       action: str, payload: Mapping[str, Any],
                       instance: str | None = None) -> dict[str, Any]:
        """Coordinator QKD step over the fixed ``qkd_step`` envelope."""
        worker, token, wire = self._qkd_envelope(
            node_id, operation_id=operation_id, session_id=session_id,
            action=action, payload=payload, instance=instance,
        )
        try:
            response = await worker.qkd_step(
                operation_id=wire["operation_id"], session_id=wire["session_id"],
                action=wire["action"], payload=wire["payload"],
                token=token, node=node_id, instance=wire["instance"],
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "qkd_step", operation_id, response)
        return response

    async def qkd_owner(self, node_id: str, *, operation_id: str, session_id: str,
                        action: str, payload: Mapping[str, Any],
                        instance: str | None = None) -> dict[str, Any]:
        """Owner-private capability path over the fixed ``qkd_owner`` envelope.

        Same wire codec as the remote path; the gateway never proxies this.
        """
        worker, token, wire = self._qkd_envelope(
            node_id, operation_id=operation_id, session_id=session_id,
            action=action, payload=payload, instance=instance,
        )
        try:
            response = await worker.qkd_owner(
                operation_id=wire["operation_id"], session_id=wire["session_id"],
                action=wire["action"], payload=wire["payload"],
                token=token, node=node_id, instance=wire["instance"],
            )
        except QuantumNodeError as exc:
            raise self._failed(exc) from exc
        self._note(node_id, "qkd_owner", operation_id, response)
        return response

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
        # Decode ourselves: httpx's aiter_bytes may inflate one compressed
        # wire chunk without a bound before yielding it to our byte check.
        # Only advertised codecs are admitted; raw and decoded bytes each
        # have a hard cap, with at most one bounded chunk beyond that cap.
        import zlib

        deadline_at = time.monotonic() + self.deadline

        def bad_reply(detail: str) -> NodeTransportError:
            failure = NodeTransportUnavailable if readonly else NodeTransportAmbiguous
            return failure(f"node {node_id!r} {action} {detail}")

        async def receive() -> tuple[int, bytearray]:
            data = bytearray()
            raw_count = 0
            chunk_size = 4096

            def admit(chunk: bytes) -> None:
                if time.monotonic() >= deadline_at:
                    raise asyncio.TimeoutError
                if len(data) + len(chunk) > MAX_BODY_BYTES:
                    raise bad_reply("returned an oversized reply")
                data.extend(chunk)

            async with client.stream(
                "POST", url, content=raw,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "gzip, deflate, identity",
                },
            ) as response:
                encoding = response.headers.get("content-encoding", "identity").strip().lower()
                if encoding not in ("identity", "gzip", "deflate"):
                    raise bad_reply("returned an unsupported reply encoding")
                # Injected transports can supply an already-read response.
                # Its content is already decoded; admit before copying it.
                if response.is_stream_consumed:
                    admit(response.content)
                    return response.status_code, data
                decoder = None if encoding == "identity" else zlib.decompressobj(
                    16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
                )
                async for chunk in response.aiter_raw(chunk_size=chunk_size):
                    if time.monotonic() >= deadline_at:
                        raise asyncio.TimeoutError
                    raw_count += len(chunk)
                    if raw_count > MAX_BODY_BYTES:
                        raise bad_reply("returned an oversized reply")
                    if decoder is None:
                        admit(chunk)
                        continue
                    try:
                        pending = chunk
                        while True:
                            decoded = decoder.decompress(pending, chunk_size)
                            admit(decoded)
                            pending = decoder.unconsumed_tail
                            if decoder.unused_data:
                                raise bad_reply("returned an invalid compressed reply")
                            if not pending and len(decoded) < chunk_size:
                                break
                    except zlib.error as exc:
                        raise bad_reply("returned an invalid compressed reply") from exc
                if decoder is not None and not decoder.eof:
                    raise bad_reply("returned an incomplete compressed reply")
                return response.status_code, data

        try:
            status, response_bytes = await asyncio.wait_for(receive(), timeout=self.deadline)
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
        except httpx.ConnectError as exc:
            # Definitive pre-send failure (DNS / refused / connect-timeout):
            # nothing was sent, so the operation was not applied.
            raise NodeTransportUnavailable(f"node {node_id!r} unreachable: {type(exc).__name__}") from exc
        except httpx.NetworkError as exc:
            # Post-send ReadError / WriteError / CloseError: the command may
            # have applied. Mutating calls quarantine (ambiguous); the
            # read-only probe carries no effect, so it stays unavailable.
            if readonly:
                raise NodeTransportUnavailable(f"node {node_id!r} unreachable: {type(exc).__name__}") from exc
            raise NodeTransportAmbiguous(
                f"node {node_id!r} {action} failed ambiguously: {type(exc).__name__}"
            ) from exc
        except httpx.HTTPError as exc:
            raise bad_reply(f"failed: {type(exc).__name__}") from exc
        if status >= 500:
            raise bad_reply(f"failed with {status}")
        try:
            payload = json.loads(response_bytes)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise bad_reply("returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise bad_reply("returned a non-object payload")
        if payload.get("ok") is not True and payload.get("ok") is not False:
            raise bad_reply("returned a malformed acknowledgement")
        if status >= 400 or payload.get("ok") is False:
            raise NodeCommandFailed(
                status,
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

    async def inspect(self, node_id: str, *, instance: str | None = None,
                      lease_offset: int = 0, lease_limit: int = 64,
                      resource_ids: list[str] | None = None) -> dict[str, Any]:
        # Discovery never carries a cached instance; explicit inspection
        # keeps its original pin. Snapshots do not refute in-flight effects.
        if resource_ids is not None and not isinstance(resource_ids, list):
            raise NodeCommandFailed(400, "invalid_resources", "resource_ids must be a list")
        body: dict[str, Any] = {
            "node": node_id, "instance": instance if instance is not None else "",
            "lease_offset": lease_offset, "lease_limit": lease_limit,
            "resource_ids": resource_ids,
        }
        payload = await self._post(node_id, "inspect", body, operation_id=None, readonly=True)
        if instance in (None, "") and isinstance(payload.get("instance_id"), str):
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

    async def _qkd_post(self, node_id: str, path: str, *, operation_id: str, session_id: str,
                        action: str, payload: Mapping[str, Any],
                        instance: str | None, readonly: bool) -> dict[str, Any]:
        """One fixed QKD envelope: pinned original instance, measured caps.

        The coordinator names the node only; token and base URL stay in
        operator configuration. ``lengths`` and ``capability`` are readonly
        (deadline semantics); every other QKD action is a pinned mutation.
        """
        if not isinstance(action, str):
            raise ValueError("qkd action must be a string")
        if not isinstance(payload, Mapping):
            raise ValueError("qkd payload must be a mapping of wire DTOs")
        body = {"node": node_id, "instance": self._instance(node_id, instance),
                "operation_id": operation_id, "session_id": session_id,
                "action": action, "payload": dict(payload)}
        return await self._post(node_id, path, body, operation_id=operation_id, readonly=readonly)

    async def qkd_step(self, node_id: str, *, operation_id: str, session_id: str,
                       action: str, payload: Mapping[str, Any],
                       instance: str | None = None) -> dict[str, Any]:
        """Coordinator QKD step over ``POST /v1/node/qkd_step``."""
        return await self._qkd_post(node_id, "qkd_step", operation_id=operation_id,
                                    session_id=session_id, action=action, payload=payload,
                                    instance=instance, readonly=action == "lengths")

    async def qkd_owner(self, node_id: str, *, operation_id: str, session_id: str,
                        action: str, payload: Mapping[str, Any],
                        instance: str | None = None) -> dict[str, Any]:
        """Owner-private capability path over ``POST /v1/node/qkd_owner``.

        Transport-level only; the gateway never proxies this path.
        """
        return await self._qkd_post(node_id, "qkd_owner", operation_id=operation_id,
                                    session_id=session_id, action=action, payload=payload,
                                    instance=instance, readonly=action == "capability")
