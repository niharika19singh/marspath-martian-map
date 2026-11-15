import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const SCREENSHOT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/prod_verification';
const PROD_URL = 'https://marspath.vercel.app/mission-control/?view=planner';

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function connectToChrome(port) {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`);
      const tabs = await res.json();
      if (tabs.length > 0 && tabs[0].webSocketDebuggerUrl) {
        return tabs[0].webSocketDebuggerUrl;
      }
    } catch {}
    await delay(500);
  }
  throw new Error('Could not connect to Chrome debugging port.');
}

async function run() {
  console.log('🚀 Launching Headless Chrome for Live Production Verification...');
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    '--disable-gpu',
    '--remote-debugging-port=9240',
    '--remote-allow-origins=*',
    '--window-size=1440,900',
    PROD_URL
  ], { stdio: 'ignore' });

  try {
    const wsUrl = await connectToChrome(9240);
    const ws = new WebSocket(wsUrl);
    await new Promise(r => ws.onopen = r);

    let idCounter = 1;
    function send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = idCounter++;
        const handler = (event) => {
          const msg = JSON.parse(event.data);
          if (msg.id === id) {
            ws.removeEventListener('message', handler);
            if (msg.error) reject(new Error(msg.error.message));
            else resolve(msg.result);
          }
        };
        ws.addEventListener('message', handler);
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    async function evalCode(expression) {
      const res = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      return res?.result?.value;
    }

    async function captureScreenshot(filename) {
      const { data } = await send('Page.captureScreenshot', { format: 'png' });
      const filepath = path.join(SCREENSHOT_DIR, filename);
      fs.writeFileSync(filepath, Buffer.from(data, 'base64'));
      console.log(`📸 Captured: ${filename}`);
    }

    await send('Page.enable');
    await send('Runtime.enable');

    console.log('⏳ Waiting for production page to load...');
    await delay(6000);

    // 1. Initial Map View
    console.log('Checking map canvas...');
    await captureScreenshot('prod_01_planetary_map_loaded.png');

    // 2. Select Delta Traverse Preset and Plan Route
    console.log('Clicking Delta Traverse preset...');
    await evalCode(`
      const chips = Array.from(document.querySelectorAll('.preset-chip'));
      const deltaChip = chips.find(c => c.textContent.includes('Western Delta') || c.textContent.includes('Delta'));
      if (deltaChip) deltaChip.click();
    `);
    await delay(1000);

    console.log('Clicking Plan Route button on live backend...');
    await evalCode(`
      const planBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Plan Route') || b.textContent.includes('Plan Multi-Objective'));
      if (planBtn) planBtn.click();
    `);

    // Wait for route planning on production Render backend
    console.log('Waiting for route plan response from Render...');
    for (let i = 0; i < 20; i++) {
      const hudSelector = await evalCode(`document.querySelector('.map-hud-route-selector') !== null`);
      if (hudSelector) {
        console.log('✓ Route candidates received from production backend!');
        break;
      }
      await delay(1000);
    }
    await delay(2000);

    // 3. Capture Map HUD Corridor Selector & Map Path
    await captureScreenshot('prod_02_route_candidates_hud.png');

    // 4. Switch Candidate Corridor via Map HUD
    console.log('Clicking alternative candidate corridor on Map HUD...');
    await evalCode(`
      const badges = document.querySelectorAll('.route-candidate-badge');
      if (badges.length > 1) badges[1].click();
    `);
    await delay(1500);
    await captureScreenshot('prod_03_alternative_candidate_selected.png');

    // 5. Inspect Left Drawer: Cost Breakdown & Resources
    console.log('Capturing Cost & Terrain Breakdown with MMRTG notice...');
    await captureScreenshot('prod_04_cost_breakdown_and_resources.png');

    // 6. Test Quick Navigation to Robustness / Deep Intelligence
    console.log('Clicking Robustness quick-navigation pill...');
    await evalCode(`
      const pills = Array.from(document.querySelectorAll('.intel-pill'));
      const robPill = pills.find(p => p.textContent.includes('Robustness'));
      if (robPill) robPill.click();
    `);
    await delay(2000);
    await captureScreenshot('prod_05_robustness_and_deep_intel.png');

    // 7. Verify Return Zone Isochrone Legend and Map Overlay
    console.log('Toggling Return Zone Isochrone overlay...');
    await evalCode(`
      const chk = document.querySelector('.return-legend-toggle input');
      if (chk && !chk.checked) chk.click();
    `);
    await delay(1500);
    await captureScreenshot('prod_06_return_zone_isochrone.png');

    console.log('🎉 All live production browser verification screenshots captured successfully!');
    ws.close();
  } finally {
    chrome.kill();
  }
}

run().catch(err => {
  console.error('❌ Verification failed:', err);
  process.exit(1);
});
