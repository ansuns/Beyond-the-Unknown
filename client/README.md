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


## VS-4 law interaction orchestration

LawController wraps PersonalLevelSession for scene/input adapters:

- Loads the server-owned rule catalog and personal mechanism state after a level run starts.
- Disables casts until a rule is unlocked and its backend config_status is READY; current TUNING_REQUIRED settings remain visibly unavailable.
- Checks basic target shape before sending point-scoped or object-scoped casts. The server remains authoritative for target existence, geometry, radius, cooldown and combo results.
- Generates a fresh idempotency key for each cast through an injected factory.
- Maintains an active GAZE lease at one-third of the server-provided lease timeout (with a 250 ms minimum) when the scene calls maintainGazeIfDue(). Call stopGaze() when gaze input ends or the scene is exited.
- Refreshes and exposes the server-owned personal mechanism state after successful interactions.

This controller is engine-independent and can be called from Cocos Creator components. It does not provide scene assets, hit-testing, animations, audio, or a completed playable room.
