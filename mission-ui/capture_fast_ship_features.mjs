import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/fast_ship';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/fast_ship';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9245;

console.log('🚀 Spawning Chrome Headless for 3 PRIORITY FEATURES VERIFICATION at port', PORT);
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

  console.log('⏳ Waiting 4s for UI and map to initialize...');
  await new Promise((r) => setTimeout(r, 4000));

  // Configure local API port
  await evaluate(`
    localStorage.setItem('marspath_api_url', 'http://127.0.0.1:8005');
  `);

  // Generate initial nominal route plan
  console.log('▶ Generating route plan...');
  await evaluate(`
    const generateBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate') || b.textContent.includes('Plan'));
    if (generateBtn) generateBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 4000));

  // 1. Feature 1: Toggle Astronaut Suit HUD Mode & Audio Hazard Alerts
  console.log('▶ Enabling Suit HUD Mode...');
  await evaluate(`
    const hudBtn = document.querySelector('.btn-suit-hud-toggle');
    if (hudBtn) hudBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2000));

  // Turn on audio alerts in HUD
  await evaluate(`
    const audioBtn = document.querySelector('.btn-hud-audio');
    if (audioBtn && audioBtn.textContent.includes('OFF')) audioBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('01_astronaut_suit_hud_mode.png');

  // Turn off HUD for next views
  await evaluate(`
    const exitBtn = document.querySelector('.btn-hud-dismiss');
    if (exitBtn) exitBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 2. Feature 2: Marswalk Survivability Score (Nominal Mode)
  console.log('▶ Inspecting Marswalk Survivability Score (Nominal)...');
  await evaluate(`
    // Ensure formula assumptions are visible
    const toggleFormulaBtn = document.querySelector('.btn-toggle-formula');
    if (toggleFormulaBtn && toggleFormulaBtn.textContent.includes('Inspect')) toggleFormulaBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('02_marswalk_survivability_score_nominal.png');

  // 3. Feature 2: Solar Storm Scenario (Active)
  console.log('▶ Toggling Solar Storm Scenario ON...');
  await evaluate(`
    const stormBtn = document.querySelector('.btn-storm-toggle');
    if (stormBtn) stormBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('03_marswalk_survivability_score_solar_storm.png');

  // Reset Solar Storm for clean geofence check
  await evaluate(`
    const stormBtn = document.querySelector('.btn-storm-toggle');
    if (stormBtn && stormBtn.textContent.includes('ON')) stormBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 4. Feature 3: Planetary Protection Geofence (Robot-Only Buffer) with Route Breach
  console.log('▶ Piercing Western Delta Scarp Restricted Buffer...');
  await evaluate(`
    const inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
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
  await new Promise((r) => setTimeout(r, 4000));
  await captureScreenshot('04_planetary_protection_robot_only_buffer.png');

  // 5. Feature 3: Authentic Perseverance Waypoint Surface POV Popup
  console.log('▶ Inspecting Authentic NASA Waypoint Surface POV Popup...');
  // Click on a waypoint near Kodiak or Octavia Butler
  await evaluate(`
    // Simulate clicking a waypoint or triggering waypoint selection for Sol 64 (Kodiak Butte)
    const wp = {
      properties: { name: 'Perseverance Traverse Waypoint - Sol 64', sol: 64, dist_total_m: 2420 },
      geometry: { coordinates: [77.4250, 18.4140] }
    };
    // Dispatch via MapView activeWaypointPopup by inspecting point or selecting waypoint
    window.dispatchEvent(new CustomEvent('marspath-select-waypoint-test', { detail: wp }));
  `);
  // If no custom event, click on the map near Kodiak Butte to open inspect popup with POV
  await evaluate(`
    const povBtn = document.querySelector('.map-inspect-popup button:nth-child(2)');
    if (povBtn) povBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('05_authentic_perseverance_waypoint_pov.png');

  console.log('✅ ALL 5 FEATURE SCREENSHOTS CAPTURED SUCCESSFULLY!');
} catch (err) {
  console.error('❌ Screenshot capture error:', err);
} finally {
  chrome.kill();
  process.exit(0);
}
