import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Sky } from "three/addons/objects/Sky.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { SMAAPass } from "three/addons/postprocessing/SMAAPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const MAT = {};
const GEO = {};
const DUMMY = new THREE.Object3D();
const V3 = new THREE.Vector3();

const GradeShader = {
  uniforms: {
    tDiffuse: { value: null },
    sat: { value: 0.06 },
    lift: { value: 0.04 },
    gain: { value: 1.02 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform float sat, lift, gain;
    varying vec2 vUv;
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      float luma = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
      vec3 d = mix(vec3(luma), c.rgb, sat);
      d = d * gain * (1.0 - lift) + lift;
      gl_FragColor = vec4(d, c.a);
    }
  `,
};

function M(id, color, extra = {}) {
  if (!MAT[id]) {
    const physical = extra.physical;
    const rest = { ...extra };
    delete rest.physical;
    const Ctor = physical ? THREE.MeshPhysicalMaterial : THREE.MeshStandardMaterial;
    MAT[id] = new Ctor({
      color,
      roughness: rest.roughness ?? 0.7,
      metalness: rest.metalness ?? 0.04,
      envMapIntensity: rest.envMapIntensity ?? 0.9,
      ...rest,
    });
  }
  return MAT[id];
}

function G(id, factory) {
  if (!GEO[id]) GEO[id] = factory();
  return GEO[id];
}

let renderer, scene, camera, controls, clock, composer, gtaoPass, smaaPass, labelRenderer;
let siteGroup, liveGroup, craneTop, trolley, hook, cable;
let mixerDrums = [];
let dustPts, workers = [];
let running = true;
let maps = {};
const clayPool = [];
const EDGE_CACHE = new Map();
const VEH_CACHE = {};
const cranes = [];
const picks = new Map();
let pickHelper = null;
let focusAim = null;
let edgeLineMat = null;
let frameN = 0;
let twinCanvas = null;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const _box = new THREE.Box3();
const _ctr = new THREE.Vector3();

export async function initTwin(canvas) {
  twinCanvas = canvas;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.92;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0a);
  scene.fog = new THREE.Fog(0x0a0a0a, 140, 420);

  camera = new THREE.PerspectiveCamera(28, canvas.clientWidth / Math.max(canvas.clientHeight, 1), 0.4, 900);
  camera.position.set(108, 78, 96);
  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.target.set(8, 6, -10);
  controls.maxPolarAngle = Math.PI * 0.42;
  controls.minDistance = 16;
  controls.maxDistance = 280;
  controls.autoRotate = false;

  clock = new THREE.Clock();
  makeTextures();
  nightLights();
  siteGroup = new THREE.Group();
  scene.add(siteGroup);
  liveGroup = new THREE.Group();
  scene.add(liveGroup);
  setupLabels(canvas);
  try { setupComposer(canvas); } catch { composer = null; }
  bindZoom();
  bindPicking(canvas);
  window.addEventListener("resize", () => resize(canvas));
  animate();

  await fillSite(siteGroup);
  for (const child of [...siteGroup.children]) {
    applyNightClay(child, true);
    await yieldFrame();
  }
  try { collapseEdges(siteGroup); } catch { /* keep local edges */ }
  addSitePins();
  try {
    applyScene(await fetch("/api/twin/current").then((r) => r.json()));
  } catch {
    applyScene({ mode: "default", equipment: defaultKit(), points: { xyz: [], rgb: [] }, cameras: [] });
  }
  renderer.shadowMap.needsUpdate = true;
  renderer.shadowMap.autoUpdate = false;
  selectPick("CRN-A-MSK");
}

export function applyScene(data) {
  if (!liveGroup) return;
  while (liveGroup.children.length) liveGroup.remove(liveGroup.children[0]);
  mixerDrums = [];
  const eq = (data.mode === "reconstructed" && data.equipment?.length >= 8)
    ? data.equipment
    : defaultKit();
  eq.forEach((item) => liveGroup.add(vehicle(item)));
  const cloud = pointCloud(data.points);
  if (cloud) liveGroup.add(cloud);
  (data.cameras || []).forEach((cam) => liveGroup.add(cameraPole(cam)));
  const title = document.getElementById("twin-title");
  const mode = document.getElementById("twin-mode");
  if (title) title.textContent = data.title || "Цифровой двойник площадки";
  if (mode && !document.getElementById("unit-id")?.dataset.locked) {
    mode.textContent = data.mode === "reconstructed" ? "реконструкция" : "эталон";
  }
  const dl = document.getElementById("twin-download");
  if (dl) {
    if (data.gltf_url) { dl.href = data.gltf_url; dl.classList.remove("hidden"); }
    else dl.classList.add("hidden");
  }
  renderer && (renderer.shadowMap.needsUpdate = true);
}

export function pauseTwin(paused) { running = !paused; }

function yieldFrame() {
  return new Promise((r) => requestAnimationFrame(r));
}

function defaultKit() {
  return [
    { code: "excavator", id: "EXC-01-MSK", position: [-7.2, -2.52, 7.4], yaw: 0.62 },
    { code: "excavator", id: "EXC-02-MSK", position: [2.1, -2.52, 1.6], yaw: -0.95 },
    { code: "excavator", id: "EXC-03-MSK", position: [-18.4, -2.52, 4.2], yaw: 1.15 },
    { code: "dump_truck", id: "DMP-01-MSK", position: [-12.2, 0, 14.2], yaw: 0.38 },
    { code: "dump_truck", id: "DMP-02-MSK", position: [-17.4, 0, 20.2], yaw: 1.28 },
    { code: "dump_truck", id: "DMP-03-MSK", position: [-36.5, 0, 8.4], yaw: 1.57 },
    { code: "concrete_mixer", id: "MXR-01-MSK", position: [1.8, 0, 13.4], yaw: -0.48 },
    { code: "concrete_mixer", id: "MXR-02-MSK", position: [18.6, 0, 18.2], yaw: 0.22 },
    { code: "mobile_crane", id: "MCR-01-MSK", position: [8.4, 0, 0.4], yaw: 0.32 },
    { code: "mobile_crane", id: "MCR-02-MSK", position: [28.5, 0, -8.2], yaw: -0.4 },
    { code: "bulldozer", id: "DOZ-01-MSK", position: [-9.8, -2.52, 1.2], yaw: 0.85 },
    { code: "roller", id: "ROL-01-MSK", position: [-32.6, 0, 18.2], yaw: 0.04 },
    { code: "manipulator_crane", id: "MAN-01-MSK", position: [19.2, 0, -2.1], yaw: -0.7 },
    { code: "truck", id: "TRK-01-MSK", position: [-40.8, 0, -6.4], yaw: 1.57 },
    { code: "truck", id: "TRK-02-MSK", position: [22.5, 0, 10.5], yaw: -0.2 },
    { code: "truck", id: "TRK-03-MSK", position: [42.2, 0, 6.8], yaw: 3.2 },
  ];
}

function setupComposer(canvas) {
  const w = canvas.clientWidth;
  const h = Math.max(canvas.clientHeight, 1);
  composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  gtaoPass = new GTAOPass(scene, camera, Math.floor(w * 0.55), Math.floor(h * 0.55));
  gtaoPass.output = GTAOPass.OUTPUT.Default;
  gtaoPass.blendIntensity = 0.34;
  gtaoPass.updateGtaoMaterial({
    radius: 0.55,
    samples: 10,
    thickness: 2.2,
    distanceFallOff: 0.55,
    scale: 1.05,
  });
  composer.addPass(gtaoPass);
  composer.addPass(new OutputPass());
  composer.addPass(new ShaderPass(GradeShader));
  smaaPass = new SMAAPass(Math.floor(w * renderer.getPixelRatio()), Math.floor(h * renderer.getPixelRatio()));
  composer.addPass(smaaPass);
}

/* ---------- textures ---------- */

function makeTextures() {
  maps.dirtFine = surfTex(512, (u, v) => {
    const n = fbm(u * 18, v * 18);
    const r = 86 + n * 28;
    return [r, r * 0.8, r * 0.58, n * 0.4];
  });
  maps.grass = surfTex(512, (u, v) => {
    const n = fbm(u * 22, v * 22, 6);
    const blade = Math.abs(Math.sin(u * 90 + n * 4) * Math.sin(v * 70));
    const g = 78 + n * 28 + blade * 18;
    return [g * 0.62, g, g * 0.48, n * 0.5 + blade * 0.25];
  });
  maps.conc = surfTex(512, (u, v) => {
    const n = fbm(u * 7, v * 7, 6);
    const agg = vnoise(u * 90, v * 90);
    const panel = (frac(u * 4) < 0.01 || frac(v * 4) < 0.01) ? 16 : 0;
    const stain = Math.max(0, fbm(u * 2.2, v * 2.2) - 0.58) * 28;
    const crack = Math.abs(vnoise(u * 2.5, v * 48) - 0.5) < 0.012 ? 18 : 0;
    const du = frac(u * 8) - 0.5, dv = frac(v * 8) - 0.5;
    const tie = Math.hypot(du, dv) < 0.04 ? 22 : 0;
    const c = 168 + n * 18 + agg * 10 - panel - stain - crack - tie;
    return [c, c - 3, c - 8, n * 0.4 + agg * 0.2 + (tie ? 0.35 : 0)];
  });
  maps.asph = surfTex(512, (u, v) => {
    const n = fbm(u * 16, v * 16, 6);
    const chip = vnoise(u * 90, v * 90);
    const oil = Math.max(0, fbm(u * 3.5, v * 3.5) - 0.62) * 40;
    const crack = Math.abs(vnoise(u * 1.8, v * 55) - 0.5) < 0.01 ? 14 : 0;
    const wet = Math.max(0, fbm(u * 1.6, v * 1.6, 3) - 0.58);
    const c = 44 + n * 16 + chip * 10 - oil - crack - wet * 18;
    return [c, c, c + 2, n * 0.4 + chip * 0.2 - wet * 0.35];
  });
  maps.dirt = surfTex(512, (u, v) => {
    const n = fbm(u * 10, v * 10, 6);
    const peb = vnoise(u * 48, v * 48);
    const track = Math.abs(Math.sin(v * 28 + n * 2)) * Math.max(0, 0.55 - Math.abs(u - 0.5) * 3);
    const r = 88 + n * 36 + peb * 12 - track * 22;
    return [r, r * 0.76, r * 0.52, n * 0.5 + peb * 0.25 + track * 0.3];
  });
  maps.wood = surfTex(256, (u, v) => {
    const warp = fbm(u * 2, v * 0.35) * 0.18;
    const grain = Math.sin((v + warp) * 48);
    const n = fbm(u * 3, v * 16, 5);
    const knot = Math.hypot(frac(u * 3) - 0.5, frac(v * 5) - 0.5);
    const k = knot < 0.08 ? (0.08 - knot) * 180 : 0;
    const c = 104 + grain * 16 + n * 14 - k;
    return [c, c * 0.66, c * 0.36, n * 0.4 + Math.abs(grain) * 0.18 + (k ? 0.4 : 0)];
  });
  maps.wool = surfTex(256, (u, v) => {
    const fiber = Math.abs(Math.sin(u * 90 + fbm(u * 8, v * 8) * 4));
    const n = fbm(u * 14, v * 18, 5);
    const c = 168 + n * 22 + fiber * 18;
    return [c, c * 0.88, c * 0.42, n * 0.55 + fiber * 0.3];
  });
  maps.paint = surfTex(256, (u, v) => {
    const n = fbm(u * 12, v * 12, 5);
    const dust = fbm(u * 3.2, v * 3.2);
    const chip = vnoise(u * 40, v * 40) > 0.92 ? 40 : 0;
    const drip = Math.max(0, 0.55 - u) * fbm(u * 8, v * 2) * 22;
    const c = 208 + n * 10 - dust * 20 - chip - drip;
    return [c, c - 5, c - 12, n * 0.25 + chip * 0.01];
  });
  maps.gravel = surfTex(256, (u, v) => {
    const n = fbm(u * 28, v * 28);
    const stone = vnoise(u * 55, v * 55);
    const c = 96 + n * 30 + stone * 16;
    return [c, c - 4, c - 10, n * 0.7];
  });
  maps.rust = surfTex(256, (u, v) => {
    const n = fbm(u * 9, v * 9);
    const streak = Math.abs(Math.sin(v * 18 + n * 6));
    return [118 + n * 50, 62 + n * 18, 32 + n * 8, n * 0.5 + streak * 0.2];
  });
  maps.corr = surfTex(256, (u, v) => {
    const wave = Math.sin(u * Math.PI * 18) * 0.5 + 0.5;
    const rust = Math.max(0, fbm(u * 6, v * 6) - 0.62);
    const c = 108 + wave * 28;
    return [c + rust * 40, c - 2, c - 6, wave * 0.7];
  });
  maps.brick = brickTex(256);
  maps.stripe = stripeTex();
  maps.banner = labelTex("STROSYNC  ·  ПЛОЩАДКА №1", "#2c3d52", "#d8c07a");
  maps.ppe = labelTex("PPE  ·  КАСКА  ·  ЖИЛЕТ", "#6a2a2a", "#ece8e0");
  maps.speed = labelTex("20", "#b89a4a", "#1c1c1c");
  maps.warn = labelTex("ОПАСНО", "#6a1c1c", "#f2c94c");
  maps.net = netTex();
  bindRepeat(maps.dirt, 18, 18);
  bindRepeat(maps.dirtFine, 12, 12);
  bindRepeat(maps.grass, 24, 24);
  bindRepeat(maps.conc, 5, 5);
  bindRepeat(maps.asph, 12, 3);
  bindRepeat(maps.gravel, 8, 8);
  bindRepeat(maps.wood, 2, 6);
  bindRepeat(maps.corr, 6, 2);
  bindRepeat(maps.brick, 5, 3);
  bindRepeat(maps.paint, 3, 3);
  bindRepeat(maps.wool, 6, 8);
}

function surfTex(size, sample) {
  const { canvas, ctx, img } = canvasImg(size);
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const [r, g, b, h] = sample(x / size, y / size);
      const i = (y * size + x) * 4;
      img.data[i] = clamp(r);
      img.data[i + 1] = clamp(g);
      img.data[i + 2] = clamp(b);
      img.data[i + 3] = 255;
      height[y * size + x] = h ?? 0.5;
    }
  }
  ctx.putImageData(img, 0, 0);
  const albedo = texFrom(canvas, true);
  albedo.normal = normalFromHeight(height, size, 3.2);
  albedo.rough = roughFromHeight(height, size);
  return albedo;
}

function bindRepeat(tex, x, y) {
  [tex, tex.normal, tex.rough].forEach((t) => {
    if (!t) return;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(x, y);
  });
}

function normalFromHeight(height, size, strength = 2.8) {
  const data = new Uint8Array(size * size * 4);
  const at = (x, y) => height[(((y % size) + size) % size) * size + (((x % size) + size) % size)];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = at(x + 1, y) - at(x - 1, y);
      const dy = at(x, y + 1) - at(x, y - 1);
      const nx = -dx * strength;
      const ny = -dy * strength;
      const len = Math.hypot(nx, ny, 1) || 1;
      const i = (y * size + x) * 4;
      data[i] = (nx / len * 0.5 + 0.5) * 255;
      data[i + 1] = (ny / len * 0.5 + 0.5) * 255;
      data[i + 2] = (1 / len * 0.5 + 0.5) * 255;
      data[i + 3] = 255;
    }
  }
  const t = new THREE.DataTexture(data, size, size);
  t.colorSpace = THREE.NoColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.needsUpdate = true;
  return t;
}

function roughFromHeight(height, size) {
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < height.length; i++) {
    const r = clamp(140 + height[i] * 80);
    data[i * 4] = r;
    data[i * 4 + 1] = r;
    data[i * 4 + 2] = r;
    data[i * 4 + 3] = 255;
  }
  const t = new THREE.DataTexture(data, size, size);
  t.colorSpace = THREE.NoColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.needsUpdate = true;
  return t;
}

function brickTex(size) {
  const { canvas, ctx, img } = canvasImg(size);
  const bw = 32, bh = 14;
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const row = Math.floor(y / bh);
      const ox = row % 2 ? bw / 2 : 0;
      const mortar = ((x + ox) % bw < 2 || y % bh < 2);
      const n = vnoise((x + ox) / bw, row * 0.7);
      const i = (y * size + x) * 4;
      if (mortar) {
        img.data[i] = 176; img.data[i + 1] = 170; img.data[i + 2] = 160;
        height[y * size + x] = 0.2;
      } else {
        img.data[i] = clamp(128 + n * 28);
        img.data[i + 1] = clamp(72 + n * 14);
        img.data[i + 2] = clamp(56 + n * 10);
        height[y * size + x] = 0.55 + n * 0.2;
      }
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const albedo = texFrom(canvas, true);
  albedo.normal = normalFromHeight(height, size, 4);
  return albedo;
}

function stripeTex() {
  const { canvas, ctx } = canvasImg(128);
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, 128, 128);
  ctx.fillStyle = "#c4b06a";
  for (let i = -128; i < 256; i += 18) {
    ctx.save();
    ctx.translate(i, 0);
    ctx.rotate(-0.7);
    ctx.fillRect(0, -40, 8, 220);
    ctx.restore();
  }
  const t = texFrom(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(4, 1);
  return t;
}

function netTex() {
  const { canvas, ctx, img } = canvasImg(256);
  for (let y = 0; y < 256; y++) {
    for (let x = 0; x < 256; x++) {
      const i = (y * 256 + x) * 4;
      const yarn = (x % 10 < 2) || (y % 10 < 2);
      if (yarn) {
        const n = vnoise(x * 0.08, y * 0.08);
        img.data[i] = 28 + n * 18;
        img.data[i + 1] = 110 + n * 30;
        img.data[i + 2] = 52 + n * 12;
        img.data[i + 3] = 230;
      } else {
        img.data[i] = 20; img.data[i + 1] = 60; img.data[i + 2] = 30; img.data[i + 3] = 12;
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  const t = texFrom(canvas, true);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(18, 14);
  return t;
}

function labelTex(text, bg, fg) {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 128;
  const ctx = c.getContext("2d");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 512, 128);
  ctx.strokeStyle = fg;
  ctx.lineWidth = 8;
  ctx.strokeRect(8, 8, 496, 112);
  ctx.fillStyle = fg;
  ctx.font = "700 42px IBM Plex Sans, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 256, 68);
  const t = texFrom(c);
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  return t;
}

function canvasImg(size) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  return { canvas, ctx, img: ctx.createImageData(size, size) };
}

function texFrom(canvas, srgb = true) {
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = renderer?.capabilities.getMaxAnisotropy() || 8;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  return t;
}

function hash(x, y) {
  const s = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

function vnoise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  return (
    hash(xi, yi) * (1 - u) * (1 - v) +
    hash(xi + 1, yi) * u * (1 - v) +
    hash(xi, yi + 1) * (1 - u) * v +
    hash(xi + 1, yi + 1) * u * v
  );
}

function fbm(x, y, oct = 5) {
  let s = 0, a = 0.5, f = 1;
  for (let i = 0; i < oct; i++) {
    s += a * vnoise(x * f, y * f);
    f *= 2.03;
    a *= 0.5;
  }
  return s;
}

function frac(v) { return v - Math.floor(v); }

function clamp(v) { return Math.max(0, Math.min(255, v)); }

function seedRand(s) {
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

/* ---------- sky / lights ---------- */

function nightLights() {
  scene.add(new THREE.AmbientLight(0x8a8a8e, 0.38));
  scene.add(new THREE.HemisphereLight(0x3a3a40, 0x101010, 0.55));
  const key = new THREE.DirectionalLight(0xe8e8ec, 1.35);
  key.position.set(48, 88, 28);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0002;
  key.shadow.normalBias = 0.05;
  Object.assign(key.shadow.camera, { left: -120, right: 120, top: 90, bottom: -90, near: 6, far: 260 });
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9aa4b4, 0.42);
  rim.position.set(-70, 28, -40);
  scene.add(rim);
}

function clayMat(hex, rough = 0.94) {
  const m = new THREE.MeshStandardMaterial({
    color: hex, roughness: rough, metalness: 0.06, envMapIntensity: 0.12,
  });
  clayPool.push(m);
  return m;
}

function edgesFor(geo) {
  let eg = EDGE_CACHE.get(geo.uuid);
  if (!eg) {
    eg = new THREE.EdgesGeometry(geo, 28);
    EDGE_CACHE.set(geo.uuid, eg);
  }
  return eg;
}

function applyNightClay(root, edges) {
  if (!root) return;
  const dark = clayMat(0x242424);
  const mid = clayMat(0x303030);
  const pale = clayMat(0x3c3c3c, 0.78);
  if (!edgeLineMat) {
    edgeLineMat = new THREE.LineBasicMaterial({ color: 0x8a8a8a, transparent: true, opacity: 0.78 });
    clayPool.push(edgeLineMat);
  }
  root.traverse((o) => {
    if (!o.isMesh || o.userData.hudSkip) return;
    const n = o.name || "";
    o.material = /glass|win|cgl|puddle/i.test(n) || o.material?.transparent ? pale : (o.castShadow ? mid : dark);
    o.material.transparent = false;
    o.material.opacity = 1;
    if (o.material.map) o.material.map = null;
    const count = o.geometry?.attributes?.position?.count || 0;
    if (edges && !o.isInstancedMesh && count > 0 && count < 2400 && !o.userData.edged) {
      const eg = edgesFor(o.geometry);
      if (eg.attributes.position.count) {
        const lines = new THREE.LineSegments(eg, edgeLineMat);
        lines.userData.hudSkip = true;
        o.add(lines);
        o.userData.edged = true;
      }
    }
  });
}

function collapseEdges(root) {
  if (!root || !edgeLineMat) return;
  root.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const geos = [];
  const kill = [];
  root.traverse((o) => {
    if (!o.isLineSegments || !o.userData.hudSkip) return;
    let p = o.parent, live = false;
    while (p && p !== root) {
      if (p.userData.live) { live = true; break; }
      p = p.parent;
    }
    if (live) return;
    const g = o.geometry.clone();
    g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld));
    geos.push(g);
    kill.push(o);
  });
  kill.forEach((o) => o.parent?.remove(o));
  if (geos.length < 2) return;
  const merged = mergeGeometries(geos, false);
  if (!merged) return;
  const lines = new THREE.LineSegments(merged, edgeLineMat);
  lines.userData.hudSkip = true;
  root.add(lines);
}

function setupLabels(canvas) {
  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
  const el = labelRenderer.domElement;
  el.style.position = "absolute";
  el.style.inset = "0";
  el.style.zIndex = "5";
  el.style.pointerEvents = "none";
  canvas.parentElement.appendChild(el);
}

function dossier(id, extra = {}) {
  const base = DOSSIERS[id] || {
    id,
    title: extra.title || id,
    kind: extra.kind || "unit",
    status: extra.status || "active",
    power: extra.power ?? 72,
    session: extra.session || "6HR 10MIN",
    signal: extra.signal || "STABLE",
    load: extra.load ?? 54,
    facts: extra.facts || [],
  };
  return { ...base, ...extra, id };
}

const DOSSIERS = {
  "CRN-A-MSK": {
    title: "Башенный кран №1", kind: "crane", status: "active",
    power: 86, session: "14HR 10MIN", signal: "STABLE", load: 71,
    facts: ["Liebherr 280 EC-H · стрела 62 м", "Груз на крюке 8.2 т", "Обслуживает корпус A", "Сессия с 06:20"],
  },
  "CRN-B-MSK": {
    title: "Башенный кран №2", kind: "crane", status: "active",
    power: 79, session: "11HR 40MIN", signal: "MODERATE", load: 64,
    facts: ["Potain MDT 319 · стрела 55 м", "Контргруз 18 т", "Обслуживает корпус B", "Ветер 7 м/с — режим снижен"],
  },
  "BLD-A-MSK": {
    title: "Корпус A · каркас", kind: "building", status: "active",
    power: 68, session: "DAY 47", signal: "STABLE", load: 58,
    facts: ["5 этажей монолит", "Байты 5×3 · плиты 60%", "Сетка + ограждение кровли", "WBS 4.2 / 4.3"],
  },
  "BLD-B-MSK": {
    title: "Корпус B · высотка", kind: "building", status: "active",
    power: 74, session: "DAY 62", signal: "STABLE", load: 66,
    facts: ["7 этажей · секция 2", "Фасад: кирпич + вата", "Лестничная клетка до +6", "WBS 5.1"],
  },
  "BLD-C-MSK": {
    title: "Корпус C · фундамент", kind: "building", status: "warning",
    power: 41, session: "DAY 12", signal: "MODERATE", load: 33,
    facts: ["2 этажа · ростверк", "Армокаркасы на пятне", "Ожидание бетона 04:00", "WBS 3.1"],
  },
  "PIT-01-MSK": {
    title: "Котлован / шпунт", kind: "pit", status: "active",
    power: 62, session: "DAY 19", signal: "STABLE", load: 55,
    facts: ["Отм. −2.7 м", "Шпунт + распорки", "Два экскаватора в забое", "Водоотлив работает"],
  },
  "SCF-01-MSK": {
    title: "Леса корпуса A", kind: "scaffold", status: "active",
    power: 70, session: "DAY 31", signal: "STABLE", load: 48,
    facts: ["Трубчатые леса 14 м", "Настил + защитная сетка", "10 секций по фасаду", "Допуск до яруса 7"],
  },
  "SCF-02-MSK": {
    title: "Леса корпуса B", kind: "scaffold", status: "active",
    power: 66, session: "DAY 28", signal: "STABLE", load: 44,
    facts: ["8 секций · южный торец", "Сетка по внешнему контуру", "Подача с крана №2"],
  },
  "WEL-01-MSK": {
    title: "Бытовой городок", kind: "welfare", status: "active",
    power: 91, session: "24HR", signal: "STABLE", load: 38,
    facts: ["3 модуля: офис / столовая / штаб", "Персонал на смене 46", "Пропускной режим"],
  },
  "PLT-01-MSK": {
    title: "Растворный узел", kind: "plant", status: "active",
    power: 77, session: "9HR 05MIN", signal: "STABLE", load: 69,
    facts: ["Силос + бункер + ДГУ", "Подача на корпус A/B", "Запас цемента 18 т"],
  },
  "YRD-01-MSK": {
    title: "Склад контейнеров", kind: "yard", status: "active",
    power: 54, session: "DAY 47", signal: "STABLE", load: 42,
    facts: ["5 контейнеров", "Инструмент / опалубка", "Учёт RFID"],
  },
  "STK-01-MSK": {
    title: "Склад материалов", kind: "stock", status: "warning",
    power: 48, session: "DAY 47", signal: "MODERATE", load: 61,
    facts: ["Арматура, трубы, мешки", "Поддоны кирпича", "Плёнка / рубероид"],
  },
  "GAT-01-MSK": {
    title: "КПП / въезд", kind: "gate", status: "active",
    power: 88, session: "24HR", signal: "STABLE", load: 29,
    facts: ["Два створа · мойка колёс", "ANPR на въезде", "Очередь: 1 миксер"],
  },
};

function markPick(root, id, extra) {
  if (!root || !id) return root;
  const d = dossier(id, extra);
  d.object = root;
  picks.set(id, d);
  root.userData.pick = d;
  root.traverse((o) => {
    if (o.isMesh || o.isInstancedMesh) o.userData.pick = d;
  });
  return root;
}

export function selectPick(id) {
  const d = typeof id === "string" ? picks.get(id) || dossier(id) : id;
  if (!d) return;
  const led = d.status === "warning" ? "warn" : d.status === "inactive" ? "crit" : "on";
  const sigWarn = /MODERATE|WEAK|LOW/i.test(d.signal || "");
  const set = (sid, v) => { const el = document.getElementById(sid); if (el) el.textContent = v; };
  set("unit-id", d.id);
  set("unit-kind", d.title || d.kind || "");
  const mode = document.getElementById("twin-mode");
  if (mode) mode.textContent = d.status === "active" ? "active" : d.status || "эталон";
  const headLed = document.querySelector(".unit-head .led");
  if (headLed) headLed.className = `led ${led}`;
  set("m-power", `${d.power}%`);
  set("m-session", d.session);
  set("m-signal", d.signal);
  const pb = document.getElementById("m-power-bar");
  const sb = document.getElementById("m-session-bar");
  const gb = document.getElementById("m-signal-bar");
  const lb = document.getElementById("m-load-bar");
  if (pb) pb.style.width = `${d.power}%`;
  if (sb) sb.style.width = `${Math.min(100, 40 + (d.power || 0) * 0.4)}%`;
  if (gb) gb.style.width = `${sigWarn ? 46 : 78}%`;
  if (lb) lb.style.width = `${d.load}%`;
  set("m-load", `${d.load}%`);
  const sig = document.getElementById("m-signal");
  if (sig) sig.classList.toggle("warn", sigWarn);
  document.getElementById("m-signal-row")?.classList.toggle("warn", sigWarn);
  set("twin-meta", (d.facts && d.facts[0]) || "Preparing performance details…");
  const facts = document.getElementById("pick-facts");
  if (facts) facts.innerHTML = (d.facts || []).map((f) => `<li>${f}</li>`).join("");
  document.querySelectorAll("#unit-strip .unit").forEach((b) => {
    b.classList.toggle("active", b.dataset.pick === d.id || b.querySelector("b")?.textContent === d.id);
  });
  if (d.object) {
    if (pickHelper) scene.remove(pickHelper);
    pickHelper = new THREE.BoxHelper(d.object, 0xf2f2f2);
    pickHelper.userData.hudSkip = true;
    scene.add(pickHelper);
    _box.setFromObject(d.object);
    _box.getCenter(_ctr);
    focusAim = _ctr.clone();
  }
}

function bindPicking(canvas) {
  let down = null;
  canvas.addEventListener("pointerdown", (e) => {
    down = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener("pointermove", (e) => {
    const r = canvas.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects([siteGroup, liveGroup].filter(Boolean), true)[0];
    canvas.style.cursor = hit?.object?.userData?.pick ? "pointer" : "";
  });
  canvas.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
    const r = canvas.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects([siteGroup, liveGroup].filter(Boolean), true)[0];
    const d = hit?.object?.userData?.pick;
    if (d) selectPick(d.id);
  });
}

function addSitePins() {
  const pins = [
    ["CRN-A-MSK", 3.2, 31.6, -20.4],
    ["CRN-B-MSK", 38, 31.6, -16],
    ["BLD-A-MSK", 13.2, 18.4, -9.2],
    ["BLD-B-MSK", 32, 24.8, -28],
    ["BLD-C-MSK", -28, 8.4, -32],
    ["PIT-01-MSK", -3.2, 1.6, 6.2],
    ["APD-7100-NYC", 26.5, 3.2, -18],
    ["IUH-305-NYC", 3.2, 31.4, -20.4],
    ["BDS-230-NYC", -22.4, 2.4, 8.2],
  ];
  pins.forEach(([id, x, y, z]) => {
    const wrap = document.createElement("div");
    wrap.className = "hud-pin-wrap";
    wrap.innerHTML = `<i class="hud-pin"></i><span class="hud-label">${id}</span>`;
    wrap.addEventListener("click", (e) => { e.stopPropagation(); selectPick(id); });
    const obj = new CSS2DObject(wrap);
    obj.position.set(x, y, z);
    scene.add(obj);
    const mark = mesh(G("pin:0.28", () => new THREE.BoxGeometry(0.28, 0.28, 0.28)), clayMat(0xf0f0f0, 0.3), x, y, z, false);
    mark.userData.hudSkip = true;
    mark.userData.pick = picks.get(id) || dossier(id);
    scene.add(mark);
  });
}

function bindZoom() {
  document.getElementById("zoom-in")?.addEventListener("click", () => {
    camera.position.multiplyScalar(0.86);
    controls.update();
  });
  document.getElementById("zoom-out")?.addEventListener("click", () => {
    camera.position.multiplyScalar(1.16);
    controls.update();
  });
}

export function initDroneHud(canvas) {
  if (!canvas) return;
  const r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  r.setPixelRatio(1);
  r.setSize(canvas.clientWidth || 320, canvas.clientHeight || 168, false);
  r.setClearColor(0x000000, 1);
  const sc = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(28, (canvas.clientWidth || 320) / (canvas.clientHeight || 168), 0.1, 40);
  cam.position.set(0.9, 0.7, 1.55);
  cam.lookAt(0, 0.05, 0);
  sc.add(new THREE.AmbientLight(0xffffff, 0.35));
  const L = new THREE.DirectionalLight(0xffffff, 0.8);
  L.position.set(2, 3, 2);
  sc.add(L);
  const mat = new THREE.MeshBasicMaterial({ color: 0xf2f2f2, wireframe: true });
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.1, 0.42), mat));
  [[-0.38, 0.38], [0.38, 0.38], [-0.38, -0.38], [0.38, -0.38]].forEach(([x, z]) => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.04), mat);
    arm.position.set(x * 0.55, 0.02, z * 0.55);
    arm.rotation.y = Math.atan2(z, x);
    g.add(arm);
    const rotor = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.012, 6, 18), mat);
    rotor.rotation.x = Math.PI / 2;
    rotor.position.set(x, 0.08, z);
    g.add(rotor);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.06, 8), mat);
    hub.position.set(x, 0.05, z);
    g.add(hub);
  });
  const skid = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.02, 0.04), mat);
  skid.position.set(0, -0.1, 0.14);
  g.add(skid);
  sc.add(g);
  let last = 0;
  const tick = (now) => {
    if (now - last > 33) {
      g.rotation.y += 0.01;
      r.render(sc, cam);
      last = now;
    }
    requestAnimationFrame(tick);
  };
  tick(0);
}

function addSky() { /* night HUD: unused */ }

function lights() { nightLights(); }

/* ---------- primitives ---------- */

function mesh(geo, mat, x, y, z, shadow = true) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.castShadow = shadow;
  m.receiveShadow = true;
  return m;
}

function box(w, h, d, mat, x, y, z, shadow = true) {
  return mesh(G(`b:${w}:${h}:${d}`, () => new THREE.BoxGeometry(w, h, d)), mat, x, y + h / 2, z, shadow);
}

function boxC(w, h, d, mat, x, y, z, shadow = true) {
  return mesh(G(`b:${w}:${h}:${d}`, () => new THREE.BoxGeometry(w, h, d)), mat, x, y, z, shadow);
}

function rboxC(w, h, d, mat, x, y, z, shadow = true) {
  const r = Math.min(w, h, d) * 0.08;
  return mesh(G(`rb2:${w}:${h}:${d}`, () => new RoundedBoxGeometry(w, h, d, 2, r)), mat, x, y, z, shadow);
}

function extrude(pts, depth, mat, x, y, z, bevel = 0.028) {
  const shape = new THREE.Shape();
  shape.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) shape.lineTo(pts[i][0], pts[i][1]);
  shape.closePath();
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 2,
    curveSegments: 6,
  });
  geo.translate(0, 0, -depth / 2);
  geo.computeVertexNormals();
  return mesh(geo, mat, x, y, z);
}

function lathe(pts, mat, x, y, z, segs = 28) {
  const path = pts.map(([px, py]) => new THREE.Vector2(px, py));
  return mesh(new THREE.LatheGeometry(path, segs), mat, x, y, z);
}

function iGeo(len, h = 0.38, w = 0.22, tf = 0.016, tw = 0.012) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2, -h / 2);
  s.lineTo(w / 2, -h / 2);
  s.lineTo(w / 2, -h / 2 + tf);
  s.lineTo(tw / 2, -h / 2 + tf);
  s.lineTo(tw / 2, h / 2 - tf);
  s.lineTo(w / 2, h / 2 - tf);
  s.lineTo(w / 2, h / 2);
  s.lineTo(-w / 2, h / 2);
  s.lineTo(-w / 2, h / 2 - tf);
  s.lineTo(-tw / 2, h / 2 - tf);
  s.lineTo(-tw / 2, -h / 2 + tf);
  s.lineTo(-w / 2, -h / 2 + tf);
  const geo = new THREE.ExtrudeGeometry(s, {
    depth: len, bevelEnabled: true, bevelThickness: 0.003, bevelSize: 0.003, bevelSegments: 1,
  });
  geo.translate(0, 0, -len / 2);
  geo.computeVertexNormals();
  return geo;
}

function corrugate(len, width, mat, x, y, z) {
  const s = new THREE.Shape();
  const amp = 0.045, step = 0.16;
  s.moveTo(0, 0);
  for (let t = 0; t <= width; t += step) {
    s.lineTo(t, Math.abs(((t / step) % 2) - 1) * amp);
  }
  s.lineTo(width, -0.02);
  s.lineTo(0, -0.02);
  const geo = new THREE.ExtrudeGeometry(s, { depth: len, bevelEnabled: false, steps: 1 });
  geo.rotateX(-Math.PI / 2);
  geo.translate(-width / 2, 0, -len / 2);
  geo.computeVertexNormals();
  return mesh(geo, mat, x, y, z, false);
}

function cyl(r, h, mat, x, y, z, rx = 0, rz = 0, seg = 20) {
  const m = mesh(G(`c:${r}:${h}:${seg}`, () => new THREE.CylinderGeometry(r, r, h, seg)), mat, x, y, z);
  m.rotation.x = rx;
  m.rotation.z = rz;
  return m;
}

function cone(r, h, mat, x, y, z, seg = 14) {
  return mesh(G(`k:${r}:${h}:${seg}`, () => new THREE.ConeGeometry(r, h, seg)), mat, x, y, z);
}

function rod(ax, ay, az, bx, by, bz, r, mat) {
  const dx = bx - ax, dy = by - ay, dz = bz - az;
  const len = Math.max(Math.hypot(dx, dy, dz), 0.02);
  const m = mesh(G(`c:${r}:${len}:10`, () => new THREE.CylinderGeometry(r, r, len, 10)), mat, (ax + bx) / 2, (ay + by) / 2, (az + dz) / 2);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), V3.set(dx, dy, dz).normalize());
  return m;
}

function hose(ax, ay, az, bx, by, bz, r, mat) {
  const mx = (ax + bx) * 0.5, my = (ay + by) * 0.5 + 0.14, mz = (az + bz) * 0.5;
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(ax, ay, az),
    new THREE.Vector3(mx, my, mz),
    new THREE.Vector3(bx, by, bz),
  ]);
  const m = new THREE.Mesh(new THREE.TubeGeometry(curve, 12, r, 6, false), mat);
  m.castShadow = false;
  m.receiveShadow = false;
  return m;
}

function instanced(geo, mat, poses, shadow = true) {
  const im = new THREE.InstancedMesh(geo, mat, poses.length);
  im.castShadow = shadow;
  im.receiveShadow = true;
  poses.forEach((p, i) => {
    DUMMY.position.set(p[0], p[1], p[2]);
    DUMMY.rotation.set(p[3] || 0, p[4] || 0, p[5] || 0);
    DUMMY.scale.set(p[6] ?? 1, p[7] ?? 1, p[8] ?? 1);
    DUMMY.updateMatrix();
    im.setMatrixAt(i, DUMMY.matrix);
  });
  return im;
}

function colH(h, mat) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(G(`icol:${h}`, () => iGeo(h)), mat);
  m.rotation.x = Math.PI / 2;
  m.position.y = h / 2;
  m.castShadow = m.receiveShadow = true;
  g.add(m);
  return g;
}

function beamX(len, mat) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(G(`ibeamx:${len}`, () => iGeo(len, 0.34, 0.2)), mat);
  m.rotation.y = Math.PI / 2;
  m.castShadow = m.receiveShadow = true;
  g.add(m);
  return g;
}

function beamZ(len, mat) {
  const g = beamX(len, mat);
  g.rotation.y = Math.PI / 2;
  return g;
}

/* ---------- site ---------- */

function buildSite() {
  const g = new THREE.Group();
  fillSiteSync(g);
  return g;
}

async function fillSite(g) {
  const add = (obj, id) => { if (id) markPick(obj, id); g.add(obj); };
  const chunks = [
    () => g.add(terrain()),
    () => g.add(context()),
    () => g.add(roads()),
    () => add(pit(), "PIT-01-MSK"),
    () => g.add(slab()),
    () => add(building(5, 13.2, -9.2, "building-a"), "BLD-A-MSK"),
    () => add(building(7, 32, -28, "building-b"), "BLD-B-MSK"),
    () => add(building(2, -28, -32, "building-c"), "BLD-C-MSK"),
    () => add(scaffold(3.6, -16.2, 10), "SCF-01-MSK"),
    () => add(scaffold(22.4, -35.6, 8), "SCF-02-MSK"),
    () => g.add(fence()),
    () => add(gate(), "GAT-01-MSK"),
    () => add(yard(), "YRD-01-MSK"),
    () => add(welfare(), "WEL-01-MSK"),
    () => add(plant(), "PLT-01-MSK"),
    () => add(stock(), "STK-01-MSK"),
    () => add(towerCrane(3.2, -20.4), "CRN-A-MSK"),
    () => add(towerCrane(38, -16), "CRN-B-MSK"),
    () => g.add(lightTowers()),
    () => g.add(people()),
    () => g.add(signs()),
    () => g.add(dust()),
    () => g.add(cables()),
  ];
  for (const fn of chunks) {
    fn();
    await yieldFrame();
  }
}

function fillSiteSync(g) {
  /* reserved for tests */
}

function terrain() {
  const g = new THREE.Group();
  const grassGeo = new THREE.PlaneGeometry(380, 380, 80, 80);
  grassGeo.rotateX(-Math.PI / 2);
  const pos = grassGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    const pad = Math.abs(x) < 62 && Math.abs(z) < 56;
    const n = Math.sin(x * 0.07) * 0.22 + Math.cos(z * 0.06) * 0.18 + Math.sin((x + z) * 0.045) * 0.12;
    pos.setY(i, pad ? n * 0.08 : n);
  }
  grassGeo.computeVertexNormals();
  const grass = new THREE.Mesh(grassGeo, M("grass", 0x5c6756, {
    map: maps.grass, normalMap: maps.grass.normal, roughnessMap: maps.grass.rough,
    roughness: 0.94, metalness: 0, envMapIntensity: 0.28, normalScale: new THREE.Vector2(0.55, 0.55),
  }));
  grass.receiveShadow = true;
  g.add(grass);

  const padGeo = new THREE.PlaneGeometry(118, 108, 64, 52);
  padGeo.rotateX(-Math.PI / 2);
  const pp = padGeo.attributes.position;
  for (let i = 0; i < pp.count; i++) {
    const x = pp.getX(i), z = pp.getZ(i);
    const n = Math.sin(x * 0.11) * 0.07 + Math.cos(z * 0.09) * 0.06 + Math.sin((x + z) * 0.07) * 0.04;
    const rut = Math.exp(-((x + 22.8) * (x + 22.8)) / 1.6) * Math.abs(Math.sin(z * 0.85)) * 0.09
      + Math.exp(-((z - 22.4) * (z - 22.4)) / 2.2) * Math.abs(Math.sin(x * 0.7)) * 0.07;
    pp.setY(i, 0.02 + n - rut);
  }
  padGeo.computeVertexNormals();
  const pad = new THREE.Mesh(padGeo, M("pad", 0x6a5a44, {
    map: maps.dirt, normalMap: maps.dirt.normal, roughnessMap: maps.dirt.rough,
    roughness: 0.96, metalness: 0, envMapIntensity: 0.22, normalScale: new THREE.Vector2(0.85, 0.85),
  }));
  pad.receiveShadow = true;
  pad.position.set(0, 0, 1);
  g.add(pad);
  return g;
}

function context() {
  const g = new THREE.Group();
  const specs = [
    [-78, -42, 20, 26, 18, 0x8a93a0],
    [76, -30, 16, 32, 22, 0x7d868f],
    [72, 44, 18, 20, 14, 0x949ca6],
    [-80, 34, 14, 26, 16, 0x6f7884],
    [-58, 62, 22, 14, 10, 0x88919c],
    [48, -52, 14, 18, 28, 0x7a828c],
    [-46, -54, 12, 16, 20, 0x6e7680],
    [54, 28, 10, 14, 16, 0x858d96],
    [-52, 38, 16, 12, 12, 0x737b86],
    [38, 56, 18, 10, 22, 0x808890],
    [-96, -8, 18, 22, 24, 0x6c7480],
    [92, 8, 16, 24, 30, 0x7e8690],
    [8, 78, 28, 16, 16, 0x747c86],
    [-12, -78, 20, 18, 14, 0x6a727c],
    [64, -68, 14, 16, 26, 0x808890],
  ];
  specs.forEach(([x, z, w, d, h, col], i) => {
    g.add(box(w, h, d, M("city" + i, col, {
      roughness: 0.78, map: maps.conc, normalMap: maps.conc.normal, envMapIntensity: 0.55,
    }), x, 0, z, false));
    g.add(box(w + 0.6, 0.35, d + 0.6, M("par" + i, 0x6a727c, { roughness: 0.62, metalness: 0.15 }), x, h, z, false));
    const win = M("win", 0x6a8494, {
      physical: true, roughness: 0.08, metalness: 0.12, transparent: true, opacity: 0.55,
      envMapIntensity: 1.4,
    });
    const poses = [];
    for (let fy = 1.6; fy < h - 1; fy += 2.15) {
      for (let fx = -w / 2 + 1.6; fx < w / 2 - 1; fx += 2.7) {
        poses.push([x + fx, fy + 0.55, z + d / 2 + 0.04, 0, 0, 0]);
        poses.push([x + fx, fy + 0.55, z - d / 2 - 0.04, 0, 0, 0]);
      }
    }
    if (poses.length) g.add(instanced(G("b:1.15:1.25:0.07", () => new THREE.BoxGeometry(1.15, 1.25, 0.07)), win, poses, false));
  });

  const rnd = seedRand(42);
  const trunks = [], crowns = [], crowns2 = [];
  for (let i = 0; i < 46; i++) {
    const a = rnd() * Math.PI * 2;
    const r = 72 + rnd() * 70;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (Math.abs(x) < 62 && Math.abs(z) < 56) continue;
    const s = 0.9 + rnd() * 0.5;
    trunks.push([x, 0.85 * s, z, 0, 0, 0, 1, s, 1]);
    crowns.push([x, 2.15 * s, z, 0, rnd() * 0.4, 0, s * 1.05, s * 1.15, s * 0.95]);
    crowns2.push([x + 0.35 * s, 2.7 * s, z - 0.2 * s, 0, 0.4, 0, s * 0.75, s * 0.8, s * 0.7]);
  }
  g.add(instanced(G("c:0.16:1.7:8", () => new THREE.CylinderGeometry(0.12, 0.2, 1.7, 8)), M("bark", 0x4a3c30, { roughness: 0.95, envMapIntensity: 0.2 }), trunks, false));
  const leaf = M("leaf", 0x4a5c42, { roughness: 0.88, envMapIntensity: 0.25 });
  g.add(instanced(G("ico:1.25", () => new THREE.IcosahedronGeometry(1.25, 1)), leaf, crowns, false));
  g.add(instanced(G("ico:0.95", () => new THREE.IcosahedronGeometry(0.95, 1)), M("leaf2", 0x3e5340, { roughness: 0.9, envMapIntensity: 0.25 }), crowns2, false));
  return g;
}

function roads() {
  const g = new THREE.Group();
  const pdn = M("pdn", 0x8a8680, {
    map: maps.conc, normalMap: maps.conc.normal, roughnessMap: maps.conc.rough,
    roughness: 0.84, metalness: 0.03, envMapIntensity: 0.28, normalScale: new THREE.Vector2(0.7, 0.7),
  });
  const geo = G("pdn:2.46:0.15:1.96", () => new RoundedBoxGeometry(2.46, 0.15, 1.96, 1, 0.018));
  const a = [], b = [], c = [], d = [];
  for (let z = -58; z < 62; z += 2.08) {
    for (let xi = -1; xi <= 1; xi++) a.push([-22.8 + xi * 2.55, 0.09 + ((Math.abs(z) + xi) % 2) * 0.012, z]);
  }
  for (let x = -58; x < 62; x += 2.08) {
    for (let zi = -1; zi <= 1; zi++) b.push([x, 0.09 + ((Math.abs(x) + zi) % 2) * 0.01, 22.4 + zi * 2.35]);
  }
  for (let z = -36; z < 22; z += 2.08) {
    for (let xi = -1; xi <= 1; xi++) c.push([24.5 + xi * 2.25, 0.09, z]);
  }
  for (let x = -50; x < 54; x += 2.08) {
    for (let zi = -1; zi <= 1; zi++) d.push([x, 0.09, -40.8 + zi * 2.25]);
  }
  g.add(instanced(geo, pdn, a, false));
  g.add(instanced(geo, pdn, b, false));
  g.add(instanced(geo, pdn, c, false));
  g.add(instanced(geo, pdn, d, false));
  const curb = M("curb", 0xa8a298, { roughness: 0.8, map: maps.conc });
  g.add(box(0.28, 0.22, 120, curb, -18.6, 0, 2, false));
  g.add(box(0.28, 0.22, 120, curb, -27, 0, 2, false));
  const gravel = M("shldr", 0x6a655c, { map: maps.gravel, roughness: 0.95, normalMap: maps.gravel.normal });
  g.add(box(2.2, 0.1, 90, gravel, -17.2, 0, 2, false));
  const puddle = M("puddle", 0x1c242c, {
    physical: true, roughness: 0.07, metalness: 0.14, transparent: true, opacity: 0.58,
    envMapIntensity: 1.7, clearcoat: 1, clearcoatRoughness: 0.06,
  });
  [[-22.5, 6.4, 2.6, 1.05], [-21.8, 15.1, 1.7, 0.72], [3.8, 21.6, 2.15, 0.88], [24.2, -0.8, 1.35, 0.52], [-8.2, 10.4, 1.4, 0.6]].forEach(([x, z, sx, sz]) => {
    const m = mesh(G("circ:1:28", () => new THREE.CircleGeometry(1, 28)), puddle, x, 0.12, z, false);
    m.rotation.x = -Math.PI / 2;
    m.scale.set(sx, sz, 1);
    g.add(m);
  });
  return g;
}

function pit() {
  const g = new THREE.Group();
  const dirt = M("pit", 0x4a3724, { map: maps.dirt, roughness: 0.97 });
  g.add(box(26, 0.22, 24, dirt, -3.2, -2.72, 6.2, false));
  const slopes = [
    [26, 3.6, -3.2, -5.2, 0.52, 0],
    [26, 3.6, -3.2, 17.6, -0.52, 0],
    [3.6, 24, -16.4, 6.2, 0, -0.52],
    [3.6, 24, 10, 6.2, 0, 0.52],
  ];
  slopes.forEach(([w, d, x, z, rx, rz]) => {
    const m = box(w, 0.32, d, dirt, x, -1.45, z, false);
    m.rotation.x = rx; m.rotation.z = rz;
    g.add(m);
  });
  const ramp = box(5.6, 0.22, 11, M("ramp", 0x5c4a34, { map: maps.gravel }), -12.4, -1.45, 14.4, false);
  ramp.rotation.x = -0.26;
  g.add(ramp);

  const sheet = M("sheet", 0x6a7380, { metalness: 0.62, roughness: 0.32, map: maps.corr });
  const piles = [];
  for (let i = 0; i < 22; i++) piles.push([10.15, -1.15, -3.4 + i * 1.12, 0, 0, 0]);
  g.add(instanced(G("b:0.1:3.2:0.78", () => new THREE.BoxGeometry(0.1, 3.2, 0.78)), sheet, piles, false));
  g.add(box(0.22, 0.28, 24.5, M("waler", 0x8a9098, { metalness: 0.55 }), 9.85, -0.15, 6.2));
  for (let i = 0; i < 5; i++) {
    g.add(cyl(0.07, 12.5, M("strut", 0x9aa0a6, { metalness: 0.5 }), 3.4, -0.05, -2 + i * 4.2, 0, Math.PI / 2, 8));
  }
  g.add(box(1.6, 0.4, 1.6, M("sump", 0x2a2a2c), -8.5, -2.72, 12.5, false));
  g.add(box(0.7, 0.55, 0.5, M("pump", 0xccaa22), -8.5, -2.32, 12.5));
  g.add(cyl(0.06, 4.2, M("hose", 0x1a1a1a), -6.4, -2.4, 12.5, 0, Math.PI / 2));

  const spoil = mesh(G("ico:2.8", () => new THREE.IcosahedronGeometry(2.8, 1)), M("spoil", 0x6a5030, { map: maps.dirt, roughness: 0.98 }), -1.2, -0.15, 19.2, false);
  spoil.scale.set(1.35, 0.42, 1.1);
  g.add(spoil);
  const agg = mesh(G("ico:1.8", () => new THREE.IcosahedronGeometry(1.8, 1)), M("agg", 0x8a8478, { map: maps.gravel }), 8.5, 0.5, 18.6, false);
  agg.scale.set(1.1, 0.5, 1.2);
  g.add(agg);
  return g;
}

function slab() {
  const g = new THREE.Group();
  g.name = "slab";
  const conc = M("slab", 0x9a958c, {
    map: maps.conc, normalMap: maps.conc.normal, roughnessMap: maps.conc.rough,
    roughness: 0.78, metalness: 0.04, envMapIntensity: 0.4, normalScale: new THREE.Vector2(0.5, 0.5),
  });
  const pours = [];
  for (let ix = -2; ix <= 2; ix++) {
    for (let iz = -1; iz <= 1; iz++) {
      pours.push([ix * 4.05, 0.2, 4.6 + iz * 5.2]);
    }
  }
  g.add(instanced(G("rb:3.9:0.38:5.0", () => new RoundedBoxGeometry(3.9, 0.38, 5.0, 1, 0.03)), conc, pours));
  const form = M("form", 0x8a6238, { map: maps.wood, roughness: 0.86 });
  g.add(box(21.5, 0.62, 0.16, form, 0, 0, -3.75));
  g.add(box(21.5, 0.62, 0.16, form, 0, 0, 12.95));
  g.add(box(0.16, 0.62, 17, form, -10.55, 0, 4.6));
  g.add(box(0.16, 0.62, 17, form, 10.55, 0, 4.6));
  for (let i = -5; i <= 5; i++) g.add(box(0.08, 0.7, 0.08, form, i * 1.9, 0, -3.75));

  const rebar = M("rebar", 0x7a828c, { metalness: 0.72, roughness: 0.32 });
  const longs = [], trans = [];
  for (let i = -9; i <= 9; i++) longs.push([i * 1.05, 0.52, 4.6, Math.PI / 2, 0, 0]);
  for (let j = -7; j <= 7; j++) trans.push([0, 0.58, 4.6 + j * 1.05, 0, 0, Math.PI / 2]);
  g.add(instanced(G("c:0.028:15.4:5", () => new THREE.CylinderGeometry(0.028, 0.028, 15.4, 5)), rebar, longs, false));
  g.add(instanced(G("c:0.028:18.8:5", () => new THREE.CylinderGeometry(0.028, 0.028, 18.8, 5)), rebar, trans, false));

  const cage = rebarCage();
  cage.position.set(-16.5, 0, -14.5);
  g.add(cage);
  const cage2 = rebarCage();
  cage2.position.set(-13.2, 0, -14.5);
  g.add(cage2);
  return g;
}

function rebarCage() {
  const g = new THREE.Group();
  const m = M("cage", 0x8b9198, { metalness: 0.7, roughness: 0.35 });
  for (let x = 0; x < 4; x++) for (let z = 0; z < 4; z++) {
    g.add(cyl(0.035, 2.4, m, x * 0.32, 1.2, z * 0.32, 0, 0, 6));
  }
  for (let y = 0.35; y < 2.3; y += 0.38) {
    g.add(boxC(1.05, 0.03, 1.05, m, 0.48, y, 0.48, false));
  }
  return g;
}

function pvcFrame(g, x, y, z, w, h, pvc, hw) {
  const t = 0.07;
  g.add(boxC(w, t, t, pvc, x, y + h / 2, z));
  g.add(boxC(w, t, t, pvc, x, y - h / 2, z));
  g.add(boxC(t, h, t, pvc, x - w / 2, y, z));
  g.add(boxC(t, h, t, pvc, x + w / 2, y, z));
  g.add(boxC(t * 0.7, h, t, pvc, x, y, z));
  g.add(boxC(w, t * 0.6, t, pvc, x, y, z));
  g.add(boxC(0.04, 0.14, 0.035, hw, x + w / 2 - 0.08, y - 0.12, z + 0.03));
}

function building(floors, ox = 13.2, oz = -9.2, name = "building") {
  const g = new THREE.Group();
  g.name = name;
  const conc = M("bconc", 0x9e9a92, {
    map: maps.conc, normalMap: maps.conc.normal, roughnessMap: maps.conc.rough,
    roughness: 0.72, metalness: 0.05, envMapIntensity: 0.45, normalScale: new THREE.Vector2(0.55, 0.55),
  });
  const brick = M("brick", 0xb56a48, { map: maps.brick, roughness: 0.82, normalMap: maps.brick.normal });
  const wool = M("wool", 0xc4b45a, { map: maps.wool, roughness: 0.92, normalMap: maps.wool.normal });
  const pvc = M("pvc", 0xe4e8ea, { roughness: 0.32, metalness: 0.08, envMapIntensity: 0.7 });
  const hw = M("pvchw", 0x6a7380, { metalness: 0.55, roughness: 0.28 });

  g.add(rboxC(18.6, 0.95, 14, conc, ox, 0.475, oz));

  const cols = [];
  for (let ix = -2; ix <= 2; ix++) {
    for (let iz = -1; iz <= 1; iz++) cols.push([ox + ix * 3.7, oz + iz * 5.4]);
  }

  for (let f = 0; f < floors; f++) {
    const y0 = 0.95 + f * 3.65;
    cols.forEach(([cx, cz]) => {
      g.add(rboxC(0.56, 3.35, 0.56, conc, cx, y0 + 1.675, cz));
      g.add(rboxC(0.82, 0.16, 0.82, conc, cx, y0 + 3.26, cz));
      if (f === floors - 1) {
        for (let k = 0; k < 8; k++) {
          const a = (k / 8) * Math.PI * 2;
          g.add(cyl(0.016, 1.35, M("reb2", 0x9aa2aa, { metalness: 0.82 }), cx + Math.cos(a) * 0.16, y0 + 4.0, cz + Math.sin(a) * 0.16, 0, 0, 5));
        }
      }
    });
    const ties = [];
    cols.forEach(([cx, cz]) => {
      for (let ty = 0.4; ty < 3.15; ty += 0.5) {
        ties.push([cx + 0.29, y0 + ty, cz, 0, 0, Math.PI / 2]);
        ties.push([cx, y0 + ty, cz + 0.29, Math.PI / 2, 0, 0]);
      }
    });
    g.add(instanced(G("c:0.016:0.05:6", () => new THREE.CylinderGeometry(0.016, 0.016, 0.05, 6)), M("tie", 0x6a6e72, { metalness: 0.45, roughness: 0.5 }), ties, false));
    for (let iz = -1; iz <= 1; iz++) g.add(rboxC(15.2, 0.48, 0.4, conc, ox, y0 + 3.32, oz + iz * 5.4));
    for (let ix = -2; ix <= 2; ix++) g.add(rboxC(0.4, 0.48, 11.2, conc, ox + ix * 3.7, y0 + 3.32, oz));
    for (let ix = -2; ix <= 1; ix++) {
      for (let iz = -1; iz <= 0; iz++) {
        if (f >= floors - 1 && ((ix + iz + f) & 1)) continue;
        g.add(rboxC(3.4, 0.15, 5.02, conc, ox + ix * 3.7 + 1.85, y0 + 3.56, oz + iz * 5.4 + 2.7));
      }
    }

    for (let ix = -2; ix <= 1; ix++) {
      const cx = ox + ix * 3.7 + 1.85;
      const z = oz - 6.85;
      g.add(box(0.55, 2.55, 0.28, brick, cx - 1.55, y0, z));
      g.add(box(0.55, 2.55, 0.28, brick, cx + 1.55, y0, z));
      g.add(box(2.55, 0.55, 0.28, brick, cx, y0, z));
      g.add(box(2.55, 0.42, 0.28, brick, cx, y0 + 2.13, z));
      pvcFrame(g, cx, y0 + 1.35, z + 0.12, 1.55, 1.55, pvc, hw);
      if ((ix + f) % 2 === 0) g.add(box(1.48, 1.42, 0.1, wool, cx, y0 + 0.58, z + 0.22));
    }
    for (let iz = -1; iz <= 0; iz++) {
      const cz = oz + iz * 5.4 + 2.7;
      g.add(box(0.28, 2.4, 2.2, brick, ox - 9.15, y0, cz));
      if ((iz + f) % 2) g.add(box(0.1, 1.6, 1.7, wool, ox - 8.95, y0 + 0.4, cz));
    }

    const rail = M("rail", 0xb89a48, { metalness: 0.45, roughness: 0.42, envMapIntensity: 0.9 });
    [[0, 6.55]].forEach(([dx, dz]) => {
      g.add(box(17.8, 0.05, 0.05, rail, ox + dx, y0 + 4.45, oz + dz, false));
      g.add(box(17.8, 0.05, 0.05, rail, ox + dx, y0 + 3.85, oz + dz, false));
      for (let i = -4; i <= 4; i++) g.add(cyl(0.03, 1.15, rail, ox + i * 1.9, y0 + 3.95, oz + dz, 0, 0, 6));
    });
  }

  const yR = 0.95 + floors * 3.65;
  g.add(rboxC(18.0, 0.16, 13.2, M("roofmem", 0x3a3a3c, { roughness: 0.78, map: maps.asph, normalMap: maps.asph.normal }), ox, yR + 0.08, oz));
  g.add(rboxC(18.2, 0.82, 0.22, conc, ox, yR + 0.5, oz - 6.55));
  g.add(rboxC(18.2, 0.82, 0.22, conc, ox, yR + 0.5, oz + 6.55));
  g.add(rboxC(0.22, 0.82, 13.0, conc, ox - 9.0, yR + 0.5, oz));
  g.add(rboxC(0.22, 0.82, 13.0, conc, ox + 9.0, yR + 0.5, oz));
  [[-4.2, -2.4], [3.4, 1.8], [0.2, -3.2]].forEach(([dx, dz], i) => {
    g.add(lathe(
      [[0.22, 0], [0.38, 0.04], [0.36, 0.85], [0.28, 1.05], [0.08, 1.12]],
      M("vent" + i, 0xc8cdd2, { metalness: 0.25, roughness: 0.45 }),
      ox + dx, yR + 0.16, oz + dz, 16
    ));
  });

  const stair = M("stair", 0x9a9590, { roughness: 0.7, map: maps.conc });
  for (let s = 0; s < floors * 12; s++) {
    g.add(box(1.7, 0.13, 0.42, stair, ox + 7.55, 0.2 + s * 0.3, oz + 1.35 - (s % 2) * 0.18, false));
  }
  g.add(box(0.08, floors * 3.7, 0.08, M("steel", 0x8a9098, { metalness: 0.62, roughness: 0.34 }), ox + 6.75, 0.95, oz + 1.9, false));
  g.add(box(0.08, floors * 3.7, 0.08, M("steel", 0x8a9098, { metalness: 0.62, roughness: 0.34 }), ox + 8.35, 0.95, oz + 1.9, false));

  const net = mesh(G("pl:16:10", () => new THREE.PlaneGeometry(16, 10)), M("bnet", 0x228855, {
    map: maps.net, transparent: true, opacity: 0.78, side: THREE.DoubleSide, roughness: 0.7, alphaTest: 0.08, depthWrite: false,
  }), ox, 6.2, oz + 7.05, false);
  g.add(net);
  return g;
}

function scaffold(ox = 3.6, oz = -16.2, bays = 8) {
  const g = new THREE.Group();
  const tube = M("scaf", 0xc9a227, { metalness: 0.55, roughness: 0.38, map: maps.paint, envMapIntensity: 0.85 });
  const plank = M("plank", 0xc4a574, { map: maps.wood, roughness: 0.88, normalMap: maps.wood.normal });
  const lock = M("scaflock", 0x3a3a3c, { metalness: 0.55, roughness: 0.35 });
  for (let i = 0; i < bays; i++) {
    const x = ox + i * 1.75;
    g.add(cyl(0.058, 14.2, tube, x, 7.1, oz, 0, 0, 12));
    g.add(cyl(0.058, 14.2, tube, x, 7.1, oz + 1.45, 0, 0, 12));
    g.add(rboxC(0.22, 0.1, 0.22, M("basep", 0x2a2a2c, { metalness: 0.4 }), x, 0.05, oz, false));
    g.add(rboxC(0.22, 0.1, 0.22, M("basep", 0x2a2a2c, { metalness: 0.4 }), x, 0.05, oz + 1.45, false));
    for (let y = 1.7; y < 14; y += 1.7) {
      g.add(cyl(0.045, 1.75, tube, x, y, oz, 0, Math.PI / 2, 10));
      g.add(cyl(0.045, 1.45, tube, x, y, oz + 0.72, Math.PI / 2, 0, 10));
      g.add(box(1.62, 0.045, 0.22, plank, x, y + 0.06, oz + 0.48, false));
      g.add(box(1.62, 0.045, 0.22, plank, x, y + 0.06, oz + 0.96, false));
      const diag = cyl(0.032, 2.15, tube, x, y + 0.85, oz, 0, 0.72, 8);
      g.add(diag);
      g.add(mesh(G("tor:0.07:0.02", () => new THREE.TorusGeometry(0.07, 0.02, 6, 12)), lock, x, y, oz));
      g.add(mesh(G("tor:0.07:0.02", () => new THREE.TorusGeometry(0.07, 0.02, 6, 12)), lock, x, y, oz + 1.45));
    }
  }
  const ladder = M("lad", 0xb8b8b8, { metalness: 0.5 });
  g.add(cyl(0.03, 13.4, ladder, ox - 0.15, 6.7, oz + 0.35, 0, 0, 6));
  g.add(cyl(0.03, 13.4, ladder, ox - 0.15, 6.7, oz + 1.1, 0, 0, 6));
  for (let y = 0.4; y < 13.4; y += 0.32) g.add(box(0.03, 0.03, 0.75, ladder, ox - 0.15, y, oz + 0.72, false));

  const netW = Math.max(14, bays * 1.75);
  const net = mesh(G(`pl:${netW}:13`, () => new THREE.PlaneGeometry(netW, 13)), M("snet", 0x1a8a4a, {
    map: maps.net, transparent: true, opacity: 0.82, side: THREE.DoubleSide, roughness: 0.7, metalness: 0.05,
    alphaTest: 0.08, depthWrite: false,
  }), ox + netW / 2 - 0.9, 6.8, oz - 0.12, false);
  g.add(net);
  return g;
}

function fence() {
  const g = new THREE.Group();
  const post = M("post", 0x3a3a3c, { metalness: 0.35 });
  const sheet = M("hoard", 0x3d4a38, { roughness: 0.72, map: maps.corr, normalMap: maps.corr.normal });
  const stripe = M("hstr", 0xd4a017);
  const ring = [[-50, -46, 56, -46], [56, -46, 56, 48], [56, 48, -50, 48], [-50, 48, -50, -46]];
  ring.forEach(([x1, z1, x2, z2]) => {
    const dx = x2 - x1, dz = z2 - z1, len = Math.hypot(dx, dz), n = Math.floor(len / 2.35);
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const x = x1 + dx * t, z = z1 + dz * t;
      g.add(box(0.14, 2.7, 0.14, post, x, 0, z, false));
      if (i < n) {
        const mx = x + dx / n / 2, mz = z + dz / n / 2;
        const yaw = Math.atan2(dx, dz);
        const pan = box(2.2, 2.25, 0.05, sheet, mx, 0.22, mz, false);
        pan.rotation.y = yaw;
        g.add(pan);
        if (i % 2 === 0) {
          const s = box(2.2, 0.2, 0.06, stripe, mx, 2.22, mz, false);
          s.rotation.y = yaw;
          g.add(s);
        }
      }
    }
  });
  const ban = box(8.4, 1.35, 0.06, new THREE.MeshStandardMaterial({ map: maps.banner, roughness: 0.55 }), 0, 0.85, -46.08, false);
  g.add(ban);
  return g;
}

function gate() {
  const g = new THREE.Group();
  g.position.set(-50, 0, 12);
  const steel = M("gp", 0x1e1e20, { metalness: 0.4 });
  g.add(box(0.28, 3.7, 0.28, steel, 0, 0, -3.6));
  g.add(box(0.28, 3.7, 0.28, steel, 0, 0, 3.6));
  g.add(box(0.18, 0.18, 7.3, M("gbar", 0xc9a227, { metalness: 0.5 }), 0, 3.55, 0));
  g.add(box(4.2, 1.05, 0.07, new THREE.MeshStandardMaterial({ map: maps.ppe, roughness: 0.5 }), 0.12, 3.85, 0));
  g.add(box(1.55, 2.25, 0.07, M("gateL", 0x4a4a4c), 0, 0, -1.7));
  g.add(box(1.55, 2.25, 0.07, M("gateR", 0x4a4a4c), 0, 0, 1.7));
  g.add(box(2.6, 0.12, 6.4, M("wash", 0x3a3a3c), 1.4, 0, 0, false));
  return g;
}

function corrugatedBox(w, h, d, color, rust = 0.15) {
  const g = new THREE.Group();
  const body = M("cb" + color, color, { map: maps.corr, roughness: 0.52, metalness: 0.22 });
  g.add(boxC(w, h, d, body, 0, h / 2, 0));
  const rib = M("rib" + color, color, { roughness: 0.48, metalness: 0.25 });
  for (let i = 0; i < Math.floor(w / 0.28); i++) {
    g.add(boxC(0.06, h * 0.96, d + 0.04, rib, -w / 2 + 0.2 + i * 0.28, h / 2, 0, false));
  }
  [[-w / 2, 0, -d / 2], [w / 2, 0, -d / 2], [-w / 2, 0, d / 2], [w / 2, 0, d / 2]].forEach(([x, , z]) => {
    g.add(boxC(0.16, 0.16, 0.16, M("cast", 0x222), x, 0.08, z, false));
    g.add(boxC(0.16, 0.16, 0.16, M("cast", 0x222), x, h - 0.08, z, false));
  });
  g.add(boxC(0.06, h * 0.85, d * 0.9, M("cdoor", 0x1a1a1a), w / 2 + 0.02, h / 2, 0, false));
  if (rust) g.add(boxC(w * 0.3, 0.08, d + 0.02, M("crust", 0x8a4a22, { map: maps.rust }), 0, h + 0.02, 0, false));
  return g;
}

function container(x, z, y, color, rot = 0) {
  const g = corrugatedBox(6.06, 2.59, 2.44, color);
  g.position.set(x, y, z);
  g.rotation.y = rot;
  return g;
}

function yard() {
  const g = new THREE.Group();
  g.add(container(-27, -11, 0, 0xc45c26));
  g.add(container(-27, -13.55, 0, 0x2e6b8a));
  g.add(container(-27, -11, 2.59, 0xd4a017));
  g.add(container(-27, 19.5, 0, 0x1f6f4a, 0.18));
  g.add(container(26.5, -18, 0, 0x8b1e3f, 1.2));
  return g;
}

function welfare() {
  const g = new THREE.Group();
  const cabin = (x, z, w, label) => {
    const c = new THREE.Group();
    c.position.set(x, 0, z);
    c.add(box(w, 2.7, 3.3, M("cab" + x, 0xd6d0c2, { roughness: 0.78 }), 0, 0.15, 0));
    c.add(box(w + 0.2, 0.12, 3.5, M("croof", 0x4a5560, { metalness: 0.3 }), 0, 2.85, 0));
    c.add(box(1.15, 1.15, 0.06, M("cwin", 0x2a4050, { metalness: 0.55, roughness: 0.12 }), 0.4, 1.25, 1.68));
    c.add(box(0.85, 1.55, 0.07, M("cdoor", 0x6a4a28), -w / 2 + 0.7, 0.15, 1.68));
    for (let i = 0; i < 5; i++) c.add(box(0.85, 0.14, 0.32, M("cst", 0x888), -w / 2 - 0.5, i * 0.16, 1.3, false));
    c.add(box(0.7, 0.32, 0.7, M("ac", 0xc8c8c8, { metalness: 0.3 }), w / 2 - 0.6, 2.85, 0.4));
    if (label) c.add(box(1.8, 0.4, 0.04, new THREE.MeshStandardMaterial({ map: maps.ppe, roughness: 0.5 }), 0, 2.4, 1.68));
    return c;
  };
  g.add(cabin(25.2, 17.4, 7.4, true));
  g.add(cabin(25.2, 13.4, 6.2, false));
  g.add(cabin(25.2, 21.5, 5.4, false));
  for (let i = 0; i < 4; i++) {
    g.add(box(1.1, 2.2, 1.1, M("wc" + i, 0x2a8a4a), -30.5, 0, 14.2 + i * 1.25));
    g.add(box(1.12, 0.08, 1.12, M("wcr", 0x1a5a32), -30.5, 2.2, 14.2 + i * 1.25, false));
  }
  return g;
}

function plant() {
  const g = new THREE.Group();
  g.add(lathe([[1.32, 0.15], [1.38, 0.35], [1.34, 6.55], [0.18, 7.15]], M("silo", 0xc8cdd2, { metalness: 0.35, roughness: 0.4 }), 29.5, 0, -8, 24));
  g.add(lathe([[0.05, 0], [1.42, 0.04], [0.12, 1.15]], M("silotop", 0xb0b6bc, { metalness: 0.35 }), 29.5, 7.05, -8, 16));
  g.add(cyl(0.12, 2.4, M("siloleg", 0x666), 28.4, 1.2, -8));
  g.add(cyl(0.12, 2.4, M("siloleg", 0x666), 30.6, 1.2, -8));
  g.add(extrude([[-1.15, 0.02], [-1.18, 1.95], [1.12, 2.08], [1.15, 0.02]], 2.35, M("hopper", 0x4a90c3, { metalness: 0.25 }), 29.5, 0, -4.6, 0.03));
  g.add(lathe([[0.08, 0], [1.05, 0.05], [0.12, 1.12]], M("hop2", 0x3a7aaa), 29.5, 2.05, -4.6, 14));

  g.add(extrude([[-0.95, 0.02], [-0.98, 1.28], [0.72, 1.42], [0.95, 0.08]], 1.12, M("gen", 0x2d5a2d, { map: maps.paint, roughness: 0.62 }), 28.2, 0, -1.2, 0.03));
  g.add(lathe([[0.12, 0], [0.22, 0.04], [0.2, 0.52], [0.12, 0.58]], M("gentank", 0x222), 27.15, 0.35, -1.2, 12));
  g.add(cyl(0.08, 1.4, M("exh", 0x333), 28.7, 2.1, -1.2));

  g.add(extrude([[-0.7, 0.02], [-0.72, 1.05], [0.55, 1.12], [0.7, 0.08]], 0.85, M("comp", 0xccaa22, { map: maps.paint }), 28.2, 0, 1.4, 0.025));
  g.add(cyl(0.35, 0.9, M("air", 0xc8c8c8, { metalness: 0.4 }), 27.4, 0.55, 1.4, 0, Math.PI / 2));

  g.add(mesh(G("cylt:1.55:2.15:18", () => new THREE.CylinderGeometry(1.55, 1.62, 2.15, 18)), M("tank", 0x3a88c4, { metalness: 0.28, roughness: 0.4 }), 22.8, 1.08, -8));
  g.add(cyl(0.12, 0.55, M("tankcap", 0x222), 22.8, 2.35, -8));
  return g;
}

function stock() {
  const g = new THREE.Group();
  const wood = M("tim", 0x8b5a2b, { map: maps.wood, roughness: 0.88 });
  for (let i = 0; i < 10; i++) g.add(box(3.6, 0.1, 0.16, wood, 21.5, 0.04 + i * 0.11, -16.4 + (i % 2) * 0.08, false));
  g.add(box(1.2, 0.12, 3.6, wood, 21.5, 0, -16.4, false));

  const pipe = M("pipe", 0x9aa3ad, { metalness: 0.62, roughness: 0.28 });
  for (let i = 0; i < 12; i++) {
    g.add(cyl(0.075, 5.2, pipe, 19.4 + (i % 4) * 0.18, 0.08, -12.4 + Math.floor(i / 4) * 0.18, 0, Math.PI / 2, 8));
  }
  g.add(box(1.4, 0.08, 1.1, M("piperack", 0x555), 19.7, 0, -12.4, false));

  const bag = M("bag", 0xcfc6a8, { roughness: 0.9 });
  for (let i = 0; i < 16; i++) {
    g.add(box(0.42, 0.2, 0.65, bag, 16.6 + (i % 4) * 0.46, Math.floor(i / 4) * 0.2, -18.2, false));
  }

  const meshM = M("wmesh", 0x8a9098, { metalness: 0.55, roughness: 0.4 });
  for (let i = 0; i < 6; i++) {
    const p = box(2.4, 1.8, 0.04, meshM, 17.8, 0.05 + i * 0.08, -20.4 + i * 0.05, false);
    p.rotation.x = -0.08;
    g.add(p);
  }

  g.add(extrude([[-1.15, 0.02], [-1.22, 1.48], [1.18, 1.52], [1.12, 0.02]], 1.68, M("skip", 0x1a6b3a, { roughness: 0.7, map: maps.paint }), 20.6, 0, 19.4, 0.03));
  g.add(extrude([[-1.22, 1.48], [-1.18, 1.58], [1.2, 1.6], [1.16, 1.48]], 1.78, M("skiplid", 0x14552e), 20.6, 0, 19.4, 0.012));

  const pal = M("pal", 0xb8955a, { map: maps.wood });
  for (let i = 0; i < 6; i++) {
    g.add(box(1.2, 0.14, 1.0, pal, -18.5 + (i % 3) * 1.35, Math.floor(i / 3) * 0.14, -20, false));
    g.add(box(1.05, 0.85, 0.9, M("brickst", 0xb45a3a, { map: maps.brick }), -18.5 + (i % 3) * 1.35, 0.14 + Math.floor(i / 3) * 0.14, -20));
  }

  g.add(box(1.35, 1.05, 0.85, M("ibc", 0xffffff, { transparent: true, opacity: 0.35, roughness: 0.2 }), 18.4, 0.35, 18.2));
  g.add(box(1.4, 0.18, 0.9, pal, 18.4, 0, 18.2, false));

  const felt = M("felt", 0x2a2a2c, { roughness: 0.88 });
  for (let i = 0; i < 6; i++) {
    g.add(cyl(0.18, 1.05, felt, 16.2 + (i % 3) * 0.42, 0.18, -14.6 + Math.floor(i / 3) * 0.4, 0, Math.PI / 2, 12));
  }
  const film = mesh(G("pl:2.4:1.6", () => new THREE.PlaneGeometry(2.4, 1.6)), M("film", 0x9ab0c0, {
    physical: true, transparent: true, opacity: 0.28, roughness: 0.12, metalness: 0.05, side: THREE.DoubleSide,
  }), 15.2, 0.12, 16.4, false);
  film.rotation.x = -1.15;
  film.rotation.z = 0.35;
  g.add(film);
  for (let i = 0; i < 9; i++) {
    const br = mesh(G("ico:0.12", () => new THREE.IcosahedronGeometry(0.12, 0)), M("brkbit", 0xb45a3a, { map: maps.brick }), 19.2 + (i % 3) * 0.28, 0.08, 17.6 + Math.floor(i / 3) * 0.22, false);
    br.rotation.set(i * 0.4, i * 0.7, 0.2);
    g.add(br);
  }
  g.add(box(1.35, 0.06, 0.22, M("scrap", 0x8b5a2b, { map: maps.wood }), 14.6, 0.02, 15.8, false));
  g.add(box(0.9, 0.05, 0.16, M("scrap2", 0x8b5a2b, { map: maps.wood }), 15.1, 0.04, 16.1, false));

  const coneM = M("cone", 0xe85d04);
  for (let i = 0; i < 14; i++) {
    const x = -22.8 + (i % 2) * 0.72, z = -12 + i * 1.15;
    g.add(cone(0.15, 0.52, coneM, x, 0.32, z, 10));
    g.add(boxC(0.16, 0.05, 0.16, M("cwht", 0xeee), x, 0.46, z, false));
  }

  const bar = M("barrier", 0xc9a227, { map: maps.stripe, roughness: 0.5 });
  for (let i = 0; i < 6; i++) {
    const z = -6 + i * 2.2;
    g.add(box(0.08, 1.05, 0.08, M("bleg", 0x222), -19.2, 0, z, false));
    g.add(box(0.08, 1.05, 0.08, M("bleg", 0x222), -17.4, 0, z, false));
    g.add(box(1.9, 0.18, 0.06, bar, -18.3, 0.85, z, false));
  }
  return g;
}

function towerCrane(x = 3.2, z = -20.4) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  const yel = M("cr", 0xc4a44a, { metalness: 0.42, roughness: 0.4, envMapIntensity: 0.95, map: maps.paint, physical: true, clearcoat: 0.15, clearcoatRoughness: 0.45 });
  g.add(box(5.2, 0.85, 5.2, M("cf", 0x6a6e74, { metalness: 0.3 }), 0, 0, 0));
  g.add(box(4.6, 0.55, 4.6, M("cf2", 0x4a4e54), 0, 0.85, 0));
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2 + 0.4;
    g.add(box(1.1, 0.35, 2.8, M("cleg", 0x555), Math.cos(a) * 2.4, 0, Math.sin(a) * 2.4));
  }
  g.add(latticeMast(30, 1.85, yel));
  const cap = boxC(2.2, 0.35, 2.2, yel, 0, 30.2, 0);
  g.add(cap);

  const top = new THREE.Group();
  top.userData.live = true;
  top.position.y = 30.2;
  top.add(extrude(
    [[-0.95, 0.15], [-1.0, 1.55], [0.55, 2.05], [1.15, 1.55], [1.18, 0.15]],
    2.05, M("cab", 0x1c2732, { roughness: 0.32, map: maps.paint }), 1.55, 0.35, 0, 0.03
  ));
  top.add(boxC(1.55, 0.95, 0.06, M("cgl", 0x7ec8e3, { physical: true, transparent: true, opacity: 0.38, metalness: 0.2, roughness: 0.08, envMapIntensity: 1.4 }), 1.55, 1.55, 1.08));
  top.add(boxC(0.06, 0.95, 1.55, M("cgl2", 0x7ec8e3, { physical: true, transparent: true, opacity: 0.38, metalness: 0.2, roughness: 0.08, envMapIntensity: 1.4 }), 2.68, 1.55, 0));
  top.add(rboxC(2.6, 0.22, 2.3, yel, 0, 2.45, 0));
  [-12.4, -14.1, -15.8].forEach((cx, n) => {
    top.add(rboxC(1.55, 1.55, 1.7, M("cw" + n, n % 2 ? 0x2a2a2c : 0x3a3a3c, { metalness: 0.25, roughness: 0.55 }), cx, 0.55, 0));
  });
  const jib = latticeJib(34, yel);
  jib.position.set(17.2, 1.55, 0);
  top.add(jib);
  const cj = latticeJib(13, yel);
  cj.position.set(-7.4, 1.55, 0);
  top.add(cj);
  top.add(boxC(0.15, 4.8, 0.15, yel, 0, 4.9, 0));
  top.add(rod(0, 7.2, 0, 16, 2.3, 0, 0.03, M("stay", 0x222)));
  top.add(rod(0, 7.2, 0, -12, 2.3, 0, 0.03, M("stay2", 0x222)));

  const trol = new THREE.Group();
  trol.position.set(18.5, 1.15, 0);
  trol.add(boxC(1.1, 0.35, 0.85, M("trol", 0x333), 0, 0, 0));
  trol.add(cyl(0.08, 0.9, M("tw", 0x111), 0.35, 0.2, 0, Math.PI / 2, 0, 8));
  trol.add(cyl(0.08, 0.9, M("tw", 0x111), -0.35, 0.2, 0, Math.PI / 2, 0, 8));
  top.add(trol);

  const hkGrp = new THREE.Group();
  hkGrp.position.set(18.5, -9.2, 0);
  hkGrp.add(rboxC(0.62, 0.55, 0.22, M("block", 0x222, { metalness: 0.4, roughness: 0.4 }), 0, 0.4, 0));
  hkGrp.add(cyl(0.13, 0.38, M("pulley", 0x555, { metalness: 0.55, roughness: 0.32 }), 0.16, 0.42, 0, Math.PI / 2, 0, 12));
  hkGrp.add(cyl(0.13, 0.38, M("pulley", 0x555, { metalness: 0.55, roughness: 0.32 }), -0.16, 0.42, 0, Math.PI / 2, 0, 12));
  hkGrp.add(cyl(0.1, 0.28, M("pulley2", 0x444, { metalness: 0.5 }), 0, 0.18, 0, Math.PI / 2, 0, 10));
  const hk = mesh(G("tor:0.22:0.05", () => new THREE.TorusGeometry(0.22, 0.05, 8, 16)), M("hkr", 0x111, { metalness: 0.5 }), 0, -0.18, 0);
  hk.rotation.x = Math.PI / 2;
  hkGrp.add(hk);
  top.add(hkGrp);

  const cab = new THREE.Mesh(G("c:0.022:10:6", () => new THREE.CylinderGeometry(0.022, 0.022, 10, 6)), M("cbl", 0x2a2a2c, { metalness: 0.65, roughness: 0.35 }));
  cab.position.set(18.5, -4.2, 0);
  top.add(cab);
  g.add(top);
  cranes.push({ top, trolley: trol, hook: hkGrp, cable: cab });
  if (!craneTop) {
    craneTop = top;
    trolley = trol;
    hook = hkGrp;
    cable = cab;
  }
  return g;
}

function latticeMast(h, w, mat) {
  const g = new THREE.Group();
  const half = w / 2;
  [[-half, -half], [half, -half], [half, half], [-half, half]].forEach(([x, z]) => {
    g.add(cyl(0.055, h, mat, x, h / 2, z, 0, 0, 8));
  });
  for (let y = 0; y < h; y += 1.28) {
    g.add(cyl(0.04, w, mat, 0, y, -half, 0, Math.PI / 2, 8));
    g.add(cyl(0.04, w, mat, 0, y, half, 0, Math.PI / 2, 8));
    g.add(cyl(0.04, w, mat, -half, y, 0, Math.PI / 2, 0, 8));
    g.add(cyl(0.04, w, mat, half, y, 0, Math.PI / 2, 0, 8));
    const dlen = Math.hypot(w, 1.28);
    [[0, -half, 0.72], [0, half, -0.72], [-half, 0, 0.72], [half, 0, -0.72]].forEach(([x, z, rot], n) => {
      const b = cyl(0.032, dlen, mat, x, y + 0.64, z, 0, 0, 8);
      if (n < 2) b.rotation.z = rot;
      else b.rotation.x = rot;
      g.add(b);
    });
  }
  return g;
}

function latticeJib(len, mat) {
  const g = new THREE.Group();
  const t = 0.07;
  g.add(box(len, t, t, mat, 0, 0.62, -0.48, false));
  g.add(box(len, t, t, mat, 0, 0.62, 0.48, false));
  g.add(box(len, t, t, mat, 0, 0, 0, false));
  for (let x = -len / 2; x < len / 2; x += 1.45) {
    g.add(box(t, 0.62, t, mat, x, 0, -0.48, false));
    g.add(box(t, 0.62, t, mat, x, 0, 0.48, false));
    g.add(box(t, t, 0.96, mat, x, 0.62, 0, false));
    const d = box(1.6, t, t, mat, x + 0.7, 0.31, -0.24, false);
    d.rotation.z = 0.4;
    g.add(d);
  }
  return g;
}

function lightTowers() {
  const g = new THREE.Group();
  [[-42, 36], [42, 36], [46, -38], [-36, -38], [8, 40], [-8, -42]].forEach(([x, z]) => {
    g.add(box(1.35, 0.35, 1.35, M("ltbase", 0x333), x, 0, z));
    g.add(cyl(0.07, 9.4, M("pole", 0x4a4a4c, { metalness: 0.4 }), x, 4.7, z, 0, 0, 8));
    for (let i = -1; i <= 1; i++) {
      g.add(box(0.55, 0.18, 0.35, M("lamp", 0xf2f0e6, { emissive: 0xffe6b0, emissiveIntensity: 0.22 }), x + i * 0.55, 9.35, z));
    }
  });
  return g;
}

function people() {
  workers = [];
  const g = new THREE.Group();
  const spots = [
    [11, 0, -6.5, 0.4], [15, 0.95, -10, -0.2], [4.5, 1.7, -15.5, 1.2],
    [-6, -2.5, 8.5, 0.7], [0.5, 0.46, 6, 2], [24, 0, 16.5, 3],
    [-24, 0, -8, 1.5], [8, 0, 12, -0.4], [14, 4.6, -9, 0],
    [-10, 0, 20, 0.2], [20, 0, -2.8, 1.1], [-20, 0, 6, 2.4],
    [32, 0.95, -26, 0.6], [28, 4.6, -28, 1.1], [-26, 0, -30, 2.1],
    [40, 0, -12, -0.3], [-42, 0, 10, 0.8], [16, 8.2, -9, 0.2],
  ];
  spots.forEach(([x, y, z, yaw], i) => {
    const p = worker(i);
    p.position.set(x, y, z);
    p.rotation.y = yaw;
    p.userData.baseY = y;
    workers.push(p);
    g.add(p);
  });
  return g;
}

function worker(i) {
  const g = new THREE.Group();
  const vis = M("vis" + (i % 3), i % 2 ? 0xc4b056 : 0xb85a38, { roughness: 0.62, envMapIntensity: 0.4, map: maps.paint });
  const navy = M("navy", 0x2c3440, { roughness: 0.88, envMapIntensity: 0.2 });
  const skin = M("skin", 0xb59878, { roughness: 0.72 });
  const boot = M("boot", 0x1a1a1a, { roughness: 0.92 });
  const helmC = i % 3 === 0 ? 0xc4b056 : 0xb85a38;
  const helm = M("helm" + (i % 2), helmC, { roughness: 0.42, map: maps.paint });
  const stripe = M("vstr", 0xeee8c8, { roughness: 0.45 });
  g.add(rboxC(0.15, 0.1, 0.28, boot, -0.09, 0.055, 0.04));
  g.add(rboxC(0.15, 0.1, 0.28, boot, 0.09, 0.055, 0.04));
  g.add(mesh(G("capleg", () => new THREE.CapsuleGeometry(0.085, 0.34, 4, 8)), navy, -0.09, 0.4, 0));
  g.add(mesh(G("capleg", () => new THREE.CapsuleGeometry(0.085, 0.34, 4, 8)), navy, 0.09, 0.4, 0));
  g.add(rboxC(0.34, 0.46, 0.22, vis, 0, 1.02, 0));
  g.add(boxC(0.36, 0.035, 0.04, stripe, 0, 0.9, 0.12, false));
  g.add(boxC(0.36, 0.035, 0.04, stripe, 0, 1.12, 0.12, false));
  g.add(mesh(G("caparm", () => new THREE.CapsuleGeometry(0.05, 0.26, 3, 6)), vis, -0.22, 0.92, 0.02));
  g.add(mesh(G("caparm", () => new THREE.CapsuleGeometry(0.05, 0.26, 3, 6)), vis, 0.22, 0.92, 0.02));
  g.add(mesh(G("sphhead", () => new THREE.SphereGeometry(0.1, 14, 12)), skin, 0, 1.28, 0));
  g.add(mesh(G("helmcap", () => new THREE.SphereGeometry(0.118, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.58)), helm, 0, 1.34, 0));
  g.add(cyl(0.13, 0.022, helm, 0, 1.285, 0.02, 0, 0, 12));
  g.add(boxC(0.035, 0.07, 0.08, helm, 0, 1.44, -0.02, false));
  return g;
}

function signs() {
  const g = new THREE.Group();
  const pole = (x, z, map) => {
    g.add(cyl(0.04, 2.4, M("spole", 0x555), x, 1.2, z, 0, 0, 6));
    g.add(mesh(G("b:0.9:0.9:0.04", () => new THREE.BoxGeometry(0.9, 0.9, 0.04)), new THREE.MeshStandardMaterial({ map, roughness: 0.45 }), x, 2.5, z));
  };
  pole(-31.5, 6.5, maps.speed);
  pole(-31.5, 12, maps.ppe);
  pole(32, -10, maps.ppe);
  pole(-33.2, -18, maps.warn);
  pole(20, -27.2, maps.warn);
  return g;
}

function dust() {
  const n = 280;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = (hash(i, 1) - 0.5) * 48;
    pos[i * 3 + 1] = hash(i, 2) * 9;
    pos[i * 3 + 2] = (hash(i, 3) - 0.5) * 42;
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  dustPts = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x4a4a4a, size: 0.05, transparent: true, opacity: 0.05, depthWrite: false, sizeAttenuation: true,
  }));
  return dustPts;
}

function cables() {
  const g = new THREE.Group();
  const mat = M("cabline", 0x1a1a1a, { roughness: 0.8 });
  const paths = [
    [[-29, 8.8, 23.5], [-10, 6, 10], [3.2, 12, -20.4]],
    [[29, 8.8, 23.5], [20, 5, 8], [13, 8, -9]],
    [[-21, 8.8, -23], [3.2, 10, -20]],
  ];
  paths.forEach((pts) => {
    const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p)));
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.025, 5, false), mat);
    tube.castShadow = false;
    g.add(tube);
  });
  return g;
}

/* ---------- vehicles ---------- */

const VEH_LABEL = {
  excavator: "Экскаватор", dump_truck: "Самосвал", concrete_mixer: "Бетоносмеситель",
  mobile_crane: "Автокран", roller: "Каток", bulldozer: "Бульдозер",
  manipulator_crane: "Кран-манипулятор", truck: "Бортовой",
};

function vehicle(item) {
  const makers = {
    excavator, dump_truck: dumpTruck, concrete_mixer: mixer,
    mobile_crane: mobileCrane, roller, bulldozer, manipulator_crane: manipulator, truck,
  };
  const fn = makers[item.code] || truck;
  if (!VEH_CACHE[item.code]) {
    const proto = fn();
    proto.userData.live = true;
    proto.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    applyNightClay(proto, true);
    VEH_CACHE[item.code] = proto;
  }
  const g = VEH_CACHE[item.code].clone(true);
  g.traverse((o) => { o.userData = { ...o.userData, live: true }; });
  g.userData.live = true;
  const [x, y, z] = item.position || [0, 0, 0];
  g.position.set(x, y, z);
  g.rotation.y = item.yaw || 0;
  g.traverse((o) => { if (o.userData.spin) mixerDrums.push(o); });
  const id = item.id || `${(item.code || "unit").slice(0, 3).toUpperCase()}-MSK`;
  markPick(g, id, {
    title: VEH_LABEL[item.code] || item.code,
    kind: item.code,
    status: item.status || "active",
    power: item.power ?? (62 + (id.charCodeAt(4) || 10) % 28),
    session: item.session || "5HR 40MIN",
    signal: item.signal || (id.includes("03") ? "MODERATE" : "STABLE"),
    load: item.load ?? (48 + (id.charCodeAt(5) || 8) % 32),
    facts: [
      `${VEH_LABEL[item.code] || item.code} · ${id}`,
      `Позиция ${x.toFixed(1)} / ${z.toFixed(1)}`,
      item.status === "inactive" ? "Простой на площадке" : "В контуре смены",
    ],
  });
  return g;
}

function wheel(x, y, z, r = 0.48, w = 0.34) {
  const g = new THREE.Group();
  const tire = mesh(G(`torus:${r}`, () => new THREE.TorusGeometry(r * 0.72, r * 0.28, 12, 28)), M("tire", 0x1a1a1a, { roughness: 0.94, envMapIntensity: 0.15 }), 0, 0, 0);
  tire.rotation.y = Math.PI / 2;
  g.add(tire);
  g.add(cyl(r * 0.42, w * 0.55, M("rim", 0x8a8a8c, { metalness: 0.62, roughness: 0.32, envMapIntensity: 1.1, physical: true }), 0, 0, 0, Math.PI / 2, 0, 20));
  g.add(cyl(r * 0.14, w * 0.7, M("hub", 0x333), 0, 0, 0, Math.PI / 2, 0, 10));
  g.position.set(x, y, z);
  return g;
}

function tracks(g, len = 4.05, y = 0.4) {
  const t = M("track", 0x1c1c1c, { roughness: 0.88 });
  const side = M("tside", 0x3a3a3c, { metalness: 0.2 });
  [-1.12, 1.12].forEach((z) => {
    const belt = mesh(
      G(`cap:${len}:0.2`, () => new THREE.CapsuleGeometry(0.2, Math.max(len - 0.4, 0.5), 4, 12)),
      t, 0, y, z
    );
    belt.rotation.z = Math.PI / 2;
    g.add(belt);
    g.add(rboxC(len * 0.88, 0.4, 0.14, side, 0, y + 0.1, z + (z > 0 ? 0.28 : -0.28)));
    for (let i = 0; i < 8; i++) {
      const x = -len / 2 + 0.35 + i * (len - 0.7) / 7;
      g.add(cyl(0.17, 0.55, M("twheel", 0x2a2a2a), x, y, z, Math.PI / 2, 0, 10));
    }
    for (let i = 0; i < 13; i++) {
      const x = -len / 2 + 0.16 + i * (len - 0.32) / 12;
      g.add(rboxC(0.22, 0.1, 0.72, t, x, y - 0.26, z, false));
    }
    g.add(cyl(0.3, 0.22, M("sprock", 0x4a4a4c, { metalness: 0.3 }), len / 2 - 0.12, y, z, Math.PI / 2, 0, 10));
  });
}

function cabGlass(g, x, y, z, w, h, d) {
  const gl = M("glass", 0x8aa4b0, {
    physical: true, transparent: true, opacity: 0.4, roughness: 0.06, metalness: 0.1,
    envMapIntensity: 1.45, clearcoat: 0.55, clearcoatRoughness: 0.1,
  });
  g.add(boxC(w, h, 0.04, gl, x, y, z + d / 2));
  g.add(boxC(0.04, h, d * 0.85, gl, x + w / 2, y, z));
  g.add(boxC(0.04, h, d * 0.85, gl, x - w / 2, y, z));
}

function excavator() {
  const g = new THREE.Group();
  const yel = M("ex", 0xc6a44a, { metalness: 0.18, roughness: 0.52, envMapIntensity: 0.7, map: maps.paint, physical: true, clearcoat: 0.2, clearcoatRoughness: 0.5 });
  const dark = M("exd", 0x2c2c2e, { roughness: 0.7 });
  tracks(g);
  g.add(extrude(
    [[-1.35, 0.55], [-1.4, 1.15], [-0.2, 1.55], [1.15, 1.45], [1.45, 0.95], [1.4, 0.55]],
    2.2, yel, 0.1, 0, 0, 0.04
  ));
  g.add(extrude(
    [[-0.7, 1.45], [-0.72, 2.15], [-0.15, 2.85], [0.55, 2.8], [0.62, 1.5]],
    1.5, M("excab", 0x2a3340, { roughness: 0.55, envMapIntensity: 0.5 }), -0.35, 0, 0, 0.03
  ));
  cabGlass(g, -0.45, 2.15, 0.15, 1.15, 0.65, 1.35);
  const boom = extrude([[0, 0], [3.6, 0.05], [3.55, 0.42], [0.05, 0.48]], 0.42, yel, 1.1, 2.05, 0, 0.02);
  boom.rotation.z = -0.48;
  g.add(boom);
  const hyd = M("hyd", 0xb89a48, { metalness: 0.45, roughness: 0.4 });
  const hs = M("hose", 0x1a1a1a, { roughness: 0.88 });
  g.add(rod(1.1, 1.75, 0.18, 2.55, 2.7, 0.18, 0.065, hyd));
  g.add(hose(1.05, 1.82, 0.28, 2.5, 2.62, 0.28, 0.022, hs));
  g.add(hose(1.05, 1.7, -0.18, 2.48, 2.55, -0.18, 0.02, hs));
  const stick = extrude([[0, 0], [2.55, 0], [2.5, 0.32], [0.05, 0.38]], 0.32, yel, 3.55, 1.35, 0, 0.018);
  stick.rotation.z = 0.62;
  g.add(stick);
  g.add(hose(3.5, 1.42, 0.14, 4.7, 0.62, 0.14, 0.018, hs));
  g.add(rod(3.55, 1.28, -0.12, 4.55, 0.7, -0.12, 0.045, hyd));
  const bucket = lathe([[0.04, 0], [0.38, 0.04], [0.42, 0.22], [0.22, 0.48], [0.05, 0.52]], M("buck", 0x4a4e54, { metalness: 0.4, roughness: 0.45, map: maps.rust }), 4.95, 0.42, 0, 24);
  bucket.rotation.z = 0.5;
  g.add(bucket);
  for (let i = -1; i <= 1; i++) g.add(boxC(0.1, 0.26, 0.08, dark, 5.25, 0.28, i * 0.22));
  return g;
}

function dumpTruck() {
  const g = new THREE.Group();
  const or = M("dt", 0xb45c38, { roughness: 0.55, metalness: 0.08, envMapIntensity: 0.55, map: maps.paint, physical: true, clearcoat: 0.12, clearcoatRoughness: 0.55 });
  g.add(extrude(
    [[-0.95, 0.08], [-1.05, 0.32], [-1.0, 0.88], [-0.42, 1.62], [0.08, 1.92], [0.88, 1.88], [0.95, 0.38], [0.72, 0.08]],
    2.08, or, -2.15, 0, 0, 0.04
  ));
  cabGlass(g, -2.35, 1.55, 0.12, 1.35, 0.7, 1.85);
  const bedG = new THREE.Group();
  bedG.position.set(-0.85, 1.05, 0);
  bedG.rotation.z = -0.52;
  bedG.add(extrude(
    [[0.05, -0.12], [0.12, 1.08], [3.85, 1.18], [4.05, -0.08]],
    2.18, M("bed", 0xc46a40, { roughness: 0.58, map: maps.paint }), 2.05, 0, 0, 0.03
  ));
  const gravel = mesh(G("ico:1.15", () => new THREE.IcosahedronGeometry(1.15, 1)), M("dtgrav", 0x8a8478, { map: maps.gravel, roughness: 0.95 }), 2.05, 0.55, 0, false);
  gravel.scale.set(1.55, 0.42, 0.82);
  bedG.add(gravel);
  g.add(bedG);
  g.add(boxC(0.12, 0.45, 0.55, M("mir", 0x88c4e0, { metalness: 0.4, roughness: 0.15 }), -1.4, 2.15, 1.15));
  g.add(boxC(0.22, 0.16, 0.35, M("hl", 0xfff2c0, { emissive: 0xffe08a, emissiveIntensity: 0.14 }), -3.12, 1.15, 0.7));
  g.add(boxC(0.22, 0.16, 0.35, M("hl", 0xfff2c0, { emissive: 0xffe08a, emissiveIntensity: 0.14 }), -3.12, 1.15, -0.7));
  g.add(rod(-0.15, 1.05, 0, 1.45, 2.55, 0, 0.08, M("dthyd", 0xb89a48, { metalness: 0.45 })));
  [-1.75, 0.25, 2.05].forEach((x) => { g.add(wheel(x, 0.5, 1.02)); g.add(wheel(x, 0.5, -1.02)); });
  return g;
}

function mixer() {
  const g = new THREE.Group();
  const blue = M("mcab", 0x4a6780, { roughness: 0.5, envMapIntensity: 0.55, map: maps.paint, physical: true, clearcoat: 0.18, clearcoatRoughness: 0.5 });
  g.add(extrude(
    [[-0.92, 0.08], [-1.0, 0.85], [-0.4, 1.58], [0.12, 1.85], [0.85, 1.8], [0.92, 0.32], [0.7, 0.08]],
    2.02, blue, -2.25, 0, 0, 0.035
  ));
  cabGlass(g, -2.4, 1.5, 0.12, 1.3, 0.62, 1.8);
  g.add(extrude([[-2.35, 0.38], [-2.38, 0.62], [2.25, 0.64], [2.32, 0.4]], 2.05, M("mxch", 0x2a2a2c, { metalness: 0.25, roughness: 0.55 }), 0.15, 0, 0, 0.02));
  const drum = lathe(
    [[0.15, -1.65], [1.05, -1.45], [1.18, -0.4], [1.08, 0.7], [0.72, 1.55], [0.2, 1.7]],
    M("drum", 0x8a9094, { metalness: 0.18, roughness: 0.55, envMapIntensity: 0.55, map: maps.conc, normalMap: maps.conc.normal }),
    0.75, 2.05, 0, 32
  );
  drum.rotation.z = Math.PI / 2.25;
  drum.userData.spin = true;
  mixerDrums.push(drum);
  g.add(drum);
  for (let i = 0; i < 5; i++) {
    const ring = mesh(G("tor:1.1:0.035", () => new THREE.TorusGeometry(1.1, 0.035, 6, 20)), M("drring", 0xeee), 0, i * 0.62 - 1.2, 0);
    ring.rotation.x = Math.PI / 2;
    drum.add(ring);
  }
  g.add(lathe([[0.05, 0], [0.48, 0.04], [0.1, 0.58]], M("hopper", 0x4a6780), -0.45, 3.02, 0, 16));
  g.add(cyl(0.09, 1.45, M("chute", 0x7a8088, { metalness: 0.4 }), 2.55, 1.15, 0, 0, Math.PI / 2.5, 12));
  g.add(boxC(0.7, 0.45, 0.55, M("water", 0x1a5276), -1.1, 1.55, -1.05));
  const lad = M("mlad", 0xc8c8c8, { metalness: 0.4, roughness: 0.4 });
  g.add(cyl(0.025, 1.85, lad, 0.55, 1.55, 1.12, 0, 0, 8));
  g.add(cyl(0.025, 1.85, lad, 1.15, 1.55, 1.12, 0, 0, 8));
  for (let i = 0; i < 8; i++) g.add(boxC(0.6, 0.03, 0.03, lad, 0.85, 0.85 + i * 0.22, 1.12, false));
  const flap = M("flap", 0x1a1a1a, { roughness: 0.92 });
  [-1.85, 0.35, 1.95].forEach((x) => {
    g.add(wheel(x, 0.5, 1.02)); g.add(wheel(x, 0.5, -1.02));
    g.add(boxC(0.55, 0.12, 0.28, flap, x, 0.42, 1.28, false));
    g.add(boxC(0.55, 0.12, 0.28, flap, x, 0.42, -1.28, false));
  });
  return g;
}

function mobileCrane() {
  const g = new THREE.Group();
  const red = M("mcr", 0xa33c34, { metalness: 0.16, roughness: 0.5, envMapIntensity: 0.6, map: maps.paint, physical: true, clearcoat: 0.15, clearcoatRoughness: 0.5 });
  g.add(extrude(
    [[-3.3, 0.55], [-3.35, 1.55], [3.25, 1.55], [3.35, 0.55]],
    2.22, red, 0, 0, 0, 0.04
  ));
  g.add(extrude(
    [[-0.95, 1.5], [-0.92, 2.55], [0.55, 2.85], [0.9, 2.5], [0.92, 1.5]],
    2.02, red, -2.35, 0, 0, 0.03
  ));
  cabGlass(g, -2.45, 2.45, 0.1, 1.55, 0.7, 1.85);
  [[-2.5, 1.55], [-2.5, -1.55], [2.5, 1.55], [2.5, -1.55]].forEach(([x, z]) => {
    g.add(boxC(0.16, 0.16, 2.85, M("out", 0x2a2a2c, { metalness: 0.3 }), x, 0.28, z));
    g.add(boxC(0.55, 0.14, 0.55, M("pad", 0x1a1a1a), x, 0.1, z + (z > 0 ? 1.4 : -1.4)));
  });
  g.add(boxC(1.6, 0.7, 2.1, M("cwt", 0x333), -0.2, 1.85, 0));
  const boom = extrude([[0, 0], [0.08, 12.4], [0.5, 12.3], [0.55, 0.06]], 0.5, M("boom", 0xc4a44a, { metalness: 0.38, roughness: 0.4 }), 0.9, 1.55, 0, 0.02);
  boom.rotation.z = -0.58;
  g.add(boom);
  const boom2 = extrude([[0, 0], [0.06, 8.15], [0.38, 8.05], [0.42, 0.05]], 0.38, M("boom2", 0xccb05a, { metalness: 0.36, roughness: 0.4 }), 5.15, 7.55, 0, 0.016);
  boom2.rotation.z = -0.58;
  g.add(boom2);
  const boom3 = extrude([[0, 0], [0.05, 5.15], [0.28, 5.05], [0.3, 0.04]], 0.28, M("boom3", 0xd4bc6a, { roughness: 0.42 }), 7.7, 11.85, 0, 0.012);
  boom3.rotation.z = -0.58;
  g.add(boom3);
  g.add(rod(5.15, 11.6, 0, 5.15, 4.2, 0, 0.025, M("cbl2", 0x222)));
  g.add(mesh(G("tor:0.18:0.04", () => new THREE.TorusGeometry(0.18, 0.04, 6, 12)), M("hk2", 0x111), 5.15, 4.05, 0));
  [-2.3, 0, 2.3].forEach((x) => { g.add(wheel(x, 0.52, 1.05, 0.52)); g.add(wheel(x, 0.52, -1.05, 0.52)); });
  return g;
}

function roller() {
  const g = new THREE.Group();
  const gr = M("rol", 0x7f8c8d, { metalness: 0.32, roughness: 0.45, map: maps.paint, physical: true, clearcoat: 0.12, clearcoatRoughness: 0.55 });
  g.add(extrude([[-1.2, 0.82], [-1.25, 1.58], [1.28, 1.65], [1.42, 0.88]], 1.72, gr, 0.4, 0, 0, 0.04));
  g.add(extrude([[-0.58, 1.55], [-0.55, 2.58], [0.55, 2.62], [0.62, 1.55]], 1.52, M("rcab", 0x2c3e50, { roughness: 0.55 }), 0.25, 0, 0, 0.03));
  cabGlass(g, 0.25, 2.4, 0.08, 1.1, 0.6, 1.4);
  const drum = lathe([[0.86, -0.95], [0.92, -0.82], [0.88, 0.82], [0.92, 0.95], [0.86, 0.98]], M("rdrum", 0x4d5656, { metalness: 0.42, roughness: 0.4 }), -1.65, 0.9, 0, 28);
  drum.rotation.z = Math.PI / 2;
  g.add(drum);
  g.add(mesh(G("tor:0.9:0.04", () => new THREE.TorusGeometry(0.9, 0.04, 6, 22)), M("dscr", 0x2a2a2c), -1.65, 0.9, 0));
  g.children[g.children.length - 1].rotation.y = Math.PI / 2;
  g.add(wheel(1.65, 0.58, 0.72, 0.56, 0.42));
  g.add(wheel(1.65, 0.58, -0.72, 0.56, 0.42));
  g.add(boxC(0.07, 1.15, 1.55, M("rops", 0xc8c8c8, { metalness: 0.4 }), 0.25, 2.95, 0));
  g.add(boxC(1.2, 0.07, 0.07, M("rops", 0xc8c8c8), 0.25, 3.5, 0.72));
  g.add(boxC(0.28, 0.16, 0.22, M("rlight", 0xfff2c0, { emissive: 0xffe08a, emissiveIntensity: 0.4 }), -0.7, 1.55, 0.9));
  return g;
}

function bulldozer() {
  const g = new THREE.Group();
  const gn = M("doz", 0xc6a44a, { roughness: 0.52, metalness: 0.12, envMapIntensity: 0.65, map: maps.paint, physical: true, clearcoat: 0.18, clearcoatRoughness: 0.5 });
  tracks(g, 4.2, 0.48);
  g.add(extrude([[-1.7, 0.7], [-1.65, 1.85], [1.55, 1.9], [1.75, 0.7]], 2.22, gn, 0.15, 0, 0, 0.04));
  g.add(extrude([[-0.6, 1.85], [-0.55, 2.75], [0.55, 2.8], [0.65, 1.85]], 1.6, M("dcab", 0x2a3340, { roughness: 0.55 }), 0.1, 0, 0, 0.03));
  cabGlass(g, 0.1, 2.35, 0.1, 1.1, 0.55, 1.45);
  const blade = extrude([[-0.08, 0], [0.12, 0.15], [0.1, 1.7], [-0.12, 1.85]], 2.85, M("blade", 0xb89a48, { metalness: 0.18, roughness: 0.5 }), -2.22, 0.15, 0, 0.02);
  g.add(blade);
  g.add(boxC(0.08, 0.18, 2.9, M("bedge", 0x2a2a2c, { metalness: 0.5 }), -2.38, 0.22, 0));
  g.add(rod(-1.5, 1.45, 0.7, -2.15, 1.45, 0.7, 0.07, gn));
  g.add(rod(-1.5, 1.45, -0.7, -2.15, 1.45, -0.7, 0.07, gn));
  g.add(boxC(0.22, 1.05, 0.22, M("rip", 0x2a2a2c), 2.05, 0.7, 0));
  g.add(boxC(0.08, 0.55, 0.7, M("rip2", 0x333), 2.2, 0.35, 0));
  g.add(boxC(0.35, 0.18, 0.35, M("dlight", 0xfff2c0, { emissive: 0xffe08a, emissiveIntensity: 0.45 }), -1.5, 1.85, 0.95));
  return g;
}

function manipulator() {
  const g = new THREE.Group();
  const cab = M("man", 0xd4d0c8, { roughness: 0.48, envMapIntensity: 0.55, map: maps.paint, physical: true, clearcoat: 0.2, clearcoatRoughness: 0.45 });
  g.add(extrude(
    [[-0.92, 0.08], [-0.98, 0.8], [-0.4, 1.5], [0.15, 1.72], [0.85, 1.68], [0.92, 0.3], [0.7, 0.08]],
    2.02, cab, -2.2, 0, 0, 0.035
  ));
  cabGlass(g, -2.25, 2.05, 0.1, 1.5, 0.6, 1.8);
  g.add(extrude([[-2.2, 0.68], [-2.18, 1.42], [2.22, 1.48], [2.35, 0.7]], 2.08, M("manb", 0xa33c34, { roughness: 0.5, map: maps.paint }), 0.45, 0, 0, 0.035));
  [[-1.6, 1.35], [1.8, 1.35], [-1.6, -1.35], [1.8, -1.35]].forEach(([x, z]) => {
    g.add(boxC(0.12, 0.12, 1.6, M("mout", 0x333), x, 0.22, z));
  });
  g.add(extrude([[-0.24, 1.48], [-0.22, 1.92], [0.28, 1.95], [0.3, 1.48]], 0.52, cab, 1.35, 0, 0, 0.02));
  const a1 = extrude([[0, 0], [2.85, 0.02], [2.8, 0.26], [0.04, 0.28]], 0.28, M("arm", 0xa33c34, { roughness: 0.45 }), 1.55, 1.85, 0, 0.014);
  a1.rotation.z = -0.68;
  g.add(a1);
  const a2 = extrude([[0, 0], [2.2, 0.02], [2.16, 0.2], [0.04, 0.22]], 0.22, M("arm2", 0xb84a40, { roughness: 0.45 }), 3.55, 3.55, 0, 0.012);
  a2.rotation.z = 0.38;
  g.add(a2);
  g.add(boxC(0.45, 0.55, 0.7, M("grab", 0x4a4a4c), 5.15, 3.35, 0));
  g.add(boxC(0.08, 0.55, 0.12, M("claw", 0x222), 5.4, 3.05, 0.22));
  g.add(boxC(0.08, 0.55, 0.12, M("claw", 0x222), 5.4, 3.05, -0.22));
  [-1.85, 0.35, 2.0].forEach((x) => { g.add(wheel(x, 0.5, 1.02)); g.add(wheel(x, 0.5, -1.02)); });
  return g;
}

function truck() {
  const g = new THREE.Group();
  const blue = M("tr", 0x4a5a66, { roughness: 0.5, envMapIntensity: 0.55, map: maps.paint, physical: true, clearcoat: 0.16, clearcoatRoughness: 0.5 });
  g.add(extrude(
    [[-0.92, 0.08], [-1.0, 0.82], [-0.42, 1.55], [0.12, 1.82], [0.85, 1.78], [0.92, 0.32], [0.7, 0.08]],
    2.08, blue, -2.2, 0, 0, 0.035
  ));
  cabGlass(g, -2.25, 2.15, 0.12, 1.5, 0.65, 1.85);
  g.add(boxC(0.22, 0.16, 0.32, M("hl", 0xfff2c0, { emissive: 0xffe08a, emissiveIntensity: 0.55 }), -3.12, 1.15, 0.7));
  g.add(rboxC(4.35, 0.32, 2.1, M("flat", 0x4a5a66, { roughness: 0.55 }), 0.65, 1.05, 0));
  g.add(boxC(4.2, 0.08, 2.0, M("deck2", 0x1a3a55), 0.65, 1.22, 0, false));
  for (let i = 0; i < 4; i++) {
    g.add(boxC(0.95, 0.14, 1.15, M("pal", 0xc9a66b, { map: maps.wood }), -0.7 + i * 1.0, 1.35, 0));
    g.add(boxC(0.85, 0.7, 1.05, M("crate" + i, i % 2 ? 0xb85a28 : 0x2e6b8a, { map: maps.corr }), -0.7 + i * 1.0, 1.78, 0));
  }
  g.add(boxC(0.08, 0.85, 2.05, M("headb", 0xeee), -1.35, 1.55, 0, false));
  [-1.85, 0.4, 2.05].forEach((x) => { g.add(wheel(x, 0.5, 1.02)); g.add(wheel(x, 0.5, -1.02)); });
  return g;
}

function pointCloud(points) {
  const xyz = points?.xyz || [];
  const rgb = points?.rgb || [];
  const n = Math.floor(xyz.length / 3);
  if (!n) return null;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3);
  const col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    pos.set([xyz[i * 3], xyz[i * 3 + 1] + 0.04, xyz[i * 3 + 2]], i * 3);
    col.set([(rgb[i * 3] || 180) / 255, (rgb[i * 3 + 1] || 180) / 255, (rgb[i * 3 + 2] || 180) / 255], i * 3);
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  return new THREE.Points(geo, new THREE.PointsMaterial({
    size: 0.12, vertexColors: true, color: 0x888888, opacity: 0.35, transparent: true,
  }));
}

function cameraPole(cam) {
  const g = new THREE.Group();
  const p = cam.position || [0, 12, 20];
  g.add(cyl(0.07, p[1], M("cpole", 0x3a3a3c, { metalness: 0.3 }), p[0], p[1] / 2, p[2], 0, 0, 8));
  const head = mesh(G("b:0.38:0.22:0.48", () => new THREE.BoxGeometry(0.38, 0.22, 0.48)), M("chead", 0x111), p[0], p[1], p[2]);
  head.lookAt(new THREE.Vector3(...(cam.look_at || [0, 0, 0])));
  g.add(head);
  markPick(g, cam.id || "CAM-01", {
    title: cam.name || cam.id || "Камера",
    kind: "camera",
    status: "active",
    power: 92,
    session: "24HR",
    signal: "STABLE",
    load: 18,
    facts: [cam.view || "Обзор площадки", cam.zone || "", `${cam.height_m || 12} м / ${cam.angle_deg || 40}°`].filter(Boolean),
  });
  return g;
}

function setProgress() { /* корпуса заданы при сборке сцены */ }

function resize(canvas) {
  const w = canvas.clientWidth, h = Math.max(canvas.clientHeight, 1);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
  composer?.setSize(w, h);
  gtaoPass?.setSize(Math.floor(w * 0.55), Math.floor(h * 0.55));
  smaaPass?.setSize(w * renderer.getPixelRatio(), h * renderer.getPixelRatio());
  labelRenderer?.setSize(w, h);
}

function animate() {
  requestAnimationFrame(animate);
  if (!running) return;
  const t = clock.getElapsedTime();
  frameN++;
  cranes.forEach((c, i) => {
    const ph = i * 1.65;
    c.top.rotation.y = Math.sin(t * 0.045 + ph) * 0.28;
    c.trolley.position.x = 14 + Math.sin(t * 0.12 + ph) * 8;
    c.hook.position.x = c.trolley.position.x;
    c.hook.position.y = -8.6 + Math.sin(t * 0.22 + ph) * 0.7;
    const len = c.trolley.position.y - c.hook.position.y;
    c.cable.scale.y = Math.max(len / 10, 0.2);
    c.cable.position.x = c.trolley.position.x;
    c.cable.position.y = (c.trolley.position.y + c.hook.position.y) / 2;
  });
  mixerDrums.forEach((d) => { d.rotation.x = t * 0.35; });
  if (dustPts && frameN % 2 === 0) {
    const arr = dustPts.geometry.attributes.position.array;
    for (let i = 0; i < arr.length; i += 3) {
      arr[i + 1] = (arr[i + 1] + 0.0024) % 9;
    }
    dustPts.geometry.attributes.position.needsUpdate = true;
  }
  if (focusAim) {
    controls.target.lerp(focusAim, 0.06);
    if (controls.target.distanceTo(focusAim) < 0.08) focusAim = null;
  }
  if (pickHelper && frameN % 2 === 0) pickHelper.update();
  controls.update();
  if (composer) composer.render();
  else renderer.render(scene, camera);
  labelRenderer?.render(scene, camera);
}

window.StroyTwin = {
  initTwin,
  applyScene,
  pauseTwin,
  initDroneHud,
  selectPick,
  get camera() { return camera; },
  get controls() { return controls; },
};
