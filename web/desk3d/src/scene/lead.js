import {
  CylinderGeometry,
  EdgesGeometry,
  Group,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  TorusGeometry,
} from 'three';
import { animate } from 'animejs';
import { Robot } from './robot.js';
import { Screen } from './screen.js';
import { el, neon, tag, wire } from './parts.js';
import { STATUS_LABELS } from '../config.js';
import { STATUS_COLORS } from './palette.js';

const RING_SPEED = { idle: 16000, thinking: 5000, working: 2600, blocked: 12000, error: 0, offline: 0 };

export class LeadNode {
  constructor({ bot, position, reducedMotion, onPick }) {
    this.id = bot.id;
    this.hue = bot.hue;
    this.reducedMotion = reducedMotion;
    this.status = null;
    this.home = position.clone();

    this.group = new Group();
    this.group.position.copy(position);

    const platformGeometry = new CylinderGeometry(1.55, 1.75, 0.14, 6, 1, false, Math.PI / 6);
    const platform = new Mesh(platformGeometry, new MeshStandardMaterial({
      color: '#0f1829',
      metalness: 0.6,
      roughness: 0.35,
      envMapIntensity: 0.12,
      transparent: true,
      opacity: 0.9,
    }));
    const platformEdges = new LineSegments(new EdgesGeometry(platformGeometry), wire(bot.hue, 0.55, 1.8));
    this.group.add(platform, platformEdges);

    this.robot = new Robot({ hue: bot.hue, standing: true, scale: 1.5, reducedMotion });
    this.robot.group.position.y = 0.07;
    this.group.add(this.robot.group);

    this.rings = [0, 1].map((i) => {
      const ring = new Mesh(new TorusGeometry(1.15 + i * 0.2, 0.012, 6, 160), neon(bot.hue, 2, 0.5));
      ring.rotation.set(Math.PI / 2 + (i ? 0.1 : -0.08), i ? 0.06 : 0, 0);
      const holder = new Group();
      holder.position.y = 0.2 + i * 0.08;
      holder.add(ring);
      this.group.add(holder);
      return holder;
    });
    this.ringLoops = [];

    this.screen = new Screen({ hue: bot.hue, width: 2.1 });
    this.screen.group.position.y = 3.75;
    this.screen.set({ title: bot.name, caption: 'REQUEST', empty: 'Waiting for a request' });
    this.group.add(this.screen.group);

    const label = tag('seat-tag seat-tag--lead');
    this.tagEl = label.el;
    this.tagEl.style.setProperty('--hue', bot.hue);
    this.tagStatus = el('span', 'seat-tag__status', '');
    this.tagEl.append(el('i', 'seat-tag__dot'), el('span', 'seat-tag__name', bot.name), el('span', 'seat-tag__where', 'outside the desk'), this.tagStatus);
    this.tagEl.addEventListener('click', () => onPick(this.id));
    label.obj.position.set(0, -0.2, 1.9);
    this.group.add(label.obj);

    this.hit = new Mesh(new CylinderGeometry(1.4, 1.4, 3.2, 10), new MeshBasicMaterial({ visible: false }));
    this.hit.position.y = 1.6;
    this.hit.userData.pick = this.id;
    this.group.add(this.hit);
  }

  anchor() {
    return this.robot.anchor();
  }

  mute(muted) {
    this.tagEl.classList.toggle('is-muted', muted);
  }

  setStatus(status) {
    if (status === this.status) return;
    this.status = status;
    this.robot.setStatus(status);
    for (const loop of this.ringLoops) loop.cancel();
    this.ringLoops = [];
    const speed = RING_SPEED[status];
    if (speed && !this.reducedMotion) {
      this.ringLoops = this.rings.map((holder, i) => animate(holder, {
        rotateY: i ? '-=360' : '+=360',
        duration: speed * (i ? 1.35 : 1),
        ease: 'linear',
        loop: true,
      }));
    }
    this.tagStatus.textContent = STATUS_LABELS[status];
    this.tagEl.dataset.status = status;
    this.screen.set({ status: STATUS_LABELS[status], statusColor: STATUS_COLORS[status] });
  }
}
