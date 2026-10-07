import {
  BufferGeometry,
  CylinderGeometry,
  EdgesGeometry,
  Float32BufferAttribute,
  Group,
  Line,
  LineSegments,
  Mesh,
  MeshStandardMaterial,
  Points,
  PointsMaterial,
  Raycaster,
  RingGeometry,
  Vector2,
  Vector3,
} from 'three';
import 'animejs/adapters/three';
import { animate, createTimeline, stagger } from 'animejs';
import { createStage } from './stage.js';
import { Station } from './station.js';
import { LeadNode } from './lead.js';
import { GatewayLayer } from './gateway.js';
import { Packets, Bursts } from './packets.js';
import { neon, wire } from './parts.js';
import { DESK_EDGE } from './palette.js';

const DESK_Y = 1.0;
const DESK_RADIUS = 5.9;
const SEAT_RADIUS = 4.1;
const LEAD_POSITION = new Vector3(0, 4.0, -8.6);
const OUTSIDE = new Vector3(0, 17, -30);

const line = (points, material) => {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(points.flatMap((p) => [p.x, p.y, p.z]), 3));
  return new Line(geometry, material);
};

function starfield() {
  const points = [];
  for (let i = 0; i < 700; i += 1) {
    const r = 45 + Math.random() * 60;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(Math.random() * 1.6 - 0.6);
    points.push(r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi) - 8, r * Math.sin(phi) * Math.cos(theta));
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(points, 3));
  return new Points(geometry, new PointsMaterial({ color: '#8fa6d6', size: 0.14, transparent: true, opacity: 0.55, depthWrite: false, fog: false }));
}

export function createDeskScene(host, { lead, seats, gateway, resources, reducedMotion, onPick, insets = () => ({ left: 0, right: 0 }) }) {
  const stage = createStage(host);
  const { scene, camera, controls } = stage;

  scene.add(starfield());

  const desk = new Group();
  const slabGeometry = new CylinderGeometry(DESK_RADIUS, DESK_RADIUS - 0.25, 0.3, 6, 1, false, Math.PI / 6);
  const slab = new Mesh(slabGeometry, new MeshStandardMaterial({
    color: '#0e1627',
    metalness: 0.2,
    roughness: 0.75,
    envMapIntensity: 0.12,
    transparent: true,
    opacity: 0.94,
  }));
  slab.position.y = DESK_Y - 0.15;
  const slabEdges = new LineSegments(new EdgesGeometry(slabGeometry), wire(DESK_EDGE, 0.6, 1.6));
  slabEdges.position.copy(slab.position);
  const underGlow = new Mesh(new RingGeometry(DESK_RADIUS - 0.6, DESK_RADIUS + 0.2, 6, 1, Math.PI / 6), neon(DESK_EDGE, 1.2, 0.18));
  underGlow.rotation.x = -Math.PI / 2;
  underGlow.position.y = DESK_Y - 0.4;
  const innerHex = new LineSegments(new EdgesGeometry(new CylinderGeometry(2.1, 2.1, 0.001, 6, 1, false, Math.PI / 6)), wire(DESK_EDGE, 0.35, 1.4));
  innerHex.position.y = DESK_Y + 0.01;
  const emblem = new Mesh(new CylinderGeometry(0.34, 0.34, 0.5, 6, 1, false, Math.PI / 6), neon(DESK_EDGE, 1.4, 0.35));
  emblem.position.y = DESK_Y + 0.35;
  desk.add(slab, slabEdges, underGlow, innerHex, emblem);
  scene.add(desk);

  const stations = new Map();
  seats.forEach((bot, i) => {
    const angle = (i * Math.PI) / 3;
    const station = new Station({ bot, angle, radius: SEAT_RADIUS, deskY: DESK_Y, reducedMotion, onPick });
    stations.set(bot.id, station);
    scene.add(station.group);
    const spoke = line(
      [new Vector3(Math.sin(angle) * 0.6, DESK_Y + 0.015, Math.cos(angle) * 0.6), new Vector3(Math.sin(angle) * (SEAT_RADIUS - 0.8), DESK_Y + 0.015, Math.cos(angle) * (SEAT_RADIUS - 0.8))],
      wire(bot.hue, 0.28, 1.6),
    );
    desk.add(spoke);
  });

  const leadNode = new LeadNode({ bot: lead, position: LEAD_POSITION, reducedMotion, onPick });
  scene.add(leadNode.group);
  scene.add(line([LEAD_POSITION.clone().add(new Vector3(0, -0.1, 0)), new Vector3(0, DESK_Y + 0.02, -(DESK_RADIUS * 0.866))], wire(lead.hue, 0.22, 1.4)));

  const layer = new GatewayLayer({ gateway, resources, deskUnderside: new Vector3(0, DESK_Y - 0.3, 0), reducedMotion });
  scene.add(layer.group);

  const packets = new Packets(scene, { reducedMotion });
  const bursts = new Bursts(scene, { reducedMotion });

  const screens = [leadNode.screen, ...[...stations.values()].map((s) => s.screen)];
  stage.onFrame(() => {
    for (const screen of screens) {
      screen.face(camera);
      screen.draw();
    }
  });

  const hits = [leadNode.hit, ...[...stations.values()].map((s) => s.hit)];
  const raycaster = new Raycaster();
  const pointer = new Vector2();
  let down = null;
  const surface = stage.labels.domElement;
  surface.addEventListener('pointerdown', (e) => {
    down = { x: e.clientX, y: e.clientY };
  });
  surface.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) return;
    down = null;
    const rect = surface.getBoundingClientRect();
    pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(hits, false)[0];
    if (hit) onPick(hit.object.userData.pick);
  });

  const portrait = () => camera.aspect < 0.8;
  const OVERVIEW_DIR = new Vector3(0, 11.6, 23.5);
  const overviewDistance = () => {
    const width = Math.max(1, host.clientWidth);
    const { left, right } = insets();
    const free = Math.max(0.3, 1 - (left + right) / width);
    const halfWidth = Math.tan((camera.fov * Math.PI) / 360) * camera.aspect;
    return Math.max(OVERVIEW_DIR.length(), (portrait() ? 8 : 8.4) / (halfWidth * free));
  };
  const views = {
    overview: () => {
      const target = new Vector3(0, portrait() ? 2.4 : 0.4, -1);
      return { position: target.clone().add(OVERVIEW_DIR.clone().setLength(overviewDistance())), target };
    },
    lead: () => ({ position: new Vector3(0, 7.4, portrait() ? 3.6 : 0.6), target: LEAD_POSITION.clone().add(new Vector3(0, 2.3, 0)) }),
    gateway: () => ({ position: new Vector3(0, portrait() ? 12 : 8, portrait() ? 30 : 21.5), target: new Vector3(0, -2.8, 2.2) }),
  };

  const viewFor = (id) => {
    if (views[id]) return views[id]();
    const station = stations.get(id);
    if (!station) return views.overview();
    const p = station.group.position;
    const out = new Vector3(p.x, 0, p.z).normalize();
    const reach = portrait() ? 6.6 : 4.8;
    return {
      position: p.clone().add(out.multiplyScalar(reach)).add(new Vector3(0, 2.5, 0)),
      target: p.clone().add(new Vector3(0, 1.7, 0)),
    };
  };

  const fly = (id) => {
    const { position, target } = viewFor(id);
    const single = stations.has(id) || id === lead.id;
    for (const [seatId, station] of stations) station.mute(single && seatId !== id);
    leadNode.mute(single && id !== lead.id);
    layer.mute(single);
    const duration = reducedMotion ? 1 : 1300;
    animate(camera, { x: position.x, y: position.y, z: position.z, duration, ease: 'inOutCubic' });
    animate(controls.target, { x: target.x, y: target.y, z: target.z, duration, ease: 'inOutCubic' });
  };

  const anchor = (id) => {
    if (id === lead.id) return leadNode.anchor().clone();
    if (id === 'outside') return OUTSIDE.clone();
    if (id === gateway.id) return layer.anchor().clone();
    const station = stations.get(id);
    if (station) return station.anchor().clone();
    const resource = layer.anchor(id);
    return resource ? resource.clone() : null;
  };

  const intro = () => {
    const home = views.overview();
    const seatGroups = [...stations.values()].map((s) => s.inner);
    if (reducedMotion) {
      camera.position.copy(home.position);
      controls.target.copy(home.target);
      layer.idle();
      return;
    }
    camera.position.set(0, home.position.y * 2.1, home.position.z * 1.9);
    const tl = createTimeline({ defaults: { ease: 'outExpo' } });
    tl.add(desk, { scale: [0.05, 1], duration: 1300 }, 0)
      .add(seatGroups, { y: [-1.4, 0], scale: [0, 1], duration: 1100, delay: stagger(110) }, 350)
      .add(leadNode.group, { y: [LEAD_POSITION.y + 9, LEAD_POSITION.y], duration: 1700 }, 500)
      .add(layer.group, { y: [-7, 0], duration: 1600 }, 200)
      .add(camera, { y: home.position.y, z: home.position.z, duration: 2600, ease: 'inOutCubic' }, 0);
    tl.then(() => layer.idle());
  };

  return {
    stage,
    lead: leadNode,
    stations,
    layer,
    anchor,
    fly,
    intro,
    start: stage.start,
    redraw: () => {
      for (const screen of screens) screen.dirty = true;
    },
    send: (fromId, toId, hue, opts = {}) => {
      const from = anchor(fromId);
      const to = anchor(toId);
      if (!from || !to) return Promise.resolve();
      return packets.send({ from, to, hue, ...opts });
    },
    burst: (id, hue, opts) => {
      const station = stations.get(id);
      const at = station ? station.toolOrigin().clone() : anchor(id);
      if (at) bursts.fire(at, hue, opts);
    },
  };
}
