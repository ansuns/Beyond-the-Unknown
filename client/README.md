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

`RestClient` now exposes typed methods for the VS-3/VS-4 contract:

- `listLevels()`
- `enterLevel(levelId, entranceId, idempotencyKey)`
- `startLevel(runId)` / `abandonLevel(runId)`
- `applyLawAction(runId, ruleId, mechanismId, action, idempotencyKey)`
- `getRunMechanisms(runId)`

Write calls that can be retried accept an explicit idempotency key. The API client does not calculate law effects, combo IDs, or mechanism states; it only sends the player's intent and consumes the server-authoritative response. Scene/UI bindings and an interactive playable room are not part of this API adapter slice.
