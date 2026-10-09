"""Tests for Multi-Modal Artifact Pipeline and Streaming Tool Execution Bus (Phase 20)."""

import asyncio
import base64
import pytest
from desk_gateway.multimodal import (
    ArtifactMetadata,
    ArtifactType,
    MultiModalArtifactPipeline,
    StreamCancellationSupervisor,
    StreamingFrame,
    StreamingFrameType,
    StreamingToolBus,
)


def test_artifact_pipeline_png_ingestion():
    pipeline = MultiModalArtifactPipeline()
    # 24-byte minimal valid PNG header with width 100 and height 200
    # PNG signature: 8 bytes
    # IHDR chunk length: 4 bytes (0,0,0,13)
    # IHDR chunk type: 4 bytes 'IHDR'
    # Width: 4 bytes (100) -> 0x00, 0x00, 0x00, 0x64
    # Height: 4 bytes (200) -> 0x00, 0x00, 0x00, 0xc8
    png_header = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\r"
        b"IHDR"
        b"\x00\x00\x00\x64"
        b"\x00\x00\x00\xc8"
        b"\x08\x02\x00\x00\x00"
    )
    meta = pipeline.ingest(
        payload=png_header,
        filename="diagram.png",
        tenant_id="tenant-alpha",
        seat_id="lead",
    )
    assert meta.artifact_id.startswith("art-")
    assert meta.artifact_type == ArtifactType.IMAGE
    assert meta.mime_type == "image/png"
    assert meta.width == 100
    assert meta.height == 200
    assert meta.tenant_id == "tenant-alpha"
    assert pipeline.get_metadata(meta.artifact_id) == meta
    assert pipeline.get_payload(meta.artifact_id) == png_header


def test_artifact_pipeline_audio_ingestion():
    pipeline = MultiModalArtifactPipeline()
    # RIFF....WAVE minimal header
    wav_payload = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    meta = pipeline.ingest(payload=wav_payload, filename="voice.wav")
    assert meta.artifact_type == ArtifactType.AUDIO
    assert meta.mime_type == "audio/wav"


def test_artifact_pipeline_pdf_ingestion():
    pipeline = MultiModalArtifactPipeline()
    pdf_payload = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj"
    meta = pipeline.ingest(payload=pdf_payload, filename="spec.pdf")
    assert meta.artifact_type == ArtifactType.DOCUMENT
    assert meta.mime_type == "application/pdf"


def test_artifact_pipeline_executable_rejection():
    pipeline = MultiModalArtifactPipeline()
    exe_payload = b"MZ\x90\x00\x03\x00\x00\x00"
    with pytest.raises(ValueError, match="Disallowed executable"):
        pipeline.ingest(exe_payload)

    elf_payload = b"\x7fELF\x02\x01\x01\x00"
    with pytest.raises(ValueError, match="Disallowed executable"):
        pipeline.ingest(elf_payload)


@pytest.mark.asyncio
async def test_streaming_tool_bus_execution():
    supervisor = StreamCancellationSupervisor()
    bus = StreamingToolBus(supervisor=supervisor)

    async def sample_generator():
        yield ("telemetry", {"phase": "analyzing", "percent": 25})
        yield ("chunk", {"text": "Step 1 complete"})
        yield ("telemetry", {"phase": "generating", "percent": 75})
        yield ("chunk", {"text": "Step 2 complete"})

    frames = []
    async for frame in bus.execute_stream(tool_name="test_runner", generator_func=sample_generator, stream_id="str-101"):
        frames.append(frame)

    assert len(frames) == 6  # START + 2 telemetry + 2 chunks + COMPLETE
    assert frames[0].frame_type == StreamingFrameType.START
    assert frames[1].frame_type == StreamingFrameType.TELEMETRY
    assert frames[2].frame_type == StreamingFrameType.CHUNK
    assert frames[3].frame_type == StreamingFrameType.TELEMETRY
    assert frames[4].frame_type == StreamingFrameType.CHUNK
    assert frames[5].frame_type == StreamingFrameType.COMPLETE
    assert frames[5].payload["total_frames"] == 6

    # Test SSE format output
    sse_text = frames[2].to_sse_event()
    assert "event: chunk\n" in sse_text
    assert '"tool": "test_runner"' in sse_text


@pytest.mark.asyncio
async def test_streaming_tool_bus_cancellation():
    supervisor = StreamCancellationSupervisor()
    bus = StreamingToolBus(supervisor=supervisor)

    stream_id = "str-cancel-test"
    cleanup_ran = False

    def on_cleanup():
        nonlocal cleanup_ran
        cleanup_ran = True

    async def long_generator():
        yield ("chunk", {"data": 1})
        # Simulate delay where cancellation happens
        supervisor.cancel_stream(stream_id, reason="User abort")
        await asyncio.sleep(0.01)
        yield ("chunk", {"data": 2})

    supervisor.on_cleanup(stream_id, on_cleanup)

    frames = []
    async for frame in bus.execute_stream(tool_name="long_task", generator_func=long_generator, stream_id=stream_id):
        frames.append(frame)

    assert any(f.frame_type == StreamingFrameType.CANCELLED for f in frames)
    assert cleanup_ran is True


def test_multimodal_api_routes():
    from starlette.testclient import TestClient
    from desk_gateway.server import build_app

    app, _ = build_app()
    client = TestClient(app)

    # 1. Ingest via JSON base64
    fake_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\r"
        b"IHDR"
        b"\x00\x00\x00\x20"
        b"\x00\x00\x00\x20"
        b"\x08\x02\x00\x00\x00"
    )
    b64_data = base64.b64encode(fake_png).decode("utf-8")
    resp = client.post(
        "/v1/multimodal/ingest",
        json={
            "payload_b64": b64_data,
            "filename": "icon.png",
            "tenant_id": "tenant-test",
            "seat_id": "architect",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    artifact_id = data["artifact"]["artifact_id"]
    assert artifact_id.startswith("art-")
    assert data["artifact"]["mime_type"] == "image/png"
    assert data["artifact"]["width"] == 32
    assert data["artifact"]["height"] == 32

    # 2. Get artifact metadata
    get_resp = client.get(f"/v1/multimodal/artifacts/{artifact_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["artifact"]["artifact_id"] == artifact_id

    # 3. Streaming execute endpoint
    exec_resp = client.post(
        "/v1/tools/streaming/execute",
        json={
            "tool_name": "build_compiler",
            "mock_chunks": ["compiling module 1", "compiling module 2"],
            "chunk_delay": 0.0,
        },
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["ok"] is True
    assert exec_data["total_frames"] == 6
    stream_id = exec_data["stream_id"]

    # 4. Stream status endpoint
    status_resp = client.get(f"/v1/tools/streaming/{stream_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "completed"

    # 5. Cancel endpoint
    cancel_resp = client.post("/v1/tools/streaming/test-stream-xyz/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["stream_id"] == "test-stream-xyz"

