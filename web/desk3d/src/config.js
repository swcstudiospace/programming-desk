export const LEAD = {
  id: 'lead',
  name: 'Lead',
  role: 'Takes requests from outside and delegates to the desk',
  hue: '#f4e9d0',
};

export const SEATS = [
  { id: 'systems', name: 'Systems', role: 'Backend and contracts', hue: '#ff7866' },
  { id: 'web', name: 'Web', role: 'Web and edge', hue: '#ffcf5a' },
  { id: 'android', name: 'Android', role: 'Android apps', hue: '#5fe39a' },
  { id: 'ios', name: 'iOS', role: 'iOS apps', hue: '#4fd2ff' },
  { id: 'infra', name: 'Infra', role: 'Infrastructure and Railway', hue: '#7f8cff' },
  { id: 'quality', name: 'Quality', role: 'Quality and security', hue: '#e070ff' },
];

export const GATEWAY = {
  id: 'gateway',
  name: 'Desk Gateway',
  where: 'VPS',
  hue: '#9ff5e6',
};

export const RESOURCES = [
  { id: 'greptimedb', name: 'GreptimeDB', project: 'Ultrathink', kind: 'db' },
  { id: 'timescaledb', name: 'TimescaleDB', project: 'Ultrathink', kind: 'db' },
  { id: 'dragonflydb', name: 'DragonflyDB', project: 'Ultrathink', kind: 'db' },
  { id: 'hindsight', name: 'Hindsight', project: 'Agent Substrate', kind: 'app' },
  { id: 'ragflow', name: 'RAGFlow', project: 'Agent Substrate', kind: 'app' },
];

export const STATUSES = ['idle', 'thinking', 'working', 'blocked', 'error', 'offline'];

export const STATUS_LABELS = {
  idle: 'Idle',
  thinking: 'Thinking',
  working: 'Working',
  blocked: 'Blocked',
  error: 'Error',
  offline: 'Offline',
};

export const SEMANTIC = {
  ok: '#58e0a0',
  warn: '#ffb547',
  bad: '#ff5d6c',
};
