// Minimal MCP stdio client for the WeChat DevTools `wechatide mcp` server.
// Usage: node wechatide-mcp.cjs <toolName> '<jsonArgs>'
// Prints the tool result JSON so screenshots can be located.
const { spawn } = require('child_process');

const CLI = 'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\wechatide.cmd';
const TOKEN = process.env.WECHATIDE_TOKEN || 'OpY7VoOEKr2C6nDZRgdTYUQU_FU9YNg-';
const tool = process.argv[2];
const args = process.argv[3] ? JSON.parse(process.argv[3]) : {};
if (!tool) { console.error('usage: node wechatide-mcp.cjs <toolName> <jsonArgs>'); process.exit(2); }

const child = spawn('cmd', ['/c', CLI, 'mcp', `--token=${TOKEN}`], {
  stdio: ['pipe', 'pipe', 'pipe'],
  windowsHide: true,
});

let buf = '';
const pending = new Map();
let settled = false;

function send(msg) {
  child.stdin.write(JSON.stringify(msg) + '\n');
}

function finish(code, payload) {
  if (settled) return;
  settled = true;
  if (payload !== undefined) console.log(JSON.stringify(payload, null, 2));
  try { child.kill(); } catch (e) {}
  setTimeout(() => process.exit(code), 200);
}

child.stdout.on('data', (d) => {
  buf += d.toString('utf8');
  let idx;
  while ((idx = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, idx).trim();
    buf = buf.slice(idx + 1);
    if (!line) continue;
    let msg;
    try { msg = JSON.parse(line); } catch (e) { continue; }
    if (msg.id !== undefined && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  }
});

child.stderr.on('data', (d) => { process.stderr.write('[stderr] ' + d.toString('utf8')); });

function request(id, method, params) {
  return new Promise((resolve, reject) => {
    pending.set(id, resolve);
    setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('timeout ' + method)); } }, 45000);
    send({ jsonrpc: '2.0', id, method, params });
  });
}

(async () => {
  const init = await request(1, 'initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'workbuddy', version: '1.0.0' },
  });
  if (init.error) return finish(1, init);
  send({ jsonrpc: '2.0', method: 'notifications/initialized' });

  const call = await request(2, 'tools/call', { name: tool, arguments: args });
  if (call.error) return finish(1, call);
  // MCP returns { content: [{type:'text', text:'...json...'}] }; unwrap when possible.
  let payload = call.result;
  try {
    const text = call.result && call.result.content && call.result.content[0] && call.result.content[0].text;
    if (text) payload = JSON.parse(text);
  } catch (e) {}
  finish(0, payload);
})().catch((e) => finish(1, { error: String(e && e.message || e) }));

setTimeout(() => finish(1, { error: 'overall timeout' }), 60000);
