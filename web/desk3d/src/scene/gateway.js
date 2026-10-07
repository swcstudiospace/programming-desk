import {
  BoxGeometry,
  BufferGeometry,
  CylinderGeometry,
  EdgesGeometry,
  Float32BufferAttribute,
  GridHelper,
  Group,
  Line,
  LineSegments,
  Mesh,
  OctahedronGeometry,
  TorusGeometry,
  Vector3,
} from 'three';
import { animate } from 'animejs';
import { el, glow, hdr, neon, tag, wire } from './parts.js';
import { RAILWAY_TONE } from './palette.js';

const FLOOR_Y = -3.6;
const CORE = new Vector3(0, -2.6, 2.2);
const RING_RADIUS = 6.4;
const CLUSTERS = {
  Ultrathink: { center: Math.PI / 2, spread: 0.44 },
  'Agent Substrate': { center: -Math.PI / 2, spread: 0.52 },
};

const segment = (a, b) => {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute([a.x, a.y, a.z, b.x, b.y, b.z], 3));
  return geometry;
};

export class GatewayLayer {
  constructor({ gateway, resources, deskUnderside, reducedMotion }) {
    this.reducedMotion = reducedMotion;
    this.group = new Group();
    this.nodes = new Map();

    const grid = new GridHelper(64, 64, hdr('#3a5a8f', 1), hdr('#1a2742', 1));
    grid.material.transparent = true;
    grid.material.opacity = 0.35;
    grid.material.depthWrite = false;
    grid.position.y = FLOOR_Y;
    this.group.add(grid);

    this.core = new Group();
    this.core.position.copy(CORE);
    const heart = new Mesh(new OctahedronGeometry(0.42, 0), glow(gateway.hue, 1.4));
    this.heart = heart;
    this.core.add(heart);
    this.coreRings = [0.8, 1.05, 1.3].map((r, i) => {
      const ring = new Mesh(new TorusGeometry(r, 0.016, 6, 128), neon(gateway.hue, 1.8, 0.6 - i * 0.12));
      ring.rotation.set(Math.PI / 2 + i * 0.45, i * 0.6, 0);
      this.core.add(ring);
      return ring;
    });
    this.group.add(this.core);

    const coreTag = tag('layer-tag');
    this.tags = [coreTag.el];
    coreTag.el.append(el('b', '', gateway.name), el('span', '', gateway.where));
    coreTag.obj.position.set(0, -1.75, 0);
    this.core.add(coreTag.obj);

    const uplink = new Line(segment(CORE, deskUnderside), wire(gateway.hue, 0.35, 1.6));
    this.group.add(uplink);

    const byProject = new Map();
    for (const r of resources) {
      if (!byProject.has(r.project)) byProject.set(r.project, []);
      byProject.get(r.project).push(r);
    }

    let fallback = 0;
    for (const [project, list] of byProject) {
      const cluster = CLUSTERS[project] || { center: Math.PI + fallback++ * 0.9, spread: 0.36 };
      const start = cluster.center - ((list.length - 1) * cluster.spread) / 2;
      list.forEach((resource, i) => {
        const angle = start + i * cluster.spread;
        const position = new Vector3(CORE.x + Math.sin(angle) * RING_RADIUS, CORE.y - 0.2, CORE.z + Math.cos(angle) * RING_RADIUS);
        this.addNode(resource, position);
      });
    }

    this.anchorPoint = new Vector3();
    this.loops = [];
  }

  addNode(resource, position) {
    const node = new Group();
    node.position.copy(position);
    const body = new Group();
    const materials = [];
    if (resource.kind === 'db') {
      for (let i = 0; i < 3; i += 1) {
        const mat = glow(RAILWAY_TONE, 0.35);
        materials.push(mat);
        const disc = new Mesh(new CylinderGeometry(0.42, 0.42, 0.14, 28), mat);
        disc.position.y = i * 0.21;
        body.add(disc);
      }
    } else {
      const mat = glow(RAILWAY_TONE, 0.35);
      materials.push(mat);
      const box = new Mesh(new BoxGeometry(0.56, 0.56, 0.56), mat);
      box.rotation.set(Math.PI / 4, 0, Math.PI / 4);
      box.position.y = 0.3;
      body.add(box);
      body.add(new LineSegments(new EdgesGeometry(new BoxGeometry(0.8, 0.8, 0.8)), wire(RAILWAY_TONE, 0.4)));
      body.children[1].position.y = 0.3;
    }
    node.add(body);

    const link = new Line(segment(CORE, position.clone().add(new Vector3(0, 0.2, 0))), wire(RAILWAY_TONE, 0.16, 1.4));
    this.group.add(link);

    const label = tag('resource-tag');
    label.el.append(el('b', '', resource.name), el('span', '', `Railway · ${resource.project}`));
    label.obj.position.set(0, -0.35, 0);
    node.add(label.obj);
    this.tags.push(label.el);

    this.group.add(node);
    this.nodes.set(resource.id, { node, body, materials, link, label: label.el, point: new Vector3() });
  }

  mute(muted) {
    for (const node of this.tags) node.classList.toggle('is-muted', muted);
  }

  anchor(resourceId) {
    if (!resourceId) return this.core.getWorldPosition(this.anchorPoint);
    const entry = this.nodes.get(resourceId);
    if (!entry) return null;
    return entry.node.getWorldPosition(entry.point).add(new Vector3(0, 0.25, 0));
  }

  has(resourceId) {
    return this.nodes.has(resourceId);
  }

  idle() {
    if (this.reducedMotion) return;
    this.coreRings.forEach((ring, i) => {
      this.loops.push(animate(ring, { rotateZ: i % 2 ? '-=360' : '+=360', duration: 9000 + i * 3500, ease: 'linear', loop: true }));
    });
    this.loops.push(animate(this.heart, { rotateY: '+=360', duration: 7000, ease: 'linear', loop: true }));
  }

  pulseCore(hue) {
    this.heart.material.emissive.copy(hdr(hue, 1));
    animate(this.heart, {
      emissiveIntensity: [{ to: 3.2, duration: 120 }, { to: 1.4, duration: 700 }],
      scale: [{ to: 1.35, duration: 120 }, { to: 1, duration: 600 }],
      ease: 'outQuad',
    });
  }

  pulse(resourceId, hue, ok = true) {
    const entry = this.nodes.get(resourceId);
    if (!entry) return;
    const flash = hdr(ok ? hue : '#ff5d6c', 1);
    for (const mat of entry.materials) mat.emissive.copy(flash);
    animate(entry.materials, {
      emissiveIntensity: [{ to: 2.8, duration: 140 }, { to: 0.35, duration: 1100 }],
      ease: 'outQuad',
      onComplete: () => {
        for (const mat of entry.materials) mat.emissive.set(RAILWAY_TONE);
      },
    });
    animate(entry.body, { scaleY: [{ to: 1.25, duration: 140 }, { to: 1, duration: 500 }], ease: 'outBack(2)' });
    animate(entry.link, { opacity: [{ to: 0.8, duration: 120 }, { to: 0.16, duration: 900 }] });
    entry.label.classList.remove('is-hit');
    void entry.label.offsetWidth;
    entry.label.classList.add('is-hit');
  }
}
