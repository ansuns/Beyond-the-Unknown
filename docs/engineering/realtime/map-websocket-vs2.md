# VS-2 Shared Map WebSocket Protocol

- Version: 1.0
- Status: backend vertical-slice contract
- Transport: WebSocket JSON messages at `/api/v1/ws/map`
- REST prerequisite: `POST /api/v1/map/enter`

## 1. Enter sequence

1. Client calls `POST /api/v1/map/enter` with Bearer JWT.
2. Server allocates or resumes one membership and returns `map_id`, `instance_id`, `session_id`, spawn position, current count and WebSocket path.
3. Client opens `/api/v1/ws/map`.
4. First WebSocket message MUST be `AUTH` with the same Bearer access token in `payload.token`.
5. Server validates JWT, player status and account existence, then sends `AUTH_OK`.
6. Client sends `ENTER` or `RECONNECT` with the returned `instance_id` and `session_id`.
7. Server validates that the membership belongs to the authenticated player, then sends an `ENTER` snapshot and broadcasts the joining avatar to other connected players in the same instance.

## 2. Message envelope

Every message uses the common envelope from `websocket.schema.json`:

- `v`: protocol version, currently 1.
- `cmd`: command/event name.
- `seq`: monotonically increasing sequence number per connection.
- `ts`: epoch milliseconds. Server time is authoritative.
- `payload`: command-specific object.

Client sequence numbers must increase. Duplicate or stale messages are ignored. The client must not supply `player_id` as an identity; server identity comes from JWT `sub`.

## 3. Client-to-server commands

| Command | Required payload | Server behavior |
|---|---|---|
| AUTH | `token` | Must be the first message; validates JWT and player status |
| ENTER | `instance_id`, `session_id` | Joins the previously allocated membership |
| RECONNECT | `instance_id`, `session_id` | Re-authenticates and resumes within the grace period |
| MOVE_SYNC | `x`, `y`, `dir`, `client_tick` | Validates finite coordinates, direction, movement speed and rate; persists accepted position |
| ACTION_BROADCAST | `action_id` | Only ACT_001–ACT_004; rate-limited; no gameplay value |
| PING | empty object | Refreshes membership lease and returns PONG |
| LEAVE | empty object | Immediately removes membership and broadcasts LEAVE |

## 4. Server-to-client events

- `AUTH_OK` / `AUTH_FAIL`: authentication result.
- `ENTER`: initial avatar snapshot or another player's entry.
- `MOVE_SYNC`: accepted authoritative position of another player.
- `ACTION_BROADCAST`: allowed preset action from another player.
- `PONG`: heartbeat response with server timestamp.
- `LEAVE`: explicit departure or expired disconnected membership.
- `ERROR`: rejected command, invalid payload or rate limit.

## 5. Presence and reconnect

- One player can own at most one active map membership; DB primary key is `map_instance_members.player_id`.
- Unexpected socket loss keeps the membership and avatar visible for the configured reconnect grace period (prototype default: 60 seconds).
- Reconnect requires the same player JWT plus matching `instance_id` and `session_id`.
- A reconnect updates the membership lease; the old socket cannot detach the replacement socket.
- After grace expiry, the membership is deleted, instance count decremented and LEAVE broadcast.
- Explicit LEAVE releases the membership immediately.
- Stale memberships are also removed during subsequent map entry allocation.

## 6. Prototype parameters and known limits

| Parameter | Current prototype | Status |
|---|---:|---|
| Instance admission capacity | 20 players | target test value; not load-certified |
| Reconnect grace | 60 seconds | prototype; tune after network tests |
| Movement report rate | 10 Hz | prototype; tune after client profiling |
| Maximum movement speed | 160 logical units/second | prototype; coordinate unit is not final |
| Preset action rate | 5 per 10 seconds | prototype |
| AOI | all connected players in the same instance | fallback until AOI radius/grid is tuned |
| Spawn points | 20 deterministic prototype points | placeholder; replace with approved map resource data |

The connection manager is in process memory. This PR supports one API process only. Before running multiple API workers/replicas, replace it with Redis-backed online presence and Pub/Sub (or an equivalent shared fan-out layer), and add cross-node integration tests. Do not advertise horizontal scalability yet.
