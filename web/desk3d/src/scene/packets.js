import {
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  InstancedMesh,
  Line,
  Mesh,
  MeshBasicMaterial,
  QuadraticBezierCurve3,
  SphereGeometry,
  Vector3,
} from 'three';
import { animate, stagger, utils } from 'animejs';
import { getInstances } from 'animejs/adapters/three';
import { hdr, wire } from './parts.js';
import { SEMANTIC } from '../config.js';

const TRACE_POINTS = 48;
const GHOSTS = 3;

export class Packets {
  constructor(scene, { reducedMotion }) {
    this.scene = scene;
    this.reducedMotion = reducedMotion;
    this.free = [];
    this.headGeometry = new SphereGeometry(0.1, 16, 12);
  }

  make() {
    const head = new Mesh(this.headGeometry, new MeshBasicMaterial({ toneMapped: false, transparent: true }));
    const ghosts = Array.from({ length: GHOSTS }, (_, i) => {
      const ghost = new Mesh(this.headGeometry, new MeshBasicMaterial({ toneMapped: false, transparent: true, opacity: 0.55 - i * 0.15, depthWrite: false }));
      ghost.scale.setScalar(0.75 - i * 0.18);
      return ghost;
    });
    const traceGeometry = new BufferGeometry();
    traceGeometry.setAttribute('position', new BufferAttribute(new Float32Array((TRACE_POINTS + 1) * 3), 3));
    const trace = new Line(traceGeometry, wire('#ffffff', 0));
    const packet = { head, ghosts, trace, curve: new QuadraticBezierCurve3(new Vector3(), new Vector3(), new Vector3()) };
    this.scene.add(head, ...ghosts, trace);
    return packet;
  }

  send({ from, to, hue, lift = 2.2, duration = 1100 }) {
    const packet = this.free.pop() || this.make();
    const { head, ghosts, trace, curve } = packet;
    curve.v0.copy(from);
    curve.v2.copy(to);
    curve.v1.copy(from).lerp(to, 0.5);
    curve.v1.y += lift + from.distanceTo(to) * 0.14;

    const positions = trace.geometry.attributes.position;
    const p = new Vector3();
    for (let i = 0; i <= TRACE_POINTS; i += 1) {
      curve.getPoint(i / TRACE_POINTS, p);
      positions.setXYZ(i, p.x, p.y, p.z);
    }
    positions.needsUpdate = true;
    trace.geometry.computeBoundingSphere();
    trace.material.color.copy(hdr(hue, 1.8));

    head.material.color.copy(hdr(hue, 3.4));
    for (const ghost of ghosts) ghost.material.color.copy(hdr(hue, 2.4));
    head.position.copy(from);
    for (const ghost of ghosts) ghost.position.copy(from);
    head.visible = true;
    for (const ghost of ghosts) ghost.visible = true;

    const time = this.reducedMotion ? Math.min(260, duration) : duration;
    const state = { t: 0 };

    return new Promise((resolve) => {
      animate(trace, {
        opacity: [{ to: 0.38, duration: time * 0.3 }, { to: 0, duration: time * 0.9 }],
        ease: 'outQuad',
      });
      animate(state, {
        t: 1,
        duration: time,
        ease: 'inOutSine',
        onUpdate: () => {
          curve.getPoint(state.t, head.position);
          ghosts.forEach((ghost, i) => curve.getPoint(Math.max(0, state.t - (i + 1) * 0.04), ghost.position));
        },
        onComplete: () => {
          head.visible = false;
          for (const ghost of ghosts) ghost.visible = false;
          this.free.push(packet);
          resolve();
        },
      });
    });
  }
}

export class Bursts {
  constructor(scene, { reducedMotion, count = 360 }) {
    this.reducedMotion = reducedMotion;
    this.count = count;
    this.mesh = new InstancedMesh(new BoxGeometry(0.075, 0.075, 0.075), new MeshBasicMaterial({ toneMapped: false }), count);
    this.mesh.frustumCulled = false;
    const white = hdr('#ffffff', 1);
    for (let i = 0; i < count; i += 1) this.mesh.setColorAt(i, white);
    scene.add(this.mesh);
    this.instances = getInstances(this.mesh);
    utils.set(this.instances, { scale: 0 });
    this.cursor = 0;
    this.dir = new Vector3();
  }

  fire(origin, hue, { ok = true, size = 10 } = {}) {
    if (this.reducedMotion) return;
    const color = hdr(ok ? hue : SEMANTIC.bad, 3);
    const batch = [];
    const targets = [];
    for (let k = 0; k < size; k += 1) {
      const index = this.cursor;
      this.cursor = (this.cursor + 1) % this.count;
      this.mesh.setColorAt(index, color);
      batch.push(this.instances[index]);
      this.dir.set(Math.random() * 2 - 1, Math.random() * 1.2 + 0.2, Math.random() * 2 - 1).normalize();
      const reach = 0.7 + Math.random() * 0.9;
      targets.push({ x: origin.x + this.dir.x * reach, y: origin.y + this.dir.y * reach, z: origin.z + this.dir.z * reach });
    }
    this.mesh.instanceColor.needsUpdate = true;
    utils.set(batch, { x: origin.x, y: origin.y, z: origin.z, scale: 0 });
    animate(batch, {
      x: (_, i) => targets[i].x,
      y: (_, i) => targets[i].y,
      z: (_, i) => targets[i].z,
      rotateX: () => utils.random(-220, 220),
      rotateY: () => utils.random(-220, 220),
      scale: [{ to: 1, duration: 140, ease: 'outQuad' }, { to: 0, duration: 760, ease: 'inQuad' }],
      duration: 900,
      ease: 'outCubic',
      delay: stagger(16),
    });
  }
}
