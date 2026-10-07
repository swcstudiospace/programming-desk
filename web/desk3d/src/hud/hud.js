import { animate, scrambleText } from 'animejs';
import { STATUS_LABELS } from '../config.js';

const MAX_LOG = 80;
const $ = (id) => document.getElementById(id);

const make = (tagName, className, text) => {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

const FEED_TEXT = {
  demo: 'Demo feed',
  connecting: 'Connecting',
  live: 'Live',
  reconnecting: 'Reconnecting',
  offline: 'Offline',
  error: 'Not connected',
};

export function createHud({ reducedMotion, hosted, gatewayMode, seatKeys, onView, onConnect, onDisconnect, onDemo, onLive }) {
  const app = document.querySelector('.app');
  const roster = $('roster');
  const log = $('log');
  const rows = new Map();
  let focused = null;
  let bots = new Map();
  let rejects = 0;

  const chip = (status) => {
    const node = make('span', 'chip', STATUS_LABELS[status] || status);
    node.dataset.status = status;
    return node;
  };

  function renderRoster(list) {
    bots = new Map(list.map((b) => [b.id, b]));
    roster.replaceChildren();
    rows.clear();
    list.forEach((bot) => {
      if (bot.kind === 'seat' && !roster.querySelector('.roster__divider')) {
        roster.append(make('li', 'roster__divider', `The desk · ${list.filter((b) => b.kind === 'seat').length} seats`));
      }
      const li = make('li');
      const button = make('button', 'bot');
      button.type = 'button';
      button.style.setProperty('--hue', bot.hue);
      button.dataset.id = bot.id;
      const main = make('span', 'bot__main');
      const name = make('span', 'bot__name', bot.name);
      const task = make('span', 'bot__task', '');
      main.append(name, task);
      const status = chip(bot.status);
      const key = make('kbd', 'bot__key', seatKeys[bot.id] || '');
      button.append(make('i', 'bot__swatch'), main, status, key);
      button.addEventListener('click', () => onView(bot.id));
      li.append(button);
      roster.append(li);
      rows.set(bot.id, { button, name, task, status });
      updateBot(bot);
    });
  }

  function updateBot(bot) {
    bots.set(bot.id, bot);
    const row = rows.get(bot.id);
    if (row) {
      row.name.textContent = bot.name;
      row.status.textContent = STATUS_LABELS[bot.status];
      row.status.dataset.status = bot.status;
      row.button.dataset.status = bot.status;
      row.button.classList.toggle('is-unassigned', !!bot.unassigned);
      const line = bot.kind === 'lead'
        ? 'Outside the desk'
        : bot.task ? bot.task.title : bot.unassigned ? 'Unassigned seat' : bot.detail || bot.role || 'Waiting for Lead';
      row.task.textContent = line;
    }
    if (focused === bot.id) renderFocus();
  }

  function logEntry({ ts, kind, actor, hue, tone, text, meta }, { quiet = false } = {}) {
    const li = make('li', 'entry');
    li.dataset.kind = kind;
    if (tone) li.dataset.tone = tone;
    if (hue) li.style.setProperty('--hue', hue);
    const time = make('time', 'entry__time', clock(ts));
    time.dateTime = new Date(ts).toISOString();
    const body = make('span', 'entry__text', text);
    li.append(time, make('span', 'entry__actor', actor), body);
    if (meta) li.append(make('span', 'entry__meta', meta));
    log.prepend(li);
    while (log.children.length > MAX_LOG) log.lastElementChild.remove();
    if (!reducedMotion && !quiet) {
      animate(body, { textContent: scrambleText({ text, chars: 'a-z0-9' }), duration: 360 });
      animate(li, { opacity: [0, 1], translateY: [-6, 0], duration: 280, ease: 'outQuad' });
    }
  }

  function reject({ reason }) {
    rejects += 1;
    const node = $('rejects');
    node.hidden = false;
    node.textContent = `${rejects} event${rejects === 1 ? '' : 's'} ignored. Last: ${reason}.`;
  }

  function meters({ active, tools, gateway }) {
    $('m-active').textContent = active;
    $('m-tools').textContent = tools;
    $('m-gateway').textContent = gateway;
  }

  function setFeed({ mode, state, message, retryIn }) {
    const pill = $('feed-pill');
    const key = mode === 'demo' ? 'demo' : state;
    pill.dataset.state = key;
    pill.textContent = key === 'reconnecting' && retryIn ? `Retry in ${Math.ceil(retryIn / 1000)} s` : FEED_TEXT[key] || key;
    $('feed-status').textContent = message || '';
    $('gateway-status').textContent = message || '';
    app.dataset.feed = key;
  }

  function renderFocus() {
    const card = $('focus');
    const bot = bots.get(focused);
    if (!bot) {
      card.hidden = true;
      return;
    }
    card.hidden = false;
    card.style.setProperty('--hue', bot.hue);
    $('focus-name').textContent = bot.name;
    $('focus-role').textContent = bot.kind === 'lead' ? 'Outside the desk · talks to the world' : bot.role || 'Desk bot';
    const status = $('focus-status');
    status.textContent = STATUS_LABELS[bot.status];
    status.dataset.status = bot.status;
    $('focus-task-label').textContent = bot.kind === 'lead' ? 'Delegated now' : 'Current task';
    if (bot.kind === 'lead') {
      const active = [...bots.values()].filter((b) => b.task);
      $('focus-task').textContent = active.length ? active.map((b) => `${b.name}: ${b.task.title}`).join(' · ') : 'Nothing delegated right now';
      $('focus-bar').style.width = '0%';
    } else {
      $('focus-task').textContent = bot.task ? bot.task.title : bot.unassigned ? 'This seat has no bot yet' : 'Waiting for Lead';
      $('focus-bar').style.width = `${Math.round((bot.task?.progress || 0) * 100)}%`;
    }
    $('focus-done').textContent = bot.done;
    $('focus-failed').textContent = bot.failed;
    $('focus-calls').textContent = bot.toolCalls;
    const tools = $('focus-tools');
    tools.replaceChildren();
    if (!bot.tools.length) tools.append(make('li', 'is-empty', 'No tool calls yet'));
    for (const t of bot.tools) {
      const li = make('li', '', t.text);
      li.dataset.ok = t.ok === undefined ? 'pending' : String(t.ok);
      tools.append(li);
    }
  }

  function focus(id) {
    focused = bots.has(id) ? id : null;
    for (const [botId, row] of rows) row.button.setAttribute('aria-pressed', String(botId === focused));
    renderFocus();
    document.querySelectorAll('button[data-view]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === id)));
  }

  document.querySelectorAll('button[data-view]').forEach((button) => {
    button.addEventListener('click', () => onView(button.dataset.view));
  });
  $('focus-close').addEventListener('click', () => onView('overview'));

  document.querySelectorAll('button[data-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      log.dataset.filter = button.dataset.filter;
      document.querySelectorAll('button[data-filter]').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
    });
  });

  document.querySelectorAll('button[data-panel]').forEach((button) => {
    button.addEventListener('click', () => {
      const next = app.dataset.panel === button.dataset.panel ? '' : button.dataset.panel;
      app.dataset.panel = next;
      document.querySelectorAll('button[data-panel]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.panel === next)));
    });
  });

  const panel = $('feed-panel');
  const toggle = $('feed-toggle');
  toggle.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    toggle.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden && !hosted && !gatewayMode) $('gateway-url').focus();
  });

  $('feed-form').hidden = hosted || gatewayMode;
  $('hosted-note').hidden = !hosted;
  $('gateway-note').hidden = !gatewayMode;
  document.querySelectorAll('.js-live').forEach((b) => b.addEventListener('click', () => onLive?.()));
  $('feed-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const url = $('gateway-url').value.trim();
    if (!/^wss?:\/\//i.test(url)) {
      $('feed-status').textContent = 'Enter a WebSocket address that starts with ws:// or wss://.';
      return;
    }
    onConnect(url);
  });
  $('feed-disconnect').addEventListener('click', () => onDisconnect());
  document.querySelectorAll('.js-demo').forEach((b) => b.addEventListener('click', () => onDemo()));

  return {
    renderRoster,
    updateBot,
    log: logEntry,
    reject,
    meters,
    setFeed,
    focus,
    setGatewayUrl: (url) => {
      $('gateway-url').value = url || '';
    },
    clearLog: () => log.replaceChildren(),
  };
}
