import { SEMANTIC, STATUS_LABELS } from '../config.js';
import { normalize } from '../feed/normalize.js';

const WINDOW_MS = 60000;
const TOOL_LINES = 6;

export function createDesk({ scene, hud, lead, seats, gateway, resources }) {
  const bots = new Map();
  const alias = new Map();
  const tasks = new Map();
  const toolTimes = [];
  const gatewayTimes = [];
  const unknown = new Set();
  const resourceNames = new Map(resources.map((r) => [r.id, r.name]));
  let request = null;

  const add = (bot, kind) => bots.set(bot.id, {
    ...bot,
    kind,
    status: kind === 'seat' && bot.unassigned ? 'offline' : 'idle',
    detail: '',
    task: null,
    tools: [],
    done: 0,
    failed: 0,
    toolCalls: 0,
  });
  add(lead, 'lead');
  seats.forEach((s) => add(s, 'seat'));

  const node = (id) => (id === lead.id ? scene.lead : scene.stations.get(id));
  const nameOf = (id) => {
    if (id === 'outside') return 'Outside';
    if (id === gateway.id) return gateway.name;
    return bots.get(id)?.name || resourceNames.get(id) || id;
  };
  const hueOf = (id) => bots.get(id)?.hue || lead.hue;
  const known = (id) => {
    if (!id) return null;
    const key = alias.get(id) || id;
    return bots.has(key) || key === 'outside' ? key : null;
  };

  const resolve = (id) => {
    const key = known(id);
    if (key || !id) return key;
    if (!unknown.has(id)) {
      unknown.add(id);
      hud.reject({ reason: `unknown bot "${id}"` });
    }
    return null;
  };

  const describe = (evt) => {
    const bot = (id) => bots.get(known(id));
    switch (evt.type) {
      case 'request.received':
        return { ts: evt.ts, kind: 'task', actor: 'Outside', hue: lead.hue, text: `Request to Lead: ${evt.title}` };
      case 'bot.status': {
        const b = bot(evt.bot);
        if (!b || !(evt.status === 'blocked' || evt.status === 'error' || evt.detail)) return null;
        const tone = evt.status === 'error' ? 'bad' : evt.status === 'blocked' ? 'warn' : '';
        return { ts: evt.ts, kind: 'status', actor: b.name, hue: b.hue, tone, text: `${STATUS_LABELS[evt.status]}${evt.detail ? `: ${evt.detail}` : ''}` };
      }
      case 'task.assigned': {
        const to = bot(evt.to);
        const from = known(evt.from || lead.id) || lead.id;
        if (!to) return null;
        return { ts: evt.ts, kind: 'task', actor: nameOf(from), hue: hueOf(from), text: `Assigned ${to.name}: ${evt.title}`, meta: evt.taskId };
      }
      case 'task.completed': {
        const b = bot(evt.bot);
        if (!b) return null;
        const ok = evt.ok !== false;
        const title = b.task?.id === evt.taskId ? b.task.title : evt.summary || evt.taskId;
        return { ts: evt.ts, kind: 'task', actor: b.name, hue: b.hue, tone: ok ? 'ok' : 'bad', text: `${ok ? 'Finished' : 'Failed'}: ${title}`, meta: evt.taskId };
      }
      case 'message': {
        const from = known(evt.from);
        const to = known(evt.to);
        if (!from || !to) return null;
        return { ts: evt.ts, kind: 'task', actor: nameOf(from), hue: hueOf(from), text: `To ${nameOf(to)}${evt.text ? `: ${evt.text}` : ''}` };
      }
      case 'note': {
        const b = bot(evt.bot);
        if (!b) return null;
        return { ts: evt.ts, kind: 'task', actor: b.name, hue: b.hue, text: evt.text || 'Note' };
      }
      case 'tool.call': {
        const b = bot(evt.bot);
        if (!b) return null;
        return { ts: evt.ts, kind: 'tool', actor: b.name, hue: b.hue, text: evt.tool, meta: evt.callId };
      }
      case 'tool.result': {
        const b = bot(evt.bot);
        if (!b || evt.ok) return null;
        return { ts: evt.ts, kind: 'tool', actor: b.name, hue: b.hue, tone: 'bad', text: `${evt.tool || evt.callId || 'Tool call'} failed`, meta: evt.callId };
      }
      case 'gateway.request': {
        const b = bot(evt.bot);
        if (!b) return null;
        const ok = evt.ok !== false;
        return {
          ts: evt.ts,
          kind: 'gateway',
          actor: b.name,
          hue: b.hue,
          tone: ok ? '' : 'bad',
          text: `${nameOf(evt.resource)} via gateway${evt.method ? ` ${evt.method}` : ''}${ok ? '' : ' failed'}`,
          meta: typeof evt.ms === 'number' ? formatMs(evt.ms) : '',
        };
      }
      default:
        return null;
    }
  };

  const log = (evt) => {
    const line = describe(evt);
    if (line) hud.log(line);
  };

  const refresh = (bot) => {
    const target = node(bot.id);
    if (target && bot.kind === 'seat') {
      target.screen.set({
        body: bot.task?.title || '',
        progress: bot.task ? bot.task.progress : null,
        lines: bot.tools.map((t) => ({ text: t.ms ? `${t.text}  ${formatMs(t.ms)}` : t.text, ok: t.ok })),
        empty: bot.unassigned ? 'Unassigned seat' : 'Waiting for Lead',
      });
    }
    if (target && bot.kind === 'lead') {
      target.screen.set({
        body: request?.title || '',
        lines: [...bots.values()].filter((b) => b.task).map((b) => ({ text: `${b.name}: ${b.task.title}` })),
      });
    }
    hud.updateBot(bot);
  };

  const meters = () => {
    const now = Date.now();
    while (toolTimes.length && now - toolTimes[0] > WINDOW_MS) toolTimes.shift();
    while (gatewayTimes.length && now - gatewayTimes[0] > WINDOW_MS) gatewayTimes.shift();
    hud.meters({
      active: [...bots.values()].filter((b) => b.task).length,
      tools: toolTimes.length,
      gateway: gatewayTimes.length,
    });
  };
  const ticker = setInterval(meters, 2000);

  const setStatus = (bot, status, detail = '') => {
    bot.status = status;
    bot.detail = detail;
    node(bot.id)?.setStatus(status, { dim: bot.unassigned });
    refresh(bot);
  };

  const count = (value, fallback) => (Number.isFinite(value) && value >= 0 ? value : fallback);

  const handlers = {
    'desk.snapshot'(evt) {
      const open = seats.filter((s) => bots.get(s.id).unassigned).map((s) => s.id);
      for (const entry of evt.bots) {
        if (!entry || typeof entry.id !== 'string') continue;
        let id = alias.get(entry.id) || (bots.has(entry.id) ? entry.id : null);
        let claimed = false;
        if (!id && entry.kind === 'lead') {
          id = lead.id;
          alias.set(entry.id, id);
        }
        if (!id && open.length) {
          id = open.shift();
          alias.set(entry.id, id);
          claimed = true;
        }
        if (!id) {
          hud.reject({ reason: `no free seat for "${entry.id}"` });
          continue;
        }
        const bot = bots.get(id);
        if (entry.name || entry.role || claimed) {
          bot.name = entry.name || (claimed ? entry.id : bot.name);
          bot.role = entry.role || (claimed ? '' : bot.role);
          bot.unassigned = false;
          if (bot.kind === 'seat') scene.stations.get(id).rename(bot.name, bot.role);
        }
        bot.done = count(entry.done, bot.done);
        bot.failed = count(entry.failed, bot.failed);
        bot.toolCalls = count(entry.toolCalls, bot.toolCalls);
        const status = typeof entry.status === 'string' && STATUS_LABELS[entry.status] ? entry.status : bot.status;
        setStatus(bot, status, typeof entry.detail === 'string' ? entry.detail : '');
      }

      if (Array.isArray(evt.tasks)) {
        tasks.clear();
        for (const bot of bots.values()) bot.task = null;
        for (const task of evt.tasks) {
          const id = known(task?.bot);
          if (!id || id === 'outside' || typeof task.taskId !== 'string') continue;
          const progress = Number.isFinite(task.progress) ? task.progress : 0;
          bots.get(id).task = { id: task.taskId, title: task.title || task.taskId, progress };
          tasks.set(task.taskId, id);
        }
        for (const bot of bots.values()) node(bot.id)?.setProgress?.(bot.task ? Math.max(0.02, bot.task.progress) : null);
      }

      if (Array.isArray(evt.history)) {
        hud.clearLog();
        for (const raw of evt.history) {
          const result = normalize(raw);
          const line = result.event && describe(result.event);
          if (line) hud.log(line, { quiet: true });
        }
      }

      for (const bot of bots.values()) refresh(bot);
      hud.renderRoster([...bots.values()]);
      hud.log({ ts: evt.ts, kind: 'system', actor: 'Desk', text: `Connected: ${evt.bots.length} bots on the desk` });
      meters();
    },

    'request.received'(evt) {
      request = { id: evt.requestId, title: evt.title };
      scene.send('outside', lead.id, lead.hue, { lift: 2.5, duration: 1500 }).then(() => scene.lead.robot.ping());
      refresh(bots.get(lead.id));
      log(evt);
    },

    'bot.status'(evt) {
      const id = resolve(evt.bot);
      if (!id || id === 'outside') return;
      setStatus(bots.get(id), evt.status, evt.detail || '');
      log(evt);
    },

    'task.assigned'(evt) {
      const to = resolve(evt.to);
      const from = resolve(evt.from || lead.id) || lead.id;
      if (!to || to === 'outside') return;
      const bot = bots.get(to);
      bot.task = { id: evt.taskId, title: evt.title, progress: 0 };
      tasks.set(evt.taskId, to);
      if (from === lead.id) scene.lead.robot.glance(scene.anchor(to));
      scene.send(from, to, bot.hue, { duration: 1200 }).then(() => {
        node(to)?.robot.ping();
        node(to)?.setProgress?.(0.02);
      });
      refresh(bot);
      refresh(bots.get(lead.id));
      log(evt);
    },

    'task.progress'(evt) {
      const id = resolve(evt.bot) || tasks.get(evt.taskId);
      const bot = id && bots.get(id);
      if (!bot) return;
      if (!bot.task || bot.task.id !== evt.taskId) bot.task = { id: evt.taskId, title: bot.task?.title || evt.taskId, progress: 0 };
      bot.task.progress = evt.progress;
      node(id)?.setProgress?.(evt.progress);
      refresh(bot);
    },

    'task.completed'(evt) {
      const id = resolve(evt.bot) || tasks.get(evt.taskId);
      const bot = id && bots.get(id);
      if (!bot) return;
      log(evt);
      const ok = evt.ok !== false;
      if (ok) bot.done += 1;
      else bot.failed += 1;
      bot.task = null;
      tasks.delete(evt.taskId);
      node(id)?.setProgress?.(1);
      scene.send(id, lead.id, ok ? bot.hue : SEMANTIC.bad, { duration: 1200 }).then(() => {
        scene.lead.robot.ping(ok ? bot.hue : SEMANTIC.bad);
        scene.lead.robot.glance(scene.anchor(id));
        node(id)?.setProgress?.(null);
      });
      refresh(bot);
      refresh(bots.get(lead.id));
    },

    message(evt) {
      const from = resolve(evt.from);
      const to = resolve(evt.to);
      if (!from || !to) return;
      if (from === lead.id && to === 'outside') request = null;
      scene.send(from, to, hueOf(from), { duration: 1300, lift: 1.4 }).then(() => node(to)?.robot.ping(hueOf(from)));
      refresh(bots.get(lead.id));
      log(evt);
    },

    note(evt) {
      const id = resolve(evt.bot);
      if (!id || id === 'outside') return;
      node(id)?.robot.nod();
      log(evt);
    },

    'tool.call'(evt) {
      const id = resolve(evt.bot);
      if (!id || id === 'outside') return;
      const bot = bots.get(id);
      bot.tools.unshift({ text: evt.tool, callId: evt.callId, ok: undefined });
      bot.tools.length = Math.min(bot.tools.length, TOOL_LINES);
      bot.toolCalls += 1;
      toolTimes.push(Date.now());
      scene.burst(id, bot.hue);
      node(id)?.showTool?.(evt.tool, true);
      refresh(bot);
      meters();
      log(evt);
    },

    'tool.result'(evt) {
      const id = resolve(evt.bot);
      if (!id || id === 'outside') return;
      const bot = bots.get(id);
      const entry = bot.tools.find((t) => t.callId && t.callId === evt.callId) || (evt.tool && bot.tools.find((t) => t.text === evt.tool && t.ok === undefined));
      if (entry) {
        entry.ok = evt.ok;
        entry.ms = evt.ms;
      }
      if (!evt.ok) {
        scene.burst(id, bot.hue, { ok: false, size: 14 });
        node(id)?.showTool?.(`${evt.tool || 'tool'} failed`, false);
      }
      refresh(bot);
      log(evt);
    },

    'gateway.request'(evt) {
      const id = resolve(evt.bot);
      if (!id || id === 'outside') return;
      const bot = bots.get(id);
      const ok = evt.ok !== false;
      gatewayTimes.push(Date.now());
      scene.send(id, gateway.id, bot.hue, { lift: 0.4, duration: 750 }).then(() => {
        scene.layer.pulseCore(bot.hue);
        if (!scene.layer.has(evt.resource)) return;
        scene.send(gateway.id, evt.resource, bot.hue, { lift: 0.6, duration: 700 }).then(() => scene.layer.pulse(evt.resource, bot.hue, ok));
      });
      meters();
      log(evt);
    },
  };

  for (const seat of seats) scene.stations.get(seat.id).rename(seat.name, seat.role);
  hud.renderRoster([...bots.values()]);
  for (const bot of bots.values()) {
    node(bot.id)?.setProgress?.(null);
    setStatus(bot, bot.status);
  }
  meters();

  return {
    apply(evt) {
      const handler = handlers[evt.type];
      if (handler) handler(evt);
    },
    bot: (id) => bots.get(id),
    dispose() {
      clearInterval(ticker);
    },
  };
}

function formatMs(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}
