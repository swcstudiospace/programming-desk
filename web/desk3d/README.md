# Programming Desk 3D

The live 3D view of the Programming Desk at `https://desk.swcstudio.space/`. Lead is a standing commander robot outside the desk, the six seats (Systems, Web, Android, iOS, Infra, Quality) are seated robots at consoles around a hex desk, and the Desk Gateway with its Railway data planes sits underneath. Every tool call, gateway request, status report and task the gateway sees shows up as motion in the scene and as a line in the event log.

Rendering is three.js. All motion is anime.js 4.5: its Three.js adapter animates meshes, materials, lights, the camera and instanced particles directly.

## How it is served

The desk gateway (`services/desk-gateway`) serves the built page at `/` behind a sign-in, and streams events on `/desk/events`. The event contract is [Desk live events v1](../../contracts/events/desk-live-v1.md).

| Setting in `/etc/desk-gateway/gateway.env` | Meaning |
| --- | --- |
| `DESK_VIEW_PASSPHRASE` | Passphrase for the sign-in page. Without it, `/` shows the seat connection page instead of the view. |
| `DESK_VIEW_SECRET` | Key that signs viewer sessions. Changing it, or the passphrase, signs everyone out. |

Sessions last 30 days. Eight wrong passphrases from one address in ten minutes block that address for the rest of the window.

## Build

```bash
cd web/desk3d
npm ci
npm run build          # dist/ plus services/desk-gateway/src/desk_gateway/web/desk3d.html
npm run dev            # http://localhost:5173 with the demo feed, rebuilds on save
```

`npm run build` writes three pages:

| File | Use |
| --- | --- |
| `services/desk-gateway/src/desk_gateway/web/desk3d.html` | The page the gateway serves. It connects to `/desk/events` on its own host. Restart `desk-gateway` after rebuilding. |
| `dist/desk3d.html` | Standalone page. Pass `?gateway=wss://…` or use the Feed panel. |
| `dist/desk3d.artifact.html` | Demo-only copy for hosts that block outside connections. |

## Controls

| Key | View |
| --- | --- |
| `0` or `Esc` | Whole desk |
| `L` | Lead |
| `G` | Desk Gateway and Railway |
| `1`–`6` | Systems, Web, Android, iOS, Infra, Quality |

Drag to orbit and scroll to zoom. Click a robot, its label or its roster row to open its detail card.

## Where things live

| File | What it does |
| --- | --- |
| `src/config.js` | Lead, the six seats and their colours, the gateway, and the Railway services |
| `src/feed/contract.js` | Validation rules for each event type |
| `src/feed/normalize.js` | Turns a raw frame into events |
| `src/feed/gateway.js` | WebSocket client with reconnect; stops on an ended session |
| `src/feed/demo.js` | Demo feed, sent through the same normalizer as live events |
| `src/desk/controller.js` | Applies events to desk state, the 3D scene and the HUD |
| `src/scene/robot.js` | The robot model, its visor faces, poses and antenna light for each status |
| `src/scene/station.js`, `lead.js` | A seat (robot, console, pad, screen, labels) and Lead's platform |
| `src/scene/gateway.js` | Desk Gateway core and Railway services |
| `src/scene/packets.js` | Message packets along arcs and instanced tool-call bursts |
| `src/scene/screen.js` | The holographic screen above each seat, drawn to a canvas texture |
| `src/scene/stage.js` | Renderer, bloom, labels, orbit controls and the shared frame loop |
| `src/hud/hud.js` | Roster, event log, focus card and feed panel |

## How anime.js drives the scene

- `import 'animejs/adapters/three'` registers the adapter, so `animate(mesh, { y, rotateY, scale, opacity, emissiveIntensity })` works on three.js objects and resolves material fields automatically.
- `engine.useDefaultMainLoop = false` and `engine.update()` inside `renderer.setAnimationLoop` keep anime.js and three.js on one frame.
- Robots are jointed groups (torso, head, shoulders, elbows). A status change eases every joint into a pose, then starts that status's loops: blinking and glancing when idle, a scanning visor and hand-to-chin when thinking, typing hands and a talking mouth when working, squinting amber eyes when blocked, red X eyes and a shake on error, and a slumped body when offline. The antenna and ear lights blink in the status colour.
- Tool-call bursts come from one `InstancedMesh` animated through `getInstances()` with `stagger`.
- The intro is a `createTimeline` with a staggered rise of the seats.
- Tool tags and log lines reveal with `scrambleText`.
- `prefers-reduced-motion` turns off loops, bursts and the intro.
