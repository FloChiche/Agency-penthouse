// Agent Tower — client 3D : charge la tour exportée de Blender, recrée la skyline,
// anime les agents selon l'état poussé par le serveur (Server-Sent Events).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Mêmes cotes que le script Blender (x à droite, y en haut, z vers la caméra).
const FH = 3.6, F = 0.3, SHAFT = { x: 7.15, z: -1.9 }, DOOR = { x: 5.2, z: -1.9 };
const FLOORS = [
  { level: 9, n: 'T',  name: 'Toit · Piscine' },
  { level: 8, n: '8',  name: 'Bureau de FLO' },
  { level: 7, n: 'PH', name: 'Penthouse · QG' },
  { level: 6, n: '6',  name: 'Nightclub' },
  { level: 5, n: '5',  name: 'Casino' },
  { level: 4, n: '4',  name: 'Claude Code', agent: 'claude-code' },
  { level: 3, n: '3',  name: 'n8n', agent: 'n8n' },
  { level: 2, n: '2',  name: 'Claude', agent: 'claude' },
  { level: 1, n: '1',  name: 'ChatGPT', agent: 'chatgpt' },
  { level: 0, n: '0',  name: 'Lobby & Café' },
  { level: -1, n: '-1', name: 'Garage', y: -4.4 },
];
const STATUS_TEXT = { working: 'au travail', waiting: 'attend ta réponse', idle: 'en pause', off: 'hors ligne' };

// ------------------------------------------------------------------ rendu
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.85;
document.body.prepend(renderer.domElement);
const labels = new CSS2DRenderer();
labels.setSize(innerWidth, innerHeight);
Object.assign(labels.domElement.style, { position: 'fixed', inset: '0', pointerEvents: 'none', zIndex: 2 });
document.body.appendChild(labels.domElement);

const scene = new THREE.Scene();
scene.background = skyTexture();
scene.fog = new THREE.Fog('#2a2238', 120, 380);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;
scene.environmentIntensity = 0.35;

const camera = new THREE.PerspectiveCamera(35, innerWidth / innerHeight, 0.1, 900);
window.__tower = { scene, camera };                        // accès console pour le débogage
const HOME = { pos: new THREE.Vector3(34, 16, 74), target: new THREE.Vector3(-2, 14, 0) };
camera.position.copy(HOME.pos);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(HOME.target);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI / 1.9;
controls.update();

scene.add(new THREE.HemisphereLight('#7d8fd0', '#1a1420', 0.6));
const sun = new THREE.DirectionalLight('#ffb27a', 1.4);
sun.position.set(-60, 25, -80);
scene.add(sun);
for (let level = -1; level <= 9; level++) {                 // éclairage d'ambiance par étage
  const l = new THREE.PointLight('#ffe2c0', level === 6 ? 3 : 9, 11, 2);
  l.position.set(0, level === -1 ? -1.2 : level * FH + FH - 0.7, 0.5);
  scene.add(l);
}

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.45, 0.35, 1.7));
composer.addPass(new OutputPass());
Object.assign(window.__tower, { composer, sun });

function skyTexture() {
  const c = document.createElement('canvas'); c.width = 4; c.height = 512;
  const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 512);
  gr.addColorStop(0, '#0b1030'); gr.addColorStop(0.55, '#3b3a66'); gr.addColorStop(0.82, '#c9877a'); gr.addColorStop(1, '#ffb27a');
  g.fillStyle = gr; g.fillRect(0, 0, 4, 512);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

// ------------------------------------------------------------------ skyline + One World Trade Center
function windowTexture() {
  const c = document.createElement('canvas'); c.width = 64; c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#000'; g.fillRect(0, 0, 64, 128);
  for (let y = 4; y < 128; y += 8) for (let x = 3; x < 64; x += 8) {
    const r = Math.random();
    g.fillStyle = r < 0.22 ? '#ffd9a0' : r < 0.3 ? '#cfe3ff' : '#000';
    g.fillRect(x, y, 4, 5);
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.NearestFilter; return t;
}
const winTex = [windowTexture(), windowTexture(), windowTexture()];
function building(x, z, w, d, h) {
  const t = winTex[(Math.random() * 3) | 0].clone(); t.needsUpdate = true; t.repeat.set(w / 4, h / 8);
  const m = new THREE.MeshStandardMaterial({ color: '#1a2130', roughness: 0.15, metalness: 0.7, emissive: '#ffffff', emissiveMap: t, emissiveIntensity: 0.7 });
  const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  b.position.set(x, h / 2, z); scene.add(b);
}
function oneWTC(x, z, s) {
  const H = 100 * s, rb = 11 * s, rt = 6.2 * s, base = 14 * s;
  const B = (k) => new THREE.Vector3(Math.cos(Math.PI / 4 + k * Math.PI / 2) * rb, base, Math.sin(Math.PI / 4 + k * Math.PI / 2) * rb);
  const T = (k) => new THREE.Vector3(Math.cos(k * Math.PI / 2) * rt, base + H, Math.sin(k * Math.PI / 2) * rt);
  const pts = [];
  for (let k = 0; k < 4; k++) pts.push(B(k), T(k + 1), B(k + 1), T(k + 1), T(k + 2), B(k + 1));
  const geo = new THREE.BufferGeometry().setFromPoints(pts); geo.computeVertexNormals();
  const g = new THREE.Group();
  g.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: '#6d86ad', roughness: 0.05, metalness: 0.95, emissive: '#22345e', emissiveIntensity: 0.8, side: THREE.DoubleSide })));
  const podium = new THREE.Mesh(new THREE.BoxGeometry(rb * 1.42, base, rb * 1.42), new THREE.MeshStandardMaterial({ color: '#9aa8b8', metalness: 0.6, roughness: 0.3 }));
  podium.position.y = base / 2; podium.rotation.y = Math.PI / 4; g.add(podium);
  const spire = new THREE.Mesh(new THREE.CylinderGeometry(0.25 * s, 0.6 * s, 40 * s, 8), new THREE.MeshStandardMaterial({ color: '#e8ecf2', emissive: '#e8ecf2', emissiveIntensity: 0.6 }));
  spire.position.y = base + H + 23 * s; g.add(spire);
  const top = new THREE.Mesh(new THREE.SphereGeometry(0.9 * s, 12, 8), new THREE.MeshBasicMaterial({ color: '#ffffff' }));
  top.position.y = base + H + 43 * s; g.add(top);
  g.position.set(x, 0, z); scene.add(g);
}
oneWTC(-150, -170, 1.25);
for (let i = 0; i < 110; i++) {
  const x = -230 + Math.random() * 420, z = -55 - Math.random() * 190;
  if (Math.hypot(x + 150, z + 170) < 35 || (Math.abs(x - z * 0.45) < 38 && z > -120)) continue;
  const near = z > -90 ? 0.5 : 1;
  building(x, z, 8 + Math.random() * 12, 8 + Math.random() * 12, (12 + Math.random() * 34) * near);
}
[[-30, -4, 10, 8, 15], [26, -6, 10, 8, 12], [-46, -10, 10, 10, 19]].forEach((b) => building(...b));

// ------------------------------------------------------------------ chargement de la tour
let cab = null;
const turntables = [];
const loaderEl = document.getElementById('loader'), loadText = document.getElementById('loadtext');
const draco = new DRACOLoader().setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/');
new GLTFLoader().setDRACOLoader(draco).load('assets/tower.glb', (gltf) => {
  scene.add(gltf.scene);
  gltf.scene.traverse((o) => {
    if (o.name === 'cabine') cab = o;
    if (/^turntable/.test(o.name) && o.parent === gltf.scene) turntables.push(o);
    if (!o.isMesh || !o.material) return;
    // grands sols vernis : les reflets ponctuels des lampes y font des taches de lumière en temps réel
    if (!o.geometry.boundingSphere) o.geometry.computeBoundingSphere();
    if (o.geometry.boundingSphere.radius > 2.5 && o.material.metalness < 0.5 && o.material.roughness < 0.45) {
      o.material.roughness = 0.55;
      if ('clearcoat' in o.material) o.material.clearcoat = 0;
    }
    if (o.material.transparent) o.material.depthWrite = false;
    // les intensités d'émission de Cycles sont trop fortes pour un rendu temps réel avec bloom
    if (o.material.emissiveIntensity > 1) o.material.emissiveIntensity = Math.min(3, 1 + Math.log(o.material.emissiveIntensity));
    // ampoules des modèles Poly Haven (lampes, lampadaires) : beaucoup trop fortes avec le bloom
    if (!/^m_|^beam/.test(o.material.name) && o.material.emissive && o.material.emissive.getHex()) o.material.emissiveIntensity = Math.min(o.material.emissiveIntensity, 0.25);
  });
  loaderEl.classList.add('done');
}, (e) => {
  if (e.total) loadText.textContent = `Chargement de la tour… ${Math.round((e.loaded / e.total) * 100)} %`;
}, (err) => { loadText.textContent = 'Impossible de charger la tour (assets/tower.glb).'; console.error(err); });

// ------------------------------------------------------------------ robots
function robot(color, scale = 1, visorColor = color) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.36, 8, 16), new THREE.MeshPhysicalMaterial({ color, roughness: 0.35, clearcoat: 0.6 }));
  body.position.y = 0.46; g.add(body);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 24, 16), new THREE.MeshPhysicalMaterial({ color: '#f4f4f2', roughness: 0.25, clearcoat: 0.8 }));
  head.position.y = 1.04; g.add(head);
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.07, 0.06), new THREE.MeshStandardMaterial({ color: '#000', emissive: visorColor, emissiveIntensity: 4 }));
  visor.position.set(0, 1.06, 0.17); g.add(visor);
  g.scale.setScalar(scale);
  g.userData = { body, head, visor };
  scene.add(g);
  return g;
}
const at = (level, x, y, z) => new THREE.Vector3(x, level * FH + F + y, z);

// figurants fixes (accueil, café, casino, club, FLO)
[[0, -3.8, 0, 0.15, 0, '#c8a36a'], [0, 3.2, 0, -3.15, 0, '#6b4a32'], [5, -3.6, 0, -1.8, 0, '#151515'],
 [5, 0.6, 0, -2.6, 0, '#151515'], [6, 0, 0, -3.15, 0, '#e5e5e5'], [6, -5.45, 0, 0.3, Math.PI / 2, '#e5e5e5'],
 [7, -0.2, 0, -2.5, 0, '#e5c27a']].forEach(([lv, x, y, z, r, c]) => {
  const g = robot(c); g.position.copy(at(lv, x, y, z)); g.rotation.y = r;
});
const flo = robot('#141414', 1.12, '#ffc35a');
flo.position.copy(at(8, -2.35, 0.12, -0.98)); flo.rotation.y = Math.PI;

// ------------------------------------------------------------------ agents vivants
const LEISURE = {                                              // où chacun va traîner en pause longue
  chatgpt: { level: 5, x: 0.0, z: -0.25, r: Math.PI, y: 0.1 },
  claude: { level: 5, x: 1.2, z: -0.25, r: Math.PI, y: 0.1 },
  n8n: { level: 6, x: -1.4, z: -0.9, r: Math.PI, y: 0.04, dance: true },
  'claude-code': { level: 6, x: 0.9, z: -1.1, r: Math.PI, y: 0.04, dance: true },
};
const OFF = { chatgpt: [0.75, 0.8, Math.PI / 2], claude: [4.25, 1.2, -Math.PI / 2], n8n: [4.35, -0.4, Math.PI / 2], 'claude-code': [1.4, 1.6, Math.PI] };
const LONG_IDLE = 90e3;
const agents = new Map();

function makeAgent(a) {
  const g = robot(a.color);
  const el = document.createElement('div'); el.className = 'tag';
  el.innerHTML = `<span class="nm"><span class="dot"></span>${a.name}</span><span class="dt"></span>`;
  const tag = new CSS2DObject(el); tag.position.set(0, 1.45, 0); g.add(tag);
  const helpers = [0, 1, 2].map((i) => {
    const h = robot(a.color, 0.75); h.visible = false;
    h.position.copy(at(a.floor, [-2.4, -5.2, -3.0][i], 0.1, [-1.45, -1.45, -0.6][i])); h.rotation.y = Math.PI;
    return h;
  });
  const off = OFF[a.id];
  g.position.copy(at(0, off[0], 0, off[1]));
  const ag = { data: a, g, el, helpers, path: [], level: 0, spot: 'off', pose: 'stand', dance: false };
  agents.set(a.id, ag);
  return ag;
}

function spotFor(ag) {
  const a = ag.data;
  if (a.status === 'working' || a.status === 'waiting') return { key: 'desk', level: a.floor, x: -3.8, y: 0.1, z: -1.45, r: Math.PI, pose: 'sit' };
  if (a.status === 'idle') {
    if (Date.now() - a.since > LONG_IDLE) { const l = LEISURE[a.id]; return { key: 'leisure', ...l, pose: l.dance ? 'dance' : 'sit' }; }
    return { key: 'sofa', level: a.floor, x: 0.2, y: 0.32, z: 0.55, r: Math.PI, pose: 'sit' };
  }
  const o = OFF[a.id];
  return { key: 'off', level: 0, x: o[0], y: 0, z: o[1], r: o[2], pose: 'stand' };
}

function planRoute(ag) {
  const s = spotFor(ag);
  if (s.key === ag.spot && s.level === ag.level) return;
  ag.spot = s.key;
  const route = [];
  if (s.level !== ag.level) {
    route.push({ p: at(ag.level, DOOR.x, 0, DOOR.z) }, { p: at(ag.level, SHAFT.x, 0, SHAFT.z), lift: true },
      { p: at(s.level, SHAFT.x, 0, SHAFT.z), lift: true, ride: true }, { p: at(s.level, DOOR.x, 0, DOOR.z) });
  }
  route.push({ p: at(s.level, s.x, s.y, s.z), final: s });
  ag.path = route;
  ag.level = s.level;
  ag.pose = 'walk';
}

function updateTag(ag) {
  const a = ag.data;
  ag.el.querySelector('.dot').className = `dot ${a.status}`;
  ag.el.querySelector('.dt').textContent = a.status === 'working' ? a.detail : STATUS_TEXT[a.status] + (a.detail && a.status !== 'off' ? ` · ${a.detail}` : '');
  ag.helpers.forEach((h, i) => { h.visible = a.status !== 'off' && i < (a.helpers || 0); });
}

// ------------------------------------------------------------------ données en direct
const state = { agents: {}, usage: {}, n8n: {}, feed: [], demo: false };
function onAgent(a) {
  state.agents[a.id] = a;
  const ag = agents.get(a.id) || makeAgent(a);
  ag.data = a;
  updateTag(ag);
  planRoute(ag);
  renderStats(); renderFloors();
}
const es = new EventSource('/stream');
es.addEventListener('state', (e) => {
  Object.assign(state, JSON.parse(e.data));
  Object.values(state.agents).forEach(onAgent);
  renderUsage(); renderFeed(); renderDemo();
});
es.addEventListener('agent', (e) => onAgent(JSON.parse(e.data)));
es.addEventListener('usage', (e) => { state.usage = JSON.parse(e.data); renderUsage(); });
es.addEventListener('n8n', (e) => { state.n8n = JSON.parse(e.data); renderUsage(); });
es.addEventListener('feed', (e) => { state.feed.unshift(JSON.parse(e.data)); state.feed.length = Math.min(state.feed.length, 12); renderFeed(); });
es.addEventListener('demo', (e) => { state.demo = JSON.parse(e.data); renderDemo(); });
es.onopen = () => setConn(true);
es.onerror = () => setConn(false);
function setConn(ok) {
  document.getElementById('conn-dot').className = `dot ${ok ? 'ok' : 'off'}`;
  document.getElementById('conn-text').textContent = ok ? 'en direct' : 'serveur injoignable — lance start.bat';
}
setInterval(() => agents.forEach(planRoute), 5000);          // bascule « pause longue » → casino / club

// ------------------------------------------------------------------ panneaux
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const hhmm = (iso) => new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
function renderStats() {
  const list = Object.values(state.agents);
  $('st-working').textContent = list.filter((a) => a.status === 'working' || a.status === 'waiting').length;
  $('st-idle').textContent = list.filter((a) => a.status === 'idle').length;
  $('st-helpers').textContent = list.reduce((n, a) => n + (a.helpers || 0), 0);
}
function setBar(id, pct) { const el = $(id); el.style.width = `${pct || 0}%`; el.classList.toggle('hot', pct >= 80); }
function renderUsage() {
  const c = state.usage && state.usage.claude;
  if (c && !c.error) {
    $('u-claude-sess').textContent = c.session ? `${c.session.percent} %` : '—';
    $('u-claude-week').textContent = c.week ? `${c.week.percent} %` : '—';
    setBar('u-claude-sess-bar', c.session && c.session.percent); setBar('u-claude-week-bar', c.week && c.week.percent);
    $('u-claude-reset').textContent = (c.session && c.session.resetsAt ? `reset à ${hhmm(c.session.resetsAt)}` : '') + (c.demo ? ' · valeurs de démo' : '');
  } else {
    $('u-claude-sess').textContent = '—'; $('u-claude-week').textContent = '—';
    $('u-claude-reset').textContent = 'connecte Claude Code sur ce PC (claude → /login)';
  }
  const n = state.n8n || {};
  $('u-n8n').textContent = n.connected ? `${n.today} exéc.` : '—';
  $('u-n8n-sub').textContent = n.connected ? `${n.errors} erreur(s)${n.running && n.running.length ? ` · en cours : ${n.running[0]}` : ''}` : 'clé API à mettre dans config.json';
}
function renderFeed() {
  $('feed').innerHTML = state.feed.slice(0, 8).map((f) =>
    `<div><time>${new Date(f.t).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</time>${esc(f.text)}</div>`).join('');
}
function renderDemo() { $('demo').textContent = `Démo : ${state.demo ? 'on' : 'off'}`; }
$('demo').onclick = () => fetch('/api/demo', { method: 'POST' });

let focused = null;
function renderFloors() {
  $('floors').innerHTML = FLOORS.map((f) => {
    const a = f.agent && state.agents[f.agent];
    const sub = a ? (a.status === 'working' ? a.detail : STATUS_TEXT[a.status]) : '';
    return `<button class="floor${focused === f.level ? ' on' : ''}" data-level="${f.level}">
      <span class="n">${f.n}</span><span class="t">${f.name}${sub ? `<span class="s">${esc(sub)}</span>` : ''}</span>
      ${a ? `<span class="dot ${a.status}"></span>` : ''}</button>`;
  }).join('');
  $('floors').querySelectorAll('.floor').forEach((b) => { b.onclick = () => focusFloor(+b.dataset.level); });
}
renderFloors();

let goal = null;
function focusFloor(level) {
  focused = level; renderFloors();
  const y = level === -1 ? -2.6 : level * FH + 1.6;
  goal = level === -1
    ? { pos: new THREE.Vector3(8, -1.0, 22), target: new THREE.Vector3(0, -3.4, 2) }
    : { pos: new THREE.Vector3(7.5, y + 1.7, 12.5), target: new THREE.Vector3(0.3, y - 0.3, -0.8) };
}
$('home').onclick = () => { focused = null; renderFloors(); goal = { pos: HOME.pos.clone(), target: HOME.target.clone() }; };
renderer.domElement.addEventListener('pointerdown', () => { goal = null; });

// ------------------------------------------------------------------ boucle
const clock = new THREE.Clock();
const tmp = new THREE.Vector3();
function step(ag, dt, t) {
  const g = ag.g;
  if (ag.path.length) {
    const wp = ag.path[0];
    const speed = wp.ride ? 5 : 2.4;
    tmp.copy(wp.p).sub(g.position);
    const dist = tmp.length();
    if (!wp.ride && dist > 0.05) g.rotation.y = Math.atan2(tmp.x, tmp.z);
    if (dist <= speed * dt) {
      g.position.copy(wp.p);
      ag.path.shift();
      if (wp.final) { g.rotation.y = wp.final.r; ag.pose = wp.final.pose; }
    } else g.position.addScaledVector(tmp.normalize(), speed * dt);
    if (wp.lift && cab) cab.position.y = g.position.y - 0.12;
  }
  const { body, head } = g.userData;
  const bob = ag.pose === 'walk' ? Math.abs(Math.sin(t * 9)) * 0.05 : ag.pose === 'dance' ? Math.abs(Math.sin(t * 5 + g.id)) * 0.22 : 0;
  body.position.y = 0.46 + bob; head.position.y = 1.04 + bob;
  if (ag.pose === 'sit' && ag.data.status === 'working') body.scale.y = 1 + Math.sin(t * 7 + g.id) * 0.025;
  else body.scale.y = 1;
}
(function tick() {
  const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
  agents.forEach((ag) => step(ag, dt, t));
  turntables.forEach((tt, i) => { tt.rotation.y = t * 0.15 + i; });
  if (goal) {
    camera.position.lerp(goal.pos, 0.06); controls.target.lerp(goal.target, 0.06);
    if (camera.position.distanceTo(goal.pos) < 0.05) goal = null;
  }
  controls.update();
  composer.render();
  labels.render(scene, camera);
  requestAnimationFrame(tick);
})();

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight); labels.setSize(innerWidth, innerHeight);
});
