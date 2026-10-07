import {
  ACESFilmicToneMapping,
  AmbientLight,
  Color,
  DirectionalLight,
  FogExp2,
  HemisphereLight,
  PerspectiveCamera,
  PMREMGenerator,
  Scene,
  Vector2,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { engine } from 'animejs';

export const INK = '#070b14';

export function createStage(host) {
  const renderer = new WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.className = 'stage-canvas';
  host.appendChild(renderer.domElement);

  const labels = new CSS2DRenderer();
  labels.domElement.className = 'stage-labels';
  host.appendChild(labels.domElement);

  const scene = new Scene();
  scene.background = new Color(INK);
  scene.fog = new FogExp2(INK, 0.022);
  const pmrem = new PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.3;
  pmrem.dispose();

  scene.add(new AmbientLight('#8fa6d6', 0.35));
  scene.add(new HemisphereLight('#9bb8ff', '#0a0f1c', 0.6));
  const key = new DirectionalLight('#ffffff', 1.1);
  key.position.set(6, 14, 8);
  scene.add(key);

  const camera = new PerspectiveCamera(42, 1, 0.1, 220);
  camera.position.set(0, 10.5, 18);

  const controls = new OrbitControls(camera, labels.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 5;
  controls.maxDistance = 42;
  controls.maxPolarAngle = Math.PI * 0.62;
  controls.target.set(0, 1.2, 0);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new Vector2(1, 1), 0.75, 0.5, 0.72);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  const resize = () => {
    const w = Math.max(1, host.clientWidth);
    const h = Math.max(1, host.clientHeight);
    camera.aspect = w / h;
    camera.fov = w / h < 0.8 ? 58 : 42;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    labels.setSize(w, h);
  };
  new ResizeObserver(resize).observe(host);
  resize();

  engine.useDefaultMainLoop = false;

  const frameHandlers = new Set();

  const start = () => {
    renderer.setAnimationLoop(() => {
      engine.update();
      for (const fn of frameHandlers) fn();
      controls.update();
      composer.render();
      labels.render(scene, camera);
    });
  };

  return {
    renderer,
    scene,
    camera,
    controls,
    labels,
    bloom,
    onFrame: (fn) => frameHandlers.add(fn),
    start,
  };
}
