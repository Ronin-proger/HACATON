import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

let renderer, scene, camera, controls, labelRenderer, root, canvas;
let nodes = [];
let selected = null;
let catalog = null;
let running = false;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

const FOLDER_COLOR = {
  "": 0xf2f2f2,
  Site: 0xd8d8d8,
  Equipment: 0xd4b43a,
  Safety: 0xd44848,
  Schedule: 0xb8b8c8,
  Journal: 0xc8c8c8,
  People: 0xaaaaaa,
  AI: 0xffffff,
  Inbox: 0x8a8a8a,
};

export function initNotes(el) {
  canvas = el;
  if (renderer) {
    resize();
    running = true;
    refreshNotes();
    return;
  }
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.setClearColor(0x070707, 1);
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x070707, 18, 70);
  camera = new THREE.PerspectiveCamera(38, canvas.clientWidth / Math.max(canvas.clientHeight, 1), 0.2, 200);
  camera.position.set(0, 16, 28);
  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.target.set(0, 2, 0);
  controls.maxPolarAngle = Math.PI * 0.48;
  scene.add(new THREE.AmbientLight(0x888888, 0.45));
  const key = new THREE.DirectionalLight(0xffffff, 0.7);
  key.position.set(10, 22, 8);
  scene.add(key);
  const grid = new THREE.PolarGridHelper(22, 8, 6, 64, 0x2a2a2a, 0x161616);
  grid.position.y = -0.02;
  scene.add(grid);
  root = new THREE.Group();
  scene.add(root);
  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
  Object.assign(labelRenderer.domElement.style, {
    position: "absolute", inset: "0", pointerEvents: "none", zIndex: "2",
  });
  canvas.parentElement.appendChild(labelRenderer.domElement);
  canvas.addEventListener("pointerup", onPick);
  document.getElementById("notes-q")?.addEventListener("input", () => {
    if (catalog?.notes) renderTree(catalog.notes);
  });
  window.addEventListener("resize", resize);
  running = true;
  animate();
  refreshNotes();
}

export function pauseNotes(v) {
  running = !v;
}

export async function refreshNotes() {
  const data = await fetch("/api/notes").then((r) => r.json());
  catalog = data;
  renderTree(data.notes);
  renderAnalytics(data.analytics, data.api);
  buildGraph(data.graph);
  return data;
}

function resize() {
  if (!canvas || !renderer) return;
  const w = canvas.clientWidth, h = Math.max(canvas.clientHeight, 1);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
  labelRenderer?.setSize(w, h);
}

function buildGraph(graph) {
  if (!root) return;
  while (root.children.length) root.remove(root.children[0]);
  nodes = [];
  const list = graph.nodes || [];
  const folders = [...new Set(list.map((n) => n.folder || "root"))];
  const byPath = {};
  list.forEach((n, i) => {
    const fi = folders.indexOf(n.folder || "root");
    const ang = (fi / Math.max(folders.length, 1)) * Math.PI * 2 + (i % 5) * 0.14;
    const rad = 6 + (n.links?.length || 0) * 0.35 + (fi % 3);
    const y = 1.2 + (n.chars || 80) / 220 + (n.type === "moc" ? 3 : 0);
    const pos = new THREE.Vector3(Math.cos(ang) * rad, y, Math.sin(ang) * rad);
    const color = FOLDER_COLOR[n.folder] ?? 0x9a9a9a;
    const geo = n.type === "moc"
      ? new THREE.OctahedronGeometry(0.55, 0)
      : new THREE.IcosahedronGeometry(0.32 + Math.min((n.links || []).length, 6) * 0.04, 0);
    const mat = new THREE.MeshStandardMaterial({
      color, roughness: 0.35, metalness: 0.2, emissive: color, emissiveIntensity: 0.08,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(pos);
    mesh.userData.note = n;
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.55, 0.012, 6, 24),
      new THREE.MeshBasicMaterial({ color: 0x3a3a3a }),
    );
    ring.rotation.x = Math.PI / 2;
    mesh.add(ring);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0xf0f0f0, transparent: true, opacity: 0.55 }),
    );
    mesh.add(edges);
    const lab = document.createElement("div");
    lab.className = "hud-label";
    lab.textContent = n.title;
    const css = new CSS2DObject(lab);
    css.position.set(0, 0.7, 0);
    mesh.add(css);
    root.add(mesh);
    byPath[n.path] = mesh;
    nodes.push(mesh);
  });
  (graph.edges || []).forEach((e) => {
    const a = byPath[e.source], b = byPath[e.target];
    if (!a || !b) return;
    const geo = new THREE.BufferGeometry().setFromPoints([a.position, b.position]);
    root.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x3a3a3a, transparent: true, opacity: 0.7 })));
  });
}

function onPick(ev) {
  if (!canvas) return;
  const r = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  pointer.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(nodes, false)[0];
  if (hit?.object?.userData?.note) openNote(hit.object.userData.note.path);
}

export async function openNote(path) {
  const note = await fetch("/api/notes/item?path=" + encodeURIComponent(path)).then((r) => r.json());
  selected = note;
  const title = document.getElementById("note-open-title");
  const preview = document.getElementById("note-preview");
  const meta = document.getElementById("note-open-meta");
  if (title) title.textContent = note.title;
  if (meta) meta.textContent = `${note.author} · ${note.created} · ${note.folder || "root"}`;
  if (preview) preview.textContent = note.content;
  document.querySelectorAll(".notes-tree button").forEach((b) => {
    b.classList.toggle("active", b.dataset.path === path);
  });
  nodes.forEach((m) => {
    const on = m.userData.note?.path === path;
    m.material.emissiveIntensity = on ? 0.45 : 0.08;
    m.scale.setScalar(on ? 1.35 : 1);
  });
}

function renderTree(list) {
  const box = document.getElementById("notes-tree");
  if (!box) return;
  const q = (document.getElementById("notes-q")?.value || "").toLowerCase();
  const groups = {};
  list.forEach((n) => {
    if (q && !`${n.title} ${n.path} ${(n.tags || []).join(" ")}`.toLowerCase().includes(q)) return;
    (groups[n.folder || "root"] ||= []).push(n);
  });
  box.innerHTML = Object.entries(groups).map(([folder, items]) => `
    <p class="notes-folder">${folder}</p>
    ${items.map((n) => `<button type="button" data-path="${n.path}">
      <i class="led ${n.source === "ai" ? "warn" : "on"}"></i>
      <span>${n.title}<b>${(n.tags || []).slice(0, 2).join(" ")}</b></span>
    </button>`).join("")}
  `).join("");
  box.querySelectorAll("button").forEach((b) => {
    b.onclick = () => openNote(b.dataset.path);
  });
}

function renderAnalytics(a, api) {
  const kpis = document.getElementById("notes-kpis");
  const led = document.getElementById("notes-api-led");
  const apiLbl = document.getElementById("notes-api-label");
  if (led) led.className = `led ${api?.ok ? "on" : "warn"}`;
  if (apiLbl) apiLbl.textContent = api?.ok ? "Local REST API" : "HACAOBS fallback";
  if (kpis && a?.totals) {
    kpis.innerHTML = [
      ["Заметки", a.totals.notes, "общие"],
      ["Связи", a.totals.links, "wiki"],
      ["Теги", a.totals.tags, ""],
      ["Авторы", a.totals.authors, "смены"],
      ["Папки", a.totals.folders, ""],
    ].map(([l, v, e]) => `<div class="metric"><span>${l}</span><b>${v} <em>${e}</em></b></div>`).join("");
  }
  drawBars("chart-folder", a?.by_folder || [], "папки");
  drawBars("chart-type", a?.by_type || [], "типы");
  drawLine("chart-day", a?.by_day || []);
}

function drawBars(id, rows, label) {
  const svg = document.getElementById(id);
  if (!svg) return;
  const w = 280, h = 88, max = Math.max(...rows.map(([, v]) => v), 1);
  const gap = 6, bw = Math.max(8, (w - 20) / Math.max(rows.length, 1) - gap);
  const bars = rows.slice(0, 8).map(([name, v], i) => {
    const bh = (v / max) * 58;
    const x = 10 + i * (bw + gap);
    return `<rect x="${x}" y="${70 - bh}" width="${bw}" height="${bh}" fill="#d8d8d8"/>
      <text x="${x + bw / 2}" y="84" text-anchor="middle" fill="#6a6a6a" font-size="8">${String(name).slice(0, 8)}</text>`;
  }).join("");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = `<text x="8" y="12" fill="#8a8a8a" font-size="9" letter-spacing="1.2">${label.toUpperCase()}</text>${bars}`;
}

function drawLine(id, rows) {
  const svg = document.getElementById(id);
  if (!svg) return;
  const w = 280, h = 88;
  const vals = rows.map(([, v]) => v);
  const max = Math.max(...vals, 1);
  const pts = vals.map((v, i) => {
    const x = 12 + (i / Math.max(vals.length - 1, 1)) * 256;
    const y = 70 - (v / max) * 50;
    return `${x},${y}`;
  }).join(" ");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = `<text x="8" y="12" fill="#8a8a8a" font-size="9" letter-spacing="1.2">АКТИВНОСТЬ</text>
    <polyline points="${pts}" fill="none" stroke="#f2f2f2" stroke-width="1.2"/>`;
}

function animate() {
  requestAnimationFrame(animate);
  if (!running || !renderer) return;
  root?.children.forEach((o, i) => {
    if (o.isMesh) o.rotation.y += 0.002 + (i % 5) * 0.0004;
  });
  controls?.update();
  renderer.render(scene, camera);
  labelRenderer?.render(scene, camera);
}

window.StroyNotes = {
  initNotes,
  refreshNotes,
  openNote,
  pauseNotes,
  get catalog() { return catalog; },
};
