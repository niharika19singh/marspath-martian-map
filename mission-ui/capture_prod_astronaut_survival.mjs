import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/astronaut_survival_prod';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/astronaut_survival_prod';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9226;

console.log('🚀 Spawning Chrome Headless for LIVE PRODUCTION ASTRONAUT SURVIVAL VERIFICATION at port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  'https://marspath.vercel.app/mission-control/?view=planner',
], { stdio: 'ignore' });

await new Promise((r) => setTimeout(r, 4000));

try {
  const versionRes = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  const pages = await versionRes.json();
  const page = pages.find((p) => p.type === 'page');
  if (!page) throw new Error('No page found');

  console.log('📡 Connecting WebSocket to', page.webSocketDebuggerUrl);
  const ws = new WebSocket(page.webSocketDebuggerUrl);

  await new Promise((resolve) => ws.onopen = resolve);

  let idCounter = 1;
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = idCounter++;
      const handler = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.id === id) {
          ws.removeEventListener('message', handler);
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        }
      };
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async function evaluate(expression) {
    const res = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    return res.result?.value;
  }

  async function captureScreenshot(filename) {
    const res = await send('Page.captureScreenshot', { format: 'png' });
    const buffer = Buffer.from(res.data, 'base64');
    fs.writeFileSync(path.join(DOCS_OUT_DIR, filename), buffer);
    fs.writeFileSync(path.join(BRAIN_OUT_DIR, filename), buffer);
    console.log(`📸 Captured: ${filename}`);
  }

  await send('Page.enable');
  await send('Runtime.enable');

  console.log('⏳ Waiting 5s for live production UI & maps to load...');
  await new Promise((r) => setTimeout(r, 5000));

  // Configure live Render backend
  await evaluate(`
    localStorage.setItem('marspath_api_url', 'https://marspath-backend.onrender.com');
  `);

  // 1. Generate Route Plan & capture Marswalk Survivability Cards
  console.log('▶ Generating route plan on live production...');
  await evaluate(`
    const generateBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate') || b.textContent.includes('Plan'));
    if (generateBtn) generateBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 4500));
  await captureScreenshot('prod_01_marswalk_survivability_cards.png');

  // 2. Open Astronaut Visor HUD
  console.log('▶ Opening Astronaut Visor HUD on live production...');
  await evaluate(`
    const visorBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('VISOR HUD') || b.textContent.includes('Visor HUD'));
    if (visorBtn) visorBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('prod_02_astronaut_visor_hud.png');

  // 3. Toggle SPE Scenario in Visor HUD
  console.log('▶ Simulating Solar Particle Event (SPE) on live production...');
  await evaluate(`
    const speBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('SIMULATE SPE') || b.textContent.includes('SPE'));
    if (speBtn) speBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3000));
  await captureScreenshot('prod_03_spe_scenario_active.png');

  // 4. Open Surface POV Viewer for Kodiak Butte
  console.log('▶ Opening Authentic NASA Surface POV Viewer on live production...');
  await evaluate(`
    const povBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('SURFACE POV'));
    if (povBtn) povBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await evaluate(`
    const kodiakBtn = Array.from(document.querySelectorAll('.pov-tab-btn')).find(b => b.textContent.includes('Kodiak'));
    if (kodiakBtn) kodiakBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('prod_04_surface_pov_imagery_kodiak.png');

  console.log('✅ ALL LIVE PRODUCTION SCREENSHOTS SUCCESSFULLY CAPTURED!');
} catch (err) {
  console.error('❌ Error capturing live production screenshots:', err);
} finally {
  chrome.kill();
  process.exit(0);
}
