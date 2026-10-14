#!/usr/bin/env bash
# Run systemd-analyze verify on every unit in this directory.
#
# Uses a temporary --root. ExecStart binaries, EnvironmentFile paths, WorkingDirectory,
# ReadWritePaths, and Documentation=file:// targets are stubbed inside that root.
# The host's systemd unit catalog is copied in so dependencies such as sysinit.target
# resolve. Nothing is enabled or started, and the live env file is not read.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v systemd-analyze >/dev/null 2>&1; then
  echo "verify-units.sh: systemd-analyze is not on PATH" >&2
  exit 1
fi

shopt -s nullglob
units=("$HERE"/*.service "$HERE"/*.timer)
shopt -u nullglob
if [[ ${#units[@]} -eq 0 ]]; then
  echo "verify-units.sh: no unit files in $HERE" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/usr/lib" "$tmp/etc"
cp -a /usr/lib/systemd "$tmp/usr/lib/systemd"
if [[ -d /etc/systemd ]]; then
  cp -a /etc/systemd "$tmp/etc/systemd"
fi
mkdir -p "$tmp/etc/systemd/system"

names=()
for unit in "${units[@]}"; do
  base="$(basename "$unit")"
  cp "$unit" "$tmp/etc/systemd/system/$base"
  names+=("$base")
done

python3 - "$tmp" "${units[@]}" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
unit_paths = [Path(p) for p in sys.argv[2:]]

def under_root(abs_path: str) -> Path:
    if not abs_path.startswith("/"):
        raise SystemExit(f"verify-units.sh: expected an absolute path, got {abs_path!r}")
    dest = (root / abs_path.lstrip("/")).resolve()
    if dest != root and root not in dest.parents:
        raise SystemExit("verify-units.sh: path escapes the temporary root")
    return dest

def stub_exec(path: str) -> None:
    dest = under_root(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        dest.chmod(0o755)

def touch_file(path: str) -> None:
    dest = under_root(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text("", encoding="utf-8")
        dest.chmod(0o600)

def make_dir(path: str) -> None:
    dest = under_root(path)
    dest.mkdir(parents=True, exist_ok=True)

def command_path(token: str) -> str:
    token = token.strip()
    while token[:1] in "-+@!:":
        token = token[1:]
    return token

for path in unit_paths:
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "ExecStart":
            token = value.split()[0] if value.split() else ""
            binary = command_path(token)
            if binary.startswith("/"):
                stub_exec(binary)
        elif key == "EnvironmentFile":
            spec = value[1:] if value.startswith("-") else value
            if spec.startswith("/"):
                touch_file(spec)
        elif key == "WorkingDirectory":
            if value.startswith("/"):
                make_dir(value)
        elif key == "ReadWritePaths":
            for item in value.split():
                if item.startswith("/"):
                    make_dir(item)
        elif key == "Documentation":
            for item in value.split():
                if item.startswith("file://"):
                    doc = item[len("file://"):]
                    if doc.startswith("localhost"):
                        doc = doc[len("localhost"):]
                    if doc.startswith("/"):
                        touch_file(doc)
PY

version="$(systemd-analyze --version | head -n 1)"
echo "verify-units.sh: $version"
echo "verify-units.sh: systemd-analyze verify --root (temporary) ${names[*]}"
systemd-analyze verify --root="$tmp" "${names[@]}"
echo "verify-units.sh: verified ${#names[@]} unit(s): ${names[*]}"
