import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
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
      if [ "$arg" = "recordVideo" ]; then
        exec sleep 30
      fi
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
                captured = record(UDID, out, seconds=1, system_name="Darwin")
            log = calls.read_text()
            self.assertEqual(shot["exit_code"], 0, shot)
            self.assertTrue((out / "screenshot.png").is_file())
        self.assertIn("simctl io", log)
        self.assertIn("screenshot", log)
        self.assertEqual(captured["exit_code"], 0, captured)
        self.assertIn("recordVideo", log)
        self.assertIn("stopped at --seconds cap", captured["reason"])
        self.assertEqual(captured["seconds"], 1)

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
