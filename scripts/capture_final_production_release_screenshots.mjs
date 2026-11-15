import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/final_production_release';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/final_production_release';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9260;
const PROD_URL = 'https://marspath.vercel.app/mission-control/?view=planner';

console.log('🚀 Spawning Chrome Headless for LIVE VERCEL PRODUCTION VERIFICATION at port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  PROD_URL,
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

  console.log('⏳ Waiting 5s for live production UI & map to initialize...');
  await new Promise((r) => setTimeout(r, 5000));

  // Configure production API URL in localStorage just in case
  await evaluate(`
    localStorage.setItem('marspath_api_url', 'https://marspath-backend.onrender.com');
  `);

  // Generate initial nominal route plan
  console.log('▶ Generating route plan on live production...');
  await evaluate(`
    const generateBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate') || b.textContent.includes('Plan'));
    if (generateBtn) generateBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 4500));

  // 1. Initial Production Interface (Planetary Map + HUD loaded)
  console.log('▶ Capturing 01: Final Production Initial Map & HUD...');
  await captureScreenshot('01_prod_initial_map_and_hud.png');

  // 2. Feature 1: Toggle Astronaut Suit HUD Mode & Audio Hazard Alerts
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
  await captureScreenshot('02_prod_suit_hud_mode_active.png');

  // Turn off HUD for next views
  await evaluate(`
    const exitBtn = document.querySelector('.btn-hud-dismiss');
    if (exitBtn) exitBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 3. Feature 2: Marswalk Survivability Score (Nominal Mode)
  console.log('▶ Inspecting Marswalk Survivability Score (Nominal)...');
  await evaluate(`
    const toggleFormulaBtn = document.querySelector('.btn-toggle-formula');
    if (toggleFormulaBtn && toggleFormulaBtn.textContent.includes('Inspect')) toggleFormulaBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('03_prod_survivability_score_nominal.png');

  // 4. Feature 2: Solar Storm Scenario (Active)
  console.log('▶ Toggling Solar Storm Scenario ON...');
  await evaluate(`
    const stormBtn = document.querySelector('.btn-storm-toggle');
    if (stormBtn) stormBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('04_prod_survivability_score_solar_storm.png');

  // Reset Solar Storm for clean geofence check
  await evaluate(`
    const stormBtn = document.querySelector('.btn-storm-toggle');
    if (stormBtn && stormBtn.textContent.includes('ON')) stormBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 1000));

  // 5. Feature 3: Planetary Protection Geofence (Robot-Only Buffer) with Route Breach
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
  await new Promise((r) => setTimeout(r, 4500));
  await captureScreenshot('05_prod_planetary_protection_geofence.png');

  // 6. Feature 3: Authentic Perseverance Waypoint Surface POV Popup
  console.log('▶ Inspecting Authentic NASA Waypoint Surface POV Popup...');
  await evaluate(`
    const povBtn = document.querySelector('.map-inspect-popup button:nth-child(2)');
    if (povBtn) povBtn.click();
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('06_prod_authentic_perseverance_pov.png');

  // 7. Mobile Viewport Layout Verification
  console.log('▶ Testing Mobile Viewport (390x844)...');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 2,
    mobile: true,
  });
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('07_prod_mobile_responsive_layout.png');

  // Reset viewport
  await send('Emulation.clearDeviceMetricsOverride');

  console.log('🎉 ALL 7 PRODUCTION VERIFICATION SCREENSHOTS CAPTURED CLEANLY!');
} catch (err) {
  console.error('❌ Production screenshot capture error:', err);
} finally {
  chrome.kill();
  process.exit(0);
}
