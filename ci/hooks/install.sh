#!/usr/bin/env bash
# Install the git hooks. Run once per clone.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

mkdir -p .git/hooks
ln -sf ../../ci/hooks/pre-commit .git/hooks/pre-commit
chmod +x ci/hooks/pre-commit

echo "Installed: .git/hooks/pre-commit -> ci/hooks/pre-commit"
echo
echo "Verify with:  python3 ci/gates/check_secrets.py --staged"
