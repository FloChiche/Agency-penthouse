// Agent Tower — serveur local (aucune dépendance) :
//  • sert le site (web/)
//  • reçoit les hooks Claude Code (POST /hook)
//  • interroge n8n (local) et les limites d'usage Claude
//  • pousse l'état en direct au navigateur (Server-Sent Events, GET /stream)
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'web');
const CONFIG_PATH = path.join(ROOT, 'config.json');
const config = Object.assign(
  { port: 4317, n8n: { url: 'http://localhost:5678', apiKey: '' }, demo: false },
  fs.existsSync(CONFIG_PATH) ? JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')) : {}
);
if (process.argv.includes('--demo')) config.demo = true;

// ------------------------------------------------------------------ état
const AGENTS = {
  chatgpt:      { name: 'ChatGPT',     floor: 1, color: '#10a37f' },
  claude:       { name: 'Claude',      floor: 2, color: '#d4a27f' },
  n8n:          { name: 'n8n',         floor: 3, color: '#ea4b71' },
  'claude-code':{ name: 'Claude Code', floor: 4, color: '#d97757' },
};
const state = {
  agents: Object.fromEntries(Object.entries(AGENTS).map(([id, a]) =>
    [id, { id, ...a, status: 'off', detail: '', since: Date.now(), helpers: 0 }])),
  usage: { claude: null, chatgpt: null },
  n8n: { connected: false, today: 0, errors: 0, running: [] },
  feed: [],
  demo: config.demo,
};

const clients = new Set();
function broadcast(type, payload) {
  const msg = `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const res of clients) res.write(msg);
}
function log(agentId, text) {
  const item = { t: Date.now(), agent: agentId, text };
  state.feed.unshift(item);
  state.feed.length = Math.min(state.feed.length, 40);
  broadcast('feed', item);
}
function setAgent(id, patch, feedText) {
  const a = state.agents[id];
  if (!a) return;
  if (patch.status && patch.status !== a.status) a.since = Date.now();
  Object.assign(a, patch);
  broadcast('agent', a);
  if (feedText) log(id, feedText);
}

// ------------------------------------------------------------------ hooks Claude Code
// Les hooks envoient le JSON brut de Claude Code ; on n'en garde que le strict nécessaire
// (jamais le contenu des prompts).
const projectName = (cwd) => (cwd ? path.basename(cwd) : '');
function shortTarget(input = {}) {
  const p = input.file_path || input.path || input.notebook_path || '';
  if (p) return path.basename(p);
  if (input.command) return String(input.command).split(/\s+/)[0];
  if (input.pattern) return String(input.pattern).slice(0, 30);
  if (input.description) return String(input.description).slice(0, 40);
  return '';
}
function onHook(h) {
  const ev = h.hook_event_name;
  const proj = projectName(h.cwd);
  const a = state.agents['claude-code'];
  switch (ev) {
    case 'SessionStart':
      setAgent('claude-code', { status: 'idle', detail: proj }, `session ouverte · ${proj}`);
      break;
    case 'UserPromptSubmit':
      setAgent('claude-code', { status: 'working', detail: `réfléchit · ${proj}` }, `nouvelle tâche · ${proj}`);
      break;
    case 'PreToolUse': {
      const tool = h.tool_name || '';
      if (tool === 'Task' || tool === 'Agent') {
        setAgent('claude-code', { status: 'working', helpers: a.helpers + 1, detail: `délègue · ${shortTarget(h.tool_input)}` },
          `sous-agent lancé · ${shortTarget(h.tool_input)}`);
      } else {
        const tgt = shortTarget(h.tool_input);
        setAgent('claude-code', { status: 'working', detail: tgt ? `${tool} · ${tgt}` : tool });
      }
      break;
    }
    case 'SubagentStop':
      setAgent('claude-code', { helpers: Math.max(0, a.helpers - 1) }, 'sous-agent terminé');
      break;
    case 'Notification':
      setAgent('claude-code', { status: 'waiting', detail: 'attend ta réponse' }, 'attend ta réponse');
      break;
    case 'Stop':
      setAgent('claude-code', { status: 'idle', helpers: 0, detail: `a fini · ${proj}` }, `tâche terminée · ${proj}`);
      break;
    case 'SessionEnd':
      setAgent('claude-code', { status: 'off', helpers: 0, detail: '' }, 'session fermée');
      break;
  }
}

// ------------------------------------------------------------------ limites d'usage Claude
// Même source que la commande /usage de Claude Code (adresse interne Anthropic, non documentée :
// elle peut changer). Le jeton est lu localement et n'est envoyé qu'à api.anthropic.com.
async function pollClaudeUsage() {
  try {
    const cred = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.claude', '.credentials.json'), 'utf8'));
    const token = cred.claudeAiOauth && cred.claudeAiOauth.accessToken;
    if (!token) throw new Error('pas de jeton Claude');
    const r = await fetch('https://api.anthropic.com/api/oauth/usage', {
      headers: { Authorization: `Bearer ${token}`, 'anthropic-beta': 'oauth-2025-04-20' },
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const u = await r.json();
    const pick = (w) => (w ? { percent: Math.round(w.utilization ?? 0), resetsAt: w.resets_at || null } : null);
    state.usage.claude = { session: pick(u.five_hour), week: pick(u.seven_day), updated: Date.now() };
  } catch (e) {
    state.usage.claude = { error: String(e.message || e), updated: Date.now() };
  }
  broadcast('usage', state.usage);
}

// ------------------------------------------------------------------ n8n (local)
const workflowNames = new Map();
async function n8nGet(p) {
  const r = await fetch(config.n8n.url.replace(/\/$/, '') + p, { headers: { 'X-N8N-API-KEY': config.n8n.apiKey } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
const seenExecutions = new Set();
async function pollN8n() {
  if (!config.n8n.apiKey) { state.n8n.connected = false; return; }
  try {
    if (!workflowNames.size) {
      const wf = await n8nGet('/api/v1/workflows?limit=250');
      for (const w of wf.data || []) workflowNames.set(String(w.id), w.name);
    }
    const ex = await n8nGet('/api/v1/executions?limit=50');
    const list = ex.data || [];
    const today = new Date().toDateString();
    const running = list.filter((e) => !e.stoppedAt || e.status === 'running');
    const ofToday = list.filter((e) => new Date(e.startedAt).toDateString() === today);
    state.n8n = {
      connected: true,
      today: ofToday.length,
      errors: ofToday.filter((e) => e.status === 'error' || e.status === 'crashed').length,
      running: running.map((e) => workflowNames.get(String(e.workflowId)) || `workflow ${e.workflowId}`),
    };
    for (const e of list.slice(0, 10)) {
      const key = `${e.id}:${e.status}`;
      if (seenExecutions.has(key)) continue;
      const first = seenExecutions.size === 0;
      seenExecutions.add(key);
      if (first) continue;
      const wf = workflowNames.get(String(e.workflowId)) || e.workflowId;
      if (e.status === 'error' || e.status === 'crashed') log('n8n', `❌ « ${wf} » en erreur`);
      else if (e.status === 'success') log('n8n', `✅ « ${wf} » terminé`);
    }
    if (running.length) setAgent('n8n', { status: 'working', detail: `« ${state.n8n.running[0]} »` });
    else if (state.agents.n8n.status === 'working' || state.agents.n8n.status === 'off') setAgent('n8n', { status: 'idle', detail: 'en attente' });
  } catch (e) {
    state.n8n.connected = false;
    if (state.agents.n8n.status !== 'off') setAgent('n8n', { status: 'off', detail: 'n8n injoignable' });
  }
  broadcast('n8n', state.n8n);
}

// ------------------------------------------------------------------ mode démo
const DEMO_TASKS = {
  'claude-code': ['Edit · auth.ts', 'Bash · npm test', 'Read · server.js', 'délègue · revue de code', 'Write · README.md'],
  claude: ['rédige un e-mail', 'résume un PDF', 'brainstorm'],
  chatgpt: ['génère une image', 'traduit un texte', 'répond à une question'],
  n8n: ['« Leads → CRM »', '« Facture → Drive »', '« Veille RSS »'],
};
function demoTick() {
  if (!state.demo) return;
  const ids = Object.keys(AGENTS);
  const id = ids[Math.floor(Math.random() * ids.length)];
  const a = state.agents[id];
  if (a.status === 'working' && Math.random() < 0.6) {
    setAgent(id, { status: 'idle', helpers: 0, detail: 'a fini' }, `${a.name} a fini`);
  } else {
    const t = DEMO_TASKS[id][Math.floor(Math.random() * DEMO_TASKS[id].length)];
    const helpers = id === 'claude-code' && Math.random() < 0.3 ? 1 + Math.floor(Math.random() * 2) : 0;
    setAgent(id, { status: 'working', detail: t, helpers }, `${a.name} · ${t}`);
  }
}
function demoUsage() {
  if (!state.demo || (state.usage.claude && !state.usage.claude.error)) return;
  const reset = new Date(Date.now() + 2.4 * 3600e3).toISOString();
  state.usage.claude = { session: { percent: 42, resetsAt: reset }, week: { percent: 18, resetsAt: null }, demo: true, updated: Date.now() };
  broadcast('usage', state.usage);
}

// ------------------------------------------------------------------ HTTP
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.glb': 'model/gltf-binary',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
// Les requêtes qui passent par Tailscale (Serve/Funnel) portent ces en-têtes ; les hooks locaux non.
const viaProxy = (req) => req.headers['tailscale-funnel-request'] || req.headers['x-forwarded-for'];
const authorized = (req) => {
  if (!config.password) return true;
  const [, b64 = ''] = (req.headers.authorization || '').split(' ');
  return Buffer.from(b64, 'base64').toString().split(':').slice(1).join(':') === config.password;
};
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (viaProxy(req)) {
    if (url.pathname === '/hook') { res.writeHead(403).end(); return; }
    if (!authorized(req)) { res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="Agent Tower", charset="UTF-8"' }).end('mot de passe requis'); return; }
  }
  if (req.method === 'POST' && url.pathname === '/hook') {
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 1e6) req.destroy(); });
    req.on('end', () => {
      try { onHook(JSON.parse(body)); } catch { /* hook mal formé : ignoré */ }
      res.writeHead(204).end();
    });
    return;
  }
  if (url.pathname === '/stream') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
    res.write(`event: state\ndata: ${JSON.stringify(state)}\n\n`);
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }
  if (url.pathname === '/api/state') { res.writeHead(200, { 'Content-Type': MIME['.json'] }).end(JSON.stringify(state)); return; }
  if (req.method === 'POST' && url.pathname === '/api/demo') {
    state.demo = !state.demo;
    if (!state.demo) for (const id of Object.keys(AGENTS)) setAgent(id, { status: 'off', helpers: 0, detail: '' });
    broadcast('demo', state.demo);
    res.writeHead(200, { 'Content-Type': MIME['.json'] }).end(JSON.stringify({ demo: state.demo }));
    return;
  }
  const file = path.normalize(path.join(WEB, url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname)));
  if (!file.startsWith(WEB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end('introuvable'); return; }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Content-Length': fs.statSync(file).size });
  fs.createReadStream(file).pipe(res);
});

server.listen(config.port, '127.0.0.1', () => {
  console.log(`Agent Tower → http://localhost:${config.port}${config.demo ? '  (mode démo)' : ''}`);
});
setInterval(() => { for (const res of clients) res.write(': ping\n\n'); }, 20000);
pollClaudeUsage(); setInterval(pollClaudeUsage, 3 * 60e3);
pollN8n(); setInterval(pollN8n, 5000);
setInterval(demoTick, 4000); demoUsage(); setInterval(demoUsage, 10000);
