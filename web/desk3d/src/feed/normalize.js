import { check } from './contract.js';

const toTime = (ts) => {
  if (typeof ts === 'number' && Number.isFinite(ts)) return ts < 1e12 ? ts * 1000 : ts;
  if (typeof ts === 'string') {
    const parsed = Date.parse(ts);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return Date.now();
};

export function normalize(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { error: 'event is not a JSON object' };
  }
  const type = raw.type;
  if (typeof type !== 'string') return { error: 'event has no "type"' };
  const data = raw.data && typeof raw.data === 'object' ? raw.data : {};
  const problem = check(type, data);
  if (problem) return { error: problem, type };
  return { event: { type, ts: toTime(raw.ts), ...data } };
}

export function unpack(payload) {
  if (typeof payload !== 'string') return [];
  const text = payload.trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    const out = [];
    for (const line of text.split('\n')) {
      const chunk = line.trim();
      if (!chunk) continue;
      try {
        out.push(JSON.parse(chunk));
      } catch {
        out.push(null);
      }
    }
    return out;
  }
}
