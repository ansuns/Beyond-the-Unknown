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

The server currently marks numeric law tuning and mechanism positions as `TUNING_REQUIRED`. The client must display this state and must not assume rule casting is enabled until the backend catalog reports `READY`. Scene/UI bindings and an interactive playable room are still separate integration work.


The engine-independent LawController also validates point/object target shape from the server rule scope, tracks an active GAZE target, exposes the latest personal state snapshot, and renews GAZE only when one-third of the server lease timeout has elapsed. Call maintainGazeIfDue() from the scene update loop; it suppresses per-frame network spam. The server still validates actual target identity, range, tuning, cooldown, expiry and effects.


## Player profile and character selection API

RestClient now exposes getPlayerProfile(), listCharacters(), and selectCharacter(characterId) for the existing authenticated player endpoints. Character unlock state and the selected character are read from the server; the client must not infer unlocks or treat a local selection as authoritative.


## WorldPlaySession orchestration

WorldPlaySession coordinates the existing MapSession, RestClient, PersonalLevelSession and LawController without importing Cocos engine types. A scene adapter can use it to enter the shared map, load server-owned profile/character data, select a character, list levels, enter/start a personal room, cast laws, refresh mechanism state, maintain gaze, and abandon a run. Movement/actions/ping are delegated to the existing WebSocket session. This is the application workflow layer; scene rendering, input hit-testing, prefabs and final art remain outstanding.
