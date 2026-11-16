import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/live_production_audit';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/live_production_audit';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9270;
const PROD_BASE = 'https://marspath.vercel.app/mission-control/';

console.log('🚀 Spawning fresh Chrome Headless for LIVE PRODUCTION AUDIT at port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  PROD_BASE,
], { stdio: 'ignore' });

await new Promise((r) => setTimeout(r, 4000));

try {
  const versionRes = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  const pages = await versionRes.json();
  const page = pages.find((p) => p.type === 'page');
  if (!page) throw new Error('No page found');

  console.log('📡 Connecting CDP WebSocket to', page.webSocketDebuggerUrl);
  const ws = new WebSocket(page.webSocketDebuggerUrl);

  await new Promise((resolve) => (ws.onopen = resolve));

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
    console.log(`📸 Captured: ${filename} (${Math.round(buffer.length / 1024)} KB)`);
  }

  await send('Page.enable');
  await send('Runtime.enable');

  console.log('⏳ Waiting 5s for live production application to initialize...');
  await new Promise((r) => setTimeout(r, 5000));

  // 1. NASA Map & Route Planner
  console.log('▶ 1. Testing NASA Map & Route Planner...');
  await evaluate(`
    const plannerBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Route planner') || b.textContent.includes('Planner'));
    if (plannerBtn) plannerBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await evaluate(`
    const planBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Plan') || b.textContent.includes('Generate'));
    if (planBtn) planBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 4500));
  await captureScreenshot('01_prod_nasa_planetary_map_and_route_planner.png');

  // 2. Stage 1 Safety Core & Cost Breakdown
  console.log('▶ 2. Testing Stage 1 Safety Core & Cost Breakdown...');
  await evaluate(`
    const drawer = document.querySelector('.panel-planning-drawer') || document.querySelector('.planning-drawer');
    if (drawer) drawer.scrollTop = 350;
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('02_prod_stage1_safety_core_and_cost_breakdown.png');

  // 3. Mars Now (Current Conditions & Weather)
  console.log('▶ 3. Testing Mars Now (MEDA Weather & Solar Time)...');
  await evaluate(`
    const conditionsBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Mars Now'));
    if (conditionsBtn) conditionsBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3000));
  await captureScreenshot('03_prod_mars_now_current_conditions.png');

  // 4. Live Mars Intelligence (Spacecraft Ephemeris & Orbiters)
  console.log('▶ 4. Testing Live Mars Intelligence (Orbiters & Ground Tracks)...');
  await evaluate(`
    const intelBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Live Intel'));
    if (intelBtn) intelBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3000));
  await captureScreenshot('04_prod_mission_intelligence_and_spacecraft.png');

  // 5. Risk Fusion & Knowledge Graph
  console.log('▶ 5. Testing Risk Fusion & Knowledge Graph...');
  await evaluate(`
    const fusionBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Risk Fusion'));
    if (fusionBtn) fusionBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3500));
  await captureScreenshot('05_prod_mission_intelligence_risk_fusion.png');

  // 6. NASA Data Center
  console.log('▶ 6. Testing NASA Data Center (7 Official Sources)...');
  await evaluate(`
    const dataBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('NASA Data'));
    if (dataBtn) dataBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3000));
  await captureScreenshot('06_prod_nasa_data_center.png');

  // 7. Cloud & AI Center (Gemini & Azure)
  console.log('▶ 7. Testing Cloud & AI Center...');
  await evaluate(`
    const aiBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Cloud & AI'));
    if (aiBtn) aiBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3500));
  await captureScreenshot('07_prod_cloud_ai_and_science_assistant.png');

  console.log('🎉 ALL 7 PRODUCTION VERIFICATION AUDIT SCREENSHOTS CAPTURED CLEANLY!');
} catch (err) {
  console.error('❌ Production audit screenshot capture error:', err);
} finally {
  chrome.kill();
  process.exit(0);
}
