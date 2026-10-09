import base64
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path

from ios.tools.sim_drive import boot, install, launch, record, screenshot, shutdown

ROOT = Path(__file__).resolve().parents[3]
UDID = "11111111-2222-4333-8444-555555555555"


def write_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@contextmanager
def prepend_path(directory: Path):
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = str(directory) + os.pathsep + old
    try:
        yield
    finally:
        os.environ["PATH"] = old


XCRUN = """#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
if [ "$1" != "simctl" ]; then
  echo "not simctl: $1" >&2
  exit 9
fi
case "$2" in
  list)
    printf '%s\\n' '{"devices":{}}'
    ;;
  create)
    printf '%s\\n' '{udid}'
    ;;
  boot|shutdown|erase|install|launch)
    ;;
  io)
    last=""
    for arg in "$@"; do
      last=$arg
    done
    : > "$last"
    ;;
  *)
    echo "unknown $2" >&2
    exit 9
    ;;
esac
exit 0
"""


# A real one-frame 2x2 raw-video MOV, generated with FFmpeg. Tests need no encoder.
MOV_BASE64 = (
    "AAAAFGZ0eXBxdCAgAAACAHF0ICAAAAKubW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAAAAAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAfF0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAIAAAACAAAAAAGNbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAABAAAAAAAB//wAAAAAALWhkbHIAAAAAbWhscnZpZGUAAAAAAAAAAAAAAAAMVmlkZW9IYW5kbGVyAAABOG1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACxoZGxyAAAAAGRobHJ1cmwgAAAAAAAAAAAAAAAAC0RhdGFIYW5kbGVyAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAAAzHN0YmwAAACAc3RzZAAAAAAAAAABAAAAcHJhdyAAAAAAAAAAAQAAAABGRk1QAAAAAAAABAAAAgACAEgAAABIAAAAAAAAAAEWTGF2YzYwLjMxLjEwMiByYXd2aWRlbwAAAAAAAAAAAAAY//8AAAAKZmllbAEAAAAAEHBhc3AAAAABAAAAAQAAABBzdHRzAAAAAAAAAAAAAAAQc3RzYwAAAAAAAAAAAAAAFHN0c3oAAAAAAAAAAAAAAAAAAAAQc3RjbwAAAAAAAAAAAAAAKG12ZXgAAAAgdHJleAAAAAAAAAABAAAAAQAAAAAAAAAAAAAAAAAAACF1ZHRhAAAAGalzd3IADVXETGF2ZjYwLjE2LjEwMAAAAHBtb29mAAAAEG1maGQAAAAAAAAAAQAAAFh0cmFmAAAAJHRmaGQAAAA5AAAAAQAAAAAAAALCAABAAAAAAAwBAQAAAAAAFHRmZHQBAAAAAAAAAAAAAAAAAAAYdHJ1bgAAAAUAAAABAAAAeAIAAAAAAAAUbWRhdAAAAAAAAAAAAAAAAAAAAENtZnJhAAAAK3RmcmEBAAAAAAAAAQAAAAAAAAABAAAAAAAAAAAAAAAAAAACwgEBAQAAABBtZnJvAAAAAAAAAEM="
)


def movie_atom(kind: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + kind + payload


def replace_movie_atoms(data: bytes, replacements: dict[bytes, bytes | None]) -> bytes:
    """Rewrite only the tiny embedded fixture, maintaining enclosing atom sizes."""
    result = []
    offset = 0
    while offset < len(data):
        size = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + size]
        if kind in replacements:
            replacement = replacements[kind]
            if replacement is not None:
                result.append(replacement)
        elif kind in (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"mvex", b"moof", b"traf"):
            result.append(movie_atom(kind, replace_movie_atoms(payload, replacements)))
        else:
            result.append(data[offset:offset + size])
        offset += size
    return b"".join(result)


def fixture_atom(data: bytes, kind: bytes) -> bytes:
    position = data.index(kind) - 4
    size = int.from_bytes(data[position:position + 4], "big")
    return data[position:position + size]


def classic_movie_fixture(*, wide_offsets: bool = False, compact_sizes: bool = False) -> bytes:
    """Remux the fixture's real raw-video sample into ordinary finalized tables."""
    original = base64.b64decode(MOV_BASE64)
    description = fixture_atom(original, b"stsd")
    ftyp = fixture_atom(original, b"ftyp")
    media = fixture_atom(original, b"mdat")
    full = bytes(4)

    def table(offset: int) -> bytes:
        sizes = (movie_atom(b"stz2", full + bytes(3) + bytes([4]) + (1).to_bytes(4, "big") + b"\xc0")
                 if compact_sizes else movie_atom(b"stsz", full + (12).to_bytes(4, "big") + (1).to_bytes(4, "big")))
        return movie_atom(b"stbl", description
                          + movie_atom(b"stts", full + (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + (16384).to_bytes(4, "big"))
                          + movie_atom(b"stsc", full + (1).to_bytes(4, "big") * 4)
                          + sizes
                          + movie_atom(b"co64" if wide_offsets else b"stco", full + (1).to_bytes(4, "big") + offset.to_bytes(8 if wide_offsets else 4, "big")))

    moov = replace_movie_atoms(fixture_atom(original, b"moov"), {b"mvex": None, b"stbl": table(0)})
    moov = replace_movie_atoms(moov, {b"stbl": table(len(ftyp) + len(moov) + 8)})
    return ftyp + moov + media


def install_record_xcrun(directory: Path, calls: Path, mode: str = "graceful", *, payload: bytes | None = None) -> None:
    write_exe(directory / "xcrun", f"""#!{sys.executable}
import base64, pathlib, signal, sys
calls = pathlib.Path({str(calls)!r})
with calls.open("a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
video = pathlib.Path(sys.argv[-1])
payload = base64.b64decode({MOV_BASE64 if payload is None else base64.b64encode(payload).decode("ascii")!r})
mode = {mode!r}
def finish(signum, frame):
    with calls.open("a") as log:
        log.write("SIGINT\\n")
    if mode == "graceful":
        video.write_bytes(payload)
    sys.exit(0)
if mode in ("graceful", "missing", "forced"):
    signal.signal(signal.SIGINT, signal.SIG_IGN if mode == "forced" else finish)
    while True:
        signal.pause()
elif mode == "empty":
    video.write_bytes(b"")
elif mode == "truncated":
    video.write_bytes(payload[:-3])
elif mode == "garbage":
    video.write_bytes(b"not a movie")
elif mode == "metadata-garbage":
    video.write_bytes(bytes.fromhex("000000096d6f6f7678000000096d64617478"))
else:
    video.write_bytes(payload)
""")


def install_xcrun(bin_dir: Path, calls: Path) -> None:
    script = XCRUN.replace("$CALLS", str(calls)).replace("{udid}", UDID)
    write_exe(bin_dir / "xcrun", script)


class SimDriveTests(unittest.TestCase):
    def test_linux_skip_does_not_spawn_even_when_xcrun_is_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            install_xcrun(root, calls)
            with prepend_path(root):
                result = boot("iPhone 17", "iOS-26", out=root / "out", system_name="Linux")
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("skipped:", result["reason"])
        self.assertFalse(result["invoked"])
        self.assertFalse(calls.exists())

    def test_dry_run_prints_xcrun_argv_and_spawns_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            install_xcrun(root, calls)
            with prepend_path(root):
                result = boot("iPhone 17", "iOS-26", dry_run=True, system_name="Linux")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["argv"][:3], ["xcrun", "simctl", "create"])
        self.assertIn("iPhone 17", result["argv"])
        self.assertIn("iOS-26", result["argv"])
        self.assertFalse(result["invoked"])
        self.assertFalse(calls.exists())

    def test_boot_creates_udid_with_fake_xcrun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            out = root / "evidence"
            install_xcrun(root, calls)
            with prepend_path(root):
                result = boot("iPhone 17", "iOS-26", out=out, system_name="Darwin")
            ledger = json.loads((out / "created-udids.json").read_text())
            log = calls.read_text()
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(result["udid"], UDID)
        self.assertTrue(result["created"])
        self.assertEqual(ledger[0]["udid"], UDID)
        self.assertIn("simctl create iPhone 17 iPhone 17 iOS-26", log)
        self.assertIn(f"simctl boot {UDID}", log)
        self.assertNotIn("simctl delete", log)

    def test_shutdown_refuses_a_udid_this_run_did_not_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            out = root / "evidence"
            out.mkdir()
            install_xcrun(root, calls)
            with prepend_path(root):
                mismatch = shutdown(UDID, "99999999-9999-4999-8999-999999999999", out, system_name="Darwin")
                missing = shutdown(UDID, UDID, out, system_name="Darwin")
        self.assertEqual(mismatch["exit_code"], 2)
        self.assertFalse(mismatch["invoked"])
        self.assertIn("did not create", mismatch["reason"])
        self.assertEqual(missing["exit_code"], 2)
        self.assertFalse(missing["invoked"])
        self.assertIn("not in the created-udid ledger", missing["reason"])
        self.assertFalse(calls.exists())

    def test_shutdown_and_erase_only_the_created_udid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            out = root / "evidence"
            install_xcrun(root, calls)
            with prepend_path(root):
                booted = boot("iPhone 17", "iOS-26", out=out, system_name="Darwin")
                stopped = shutdown(booted["udid"], booted["udid"], out, erase=True, system_name="Darwin")
                foreign = shutdown("99999999-9999-4999-8999-999999999999", "99999999-9999-4999-8999-999999999999", out, erase=True, system_name="Darwin")
            log = calls.read_text()
        self.assertEqual(stopped["exit_code"], 0, stopped)
        self.assertTrue(stopped["erased"])
        self.assertEqual(foreign["exit_code"], 2)
        self.assertFalse(foreign["invoked"])
        self.assertIn(f"simctl shutdown {UDID}", log)
        self.assertIn(f"simctl erase {UDID}", log)
        self.assertNotIn("simctl delete", log)
        self.assertNotIn("99999999", log)

    def test_screenshot_and_record_use_simctl_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            out = root / "evidence"
            install_xcrun(root, calls)
            with prepend_path(root):
                shot = screenshot(UDID, out, system_name="Darwin")
                install_record_xcrun(root, calls)
                captured = record(UDID, out, seconds=1, system_name="Darwin")
            log = calls.read_text()
            self.assertEqual(shot["exit_code"], 0, shot)
            self.assertTrue((out / "screenshot.png").is_file())
            self.assertGreater(Path(captured["artifact"]).stat().st_size, 0)
        self.assertIn("simctl io", log)
        self.assertIn("screenshot", log)
        self.assertEqual(captured["exit_code"], 0, captured)
        self.assertIn("recordVideo", log)
        self.assertIn("stopped at --seconds cap", captured["reason"])
        self.assertEqual(captured["seconds"], 1)
        self.assertIn("SIGINT", log)

    def test_install_and_launch_forward_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            install_xcrun(root, calls)
            with prepend_path(root):
                installed = install(UDID, "/tmp/Desk.app", system_name="Darwin")
                launched = launch(UDID, "space.swc.desk", system_name="Darwin")
            log = calls.read_text()
        self.assertEqual(installed["exit_code"], 0, installed)
        self.assertEqual(launched["exit_code"], 0, launched)
        self.assertIn(f"simctl install {UDID} /tmp/Desk.app", log)
        self.assertIn(f"simctl launch {UDID} space.swc.desk", log)

    def test_reuse_boots_a_ledger_udid_instead_of_creating_another(self):
        seen = []

        def runner(argv, **_kwargs):
            seen.append(argv)
            if "list" in argv:
                payload = {
                    "devices": {
                        "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [{"udid": UDID, "name": "iPhone 17"}]
                    }
                }
                return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
            if "create" in argv:
                raise AssertionError("create called for a device this run already recorded")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "created-udids.json").write_text(json.dumps([
                {"udid": UDID, "device_type": "iPhone 17", "runtime": "iOS-26", "name": "iPhone 17"}
            ]))
            result = boot(
                "iPhone 17", "iOS-26", out=out, system_name="Darwin",
                which=lambda name: f"/usr/bin/{name}", runner=runner,
            )
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(result["udid"], UDID)
        self.assertTrue(result["reused"])
        self.assertFalse(result["created"])
        self.assertTrue(any("boot" in argv for argv in seen))

    def test_record_rejects_a_non_positive_cap_without_spawning(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("runner called")

        result = record(UDID, Path("/tmp"), 0, system_name="Darwin", which=lambda _n: "/usr/bin/xcrun", runner=boom)
        self.assertEqual(result["exit_code"], 2)
        self.assertFalse(result["invoked"])

    def test_record_never_accepts_stale_or_missing_or_invalid_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "evidence"
            out.mkdir()
            stale = out / "recording.mov"
            stale.write_bytes(base64.b64decode(MOV_BASE64))
            stale_bytes = stale.read_bytes()
            for mode in ("missing", "empty", "truncated", "garbage", "metadata-garbage"):
                with self.subTest(mode=mode):
                    install_record_xcrun(root, root / "calls", mode)
                    with prepend_path(root):
                        result = record(UDID, out, seconds=1, system_name="Darwin")
                    self.assertEqual(result["status"], "failed", result)
                    self.assertEqual(result["exit_code"], 1)
                    self.assertEqual(stale.read_bytes(), stale_bytes)

    def test_record_preserves_previous_outputs_and_reports_each_fresh_movie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_record_xcrun(root, root / "calls", "valid")
            with prepend_path(root):
                first = record(UDID, root / "out", seconds=1, system_name="Darwin")
                first_bytes = Path(first["artifact"]).read_bytes()
                second = record(UDID, root / "out", seconds=1, system_name="Darwin")
            self.assertEqual(first["exit_code"], 0, first)
            self.assertEqual(second["exit_code"], 0, second)
            self.assertNotEqual(first["artifact"], second["artifact"])
            self.assertEqual(Path(first["artifact"]).read_bytes(), first_bytes)
            self.assertEqual(Path(second["artifact"]).read_bytes(), first_bytes)

    def test_record_accepts_real_samples_in_classic_and_fragmented_movies(self):
        movies = {
            "fragmented": base64.b64decode(MOV_BASE64),
            "classic": classic_movie_fixture(),
            "wide-offsets": classic_movie_fixture(wide_offsets=True),
            "compact-sizes": classic_movie_fixture(compact_sizes=True),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, payload in movies.items():
                with self.subTest(name=name):
                    install_record_xcrun(root, root / "calls", "valid", payload=payload)
                    with prepend_path(root):
                        result = record(UDID, root / "out", seconds=1, system_name="Darwin")
                    self.assertEqual(result["exit_code"], 0, result)
                    self.assertEqual(Path(result["artifact"]).read_bytes(), payload)

    def test_record_refuses_missing_or_inconsistent_video_samples(self):
        classic = classic_movie_fixture()
        fragmented = base64.b64decode(MOV_BASE64)
        full = bytes(4)
        missing_table = movie_atom(b"moov",
                                  movie_atom(b"mvhd", bytes(100))
                                  + movie_atom(b"trak", movie_atom(b"tkhd", bytes(84))
                                               + movie_atom(b"mdia", movie_atom(b"mdhd", bytes(24))
                                                            + movie_atom(b"hdlr", bytes(8) + b"vide"))))
        broken = {
            "parent-reproduced-missing-minf": missing_table + movie_atom(b"mdat", b"x"),
            "missing-stbl": replace_movie_atoms(classic, {b"stbl": None}),
            "missing-descriptions": replace_movie_atoms(classic, {b"stsd": movie_atom(b"stsd", full + bytes(4))}),
            "no-samples": replace_movie_atoms(classic, {
                b"stsz": movie_atom(b"stsz", full + bytes(8)),
                b"stts": movie_atom(b"stts", full + bytes(4)),
                b"stsc": movie_atom(b"stsc", full + bytes(4)),
                b"stco": movie_atom(b"stco", full + bytes(4)),
            }),
            "empty-sample": replace_movie_atoms(classic, {b"stsz": movie_atom(b"stsz", full + bytes(4) + (1).to_bytes(4, "big") + bytes(4))}),
            "outside-media": replace_movie_atoms(classic, {b"stco": movie_atom(b"stco", full + (1).to_bytes(4, "big") + bytes(4))}),
            "count-disagreement": replace_movie_atoms(classic, {b"stts": movie_atom(b"stts", full + (1).to_bytes(4, "big") + (2).to_bytes(4, "big") + (16384).to_bytes(4, "big"))}),
            "absent-description-reference": replace_movie_atoms(classic, {b"stsc": movie_atom(b"stsc", full + (1).to_bytes(4, "big") * 3 + (2).to_bytes(4, "big"))}),
        }
        for name, kind, relative, value in (
            ("fragment-no-samples", b"trun", 8, 0),
            ("fragment-outside-media", b"trun", 12, 0x7fffffff),
            ("fragment-count-disagreement", b"trun", 8, 2),
            ("fragment-empty-sample", b"tfhd", 24, 0),
            ("fragment-no-duration", b"tfhd", 20, 0),
        ):
            changed = bytearray(fragmented)
            position = changed.index(kind) + relative
            changed[position:position + 4] = value.to_bytes(4, "big")
            broken[name] = bytes(changed)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, payload in broken.items():
                with self.subTest(name=name):
                    install_record_xcrun(root, root / "calls", "valid", payload=payload)
                    with prepend_path(root):
                        result = record(UDID, root / "out", seconds=1, system_name="Darwin")
                    self.assertEqual(result["status"], "failed", result)
                    self.assertEqual(result["exit_code"], 1, result)
                    self.assertEqual(result["tool_exit_code"], 0)

    def test_record_forced_termination_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_record_xcrun(root, root / "calls", "forced")
            with prepend_path(root):
                result = record(UDID, root / "out", seconds=1, system_name="Darwin")
            self.assertEqual(result["exit_code"], 1, result)
            self.assertIn("forced termination", result["reason"])

    def test_ledger_symlink_is_refused_for_boot_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir()
            outside = root / "outside.json"
            content = json.dumps([{"udid": UDID, "device_type": "iPhone 17", "runtime": "iOS-26"}])
            outside.write_text(content)
            (out / "created-udids.json").symlink_to(outside)
            install_xcrun(root, root / "calls")
            with prepend_path(root):
                results = [
                    boot("iPhone 17", "iOS-26", out=out, system_name="Darwin"),
                    shutdown(UDID, UDID, out, erase=True, system_name="Darwin"),
                ]
            for result in results:
                self.assertEqual(result["exit_code"], 2, result)
                self.assertFalse(result["invoked"])
            self.assertEqual(outside.read_text(), content)
            self.assertFalse((root / "calls").exists())

    def test_ledger_symlink_swapped_during_create_cannot_overwrite_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            outside = root / "outside.json"
            outside.write_text("outside evidence")

            def runner(argv, **kwargs):
                if "list" in argv:
                    return subprocess.CompletedProcess(argv, 0, '{"devices":{}}', "")
                if "create" in argv:
                    (out / "created-udids.json").symlink_to(outside)
                    return subprocess.CompletedProcess(argv, 0, UDID, "")
                raise AssertionError("boot must not run without a safe ledger")

            result = boot("iPhone 17", "iOS-26", out=out, system_name="Darwin", which=lambda _: "/xcrun", runner=runner)
            self.assertEqual(result["exit_code"], 2, result)
            self.assertEqual(result["udid"], UDID)
            self.assertEqual(outside.read_text(), "outside evidence")

    def test_atomic_ledger_replace_is_pinned_against_out_path_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            outside = root / "outside"
            outside.mkdir()
            (outside / "created-udids.json").write_text("outside evidence")
            original_replace = os.replace

            def swap_then_replace(src, dst, **kwargs):
                out.rename(root / "original-out")
                out.symlink_to(outside, target_is_directory=True)
                return original_replace(src, dst, **kwargs)

            install_xcrun(root, root / "calls")
            with prepend_path(root), patch("ios.tools.sim_drive.os.replace", side_effect=swap_then_replace):
                result = boot("iPhone 17", "iOS-26", out=out, system_name="Darwin")
            self.assertEqual(result["exit_code"], 0, result)
            self.assertEqual((outside / "created-udids.json").read_text(), "outside evidence")
            ledger = json.loads((root / "original-out" / "created-udids.json").read_text())
            self.assertEqual(ledger[0]["udid"], UDID)

    def test_concurrent_process_boots_preserve_every_created_udid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            barrier = root / "barrier"
            barrier.mkdir()
            write_exe(root / "xcrun", f"""#!{sys.executable}
import json, pathlib, sys, time
if sys.argv[2] == "list":
    print(json.dumps({{"devices": {{}}}}))
elif sys.argv[2] == "create":
    udid = sys.argv[3]
    barrier = pathlib.Path({str(barrier)!r})
    (barrier / udid).touch()
    deadline = time.monotonic() + 15
    while len(list(barrier.iterdir())) < 6:
        if time.monotonic() > deadline:
            sys.exit(9)
        time.sleep(0.01)
    print(udid)
""")
            code = """
import json, pathlib, sys
from ios.tools.sim_drive import boot
print(json.dumps(boot("iPhone 17", "iOS-26", out=pathlib.Path(sys.argv[1]), name=sys.argv[2], system_name="Darwin")))
"""
            udids = [f"{index:08x}-2222-4333-8444-555555555555" for index in range(6)]
            processes = []
            with prepend_path(root):
                try:
                    for udid in udids:
                        processes.append(subprocess.Popen([sys.executable, "-c", code, str(root / "out"), udid], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
                    for process in processes:
                        stdout, stderr = process.communicate(timeout=30)
                        self.assertEqual(process.returncode, 0, stderr)
                        self.assertEqual(json.loads(stdout)["exit_code"], 0, stdout)
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()
            ledger = json.loads((root / "out" / "created-udids.json").read_text())
            self.assertEqual({row["udid"] for row in ledger}, set(udids))
            self.assertEqual(len(ledger), len(udids))

    @unittest.skipUnless(platform.system() != "Darwin", "the CLI skip is what a Linux host returns")
    def test_cli_boot_skips_on_linux(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ios.tools", "sim_drive", "boot", "--device-type", "iPhone 17", "--runtime", "iOS-26"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("skipped:", proc.stdout)
        self.assertNotIn('"status": "passed"', proc.stdout)

    def test_cli_boot_dry_run_prints_json_argv(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ios.tools", "sim_drive", "boot",
             "--device-type", "iPhone 17", "--runtime", "iOS-26", "--dry-run", "--json"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["argv"][0], "xcrun")
        self.assertEqual(body["status"], "dry-run")
        self.assertFalse(body["invoked"])


if __name__ == "__main__":
    unittest.main()
