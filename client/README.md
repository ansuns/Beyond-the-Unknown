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


## Cocos Creator project

- Editor target is pinned to **Cocos Creator 3.8.8** in `package.json`. Open the `client/` directory itself from Cocos Dashboard; it contains the required `package.json` and `assets/` project structure.
- The launch scene is `assets/scenes/Boot.scene`. It attaches `BeyondTheUnknownGameEntry`, which builds a simple placeholder UI at runtime.
- The prototype flow is WeChat login → shared-map enter → WebSocket AUTH/ENTER → remote avatar display and tap-to-move → enter the first unlocked personal room → read law catalog → abandon and return to the shared map.
- The prototype uses generated geometric placeholders only. It does not invent final art, room geometry, mechanism positions, cooldowns, radii, or law durations. Law actions remain unavailable while the backend catalog reports `TUNING_REQUIRED`.
- For local WeChat DevTools testing, the default API/WebSocket endpoints are `http://127.0.0.1:8000/api/v1` and `ws://127.0.0.1:8000`. Enable local network URL validation bypass in DevTools for this local-only setup, or change the component properties to a registered HTTPS/WSS domain before testing on a real device.
- Configure the WeChat test AppID in the editor/build profile and server-side AppID/AppSecret through environment variables only. Never place AppSecret or WeChat `session_key` in the client project or Git.
- Cocos Creator generates `.meta` files for imported assets. The Boot scene and entry script include their initial metadata; allow the editor to update metadata if it reports a format-version change.
- Editor import, scene serialization, WeChat DevTools build, and real-device testing still require running Cocos Creator/WeChat DevTools; those GUI tools are not available in the repository CI environment.

The engine-independent TypeScript tests continue to run with `npm test` and `npm run typecheck`. The Cocos component imports the engine module `cc`, so it is excluded from the Node-side typecheck and must be compiled by the pinned Cocos Creator editor.
