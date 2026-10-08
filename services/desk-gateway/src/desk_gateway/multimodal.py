"""Multi-modal artifact ingestion pipeline and streaming tool execution bus.

Implements REQ-MM-001 (multi-modal artifact ingestion and content inspection),
REQ-MM-002 (streaming tool execution bus with telemetry frames), and
REQ-MM-003 (cancellation supervisor and backpressure management).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set
from uuid import uuid4


class ArtifactType(str, Enum):
    """Categorized multi-modal artifact types."""
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    VIDEO = "video"
    BINARY = "binary"


# Recognized MIME signatures (magic bytes)
MAGIC_SIGNATURES: Dict[bytes, tuple[str, ArtifactType]] = {
    b"\x89PNG\r\n\x1a\n": ("image/png", ArtifactType.IMAGE),
    b"\xff\xd8\xff": ("image/jpeg", ArtifactType.IMAGE),
    b"GIF87a": ("image/gif", ArtifactType.IMAGE),
    b"GIF89a": ("image/gif", ArtifactType.IMAGE),
    b"RIFF": ("audio/wav", ArtifactType.AUDIO),  # RIFF....WAVE checked dynamically
    b"%PDF-": ("application/pdf", ArtifactType.DOCUMENT),
    b"ID3": ("audio/mpeg", ArtifactType.AUDIO),
    b"\xff\xfb": ("audio/mpeg", ArtifactType.AUDIO),
    b"\xff\xf3": ("audio/mpeg", ArtifactType.AUDIO),
}

DISALLOWED_SIGNATURES = [
    b"MZ",  # Windows PE Executable
    b"\x7fELF",  # Linux ELF Executable
    b"#!",  # Shell script / shebang
]


@dataclass
class ArtifactMetadata:
    """Metadata describing an ingested multi-modal artifact."""
    artifact_id: str
    artifact_type: ArtifactType
    mime_type: str
    size_bytes: int
    sha256: str
    filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    tenant_id: str = "default"
    seat_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiModalArtifactPipeline:
    """Ingests, validates, inspects, and registers multi-modal artifacts."""

    def __init__(self, max_payload_bytes: int = 50 * 1024 * 1024) -> None:
        self.max_payload_bytes = max_payload_bytes
        self._artifacts: Dict[str, ArtifactMetadata] = {}
        self._payload_store: Dict[str, bytes] = {}

    def inspect_bytes(self, payload: bytes) -> tuple[str, ArtifactType]:
        """Inspect byte header to detect MIME type and ArtifactType.
        
        Raises ValueError if content is invalid or dangerous executable.
        """
        if not payload:
            raise ValueError("Artifact payload cannot be empty")

        for sig in DISALLOWED_SIGNATURES:
            if payload.startswith(sig):
                raise ValueError("Disallowed executable or script format detected in payload")

        # Check RIFF for WAV
        if payload.startswith(b"RIFF") and len(payload) >= 12 and payload[8:12] == b"WAVE":
            return "audio/wav", ArtifactType.AUDIO

        # Check WEBP
        if payload.startswith(b"RIFF") and len(payload) >= 12 and payload[8:12] == b"WEBP":
            return "image/webp", ArtifactType.IMAGE

        for sig, (mime, art_type) in MAGIC_SIGNATURES.items():
            if sig != b"RIFF" and payload.startswith(sig):
                return mime, art_type

        # Fallback for plain text or generic binary
        if len(payload) > 0 and all(32 <= b <= 126 or b in (9, 10, 13) for b in payload[:min(512, len(payload))]):
            return "text/plain", ArtifactType.DOCUMENT

        return "application/octet-stream", ArtifactType.BINARY

    def ingest(
        self,
        payload: bytes,
        filename: Optional[str] = None,
        tenant_id: str = "default",
        seat_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactMetadata:
        """Validate, store, and record artifact metadata."""
        if len(payload) > self.max_payload_bytes:
            raise ValueError(f"Payload size {len(payload)} bytes exceeds maximum {self.max_payload_bytes} bytes")

        mime_type, art_type = self.inspect_bytes(payload)
        sha256_hash = hashlib.sha256(payload).hexdigest()
        artifact_id = f"art-{uuid4().hex[:12]}"

        # Basic dimensions extraction for PNG if possible
        width, height = None, None
        if mime_type == "image/png" and len(payload) >= 24:
            width = int.from_bytes(payload[16:20], byteorder="big")
            height = int.from_bytes(payload[20:24], byteorder="big")

        meta = ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_type=art_type,
            mime_type=mime_type,
            size_bytes=len(payload),
            sha256=sha256_hash,
            filename=filename,
            width=width,
            height=height,
            tenant_id=tenant_id,
            seat_id=seat_id,
            created_at=time.time(),
            metadata=extra_metadata or {},
        )

        self._artifacts[artifact_id] = meta
        self._payload_store[artifact_id] = payload
        return meta

    def get_metadata(self, artifact_id: str) -> Optional[ArtifactMetadata]:
        return self._artifacts.get(artifact_id)

    def get_payload(self, artifact_id: str) -> Optional[bytes]:
        return self._payload_store.get(artifact_id)


class StreamingFrameType(str, Enum):
    """Types of streaming frames emitted during tool execution."""
    START = "start"
    CHUNK = "chunk"
    TELEMETRY = "telemetry"
    ERROR = "error"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


@dataclass
class StreamingFrame:
    """A discrete frame delivered over the streaming execution bus."""
    stream_id: str
    sequence: int
    frame_type: StreamingFrameType
    tool_name: str
    payload: Any
    elapsed_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_sse_event(self) -> str:
        """Format as standard Server-Sent Event."""
        import json
        data = json.dumps({
            "stream_id": self.stream_id,
            "seq": self.sequence,
            "type": self.frame_type.value,
            "tool": self.tool_name,
            "payload": self.payload,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "timestamp": self.timestamp,
        })
        return f"event: {self.frame_type.value}\ndata: {data}\n\n"


class StreamCancellationSupervisor:
    """Supervises active streaming executions and handles graceful cancellations."""

    def __init__(self) -> None:
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._cancellation_events: Dict[str, asyncio.Event] = {}
        self._cleanup_callbacks: Dict[str, List[Callable[[], None]]] = {}
        self._cancelled_streams: Set[str] = set()

    def register_stream(self, stream_id: str, task: Optional[asyncio.Task] = None) -> asyncio.Event:
        event = asyncio.Event()
        self._cancellation_events[stream_id] = event
        if task:
            self._active_tasks[stream_id] = task
        if stream_id not in self._cleanup_callbacks:
            self._cleanup_callbacks[stream_id] = []
        return event

    def on_cleanup(self, stream_id: str, callback: Callable[[], None]) -> None:
        if stream_id not in self._cleanup_callbacks:
            self._cleanup_callbacks[stream_id] = []
        self._cleanup_callbacks[stream_id].append(callback)

    def is_cancelled(self, stream_id: str) -> bool:
        if stream_id in self._cancelled_streams:
            return True
        event = self._cancellation_events.get(stream_id)
        return event.is_set() if event else False

    def cancel_stream(self, stream_id: str, reason: str = "Client disconnect") -> bool:
        """Signal cancellation and abort active task."""
        if stream_id in self._cancelled_streams:
            return False

        self._cancelled_streams.add(stream_id)
        event = self._cancellation_events.get(stream_id)
        if event:
            event.set()

        task = self._active_tasks.get(stream_id)
        if task and not task.done():
            task.cancel()

        # Run registered cleanup callbacks
        for cb in self._cleanup_callbacks.get(stream_id, []):
            try:
                cb()
            except Exception:
                pass

        return True

    def unregister(self, stream_id: str) -> None:
        self._active_tasks.pop(stream_id, None)
        self._cancellation_events.pop(stream_id, None)
        self._cleanup_callbacks.pop(stream_id, None)


class StreamingToolBus:
    """Bus for orchestrating streaming tool executions and emitting frames."""

    def __init__(self, supervisor: Optional[StreamCancellationSupervisor] = None, max_queue_size: int = 500) -> None:
        self.supervisor = supervisor or StreamCancellationSupervisor()
        self.max_queue_size = max_queue_size
        self._stream_queues: Dict[str, asyncio.Queue] = {}
        self._stream_status: Dict[str, str] = {}

    async def execute_stream(
        self,
        tool_name: str,
        generator_func: Callable[[], AsyncGenerator[tuple[str, Any], None]],
        stream_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamingFrame, None]:
        """Wrap an async generator and yield structured StreamingFrames with backpressure."""
        stream_id = stream_id or f"stream-{uuid4().hex[:12]}"
        cancel_event = self.supervisor.register_stream(stream_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue_size)
        self._stream_queues[stream_id] = queue
        self._stream_status[stream_id] = "active"

        start_time = time.perf_counter()
        seq = 0

        # Yield START frame
        seq += 1
        start_frame = StreamingFrame(
            stream_id=stream_id,
            sequence=seq,
            frame_type=StreamingFrameType.START,
            tool_name=tool_name,
            payload={"status": "started"},
            elapsed_ms=0.0,
        )
        yield start_frame

        try:
            async for frame_type_str, chunk_data in generator_func():
                if cancel_event.is_set():
                    self._stream_status[stream_id] = "cancelled"
                    seq += 1
                    yield StreamingFrame(
                        stream_id=stream_id,
                        sequence=seq,
                        frame_type=StreamingFrameType.CANCELLED,
                        tool_name=tool_name,
                        payload={"reason": "Stream execution cancelled by supervisor"},
                        elapsed_ms=(time.perf_counter() - start_time) * 1000,
                    )
                    return

                seq += 1
                ftype = (
                    StreamingFrameType.TELEMETRY
                    if frame_type_str == "telemetry"
                    else StreamingFrameType.CHUNK
                )
                yield StreamingFrame(
                    stream_id=stream_id,
                    sequence=seq,
                    frame_type=ftype,
                    tool_name=tool_name,
                    payload=chunk_data,
                    elapsed_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Execution completed normally
            seq += 1
            self._stream_status[stream_id] = "completed"
            yield StreamingFrame(
                stream_id=stream_id,
                sequence=seq,
                frame_type=StreamingFrameType.COMPLETE,
                tool_name=tool_name,
                payload={"status": "completed", "total_frames": seq},
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        except asyncio.CancelledError:
            self._stream_status[stream_id] = "cancelled"
            seq += 1
            yield StreamingFrame(
                stream_id=stream_id,
                sequence=seq,
                frame_type=StreamingFrameType.CANCELLED,
                tool_name=tool_name,
                payload={"reason": "Async task cancelled"},
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )
            raise
        except Exception as exc:
            self._stream_status[stream_id] = "error"
            seq += 1
            yield StreamingFrame(
                stream_id=stream_id,
                sequence=seq,
                frame_type=StreamingFrameType.ERROR,
                tool_name=tool_name,
                payload={"error": str(exc)},
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )
        finally:
            self.supervisor.unregister(stream_id)
            self._stream_queues.pop(stream_id, None)

    def get_status(self, stream_id: str) -> str:
        return self._stream_status.get(stream_id, "unknown")
