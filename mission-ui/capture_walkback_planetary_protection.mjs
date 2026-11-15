import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/walkback_geofence';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/walkback_geofence';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9226;

console.log('🚀 Spawning Chrome Headless for WALK-BACK & PLANETARY PROTECTION VERIFICATION at port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  'http://127.0.0.1:3000/mission-control/?view=planner',
], { stdio: 'ignore' });

await new Promise((r) => setTimeout(r, 3000));

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

  console.log('⏳ Waiting 4s for UI and terrain to initialize...');
  await new Promise((r) => setTimeout(r, 4000));

  // Configure local API endpoint port 8005
  await evaluate(`
    localStorage.setItem('marspath_api_url', 'http://127.0.0.1:8005');
  `);

  // 1. Generate Route Plan & capture Dual-Radius Envelopes & Walk-Back Safety
  console.log('▶ Generating route plan...');
  await evaluate(`
    const generateBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate') || b.textContent.includes('Plan'));
    if (generateBtn) generateBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3500));
  await captureScreenshot('01_dual_radius_walkback_envelopes.png');

  // 2. Open High-Difficulty Bottlenecks details
  console.log('▶ Expanding Walk-Back Bottlenecks & Details...');
  await evaluate(`
    const segBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('View Segments'));
    if (segBtn) segBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 3. Select Destination crossing Western Delta Scarp (Official Restricted Zone)
  console.log('▶ Setting Destination to pierce Western Delta Scarp Restricted Zone...');
  await evaluate(`
    const inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
    // Find dest lat/lon inputs
    const destLonInput = document.querySelector('input[placeholder*="Dest Longitude"], input[name*="dest_lon"]') || inputs[2];
    const destLatInput = document.querySelector('input[placeholder*="Dest Latitude"], input[name*="dest_lat"]') || inputs[3];
    if (destLonInput && destLatInput) {
      destLonInput.value = '77.4360';
      destLonInput.dispatchEvent(new Event('input', { bubbles: true }));
      destLatInput.value = '18.4550';
      destLatInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const genBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate') || b.textContent.includes('Plan'));
    if (genBtn) genBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 3500));
  await captureScreenshot('02_walkback_limit_exceeded_warning.png');
  await captureScreenshot('03_planetary_protection_geofence_map.png');

  // 4. Inspect Special-Region Information Panel
  console.log('▶ Inspecting Special-Region Information Panel for Delta Scarp...');
  await evaluate(`
    const selectElem = document.querySelector('.zone-selector-dropdown');
    if (selectElem) {
      selectElem.value = 'ppz_jezero_delta_aquifer';
      selectElem.dispatchEvent(new Event('change', { bubbles: true }));
    }
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('04_special_region_information_panel.png');

  // 5. Open Scout Rover Reconnaissance Request Modal
  console.log('▶ Opening Simulated Scout Rover Reconnaissance Request Modal...');
  await evaluate(`
    const scoutBtn = document.querySelector('.btn-scout-dispatch');
    if (scoutBtn) scoutBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('05_scout_rover_simulated_dispatch.png');

  // Close scout modal
  await evaluate(`
    const closeBtn = document.querySelector('.scout-modal .close-btn');
    if (closeBtn) closeBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 6. Open Orbiter Pass Schedule / RF Comms Modal
  console.log('▶ Opening Orbiter Relay Schedule Modal...');
  await evaluate(`
    const orbBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Orbiter Pass'));
    if (orbBtn) orbBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('06_rf_line_of_sight_status.png');

  console.log('✅ ALL 6 WALK-BACK & PLANETARY PROTECTION SCREENSHOTS CAPTURED!');
} catch (err) {
  console.error('❌ Error capturing screenshots:', err);
} finally {
  chrome.kill();
  process.exit(0);
}
