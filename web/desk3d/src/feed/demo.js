import { createTimer } from 'animejs';
import { normalize } from './normalize.js';
import { LEAD, SEATS } from '../config.js';

const REQUESTS = [
  {
    title: 'Push notification opt-in for the mobile apps',
    plan: [
      ['systems', 'Add the device-token endpoint'],
      ['ios', 'Build the iOS opt-in sheet'],
      ['android', 'Build the Android opt-in dialog'],
    ],
    notes: [{ after: 6500, from: 'systems', to: 'ios', text: 'Device-token endpoint is up on staging' }],
  },
  {
    title: 'Fix the checkout flicker on web',
    plan: [
      ['web', 'Trace and fix the checkout re-render'],
      ['quality', 'Gate the checkout fix'],
    ],
    notes: [{ after: 5600, from: 'web', to: 'quality', text: 'Preview is ready for the gates' }],
  },
  {
    title: 'Usage metrics on the dashboard',
    plan: [
      ['systems', 'Expose usage metrics from GreptimeDB'],
      ['web', 'Chart usage on the dashboard'],
      ['infra', 'Check GreptimeDB headroom on Railway'],
    ],
    notes: [{ after: 5200, from: 'systems', to: 'web', text: 'Metrics route returns p50 and p95 now' }],
  },
  {
    title: 'Release 2.4 to the stores',
    plan: [
      ['ios', 'Ship 2.4 to TestFlight'],
      ['android', 'Ship 2.4 to the Play internal track'],
      ['quality', 'Supply-chain check for 2.4'],
    ],
    notes: [],
  },
];

const TOOLS = {
  systems: ['desk_index_query', 'desk_events_query', 'desk_cache', 'desk_contract_propose'],
  web: ['desk_vercel_deployments', 'desk_preview_check', 'desk_lsp_diagnostics', 'desk_bundle_secret_scan'],
  android: ['desk_play_track_status', 'desk_artifact_size_delta', 'desk_lint_baseline_diff', 'desk_contract_ack'],
  ios: ['desk_testflight_status', 'desk_entitlements_diff', 'desk_review_risk_check', 'desk_contract_ack'],
  infra: ['desk_railway_status', 'desk_railway_logs', 'desk_db_health', 'desk_vps_units'],
  quality: ['desk_gates_run', 'desk_secret_scan', 'desk_supply_chain_check', 'desk_greptile_review'],
};

const RESOURCE_USE = {
  systems: ['timescaledb', 'greptimedb', 'dragonflydb', 'hindsight'],
  web: ['hindsight', 'ragflow'],
  android: ['hindsight', 'ragflow'],
  ios: ['hindsight', 'ragflow'],
  infra: ['greptimedb', 'timescaledb', 'dragonflydb'],
  quality: ['ragflow', 'hindsight'],
};

const rand = (a, b) => a + Math.random() * (b - a);
const pick = (list) => list[Math.floor(Math.random() * list.length)];

export function startDemo({ onEvent }) {
  let running = true;
  let seq = 0;
  const timers = new Set();

  const wait = (ms) => new Promise((resolve) => {
    if (ms <= 0) {
      resolve();
      return;
    }
    timers.add(createTimer({
      duration: ms,
      onComplete: (self) => {
        timers.delete(self);
        resolve();
      },
    }));
  });

  const emit = (type, data) => {
    if (!running) return;
    const result = normalize({ v: 1, type, ts: Date.now(), data });
    if (result.event) onEvent(result.event);
  };

  async function runTask(bot, title) {
    seq += 1;
    const taskId = `T-${String(seq).padStart(3, '0')}`;
    emit('task.assigned', { taskId, from: LEAD.id, to: bot, title });
    await wait(rand(900, 1300));
    emit('bot.status', { bot, status: 'thinking' });
    await wait(rand(1200, 2000));
    emit('bot.status', { bot, status: 'working' });
    const steps = 3 + Math.floor(Math.random() * 3);
    for (let i = 0; i < steps && running; i += 1) {
      const tool = pick(TOOLS[bot]);
      const callId = `${taskId}.${i + 1}`;
      emit('tool.call', { bot, tool, callId, taskId });
      if (Math.random() < 0.65) {
        await wait(rand(280, 520));
        emit('gateway.request', { bot, resource: pick(RESOURCE_USE[bot]), ok: true, ms: Math.round(rand(18, 160)) });
      }
      await wait(rand(700, 1400));
      const ok = Math.random() > 0.1;
      emit('tool.result', { bot, callId, tool, ok, ms: Math.round(rand(400, 9000)) });
      if (!ok) {
        emit('bot.status', { bot, status: 'blocked', detail: `${tool} failed, retrying` });
        await wait(rand(1600, 2400));
        emit('bot.status', { bot, status: 'working' });
      }
      emit('task.progress', { taskId, bot, progress: (i + 1) / steps });
      await wait(rand(350, 800));
    }
    emit('task.completed', { taskId, bot, ok: true, summary: title });
    emit('bot.status', { bot, status: 'idle' });
  }

  async function loop() {
    emit('desk.snapshot', {
      bots: [
        { id: LEAD.id, status: 'idle' },
        ...SEATS.map((s) => ({ id: s.id, status: 'idle' })),
      ],
    });
    await wait(2800);
    let round = 0;
    while (running) {
      const request = REQUESTS[round % REQUESTS.length];
      round += 1;
      emit('request.received', { requestId: `R-${round}`, title: request.title });
      emit('bot.status', { bot: LEAD.id, status: 'thinking' });
      await wait(1700);
      emit('bot.status', { bot: LEAD.id, status: 'working' });
      const notes = request.notes.map((n) => wait(n.after).then(() => emit('message', { from: n.from, to: n.to, text: n.text })));
      await Promise.all([
        ...request.plan.map(([bot, title], i) => wait(i * 650).then(() => runTask(bot, title))),
        ...notes,
      ]);
      await wait(900);
      emit('note', { bot: LEAD.id, text: `Closing out: ${request.title}` });
      emit('message', { from: LEAD.id, to: 'outside', text: `Done: ${request.title}` });
      emit('bot.status', { bot: LEAD.id, status: 'idle' });
      await wait(rand(2600, 3800));
    }
  }

  loop();

  return {
    stop() {
      running = false;
      for (const timer of timers) timer.cancel();
      timers.clear();
    },
  };
}
