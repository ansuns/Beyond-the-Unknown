#!/usr/bin/env bash
# Build the browser target used to measure layout and loading behaviour.
#
# The WeChat build has tools/build-wechat.sh; the web build had no script at
# all, which meant nobody could reproduce the screenshots or the geometry
# numbers behind them. This makes that build a command instead of a memory.
#
# Usage: tools/build-web.sh

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
creator="${COCOS_CREATOR:-/c/ProgramData/cocos/editors/Creator/3.8.8/CocosCreator.exe}"
output="$root/client/build/web-desktop"
log="$root/build/cocos/build-web.log"

mkdir -p "$root/build/cocos"

echo "== build (web-desktop) =="
# The editor's Node picks up HTTP(S)_PROXY and fails against its update
# service, so the proxy variables are cleared for this process only.
# The editor also exits non-zero even on a successful build (it reports the
# quit state of its Electron shell), so success is judged by the log marker
# below rather than by the exit status.
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
    "$creator" --project "$root/client" \
    --build "platform=web-desktop;debug=false;md5Cache=false;buildPath=project://build;outputName=web-desktop" \
    > "$log" 2>&1 || true

if ! grep -q "build Task (web-desktop" "$log"; then
  echo "build did not run; last lines of $log:"
  tail -20 "$log"
  exit 1
fi

echo "== shell =="
node "$root/tools/patch-web-shell.mjs" "$output"

echo "OK: $output"
