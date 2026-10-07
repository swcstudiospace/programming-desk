import {
  CanvasTexture,
  DoubleSide,
  EdgesGeometry,
  Group,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  SRGBColorSpace,
  Vector3,
} from 'three';
import { wire } from './parts.js';

const W = 640;
const H = 360;
const PAD = 26;

const FONT_DISPLAY = '"Chakra Petch", "Rajdhani", "Segoe UI", sans-serif';
const FONT_BODY = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif';
const FONT_MONO = '"IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace';

const rgba = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

function fit(ctx, text, width) {
  if (ctx.measureText(text).width <= width) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (ctx.measureText(`${text.slice(0, mid)}…`).width <= width) lo = mid;
    else hi = mid - 1;
  }
  return `${text.slice(0, lo)}…`;
}

function wrap(ctx, text, width, maxLines) {
  const words = text.split(/\s+/);
  const lines = [];
  let line = '';
  for (let i = 0; i < words.length; i += 1) {
    const next = line ? `${line} ${words[i]}` : words[i];
    if (ctx.measureText(next).width <= width || !line) {
      line = next;
    } else {
      lines.push(line);
      line = words[i];
      if (lines.length === maxLines - 1) {
        line = words.slice(i).join(' ');
        break;
      }
    }
  }
  if (line) lines.push(line);
  return lines.slice(0, maxLines).map((l, i, all) => (i === all.length - 1 ? fit(ctx, l, width) : l));
}

export class Screen {
  constructor({ hue, width = 1.8 }) {
    this.hue = hue;
    this.canvas = document.createElement('canvas');
    this.canvas.width = W;
    this.canvas.height = H;
    this.ctx = this.canvas.getContext('2d');
    this.texture = new CanvasTexture(this.canvas);
    this.texture.colorSpace = SRGBColorSpace;
    this.texture.anisotropy = 4;
    const height = (width * H) / W;
    const plane = new PlaneGeometry(width, height);
    this.mesh = new Mesh(plane, new MeshBasicMaterial({
      map: this.texture,
      transparent: true,
      opacity: 0.96,
      toneMapped: false,
      depthWrite: false,
      side: DoubleSide,
    }));
    this.frame = new LineSegments(new EdgesGeometry(plane), wire(hue, 0.75, 2));
    this.group = new Group();
    this.group.add(this.mesh, this.frame);
    this.state = {
      title: '',
      status: '',
      statusColor: '#8a97b3',
      caption: 'TASK',
      body: '',
      empty: 'Waiting for Lead',
      progress: null,
      lines: [],
      dim: false,
    };
    this.dirty = true;
    this.world = new Vector3();
  }

  set(patch) {
    Object.assign(this.state, patch);
    this.dirty = true;
  }

  face(camera) {
    this.group.getWorldPosition(this.world);
    this.group.lookAt(camera.position.x, this.world.y, camera.position.z);
  }

  draw() {
    if (!this.dirty) return;
    this.dirty = false;
    const { ctx, hue, state } = this;
    const inner = W - PAD * 2;
    ctx.clearRect(0, 0, W, H);
    ctx.globalAlpha = state.dim ? 0.5 : 1;

    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, rgba(hue, 0.2));
    bg.addColorStop(1, rgba(hue, 0.05));
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.028)';
    for (let y = 0; y < H; y += 4) ctx.fillRect(0, y, W, 1);

    ctx.textBaseline = 'alphabetic';
    ctx.font = `600 36px ${FONT_DISPLAY}`;
    ctx.fillStyle = hue;
    ctx.textAlign = 'left';
    ctx.fillText(fit(ctx, state.title.toUpperCase(), inner * 0.62), PAD, 58);

    ctx.font = `500 22px ${FONT_MONO}`;
    ctx.fillStyle = state.statusColor;
    ctx.textAlign = 'right';
    ctx.fillText(state.status.toUpperCase(), W - PAD, 56);
    ctx.textAlign = 'left';

    ctx.fillStyle = rgba(hue, 0.45);
    ctx.fillRect(PAD, 76, inner, 2);

    ctx.font = `500 17px ${FONT_MONO}`;
    ctx.fillStyle = 'rgba(200, 212, 235, 0.62)';
    ctx.fillText(state.caption, PAD, 110);

    if (state.body) {
      ctx.font = `500 27px ${FONT_BODY}`;
      ctx.fillStyle = '#eef3fb';
      wrap(ctx, state.body, inner, 2).forEach((line, i) => ctx.fillText(line, PAD, 144 + i * 34));
    } else {
      ctx.font = `italic 400 25px ${FONT_BODY}`;
      ctx.fillStyle = 'rgba(200, 212, 235, 0.55)';
      ctx.fillText(state.empty, PAD, 144);
    }

    if (typeof state.progress === 'number') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.1)';
      ctx.fillRect(PAD, 202, inner, 8);
      ctx.fillStyle = hue;
      ctx.fillRect(PAD, 202, inner * Math.max(0, Math.min(1, state.progress)), 8);
    }

    ctx.font = `400 21px ${FONT_MONO}`;
    state.lines.slice(0, 4).forEach((line, i) => {
      ctx.fillStyle = line.ok === false ? '#ff7d88' : 'rgba(222, 232, 248, 0.86)';
      const mark = line.ok === false ? '✕' : line.ok === true ? '✓' : '›';
      ctx.fillText(fit(ctx, `${mark} ${line.text}`, inner), PAD, 248 + i * 29);
    });

    ctx.globalAlpha = 1;
    this.texture.needsUpdate = true;
  }
}
