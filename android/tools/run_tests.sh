#!/usr/bin/env bash
# Android-owned CI test entrypoint for android.tools.
# The repo's required workflow only runs `pytest ci/tests/`, so this suite
# is otherwise invisible to CI (Greptile P2, PR #47). .github/workflows/**
# and ci/.github/workflows/** are INFRA-owned (ownership.yaml); this script
# is the ANDROID-owned half of wiring it in — INFRA adds a step that calls it.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
python3 -m unittest android.tools.tests.test_tools -v
