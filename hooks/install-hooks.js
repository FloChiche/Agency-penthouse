// Ajoute (ou retire avec --remove) les hooks Agent Tower dans ~/.claude/settings.json.
// Une copie de sauvegarde est faite avant toute modification ; les autres réglages ne sont pas touchés.
const fs = require('fs');
const path = require('path');
const os = require('os');

const SETTINGS = path.join(os.homedir(), '.claude', 'settings.json');
const HOOK = path.join(__dirname, 'tower-hook.js').replace(/\\/g, '/');
const COMMAND = `node "${HOOK}"`;
const EVENTS = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'SubagentStop', 'Notification', 'Stop', 'SessionEnd'];
const remove = process.argv.includes('--remove');

const settings = fs.existsSync(SETTINGS) ? JSON.parse(fs.readFileSync(SETTINGS, 'utf8')) : {};
if (fs.existsSync(SETTINGS)) fs.copyFileSync(SETTINGS, `${SETTINGS}.bak-agent-tower`);
settings.hooks = settings.hooks || {};

for (const ev of EVENTS) {
  const groups = (settings.hooks[ev] || [])
    .map((g) => ({ ...g, hooks: (g.hooks || []).filter((h) => h.command !== COMMAND) }))
    .filter((g) => g.hooks.length);
  if (!remove) groups.push({ ...(ev === 'PreToolUse' ? { matcher: '*' } : {}), hooks: [{ type: 'command', command: COMMAND, timeout: 2 }] });
  if (groups.length) settings.hooks[ev] = groups; else delete settings.hooks[ev];
}
if (!Object.keys(settings.hooks).length) delete settings.hooks;

fs.mkdirSync(path.dirname(SETTINGS), { recursive: true });
fs.writeFileSync(SETTINGS, JSON.stringify(settings, null, 2));
console.log(remove ? 'Hooks Agent Tower retirés.' : `Hooks Agent Tower installés dans ${SETTINGS}`);
