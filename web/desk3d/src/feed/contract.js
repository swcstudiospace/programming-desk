import { STATUSES } from '../config.js';

const statusSet = new Set(STATUSES);

const isText = (v) => typeof v === 'string' && v.length > 0;
const isOptionalText = (v) => v === undefined || v === null || typeof v === 'string';
const isUnit = (v) => typeof v === 'number' && v >= 0 && v <= 1;

export const RULES = {
  'desk.snapshot': (d) => Array.isArray(d.bots) || 'bots must be an array',
  'request.received': (d) => isText(d.title) || 'title is required',
  'bot.status': (d) => (isText(d.bot) && statusSet.has(d.status)) || `bot and a status of ${STATUSES.join(', ')} are required`,
  'task.assigned': (d) => (isText(d.taskId) && isText(d.to) && isText(d.title)) || 'taskId, to and title are required',
  'task.progress': (d) => (isText(d.taskId) && isText(d.bot) && isUnit(d.progress)) || 'taskId, bot and progress (0 to 1) are required',
  'task.completed': (d) => (isText(d.taskId) && isText(d.bot)) || 'taskId and bot are required',
  'message': (d) => (isText(d.from) && isText(d.to) && isOptionalText(d.text)) || 'from and to are required',
  'tool.call': (d) => (isText(d.bot) && isText(d.tool)) || 'bot and tool are required',
  'tool.result': (d) => (isText(d.bot) && typeof d.ok === 'boolean') || 'bot and ok are required',
  'gateway.request': (d) => (isText(d.bot) && isText(d.resource)) || 'bot and resource are required',
  note: (d) => (isText(d.bot) && isOptionalText(d.text)) || 'bot is required',
};

export const EVENT_TYPES = Object.keys(RULES);

export function check(type, data) {
  const rule = RULES[type];
  if (!rule) return `unknown event type "${type}"`;
  const verdict = rule(data);
  return verdict === true ? null : verdict;
}
