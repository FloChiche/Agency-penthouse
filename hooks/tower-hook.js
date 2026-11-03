// Hook Claude Code → Agent Tower. Transmet l'événement au serveur local puis rend la main
// immédiatement : si la tour n'est pas lancée, Claude Code n'est jamais ralenti ni bloqué.
const http = require('http');

let body = '';
process.stdin.on('data', (c) => { body += c; });
process.stdin.on('end', () => {
  const req = http.request(
    { host: '127.0.0.1', port: 4317, path: '/hook', method: 'POST', headers: { 'Content-Type': 'application/json' }, timeout: 400 },
    () => process.exit(0)
  );
  req.on('error', () => process.exit(0));
  req.on('timeout', () => { req.destroy(); process.exit(0); });
  req.end(body);
});
setTimeout(() => process.exit(0), 800);
