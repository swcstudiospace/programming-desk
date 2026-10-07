# Desk live events v1

The Desk Gateway re-publishes its own traffic as Desk Event v1 on `wss://desk.swcstudio.space/desk/events`. The 3D desk view (`web/desk3d`) is the consumer. The socket needs a desk view session (sign in at `https://desk.swcstudio.space/`) and a same-site `Origin`.

## Envelope

```json
{ "v": 1, "type": "tool.call", "ts": 1790747518.512, "seq": 42, "data": { "bot": "ios", "tool": "desk_testflight_status", "callId": "9f3a1c2b" } }
```

| Field | Notes |
| --- | --- |
| `v` | Contract version, `1`. |
| `type` | One of the types below. Consumers ignore types they do not know. |
| `ts` | Epoch seconds from the gateway. The view also accepts ISO 8601 and epoch milliseconds. |
| `seq` | Increases by one per event within one gateway process. It restarts at 1 when the gateway restarts. |
| `data` | Payload for the type. |

Bot ids are the seat short names: `lead`, `systems`, `web`, `android`, `ios`, `infra`, `quality`. `outside` stands for whoever sent the request to Lead.

## Types

| Type | Data | Where the gateway gets it |
| --- | --- | --- |
| `desk.snapshot` | `bots: [{ id, status, detail?, done, failed, toolCalls }]`, `tasks: [{ taskId, bot, title, progress }]`, `history: [envelope…]` | Sent first on every connection. `history` holds up to the last 60 events so the log is not empty on arrival. |
| `request.received` | `requestId`, `title` | `POST /v1/intake` |
| `bot.status` | `bot`, `status`, `detail?` | Reported with `desk_event_emit`, or set automatically: a seat that calls a tool goes `working`, returns to `idle` after 2 minutes without calls, and shows `offline` after an hour without contact. |
| `task.assigned` | `taskId`, `from`, `to`, `title` | `desk_event_emit` kind `task.assigned` |
| `task.progress` | `taskId`, `bot`, `progress` (0 to 1) | `desk_event_emit` kind `task.progress` |
| `task.completed` | `taskId`, `bot`, `ok`, `summary?` | `desk_event_emit` kinds `task.done`, `task.completed`, `task.failed` |
| `message` | `from`, `to`, `text?` | `desk_event_emit` kind `message` or `handoff`; `desk_intake_ack` from Lead becomes a message to `outside` |
| `note` | `bot`, `text` | Any other `desk_event_emit` kind |
| `tool.call` | `bot`, `tool`, `callId` | Every tool call a seat makes through the gateway, except `desk_event_emit` itself |
| `tool.result` | `bot`, `callId`, `tool`, `ok`, `ms` | The same call finishing |
| `gateway.request` | `bot`, `resource`, `ok`, `ms` | Tools that reach a data plane: `hindsight`, `ragflow`, `greptimedb`, `timescaledb`, `dragonflydb` |

Text fields pass through the gateway's redaction before they are published.

## Reporting from a seat

Every seat already carries `desk_event_emit`. These calls drive the view:

| Call | Effect in the view |
| --- | --- |
| `desk_event_emit(kind="status", payload={"status": "thinking", "detail": "Reading the spec"})` | The seat's robot switches pose and visor face. Statuses: `idle`, `thinking`, `working`, `blocked`, `error`, `offline`. |
| `desk_event_emit(kind="task.assigned", task_id="T-31", payload={"to": "IOS", "title": "Ship 2.4 to TestFlight"})` | Lead sends a packet to the seat and its screen shows the task. `to` accepts `ios`, `IOS` or `bot-04-ios`. |
| `desk_event_emit(kind="task.progress", task_id="T-31", payload={"progress": 60})` | Progress arc on the seat's floor ring. `0–1` or `0–100`. |
| `desk_event_emit(kind="task.done", task_id="T-31", payload={"summary": "Build 412 on TestFlight"})` | Packet back to Lead. Use `task.failed` for a failure. |
| `desk_event_emit(kind="message", payload={"to": "WEB", "text": "Metrics route is live"})` | Packet between the two seats. |

## Example

```json
[
  { "v": 1, "type": "request.received", "ts": 1790747500.1, "seq": 1, "data": { "requestId": "in-3f9a1c", "title": "Ship 2.4 to TestFlight" } },
  { "v": 1, "type": "task.assigned", "ts": 1790747503.4, "seq": 2, "data": { "taskId": "T-31", "from": "lead", "to": "ios", "title": "Archive and upload 2.4" } },
  { "v": 1, "type": "bot.status", "ts": 1790747504.0, "seq": 3, "data": { "bot": "ios", "status": "working" } },
  { "v": 1, "type": "tool.call", "ts": 1790747504.0, "seq": 4, "data": { "bot": "ios", "tool": "desk_testflight_status", "callId": "9f3a1c2b" } },
  { "v": 1, "type": "tool.result", "ts": 1790747505.2, "seq": 5, "data": { "bot": "ios", "callId": "9f3a1c2b", "tool": "desk_testflight_status", "ok": true, "ms": 1180 } },
  { "v": 1, "type": "gateway.request", "ts": 1790747506.8, "seq": 6, "data": { "bot": "ios", "resource": "hindsight", "ok": true, "ms": 42 } },
  { "v": 1, "type": "task.completed", "ts": 1790747600.3, "seq": 7, "data": { "taskId": "T-31", "bot": "ios", "ok": true, "summary": "Build 412 on TestFlight" } },
  { "v": 1, "type": "message", "ts": 1790747602.9, "seq": 8, "data": { "from": "lead", "to": "outside", "text": "done: 2.4 is on TestFlight" } }
]
```
