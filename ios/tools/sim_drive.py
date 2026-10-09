"""Drive the iOS Simulator through ``xcrun simctl``.

``boot`` creates a device from the caller's ``--device-type`` and ``--runtime``
(or reuses one this run already created) and prints its UDID. ``shutdown`` and
``erase`` touch only that UDID, and only when the caller passes it explicitly
and it is in the ledger ``boot`` wrote under ``--out``.

On Linux, or when ``xcrun`` is missing, every subcommand skips with exit 3.
``--dry-run`` prints the argv as JSON and spawns nothing. A skip is not a pass.
"""

from __future__ import annotations

import fcntl
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

SKIP = 3
LEDGER_NAME = "created-udids.json"
UDID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def _tail(proc) -> str:
    stdout = getattr(proc, "stdout", None) or ""
    stderr = getattr(proc, "stderr", None) or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    return (stdout + stderr)[-2000:]


def _dry(argv: list[str], **extra) -> dict:
    body = {"status": "dry-run", "argv": argv, "exit_code": 0, "invoked": False}
    body.update(extra)
    return body


def _skipped(reason: str, argv: list[str]) -> dict:
    return {
        "status": "skipped",
        "reason": f"skipped: {reason}",
        "argv": argv,
        "exit_code": SKIP,
        "invoked": False,
    }


def _error(reason: str, **extra) -> dict:
    body = {"status": "error", "reason": reason, "exit_code": 2, "invoked": False}
    body.update(extra)
    return body


def _failed(reason: str, argv: list[str], proc, **extra) -> dict:
    body = {
        "status": "failed",
        "reason": reason,
        "argv": argv,
        "exit_code": 1,
        "invoked": True,
        "tool_exit_code": getattr(proc, "returncode", None),
        "output_tail": _tail(proc),
    }
    body.update(extra)
    return body


def _system(system_name: str | None) -> str:
    return system_name if system_name is not None else platform.system()


def _blocked(binary: str, argv: list[str], *, dry_run: bool, system_name: str | None, which) -> dict | None:
    """Skip when a real spawn would need macOS or a missing binary. Dry-run is not a skip."""
    if dry_run:
        return None
    if _system(system_name) != "Darwin":
        return _skipped("not on macOS", argv)
    if not which(binary):
        return _skipped(f"{binary} is not on PATH", argv)
    return None


def _resolve(which, binary: str, argv: list[str]) -> list[str]:
    found = which(binary)
    if not found:
        return list(argv)
    return [found, *argv[1:]]


def _run(runner, argv: list[str], *, timeout: int | None = None):
    kwargs = {
        "capture_output": True,
        "text": True,
        "check": False,
        "env": os.environ.copy(),
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return runner(argv, **kwargs)


def _state_text(proc) -> str:
    return _tail(proc).lower()


def _already(proc, state: str) -> bool:
    return f"current state: {state.lower()}" in _state_text(proc)


def ledger_path(out: Path) -> Path:
    return Path(out) / LEDGER_NAME


@contextmanager
def _ledger_dir(out: Path):
    """Pin and lock the directory, not the replaceable ledger inode."""
    out.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        os.close(fd)


def _read_ledger(directory: int) -> list[dict]:
    try:
        fd = os.open(LEDGER_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return []
    with os.fdopen(fd, "r", encoding="utf-8") as ledger:
        if not stat.S_ISREG(os.fstat(ledger.fileno()).st_mode):
            raise ValueError("created-udid ledger must be a regular file, not a symlink or special file")
        try:
            data = json.load(ledger)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict) and isinstance(row.get("udid"), str)]


def _load_ledger(out: Path) -> list[dict]:
    with _ledger_dir(out) as directory:
        return _read_ledger(directory)


def _append_ledger(out: Path, row: dict) -> None:
    with _ledger_dir(out) as directory:
        rows = _read_ledger(directory)
        rows.append(row)
        temporary = f".{LEDGER_NAME}-{uuid4().hex}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as ledger:
                ledger.write(json.dumps(rows, indent=2) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            try:
                existing = os.stat(LEDGER_NAME, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and not stat.S_ISREG(existing.st_mode):
                raise ValueError("refusing an unsafe created-udid ledger")
            # Both names are relative to the pinned directory. A swapped path or
            # symlink can never redirect this replacement to an outside file.
            os.replace(temporary, LEDGER_NAME, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass


def _runtime_compatible(flag: str, runtime_key: str) -> bool:
    flag_n = re.sub(r"[^a-z0-9]", "", flag.lower())
    key_n = re.sub(r"[^a-z0-9]", "", runtime_key.lower())
    return bool(flag_n) and flag_n in key_n


def _match_existing(list_stdout: str, ledger: list[dict], device_type: str, runtime: str) -> str | None:
    wanted = {
        row["udid"]
        for row in ledger
        if row.get("device_type") == device_type and row.get("runtime") == runtime
    }
    if not wanted or not list_stdout:
        return None
    try:
        data = json.loads(list_stdout)
    except json.JSONDecodeError:
        return None
    devices = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(devices, dict):
        return None
    for runtime_key, entries in devices.items():
        if not _runtime_compatible(runtime, str(runtime_key)):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("udid") in wanted:
                return str(entry["udid"])
    return None


def _require_out_dir(out: Path | None) -> dict | None:
    if out is None:
        return _error("--out is required so evidence stays in the directory the caller passed")
    if Path(out).exists() and not Path(out).is_dir():
        return _error(f"--out is not a directory: {out}")
    return None


def _child(out: Path, name: str) -> Path | None:
    root = Path(out).resolve()
    child = (Path(out) / name).resolve()
    try:
        child.relative_to(root)
    except ValueError:
        return None
    return child


def _parse_udid(stdout: str) -> str | None:
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[-1]
    if UDID_RE.match(candidate):
        return candidate
    return None


def boot(
    device_type: str,
    runtime: str,
    out: Path | None = None,
    name: str | None = None,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not device_type or not runtime:
        return _error("--device-type and --runtime are required")
    label = name or device_type
    create_argv = ["xcrun", "simctl", "create", label, device_type, runtime]
    boot_argv_template = ["xcrun", "simctl", "boot", "<udid-from-create>"]
    if dry_run:
        return _dry(create_argv, boot_argv=boot_argv_template)
    blocked = _blocked("xcrun", create_argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    out = Path(out)
    try:
        ledger = _load_ledger(out)
    except (OSError, ValueError) as exc:
        return _error(f"refusing unsafe or unreadable created-udid ledger: {exc}")
    list_argv = _resolve(which, "xcrun", ["xcrun", "simctl", "list", "devices", "-j"])
    listed = _run(runner, list_argv)
    reused = None
    if getattr(listed, "returncode", 1) == 0:
        reused = _match_existing(getattr(listed, "stdout", "") or "", ledger, device_type, runtime)
    if reused:
        udid = reused
        created = False
        create_used: list[str] | None = None
    else:
        create_used = _resolve(which, "xcrun", create_argv)
        created_proc = _run(runner, create_used)
        if created_proc.returncode != 0:
            return _failed("simctl create failed", create_used, created_proc)
        udid = _parse_udid(getattr(created_proc, "stdout", "") or "")
        if not udid:
            return _failed("simctl create did not print a UDID", create_used, created_proc)
        try:
            _append_ledger(out, {"udid": udid, "device_type": device_type, "runtime": runtime, "name": label})
        except (OSError, ValueError) as exc:
            return _error(f"could not safely save created-udid ledger: {exc}", invoked=True, udid=udid)
        created = True
    boot_argv = _resolve(which, "xcrun", ["xcrun", "simctl", "boot", udid])
    booted = _run(runner, boot_argv)
    if booted.returncode != 0 and not _already(booted, "Booted"):
        return _failed("simctl boot failed", boot_argv, booted, udid=udid, created=created)
    return {
        "status": "booted",
        "udid": udid,
        "created": created,
        "reused": not created,
        "device_type": device_type,
        "runtime": runtime,
        "argv": create_used or boot_argv,
        "boot_argv": boot_argv,
        "exit_code": 0,
        "invoked": True,
        "ledger": str(ledger_path(out)),
    }


def install(
    udid: str,
    app: str,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid or not app:
        return _error("--udid and --app are required")
    argv = ["xcrun", "simctl", "install", udid, app]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl install failed", resolved, proc)
    return {"status": "installed", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid}


def launch(
    udid: str,
    bundle_id: str,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid or not bundle_id:
        return _error("--udid and --bundle-id are required")
    argv = ["xcrun", "simctl", "launch", udid, bundle_id]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl launch failed", resolved, proc)
    return {"status": "launched", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid}


def screenshot(
    udid: str,
    out: Path | None,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid:
        return _error("--udid is required")
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    shot = _child(Path(out), "screenshot.png")
    if shot is None:
        return _error("screenshot path escaped --out")
    argv = ["xcrun", "simctl", "io", udid, "screenshot", str(shot)]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    Path(out).mkdir(parents=True, exist_ok=True)
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl screenshot failed", resolved, proc)
    return {"status": "recorded", "argv": resolved, "exit_code": 0, "invoked": True, "artifact": str(shot)}


def _movie_atoms(movie, start: int, end: int):
    offset = start
    while offset < end:
        movie.seek(offset)
        header = movie.read(8)
        if len(header) != 8:
            raise ValueError("truncated MOV atom")
        size = int.from_bytes(header[:4], "big")
        header_size = 8
        if size == 1:
            extended = movie.read(8)
            if len(extended) != 8:
                raise ValueError("truncated extended MOV atom")
            size = int.from_bytes(extended, "big")
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            raise ValueError("invalid MOV atom length")
        yield header[4:], offset + header_size, offset + size
        offset += size


def _movie_number(movie, position: int, end: int, size: int = 4, *, signed: bool = False) -> int:
    if position < 0 or position + size > end:
        raise ValueError("truncated MOV sample metadata")
    movie.seek(position)
    data = movie.read(size)
    if len(data) != size:
        raise ValueError("truncated MOV sample metadata")
    return int.from_bytes(data, "big", signed=signed)


def _movie_table(movie, start: int, end: int) -> dict:
    table = {}
    for kind, payload, stop in _movie_atoms(movie, start, end):
        if kind in table:
            raise ValueError("duplicate MOV sample metadata")
        table[kind] = (payload, stop)
    return table


def _movie_media_range(start: int, size: int, media: list[tuple[int, int]]) -> bool:
    return size > 0 and any(lower <= start and start + size <= upper for lower, upper in media)


def _movie_sample_table(movie, table: dict, media: list[tuple[int, int]]) -> tuple[int, int]:
    """Validate classic sample tables without reading or copying media payloads."""
    start, end = table[b"stsd"]
    descriptions = _movie_number(movie, start + 4, end)
    entries = list(_movie_atoms(movie, start + 8, end))
    if descriptions == 0 or len(entries) != descriptions:
        raise ValueError("MOV has no consistent video sample descriptions")
    for _, payload, stop in entries:
        if stop - payload < 78 or _movie_number(movie, payload + 6, stop, 2) == 0:
            raise ValueError("invalid MOV video sample description")

    if b"stsz" in table:
        start, end = table[b"stsz"]
        fixed_size = _movie_number(movie, start + 4, end)
        samples = _movie_number(movie, start + 8, end)
        if end - start != 12 + (0 if fixed_size else 4 * samples):
            raise ValueError("inconsistent MOV sample sizes")

        def sample_size(index: int) -> int:
            return fixed_size or _movie_number(movie, start + 12 + 4 * index, end)
    else:
        start, end = table[b"stz2"]
        bits = _movie_number(movie, start + 7, end, 1)
        samples = _movie_number(movie, start + 8, end)
        if bits not in (4, 8, 16) or end - start != 12 + (bits * samples + 7) // 8:
            raise ValueError("inconsistent compact MOV sample sizes")

        def sample_size(index: int) -> int:
            if bits == 4:
                value = _movie_number(movie, start + 12 + index // 2, end, 1)
                return (value >> 4) if index % 2 == 0 else (value & 15)
            return _movie_number(movie, start + 12 + index * (bits // 8), end, bits // 8)

    times_start, times_end = table[b"stts"]
    time_entries = _movie_number(movie, times_start + 4, times_end)
    if times_end - times_start != 8 + 8 * time_entries:
        raise ValueError("inconsistent MOV timing table")
    timed_samples = 0
    for index in range(time_entries):
        position = times_start + 8 + 8 * index
        count = _movie_number(movie, position, times_end)
        duration = _movie_number(movie, position + 4, times_end)
        if count == 0 or duration == 0:
            raise ValueError("MOV samples lack positive timing")
        timed_samples += count
    if timed_samples != samples:
        raise ValueError("MOV timing and sample counts disagree")

    offset_start, offset_end = table[b"co64"] if b"co64" in table else table[b"stco"]
    offset_size = 8 if b"co64" in table else 4
    chunks = _movie_number(movie, offset_start + 4, offset_end)
    if offset_end - offset_start != 8 + offset_size * chunks:
        raise ValueError("inconsistent MOV chunk offsets")
    map_start, map_end = table[b"stsc"]
    mappings = _movie_number(movie, map_start + 4, map_end)
    if map_end - map_start != 8 + 12 * mappings:
        raise ValueError("inconsistent MOV sample-to-chunk table")
    if samples == 0:
        if chunks or mappings:
            raise ValueError("empty MOV sample table has chunks")
        return descriptions, 0
    if chunks == 0 or mappings == 0:
        raise ValueError("MOV samples have no chunks")

    sample_index = 0
    previous_chunk = 0
    for index in range(mappings):
        position = map_start + 8 + 12 * index
        first_chunk = _movie_number(movie, position, map_end)
        per_chunk = _movie_number(movie, position + 4, map_end)
        description = _movie_number(movie, position + 8, map_end)
        next_chunk = _movie_number(movie, position + 12, map_end) if index + 1 < mappings else chunks + 1
        if (first_chunk <= previous_chunk or (index == 0 and first_chunk != 1)
                or next_chunk <= first_chunk or next_chunk > chunks + 1
                or per_chunk == 0 or not 1 <= description <= descriptions):
            raise ValueError("invalid MOV chunk mapping")
        for chunk in range(first_chunk, next_chunk):
            if sample_index + per_chunk > samples:
                raise ValueError("MOV chunks exceed the sample count")
            size = 0
            for sample in range(sample_index, sample_index + per_chunk):
                value = sample_size(sample)
                if value == 0:
                    raise ValueError("MOV contains an empty video sample")
                size += value
            offset = _movie_number(movie, offset_start + 8 + offset_size * (chunk - 1), offset_end, offset_size)
            if not _movie_media_range(offset, size, media):
                raise ValueError("MOV samples are outside media data")
            sample_index += per_chunk
        previous_chunk = first_chunk
    if sample_index != samples:
        raise ValueError("MOV chunks do not account for every sample")
    return descriptions, samples


def _movie_fragment_samples(movie, atoms: list, track_id: int, descriptions: int,
                            defaults: dict, media: list[tuple[int, int]]) -> int:
    """Validate fragmented MOV samples, including the FFmpeg regression fixture."""
    samples = 0
    atom_offset = 0
    for kind, start, end in atoms:
        moof_offset = atom_offset
        atom_offset = end
        if kind != b"moof":
            continue
        implicit_base = moof_offset
        for kind, payload, stop in _movie_atoms(movie, start, end):
            if kind != b"traf":
                continue
            children = list(_movie_atoms(movie, payload, stop))
            headers = [(start, end) for kind, start, end in children if kind == b"tfhd"]
            if len(headers) != 1:
                raise ValueError("MOV fragment lacks a unique track header")
            header_start, header_end = headers[0]
            flags = _movie_number(movie, header_start, header_end)
            fragment_track = _movie_number(movie, header_start + 4, header_end)
            description, duration, size = defaults.get(fragment_track, (0, 0, 0))
            position = header_start + 8
            base = moof_offset if flags & 0x020000 else implicit_base
            if flags & 0x000001:
                base = _movie_number(movie, position, header_end, 8)
                position += 8
            for flag, field in ((0x000002, "description"), (0x000008, "duration"), (0x000010, "size"), (0x000020, "flags")):
                if flags & flag:
                    value = _movie_number(movie, position, header_end)
                    position += 4
                    if field == "description":
                        description = value
                    elif field == "duration":
                        duration = value
                    elif field == "size":
                        size = value
            if position != header_end:
                raise ValueError("inconsistent MOV fragment header")
            selected = fragment_track == track_id
            if selected and not 1 <= description <= descriptions:
                raise ValueError("MOV fragment references an absent sample description")
            data_end = base
            for kind, run_start, run_end in children:
                if kind != b"trun":
                    continue
                run_flags = _movie_number(movie, run_start, run_end)
                count = _movie_number(movie, run_start + 4, run_end)
                position = run_start + 8
                offset = data_end
                if run_flags & 0x000001:
                    offset = base + _movie_number(movie, position, run_end, signed=True)
                    position += 4
                if run_flags & 0x000004:
                    _movie_number(movie, position, run_end)
                    position += 4
                entry_width = 4 * sum(bool(run_flags & flag) for flag in (0x000100, 0x000200, 0x000400, 0x000800))
                if position + count * entry_width != run_end or (selected and (count == 0 or flags & 0x010000)):
                    raise ValueError("inconsistent MOV fragment samples")
                if count and not run_flags & 0x000300:
                    if duration == 0 or not _movie_media_range(offset, size * count, media):
                        raise ValueError("MOV fragment has empty, untimed, or out-of-media samples")
                    data_end = offset + size * count
                    if selected:
                        samples += count
                    continue
                for _ in range(count):
                    sample_duration = duration
                    sample_size = size
                    for flag, field in ((0x000100, "duration"), (0x000200, "size"), (0x000400, "flags"), (0x000800, "composition")):
                        if run_flags & flag:
                            value = _movie_number(movie, position, run_end)
                            position += 4
                            if field == "duration":
                                sample_duration = value
                            elif field == "size":
                                sample_size = value
                    if sample_duration == 0 or not _movie_media_range(offset, sample_size, media):
                        raise ValueError("MOV fragment has empty, untimed, or out-of-media samples")
                    offset += sample_size
                    if selected:
                        samples += 1
                data_end = offset
            implicit_base = data_end
    return samples


def _usable_video(video: Path) -> bool:
    """Require consistent video sample metadata referencing bytes inside mdat."""
    try:
        fd = os.open(video, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as movie:
            info = os.fstat(movie.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                return False
            atoms = list(_movie_atoms(movie, 0, info.st_size))
            media_data = [(start, end) for kind, start, end in atoms if kind == b"mdat" and end > start]
            if not media_data:
                return False
            for kind, start, end in atoms:
                if kind != b"moov":
                    continue
                metadata = list(_movie_atoms(movie, start, end))
                if not any(kind == b"mvhd" and end - start >= 100 for kind, start, end in metadata):
                    continue
                defaults = {}
                for child, payload, stop in metadata:
                    if child == b"mvex":
                        for child, payload, stop in _movie_atoms(movie, payload, stop):
                            if child == b"trex":
                                if stop - payload != 24:
                                    raise ValueError("invalid MOV fragment defaults")
                                identifier = _movie_number(movie, payload + 4, stop)
                                defaults[identifier] = tuple(_movie_number(movie, payload + field, stop) for field in (8, 12, 16))
                for kind, start, end in metadata:
                    if kind != b"trak":
                        continue
                    track = list(_movie_atoms(movie, start, end))
                    if not any(kind == b"tkhd" and end - start >= 84 for kind, start, end in track):
                        continue
                    headers = [(start, end) for kind, start, end in track if kind == b"tkhd"]
                    header_start, header_end = headers[0]
                    version = _movie_number(movie, header_start, header_end, 1)
                    identifier = _movie_number(movie, header_start + (20 if version == 1 else 12), header_end)
                    for kind, start, end in track:
                        if kind != b"mdia":
                            continue
                        media = list(_movie_atoms(movie, start, end))
                        if not any(kind == b"mdhd" and end - start >= 24 for kind, start, end in media):
                            continue
                        video_track = False
                        sample_table = None
                        for child, payload, stop in media:
                            if child == b"hdlr" and stop - payload >= 12:
                                movie.seek(payload + 8)
                                video_track = movie.read(4) == b"vide"
                            elif child == b"minf":
                                for child, payload, stop in _movie_atoms(movie, payload, stop):
                                    if child == b"stbl":
                                        sample_table = _movie_table(movie, payload, stop)
                        if video_track and sample_table is not None:
                            descriptions, samples = _movie_sample_table(movie, sample_table, media_data)
                            fragments = _movie_fragment_samples(movie, atoms, identifier, descriptions, defaults, media_data)
                            if samples + fragments > 0:
                                return True
            return False
    except (OSError, ValueError, KeyError):
        return False


def record(
    udid: str,
    out: Path | None,
    seconds: int,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.Popen,
) -> dict:
    if not udid:
        return _error("--udid is required")
    if not isinstance(seconds, int) or seconds < 1:
        return _error("--seconds must be an integer of 1 or more; it is the hard cap on recordVideo")
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    video = _child(Path(out), f"recording-{uuid4().hex}.mov")
    if video is None:
        return _error("recording path escaped --out")
    argv = ["xcrun", "simctl", "io", udid, "recordVideo", str(video)]
    if dry_run:
        return _dry(argv, seconds=seconds)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    Path(out).mkdir(parents=True, exist_ok=True)
    resolved = _resolve(which, "xcrun", argv)
    if video.exists():
        return _error("refusing to reuse an existing recording artifact")
    proc = runner(resolved, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
    capped = False
    forced = False
    try:
        stdout, stderr = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        capped = True
        proc.send_signal(signal.SIGINT)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            forced = True
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired as exc:
                    # Descendants may keep inherited pipes open after the recorder
                    # dies. Close our ends and still reap the recorder boundedly.
                    proc.stdout.close()
                    proc.stderr.close()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    return _failed("simctl recordVideo did not stop after kill", resolved, exc, seconds=seconds)
    completed = subprocess.CompletedProcess(resolved, proc.returncode, stdout, stderr)
    if forced:
        return _failed("simctl recordVideo required forced termination; recording was not finalized gracefully", resolved, completed, seconds=seconds)
    if proc.returncode != 0:
        return _failed("simctl recordVideo failed", resolved, completed, seconds=seconds)
    if not _usable_video(video):
        return _failed("simctl recordVideo did not create a non-empty finalized MOV artifact", resolved, completed, seconds=seconds)
    return {
        "status": "recorded",
        **({"reason": f"stopped at --seconds cap ({seconds})"} if capped else {}),
        "argv": resolved,
        "exit_code": 0,
        "invoked": True,
        "seconds": seconds,
        "artifact": str(video),
    }


def _created_here(out: Path, udid: str, created_udid: str) -> dict | None:
    if not udid or not created_udid or udid != created_udid:
        return _error(
            "refusing to shutdown or erase a UDID this run did not create; "
            "pass the UDID boot printed as both --udid and --created-udid"
        )
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    try:
        rows = _load_ledger(Path(out))
    except (OSError, ValueError) as exc:
        return _error(f"refusing unsafe or unreadable created-udid ledger: {exc}")
    if not any(row.get("udid") == udid for row in rows):
        return _error(
            "refusing to shutdown or erase a UDID that is not in the created-udid ledger under --out"
        )
    return None


def shutdown(
    udid: str,
    created_udid: str,
    out: Path | None,
    erase: bool = False,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if out is None:
        return _error("--out is required so shutdown can read the created-udid ledger")
    refused = _created_here(Path(out), udid, created_udid)
    if refused:
        return refused
    argv = ["xcrun", "simctl", "shutdown", udid]
    erase_argv = ["xcrun", "simctl", "erase", udid] if erase else None
    if dry_run:
        return _dry(argv, erase_argv=erase_argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0 and not _already(proc, "Shutdown"):
        return _failed("simctl shutdown failed", resolved, proc)
    if not erase:
        return {"status": "shutdown", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid, "erased": False}
    erase_resolved = _resolve(which, "xcrun", ["xcrun", "simctl", "erase", udid])
    erased = _run(runner, erase_resolved)
    if erased.returncode != 0:
        return _failed("simctl erase failed", erase_resolved, erased, udid=udid)
    return {
        "status": "erased",
        "argv": erase_resolved,
        "shutdown_argv": resolved,
        "exit_code": 0,
        "invoked": True,
        "udid": udid,
        "erased": True,
    }
