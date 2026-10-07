import {
  BoxGeometry,
  CylinderGeometry,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  RingGeometry,
  SphereGeometry,
  TorusGeometry,
  Vector3,
} from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { animate, stagger } from 'animejs';
import { hdr, neon } from './parts.js';
import { SEMANTIC } from '../config.js';
import { STATUS_COLORS } from './palette.js';

const THINK = STATUS_COLORS.thinking;
const OFF = '#3a4460';

const SEATED = {
  idle: { shoulder: [-14, -14], elbow: [-72, -72], head: [0, 0], torso: 0 },
  thinking: { shoulder: [-14, -40], elbow: [-72, -118], head: [-6, 12], torso: 0 },
  working: { shoulder: [-36, -36], elbow: [-56, -56], head: [9, 0], torso: 4 },
  blocked: { shoulder: [-30, -30], elbow: [-40, -40], head: [0, -10], torso: -3 },
  error: { shoulder: [-18, -18], elbow: [-62, -62], head: [4, 0], torso: 0 },
  offline: { shoulder: [4, 4], elbow: [-8, -8], head: [30, 0], torso: 14 },
};

const STANDING = {
  idle: { shoulder: [0, 0], elbow: [-12, -12], head: [0, 0], torso: 0 },
  thinking: { shoulder: [0, -40], elbow: [-14, -122], head: [-8, 10], torso: 0 },
  working: { shoulder: [-8, -84], elbow: [-30, -6], head: [4, 0], torso: -2 },
  blocked: { shoulder: [-10, -10], elbow: [-30, -30], head: [0, -10], torso: 0 },
  error: { shoulder: [-6, -6], elbow: [-24, -24], head: [4, 0], torso: 0 },
  offline: { shoulder: [4, 4], elbow: [-4, -4], head: [28, 0], torso: 10 },
};

const box = (w, h, d, material, r = 0) => new Mesh(r ? new RoundedBoxGeometry(w, h, d, 3, r) : new BoxGeometry(w, h, d), material);

const place = (object, x, y, z) => {
  object.position.set(x, y, z);
  return object;
};

const lit = (hex, k = 2.6) => new MeshBasicMaterial({ color: hdr(hex, k), toneMapped: false, transparent: true });

export class Robot {
  constructor({ hue, standing = false, scale = 1, reducedMotion }) {
    this.hue = hue;
    this.standing = standing;
    this.reducedMotion = reducedMotion;
    this.poses = standing ? STANDING : SEATED;
    this.loops = [];
    this.status = null;
    this.dim = false;

    this.metal = new MeshStandardMaterial({ color: '#7d889f', metalness: 0.6, roughness: 0.36 });
    this.dark = new MeshStandardMaterial({ color: '#1b2336', metalness: 0.5, roughness: 0.45 });
    this.trim = new MeshStandardMaterial({ color: hue, emissive: hue, emissiveIntensity: 0.35, metalness: 0.3, roughness: 0.4 });
    this.glass = new MeshStandardMaterial({ color: '#03050a', metalness: 0.9, roughness: 0.1 });
    this.bodyMaterials = [this.metal, this.dark, this.trim, this.glass];

    this.group = new Group();
    this.rig = new Group();
    this.rig.scale.setScalar(scale);
    this.group.add(this.rig);

    const hipY = standing ? 0.78 : 0.4;
    this.buildLegs(hipY);
    if (!standing) this.buildSeat();

    this.torso = place(new Group(), 0, hipY + 0.07, 0);
    this.rig.add(this.torso);
    this.torso.add(place(box(0.48, 0.42, 0.3, this.metal, 0.06), 0, 0.22, 0));
    this.torso.add(place(box(0.34, 0.12, 0.26, this.dark, 0.04), 0, 0.02, 0));
    this.torso.add(place(box(0.2, 0.08, 0.02, this.trim, 0.01), 0, 0.3, 0.155));
    this.chestLights = [-0.05, 0, 0.05].map((x) => place(new Mesh(new SphereGeometry(0.014, 10, 8), lit(hue, 2)), x, 0.18, 0.152));
    this.torso.add(...this.chestLights);

    this.arms = [-1, 1].map((side) => this.buildArm(side, standing));

    this.torso.add(place(new Mesh(new CylinderGeometry(0.06, 0.075, 0.08, 16), this.dark), 0, 0.47, 0));
    this.look = place(new Group(), 0, 0.5, 0);
    this.torso.add(this.look);
    this.head = new Group();
    this.look.add(this.head);
    this.buildHead(standing);

    this.wave = new Mesh(new RingGeometry(0.72, 0.84, 64), neon(hue, 2.2, 0));
    this.wave.rotation.x = -Math.PI / 2;
    this.wave.position.y = 0.03;
    this.wave.visible = false;
    this.group.add(this.wave);

    this.anchorPoint = new Vector3();
    this.toolPoint = new Vector3();
  }

  buildLegs(hipY) {
    const legs = new Group();
    this.rig.add(legs);
    legs.add(place(box(0.36, 0.14, 0.26, this.dark, 0.04), 0, hipY, 0));
    for (const side of [-1, 1]) {
      const x = side * 0.1;
      if (this.standing) {
        legs.add(place(box(0.13, 0.36, 0.14, this.metal, 0.03), x, hipY - 0.24, 0));
        legs.add(place(box(0.12, 0.34, 0.13, this.metal, 0.03), x, 0.2, 0));
        legs.add(place(box(0.14, 0.06, 0.22, this.dark, 0.02), x, 0.03, 0.04));
        legs.add(place(new Mesh(new SphereGeometry(0.065, 14, 10), this.dark), x, 0.39, 0));
      } else {
        legs.add(place(box(0.12, 0.12, 0.34, this.metal, 0.03), x, hipY - 0.02, 0.17));
        legs.add(place(box(0.11, 0.32, 0.11, this.metal, 0.03), x, 0.2, 0.34));
        legs.add(place(box(0.13, 0.06, 0.2, this.dark, 0.02), x, 0.03, 0.4));
      }
    }
  }

  buildSeat() {
    this.rig.add(place(new Mesh(new CylinderGeometry(0.18, 0.24, 0.28, 18), this.dark), 0, 0.14, -0.04));
    this.rig.add(place(new Mesh(new CylinderGeometry(0.25, 0.25, 0.05, 24), this.trim), 0, 0.3, -0.04));

    const desk = new Group();
    desk.position.set(0, 0, 0.62);
    const slab = place(box(0.86, 0.05, 0.3, this.dark, 0.02), 0, 0.56, 0);
    slab.rotation.x = 0.14;
    desk.add(slab);
    for (const side of [-1, 1]) desk.add(place(box(0.05, 0.54, 0.05, this.metal), side * 0.36, 0.27, 0.06));
    this.keys = place(box(0.62, 0.012, 0.16, lit(this.hue, 1.6)), 0, 0.59, -0.01);
    this.keys.rotation.x = 0.14;
    this.keys.material.opacity = 0.35;
    desk.add(this.keys);
    this.rig.add(desk);
    this.toolAnchor = place(new Group(), 0, 0.72, 0.6);
    this.rig.add(this.toolAnchor);
  }

  buildArm(side, standing) {
    const shoulder = place(new Group(), side * 0.3, 0.36, 0);
    this.torso.add(shoulder);
    shoulder.add(new Mesh(new SphereGeometry(0.075, 16, 12), this.trim));
    if (standing) {
      const plate = place(box(0.2, 0.08, 0.24, this.metal, 0.03), side * 0.03, 0.06, 0);
      plate.rotation.z = side * -0.35;
      shoulder.add(plate);
    }
    shoulder.add(place(box(0.1, 0.26, 0.1, this.metal, 0.03), 0, -0.13, 0));
    const elbow = place(new Group(), 0, -0.26, 0);
    shoulder.add(elbow);
    elbow.add(new Mesh(new SphereGeometry(0.055, 12, 10), this.dark));
    elbow.add(place(box(0.09, 0.24, 0.09, this.metal, 0.03), 0, -0.12, 0));
    elbow.add(place(box(0.1, 0.07, 0.12, this.dark, 0.02), 0, -0.26, 0.01));
    if (standing) shoulder.rotation.z = side * 0.08;
    return { shoulder, elbow };
  }

  buildHead(standing) {
    const head = this.head;
    head.add(place(box(0.44, 0.34, 0.36, this.metal, 0.08), 0, 0.19, 0));
    head.add(place(box(0.37, 0.2, 0.03, this.glass, 0.02), 0, 0.2, 0.175));

    this.faceplate = place(new Group(), 0, 0.2, 0.192);
    head.add(this.faceplate);
    this.eyeMaterial = lit(this.hue);
    this.eyes = [-1, 1].map((side) => place(box(0.07, 0.06, 0.006, this.eyeMaterial), side * 0.075, 0.025, 0));
    this.faceplate.add(...this.eyes);
    this.mouthMaterial = lit(this.hue, 2);
    this.mouth = [-1, 0, 1].map((i) => place(box(0.028, 0.022, 0.006, this.mouthMaterial), i * 0.04, -0.05, 0));
    this.faceplate.add(...this.mouth);
    this.scan = place(box(0.012, 0.16, 0.006, lit(THINK, 3)), 0, 0, 0.002);
    this.scan.visible = false;
    this.faceplate.add(this.scan);
    this.crosses = [-1, 1].map((side) => {
      const cross = place(new Group(), side * 0.075, 0.02, 0.001);
      for (const angle of [Math.PI / 4, -Math.PI / 4]) {
        const bar = box(0.085, 0.016, 0.006, lit(SEMANTIC.bad, 3));
        bar.rotation.z = angle;
        cross.add(bar);
      }
      cross.visible = false;
      this.faceplate.add(cross);
      return cross;
    });

    this.signalMaterial = lit(this.hue, 2.4);
    this.ears = [-1, 1].map((side) => {
      const ear = place(new Group(), side * 0.225, 0.18, 0);
      const cap = new Mesh(new CylinderGeometry(0.07, 0.07, 0.05, 20), this.dark);
      cap.rotation.z = Math.PI / 2;
      const ring = new Mesh(new TorusGeometry(0.048, 0.011, 8, 28), this.signalMaterial);
      ring.rotation.y = Math.PI / 2;
      ring.position.x = side * 0.028;
      ear.add(cap, ring);
      head.add(ear);
      return ear;
    });

    const stalks = standing ? [-0.1, 0.1] : [0];
    this.antennaTips = stalks.map((x) => {
      const stalk = place(new Group(), x, 0.36, -0.02);
      stalk.rotation.z = x * -2.4;
      stalk.add(place(new Mesh(new CylinderGeometry(0.011, 0.014, 0.2, 8), this.dark), 0, 0.1, 0));
      const tip = place(new Mesh(new SphereGeometry(0.038, 14, 10), this.signalMaterial), 0, 0.22, 0);
      stalk.add(tip);
      head.add(stalk);
      return tip;
    });
  }

  anchor() {
    return this.head.localToWorld(this.anchorPoint.set(0, 0.2, 0.1));
  }

  toolOrigin() {
    if (!this.toolAnchor) return this.anchor();
    return this.toolAnchor.getWorldPosition(this.toolPoint);
  }

  setDim(dim) {
    if (dim === this.dim) return;
    this.dim = dim;
    for (const material of this.bodyMaterials) {
      material.transparent = dim;
      material.opacity = dim ? 0.3 : 1;
      material.depthWrite = !dim;
      material.needsUpdate = true;
    }
    this.trim.emissiveIntensity = dim ? 0.1 : 0.35;
  }

  run(target, params) {
    if (this.reducedMotion) return;
    this.loops.push(animate(target, { loop: true, ...params }));
  }

  stop() {
    for (const loop of this.loops) loop.cancel();
    this.loops = [];
  }

  pose(name) {
    const p = this.poses[name];
    const duration = this.reducedMotion ? 1 : 650;
    const ease = 'outCubic';
    this.arms.forEach((arm, i) => {
      animate(arm.shoulder, { rotateX: p.shoulder[i], rotateY: 0, duration, ease });
      animate(arm.elbow, { rotateX: p.elbow[i], duration, ease });
    });
    animate(this.head, { rotateX: p.head[0], rotateZ: p.head[1], rotateY: 0, duration, ease });
    animate(this.torso, { rotateX: p.torso, rotateZ: 0, duration, ease });
    return duration;
  }

  express(mode, hex) {
    const color = hdr(hex, 2.6);
    this.eyeMaterial.color.copy(color);
    this.mouthMaterial.color.copy(hdr(hex, 2));
    for (const cross of this.crosses) cross.visible = mode === 'cross';
    this.scan.visible = mode === 'scan';
    const eyeScale = { calm: 1, scan: 0.9, bright: 1.15, squint: 0.42, cross: 0, flat: 0.16 }[mode];
    const eyeOpacity = mode === 'scan' ? 0.4 : mode === 'flat' ? 0.5 : 1;
    const duration = this.reducedMotion ? 1 : 260;
    animate(this.eyes, { scaleY: eyeScale, scaleX: mode === 'bright' ? 1.1 : 1, opacity: eyeOpacity, duration, ease: 'outQuad' });
    const mouthScale = mode === 'squint' || mode === 'flat' || mode === 'cross' ? 0.5 : 1;
    const mouthOpacity = mode === 'calm' || mode === 'scan' ? 0.55 : 1;
    animate(this.mouth, { scaleY: mouthScale, scaleX: mode === 'squint' || mode === 'flat' ? 1.5 : 1, opacity: mouthOpacity, duration, ease: 'outQuad' });
  }

  signal(hex, level) {
    this.signalMaterial.color.copy(hdr(hex, 2.4));
    animate(this.antennaTips, { opacity: level, duration: this.reducedMotion ? 1 : 300 });
    for (const light of this.chestLights) light.material.color.copy(hdr(hex, 2));
  }

  setStatus(status) {
    if (status === this.status) return;
    this.status = status;
    this.stop();
    const settle = this.pose(status);
    const signalTips = this.antennaTips;

    if (status === 'idle') {
      this.express('calm', this.hue);
      this.signal(this.hue, 0.8);
      this.run(this.eyes, { scaleY: [{ to: 0.1, duration: 70 }, { to: 1, duration: 110 }], loopDelay: 3200, delay: 1400 });
      this.run(this.torso, { rotateZ: [-1.6, 1.6], duration: 2600, alternate: true, ease: 'inOutSine', delay: settle });
      this.run(this.head, { rotateY: [-14, 14], duration: 3800, alternate: true, ease: 'inOutSine', delay: settle });
    }

    if (status === 'thinking') {
      this.express('scan', this.hue);
      this.signal(THINK, 1);
      this.run(this.scan, { x: [-0.14, 0.14], duration: 680, alternate: true, ease: 'inOutSine' });
      this.run(this.head, { rotateX: [-9, -3], duration: 1300, alternate: true, ease: 'inOutSine', delay: settle });
      this.run(signalTips, { opacity: [0.25, 1], duration: 800, alternate: true, ease: 'inOutQuad' });
    }

    if (status === 'working') {
      this.express('bright', this.hue);
      this.signal(SEMANTIC.ok, 1);
      this.run(this.mouth, { scaleY: [0.5, 1.9], duration: 210, alternate: true, ease: 'inOutQuad', delay: stagger(70) });
      this.run(signalTips, { opacity: [0.3, 1], duration: 320, alternate: true });
      if (this.standing) {
        this.run(this.head, { rotateY: [-22, 22], duration: 2600, alternate: true, ease: 'inOutSine', delay: settle });
        this.run(this.arms[1].shoulder, { rotateY: [-18, 18], duration: 2600, alternate: true, ease: 'inOutSine', delay: settle });
      } else {
        this.arms.forEach((arm, i) => {
          this.run(arm.elbow, { rotateX: [-54, -66], duration: 150, alternate: true, ease: 'inOutQuad', delay: settle + i * 75 });
        });
        if (this.keys) this.run(this.keys, { opacity: [0.35, 0.9], duration: 150, alternate: true });
      }
    } else if (this.keys) {
      animate(this.keys, { opacity: 0.35, duration: 300 });
    }

    if (status === 'blocked') {
      this.express('squint', SEMANTIC.warn);
      this.signal(SEMANTIC.warn, 1);
      this.run(signalTips, { opacity: [0.15, 1], duration: 560, alternate: true, ease: 'inOutQuad' });
      this.run(this.head, { rotateZ: [-10, -4], duration: 1600, alternate: true, ease: 'inOutSine', delay: settle });
    }

    if (status === 'error') {
      this.express('cross', SEMANTIC.bad);
      this.signal(SEMANTIC.bad, 1);
      if (!this.reducedMotion) {
        animate(this.torso, { rotateZ: [0, 5, -5, 3, -2, 0], duration: 560, ease: 'linear' });
        animate(signalTips, { opacity: [{ to: 0.1, duration: 110 }, { to: 1, duration: 110 }, { to: 0.1, duration: 110 }, { to: 1, duration: 110 }] });
      }
    }

    if (status === 'offline') {
      this.express('flat', OFF);
      this.signal(OFF, 0.15);
    }
  }

  nod() {
    if (this.reducedMotion) return;
    animate(this.look, { rotateX: [{ to: 14, duration: 160 }, { to: 0, duration: 260 }], ease: 'outQuad' });
  }

  glance(worldPoint) {
    if (this.reducedMotion || !worldPoint) return;
    const local = this.look.parent.worldToLocal(worldPoint.clone());
    const yaw = Math.max(-60, Math.min(60, (Math.atan2(local.x, local.z) * 180) / Math.PI));
    animate(this.look, {
      rotateY: [{ to: yaw, duration: 380, ease: 'outCubic' }, { to: yaw, duration: 700 }, { to: 0, duration: 600, ease: 'inOutSine' }],
    });
  }

  ping(hex = this.hue) {
    if (this.reducedMotion) return;
    this.wave.material.color.copy(hdr(hex, 2.2));
    animate(this.wave, { scale: [1, 2.2], opacity: [0.9, 0], duration: 900, ease: 'outCubic' });
    this.nod();
  }
}
