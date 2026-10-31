# Cocos Creator client

- Engine target: Cocos Creator 3.x (pin the exact editor patch version before generating editor metadata).
- Language: TypeScript, strict mode.
- Platform: WeChat Mini Game.
- Runtime source: `assets/scripts/`.
- Automated tests: Vitest; transport and orchestration logic can be tested without the Cocos editor.

## Implemented client foundation

- WeChat login is isolated behind `WeChatPlatform`; only the temporary `wx.login` code is sent to the backend.
- REST client attaches Bearer access token, `X-Request-Id`, timeout and typed API errors; `createWeChatFetch(wx)` adapts native `wx.request`.
- Map WebSocket client follows protocol v1: AUTH must be first (seq 0), then ENTER/RECONNECT; client messages use monotonic sequence numbers. `createWeChatWebSocketFactory(wx)` adapts native `wx.connectSocket`.
- Map session orchestration performs login → map enter → WebSocket connect and exposes authoritative server events.
- On unexpected WebSocket close, `MapSession` reconnects with the same `instance_id`/`session_id` during the server-provided grace period using bounded exponential backoff; intentional leave/dispose suppresses reconnect.
- Access tokens are held in memory by default. Never persist WeChat `session_key` or secrets in the client.

## Backend endpoints

- `POST /api/v1/auth/login` with `{ wx_code, request_id }`
- `POST /api/v1/map/enter` with Bearer JWT
- `WS /api/v1/ws/map` with protocol described in `docs/engineering/realtime/map-websocket-vs2.md`

## Development

```sh
npm install
npm run typecheck
npm test
```

This is a TypeScript client foundation, not yet a complete playable Cocos scene project. Scene assets, prefabs, input bindings, art resources and WeChat DevTools packaging are subsequent client integration work. Construct `RestClient` with `createWeChatFetch(wx)` and `MapSession` with `createWeChatWebSocketFactory(wx)` in the WeChat runtime. Import the source into the pinned Cocos Creator 3.x project; do not commit editor caches or generated build output.


## Personal level and law API client

`RestClient` follows the merged VS-3/VS-4 backend contract:

- `listLevels()`
- `enterLevel(levelId, entranceId, idempotencyKey)`
- `startLevel(runId)` / `abandonLevel(runId)`
- `listRules()` — reads the server-owned rule catalog and tuning status
- `castRule(runId, ruleId, options, idempotencyKey)` — sends `target_id` and/or `target_point` as required by the rule
- `maintainGaze(runId, targetId)` / `stopGaze(runId)`
- `getLevelState(runId)` — reads `GET /api/v1/level/state/{run_id}`

Rule writes use the current backend routes (`/level/rule/cast`, `/level/rule/maintain`, `/level/rule/stop`). The client does not calculate rule effects, cooldowns, combo IDs, or mechanism state. Structured backend errors such as `RULE_COOLDOWN` remain available on `ApiError.details`.

The server currently marks numeric law tuning and mechanism positions as `TUNING_REQUIRED`. The client must display this state and must not assume rule casting is enabled until the backend catalog reports `READY`. Scene/UI bindings and a geometric playable-room prototype are now integrated in GameEntry; final art, polished HUD, collision/pathfinding and device acceptance remain separate work.


The engine-independent LawController also validates point/object target shape from the server rule scope, tracks an active GAZE target, exposes the latest personal state snapshot, and renews GAZE only when one-third of the server lease timeout has elapsed. Call maintainGazeIfDue() from the scene update loop; it suppresses per-frame network spam. The server still validates actual target identity, range, tuning, cooldown, expiry and effects.


## Player profile and character selection API

RestClient now exposes getPlayerProfile(), listCharacters(), and selectCharacter(characterId) for the existing authenticated player endpoints. Character unlock state and the selected character are read from the server; the client must not infer unlocks or treat a local selection as authoritative.


## WorldPlaySession orchestration

WorldPlaySession coordinates the existing MapSession, RestClient, PersonalLevelSession and LawController without importing Cocos engine types. A scene adapter can use it to enter the shared map, load server-owned profile/character data, select a character, list levels, enter/start a personal room, cast laws, refresh mechanism state, maintain gaze, and abandon a run. Movement/actions/ping are delegated to the existing WebSocket session. This is the application workflow layer; scene rendering, input hit-testing, prefabs and final art remain outstanding.


## Cocos Creator project

- Editor target is pinned to **Cocos Creator 3.8.8** in `package.json`. Open the `client/` directory itself from Cocos Dashboard; it contains the required `package.json` and `assets/` project structure.
- The launch scene is `assets/scenes/Boot.scene`. It attaches `BeyondTheUnknownGameEntry`, which builds a simple placeholder UI at runtime.
- The current prototype flow is WeChat login → shared-map enter → WebSocket AUTH/ENTER → remote avatar display with tap-to-move or virtual joystick → enter the next unlocked room → use server-configured law combinations → interact with room mechanisms → server-authoritative settlement → continue through ROOM-01–05 and the unlocked hidden ending. Abandon/return-to-world remains available.
- The prototype uses procedural geometric presentation only: room-specific isometric floor tiles, mechanism-type glyphs, placeholder avatars and a touch virtual joystick. It does not invent final art, room geometry, mechanism positions, cooldowns, radii, or law durations. Combo definitions, movement speed, spawn, bounds and interaction radius are read from server-owned level configuration; the server enforces the configured movement speed. Law actions remain unavailable while the backend catalog reports `TUNING_REQUIRED`.
- For local WeChat DevTools testing, the default API/WebSocket endpoints are `http://127.0.0.1:8000/api/v1` and `ws://127.0.0.1:8000`. Enable local network URL validation bypass in DevTools for this local-only setup, or change the component properties to a registered HTTPS/WSS domain before testing on a real device.
- Configure the WeChat test AppID in the editor/build profile and server-side AppID/AppSecret through environment variables only. Never place AppSecret or WeChat `session_key` in the client project or Git.
- Cocos Creator generates `.meta` files for imported assets. The Boot scene and entry script include their initial metadata; allow the editor to update metadata if it reports a format-version change.
- Editor import, scene serialization, WeChat DevTools build, and real-device testing still require running Cocos Creator/WeChat DevTools; those GUI tools are not available in the repository CI environment.

The engine-independent TypeScript tests continue to run with `npm test` and `npm run typecheck`. The Cocos component imports the engine module `cc`, so it is excluded from the Node-side typecheck and must be compiled by the pinned Cocos Creator editor.


## VS-5 progress and settlement API

- `settleLevel(runId, idempotencyKey)` sends only the caller's run ID; the server verifies required objectives and computes the result.
- `getPlayerProgress()` reads the latest permanent progress snapshot.
- `listPlayerDiscoveries()` / `listPlayerCollections()` read the personal codex.
- `listWorldArchive(limit)` reads server-owned world-first records.
- `listRewards()` / `claimReward(playerRewardId)` read and claim owned rewards.
- `getLeaderboard(boardType, periodType, scope, limit)` reads one of the three server-owned weekly/monthly boards.

`PersonalLevelSession.settle()` and `WorldPlaySession.settleRoom()` expose the authoritative settlement flow. A successful or failed settlement clears the local active-run handle; incomplete-objective errors leave it available so the scene can refresh state and retry after the puzzle is completed.

## WeChat Mini Game build

See [微信小游戏构建与联调手册](../docs/engineering/wechat-mini-game-build.md) for the Cocos Creator 3.8.8 import/build steps, test AppID selection, server-only AppSecret configuration, HTTPS/WSS domain requirements and real-device acceptance checklist.


## Current multi-room prototype boundary

- ROOM-01–05 and LV-HIDDEN-01 can be entered through the current client flow; per-room combo controls are loaded from `levels.config.prototype_combos`, not hard-coded by room ID.
- The personal-room prototype uses the GDD 4.2 45° isometric transform. The virtual joystick maps screen-space direction back into logical room direction; click-to-move remains available.
- Mechanisms are drawn from the server catalog's canonical `mechanism_type` and state. These procedural glyphs and tile palettes are temporary playtest visuals, not approved final assets.
- The asset manifest remains 112/112 `MISSING`; strict release-assets validation must remain blocked until real files, source/license data, Cocos import evidence and device acceptance are supplied.
- The complete client-side movement state machine is not finished: obstacle collision, pathfinding, final character animation, multi-touch/safe-area tuning and real-device movement feel remain open.
