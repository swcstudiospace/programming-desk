#!/usr/bin/env bash
# Android-owned CI test entrypoint for android.tools.
# INFRA-owned workflows (.github/workflows/**) can shell out to this script;
# it is not wired into any workflow here since that file is INFRA-owned.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
python3 -m unittest android.tools.tests.test_tools -v
