import { GATEWAY, LEAD, RESOURCES, SEATS } from './config.js';
import { createDeskScene } from './scene/index.js';
import { createDesk } from './desk/controller.js';
import { createHud } from './hud/hud.js';
import { connectGateway } from './feed/gateway.js';
import { startDemo } from './feed/demo.js';

const HOSTED = typeof __DESK_HOSTED__ !== 'undefined' && __DESK_HOSTED__;
const GATEWAY_MODE = typeof __DESK_GATEWAY__ !== 'undefined' && __DESK_GATEWAY__;
const SAME_ORIGIN_FEED = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/desk/events`;
const STORAGE_KEY = 'desk3d.gateway';
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const seatKeys = { [LEAD.id]: 'L', ...Object.fromEntries(SEATS.map((s, i) => [s.id, String(i + 1)])) };

const remember = (url) => {
  try {
    localStorage.setItem(STORAGE_KEY, url);
  } catch {
    return;
  }
};

const recall = () => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

let feed = null;
let demo = null;
let desk = null;

const stageHost = document.getElementById('stage');
let scene;
try {
  scene = createDeskScene(stageHost, {
    lead: LEAD,
    seats: SEATS,
    gateway: GATEWAY,
    resources: RESOURCES,
    reducedMotion,
    onPick: (id) => view(id),
    insets: () => {
      const width = stageHost.clientWidth;
      const side = (selector) => {
        const rail = document.querySelector(selector);
        if (!rail || getComputedStyle(rail).display === 'none') return null;
        const rect = rail.getBoundingClientRect();
        return rect.top < 120 ? rect : null;
      };
      const left = side('.rail--left');
      const right = side('.rail--right');
      return { left: left ? left.right + 16 : 0, right: right ? width - right.left + 16 : 0 };
    },
  });
} catch (err) {
  const note = document.createElement('p');
  note.className = 'stage-error';
  note.textContent = 'The 3D desk needs WebGL, and this browser has it turned off or unavailable. Try another browser or enable hardware acceleration.';
  stageHost.append(note);
  throw err;
}

const hud = createHud({
  reducedMotion,
  hosted: HOSTED,
  gatewayMode: GATEWAY_MODE,
  seatKeys,
  onView: (id) => view(id),
  onConnect: (url) => connect(url),
  onDisconnect: () => disconnect(),
  onDemo: () => runDemo(),
  onLive: () => connect(SAME_ORIGIN_FEED),
});

function view(id) {
  scene.fly(id);
  hud.focus(id);
}

function resetDesk() {
  feed?.close();
  feed = null;
  demo?.stop();
  demo = null;
  desk?.dispose();
  hud.clearLog();
  desk = createDesk({ scene, hud, lead: LEAD, seats: SEATS, gateway: GATEWAY, resources: RESOURCES });
}

function runDemo() {
  resetDesk();
  hud.setFeed({
    mode: 'demo',
    message: HOSTED ? '' : 'Showing simulated events. Nothing on screen comes from the gateway. Choose Go live to return.',
  });
  demo = startDemo({ onEvent: (evt) => desk.apply(evt) });
}

const stateMessage = ({ state, attempt, message }) => {
  if (state === 'connecting') return 'Connecting to the Desk Gateway.';
  if (state === 'live') return 'Connected. Waiting for desk events.';
  if (state === 'reconnecting') return `Can't reach the gateway. Retrying, attempt ${attempt}.`;
  if (state === 'offline') return 'Disconnected from the gateway.';
  return message || '';
};

function connect(url) {
  resetDesk();
  if (!GATEWAY_MODE) {
    remember(url);
    hud.setGatewayUrl(url);
  }
  feed = connectGateway({
    url,
    onEvent: (evt) => desk.apply(evt),
    onReject: (detail) => hud.reject(detail),
    onState: (state) => hud.setFeed({ mode: 'live', ...state, message: stateMessage(state) }),
  });
}

function disconnect() {
  if (!feed) return;
  feed.close();
  feed = null;
}

window.addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest?.('input, textarea, select')) return;
  const key = e.key.toLowerCase();
  if (key === 'escape' || key === '0') view('overview');
  else if (key === 'l') view(LEAD.id);
  else if (key === 'g') view('gateway');
  else {
    const seat = SEATS[Number(key) - 1];
    if (seat) view(seat.id);
  }
});

document.fonts?.ready.then(() => scene.redraw());

scene.start();
scene.intro();

const requested = GATEWAY_MODE ? SAME_ORIGIN_FEED : HOSTED ? null : new URLSearchParams(window.location.search).get('gateway') || recall();
if (!HOSTED && !GATEWAY_MODE && window.location.host) {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  document.getElementById('gateway-url').placeholder = `${scheme}://${window.location.host}/desk/events`;
}
if (requested) connect(requested);
else runDemo();
