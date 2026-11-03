#!/usr/bin/env bash
# Build the mini game and report its size in one step.
#
# Running the editor build and forgetting to measure is how the package reached
# 5.34 MB unnoticed. This wrapper always ends with the gate, so a build either
# prints a number that fits or fails loudly.
#
# The build itself lives in client/scripts/build-wechat.mjs, which also turns
# each declared bundle into a real WeChat subpackage and asserts the result.
# This script used to run that subpackage step a second time through a Python
# post-processor; two implementations of one rule is how they drift apart, so it
# now calls the single implementation and only adds the size gate.
#
# Usage: tools/build-wechat.sh [budget-mb]

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
config="$root/client/build-configs/wechat-slim.json"
output="$root/client/build/wechatgame-slim"
budget="${1:-3.5}"

mkdir -p "$root/build/reports"

echo "== build =="
(cd "$root/client" && node scripts/build-wechat.mjs)

echo "== package report =="
python "$root/tools/package_gate.py" \
  --build "$output" \
  --config "$config" \
  --budget "$budget" \
  --json "$root/build/reports/gate.json"
