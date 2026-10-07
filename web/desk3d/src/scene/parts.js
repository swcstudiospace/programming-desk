import {
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  LineBasicMaterial,
  MeshBasicMaterial,
  MeshStandardMaterial,
  AdditiveBlending,
} from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

export const hdr = (hex, k = 1) => new Color(hex).multiplyScalar(k);

export const glow = (hex, intensity = 1) => new MeshStandardMaterial({
  color: hex,
  emissive: hex,
  emissiveIntensity: intensity,
  roughness: 0.32,
  metalness: 0.15,
  flatShading: true,
});

export const neon = (hex, k = 2, opacity = 1) => new MeshBasicMaterial({
  color: hdr(hex, k),
  transparent: true,
  opacity,
  toneMapped: false,
  depthWrite: false,
  blending: AdditiveBlending,
});

export const wire = (hex, opacity = 0.5, k = 1.6) => new LineBasicMaterial({
  color: hdr(hex, k),
  transparent: true,
  opacity,
  toneMapped: false,
  depthWrite: false,
});

export function circle(radius, segments, { from = 0, span = Math.PI * 2, y = 0 } = {}) {
  const points = [];
  for (let i = 0; i <= segments; i += 1) {
    const a = from + (span * i) / segments;
    points.push(Math.sin(a) * radius, y, Math.cos(a) * radius);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(points, 3));
  return geometry;
}

export function dashedCircle(radius, dashes, fill = 0.5) {
  const points = [];
  const step = (Math.PI * 2) / dashes;
  for (let i = 0; i < dashes; i += 1) {
    const a = i * step;
    const b = a + step * fill;
    points.push(Math.sin(a) * radius, 0, Math.cos(a) * radius, Math.sin(b) * radius, 0, Math.cos(b) * radius);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(points, 3));
  return geometry;
}

export function tag(className) {
  const el = document.createElement('div');
  el.className = className;
  const obj = new CSS2DObject(el);
  return { obj, el };
}

export function el(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
