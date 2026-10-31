#!/usr/bin/env bash
# Build the mini game and report its size in one step.
#
# Running the editor build and forgetting to measure is how the package reached
# 5.34 MB unnoticed. This wrapper always ends with the gate, so a build either
# prints a number that fits or fails loudly.
#
# Usage: tools/build-wechat.sh [budget-mb]

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
creator="${COCOS_CREATOR:-/c/ProgramData/cocos/editors/Creator/3.8.8/CocosCreator.exe}"
config="$root/client/build-configs/wechat-slim.json"
output="$root/client/build/wechatgame-slim"
budget="${1:-3.5}"
log="$root/build/cocos/build-wechat.log"

mkdir -p "$root/build/cocos" "$root/build/reports"

echo "== build =="
# The editor's Node picks up HTTP(S)_PROXY and fails against its update service,
# so the proxy variables are cleared for this process only.
# The editor exits with a non-zero code even on a successful build (it reports
# the quit state of its Electron shell), so success is judged by the log marker
# below rather than by the exit status.
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
    "$creator" --project "$root/client" --build "configPath=$config" > "$log" 2>&1 || true

if ! grep -q "build Task (wechatgame" "$log"; then
  echo "build did not run; last lines of $log:"
  tail -20 "$log"
  exit 1
fi

echo "== subpackage =="
# Cocos 3.8.8 accepts bundles[].isSubpackage and then ignores it, so the
# artifact still ships the art inside the main package. This applies the same
# move the engine adapter expects: assets/<bundle> -> subpackages/<bundle>,
# a game.json declaration, and the settings registration that makes the runtime
# fetch it lazily instead of from the main package.
python "$root/tools/wechat_subpackage.py" --build "$output" --bundle resources

echo "== package report =="
python "$root/tools/package_gate.py" \
  --build "$output" \
  --config "$config" \
  --budget "$budget" \
  --json "$root/build/reports/gate.json"
