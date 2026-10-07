import { normalize, unpack } from './normalize.js';

const MAX_DELAY = 30000;
const FINAL_CLOSES = {
  4401: 'Your desk view session has ended. Reload the page to sign in again.',
  4403: 'The gateway refused this page. Open the desk view from its own address.',
};

export function connectGateway({ url, onEvent, onReject, onState }) {
  let socket = null;
  let timer = 0;
  let attempt = 0;
  let stopped = false;

  const schedule = () => {
    attempt += 1;
    const base = Math.min(MAX_DELAY, 1000 * 2 ** (attempt - 1));
    const delay = Math.round(base * (0.8 + Math.random() * 0.4));
    onState({ state: 'reconnecting', attempt, retryIn: delay });
    timer = setTimeout(open, delay);
  };

  const receive = (message) => {
    if (typeof message.data !== 'string') {
      onReject({ reason: 'binary frames are not supported' });
      return;
    }
    for (const raw of unpack(message.data)) {
      const result = normalize(raw);
      if (result.event) onEvent(result.event);
      else onReject({ reason: result.error, type: result.type });
    }
  };

  function open() {
    if (stopped) return;
    onState({ state: attempt ? 'reconnecting' : 'connecting', attempt });
    try {
      socket = new WebSocket(url);
    } catch {
      stopped = true;
      onState({ state: 'error', message: 'That address is not a valid WebSocket URL. Use ws:// or wss://.' });
      return;
    }
    socket.addEventListener('open', () => {
      attempt = 0;
      onState({ state: 'live' });
    });
    socket.addEventListener('message', receive);
    socket.addEventListener('close', (event) => {
      socket = null;
      if (stopped) return;
      const final = FINAL_CLOSES[event.code];
      if (final) {
        stopped = true;
        onState({ state: 'error', message: final });
        return;
      }
      schedule();
    });
  }

  open();

  return {
    close() {
      stopped = true;
      clearTimeout(timer);
      if (socket) socket.close(1000, 'viewer disconnected');
      socket = null;
      onState({ state: 'offline' });
    },
  };
}
