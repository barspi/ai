// Hover test for the pop-ups of collapsed boxes, in a real headless Chromium (through the DevTools protocol, no packages).
// usage: node test_hover.mjs diagram.svg 101 110 [--shot out.png]
// For each box number: scroll it into view, move the pointer to its centre, then print whether the pop-up became visible and which
// element is on top at the pointer (it must be the pop-up: `pop101`). Exit code 1 when a pop-up did not show.
// Browser: CHROME=/path/to/chrome, else Chrome, Chromium, Brave or Edge in the usual macOS/Linux places. Needs Node 22 or later
// (global WebSocket and fetch). A browser started from a sandbox needs the sandbox off for that command.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const shotAt = args.indexOf('--shot');
const shot = shotAt >= 0 ? args.splice(shotAt, 2)[1] : null;
const file = args.shift();
const nums = args.map(Number);
if (!file || !nums.length) { console.error('usage: node test_hover.mjs diagram.svg N [N...] [--shot out.png]'); process.exit(2); }

const candidates = [process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge'].filter(Boolean);
const exe = candidates.find((p) => fs.existsSync(p));
if (!exe) { console.error('no Chromium-based browser found; set CHROME=/path/to/browser'); process.exit(2); }

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hover-'));
const port = 9300 + Math.floor(Math.random() * 500);
const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, '--no-first-run',
  '--window-size=1600,1000', '--allow-file-access-from-files', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets = [];
for (let i = 0; i < 40 && !targets.length; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch (e) { await sleep(500); }
}
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let id = 0; const pending = {};
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending[d.id]) { pending[d.id](d); delete pending[d.id]; } };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.result?.value;

await send('Page.enable');
await send('Page.navigate', { url: 'file://' + path.resolve(file) });
await sleep(4000);                                   // the find-box script moves the drawing into an inner svg at load
let bad = 0;
for (const n of nums) {
  const c = await ev(`(()=>{const e=document.getElementById('n${n}');if(!e)return null;e.scrollIntoView({block:'center',inline:'center'});const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()`);
  if (!c) { console.log(`#${n}: no such box`); bad++; continue; }
  // leave the previous box first: its open pop-up may cover this box (it is drawn full size over its neighbours), and a pointer that
  // jumps from one box to the next would land on that pop-up, not on this box
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 1, y: 1 });
  await sleep(300);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: c[0], y: c[1] });
  await sleep(400);
  const r = JSON.parse(await ev(`(()=>{const p=document.getElementById('pop${n}');if(!p)return JSON.stringify({err:'no pop-up'});const cs=getComputedStyle(p);const t=document.elementFromPoint(${c[0]},${c[1]});return JSON.stringify({visible:cs.visibility,opacity:cs.opacity,top:t&&(t.closest('g')?.id||t.nodeName),siblings:!!document.querySelector('#n${n} ~ #pop${n}')})})()`));
  const ok = r.visible === 'visible' && r.top === 'pop' + n;
  if (!ok) bad++;
  console.log(`#${n}: ${ok ? 'OK' : 'FAIL'} ${JSON.stringify(r)}`);
  if (shot && n === nums[0]) fs.writeFileSync(shot, Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64'));
}
ws.close(); proc.kill();
process.exit(bad ? 1 : 0);
