import {
  CylinderGeometry,
  Group,
  Line,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  RingGeometry,
} from 'three';
import { animate, scrambleText } from 'animejs';
import { Robot } from './robot.js';
import { Screen } from './screen.js';
import { circle, dashedCircle, el, neon, tag, wire } from './parts.js';
import { STATUS_LABELS } from '../config.js';
import { STATUS_COLORS } from './palette.js';

const PAD_OPACITY = { idle: 0.35, thinking: 0.55, working: 0.75, blocked: 0.6, error: 0.6, offline: 0.1 };
const ARC_POINTS = 96;

export class Station {
  constructor({ bot, angle, radius, deskY, reducedMotion, onPick }) {
    this.id = bot.id;
    this.hue = bot.hue;
    this.reducedMotion = reducedMotion;
    this.status = null;

    this.group = new Group();
    this.group.position.set(Math.sin(angle) * radius, deskY, Math.cos(angle) * radius);
    this.group.rotation.y = angle;
    this.inner = new Group();
    this.group.add(this.inner);

    this.pad = new Mesh(new RingGeometry(0.62, 0.7, 64), neon(bot.hue, 1.6, 0.35));
    this.pad.rotation.x = -Math.PI / 2;
    this.pad.position.y = 0.012;

    this.spinner = new Group();
    this.spinner.position.y = 0.02;
    this.dashes = new LineSegments(dashedCircle(0.86, 28, 0.45), wire(bot.hue, 0, 2));
    this.dashes.visible = false;
    this.spinner.add(this.dashes);

    this.arc = new Line(circle(0.78, ARC_POINTS, { from: Math.PI, y: 0.022 }), wire(bot.hue, 1, 2.8));
    this.arc.geometry.setDrawRange(0, 0);

    this.robot = new Robot({ hue: bot.hue, scale: 1.2, reducedMotion });

    this.screen = new Screen({ hue: bot.hue, width: 1.7 });
    this.screen.group.position.y = 2.6;
    this.screen.set({ title: bot.name });

    const label = tag('seat-tag');
    this.tagEl = label.el;
    this.tagEl.style.setProperty('--hue', bot.hue);
    this.tagName = el('span', 'seat-tag__name', bot.name);
    this.tagStatus = el('span', 'seat-tag__status', '');
    this.tagEl.append(el('i', 'seat-tag__dot'), this.tagName, this.tagStatus);
    this.tagEl.addEventListener('click', () => onPick(this.id));
    label.obj.position.set(0, 0.02, 1.08);

    const toolTag = tag('tool-tag');
    this.toolEl = toolTag.el;
    this.toolEl.style.setProperty('--hue', bot.hue);
    this.toolTag = toolTag.obj;
    this.toolTag.position.set(1.0, 1.25, 0);
    this.toolTag.visible = false;

    this.hit = new Mesh(new CylinderGeometry(1, 1, 3.2, 10), new MeshBasicMaterial({ visible: false }));
    this.hit.position.y = 1.6;
    this.hit.userData.pick = this.id;

    this.inner.add(this.pad, this.spinner, this.arc, this.robot.group, this.screen.group, label.obj, this.toolTag, this.hit);
    this.spin = null;
    this.toolFade = null;
  }

  anchor() {
    return this.robot.anchor();
  }

  toolOrigin() {
    return this.robot.toolOrigin();
  }

  mute(muted) {
    this.tagEl.classList.toggle('is-muted', muted);
  }

  rename(name, role) {
    this.tagName.textContent = name;
    this.screen.set({ title: name });
    this.name = name;
    this.role = role;
  }

  setStatus(status, { dim = false } = {}) {
    if (status === this.status) return;
    this.status = status;
    this.robot.setDim(dim);
    this.robot.setStatus(status);
    animate(this.pad, { opacity: PAD_OPACITY[status] ?? 0.35, duration: 500 });
    const thinking = status === 'thinking';
    animate(this.dashes, { opacity: thinking ? 0.95 : 0, duration: 400 });
    if (this.spin) {
      this.spin.cancel();
      this.spin = null;
    }
    if (thinking && !this.reducedMotion) {
      this.spin = animate(this.spinner, { rotateY: '+=360', duration: 2600, ease: 'linear', loop: true });
    }
    this.tagStatus.textContent = STATUS_LABELS[status];
    this.tagEl.dataset.status = status;
    this.screen.set({ status: STATUS_LABELS[status], statusColor: STATUS_COLORS[status], dim });
  }

  setProgress(value) {
    const count = typeof value === 'number' ? Math.round(Math.max(0, Math.min(1, value)) * (ARC_POINTS + 1)) : 0;
    animate(this.arc.geometry.drawRange, {
      count,
      duration: this.reducedMotion ? 1 : 600,
      ease: 'outCubic',
      modifier: (v) => Math.round(v),
    });
  }

  showTool(text, ok) {
    this.toolEl.dataset.ok = ok === false ? 'false' : 'true';
    this.toolTag.visible = true;
    if (this.toolFade) this.toolFade.cancel();
    if (this.reducedMotion) {
      this.toolEl.textContent = text;
      this.toolEl.style.opacity = '1';
    } else {
      animate(this.toolEl, { textContent: scrambleText({ text, chars: 'a-z0-9._-' }), duration: 520 });
      animate(this.toolEl, { opacity: [0, 1], duration: 180 });
      animate(this.toolTag, { y: [0.85, 1.15], duration: 500, ease: 'outCubic' });
    }
    this.toolFade = animate(this.toolEl, {
      opacity: 0,
      delay: 2200,
      duration: 500,
      onComplete: () => {
        this.toolTag.visible = false;
      },
    });
  }
}
