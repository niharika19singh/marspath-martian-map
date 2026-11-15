import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const PORT = 9228;
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ARTIFACTS_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/p1_verification';
const LOCAL_SCREENSHOTS_DIR = path.resolve('docs/screenshots/p1_remediation');

if (!fs.existsSync(ARTIFACTS_DIR)) fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
if (!fs.existsSync(LOCAL_SCREENSHOTS_DIR)) fs.mkdirSync(LOCAL_SCREENSHOTS_DIR, { recursive: true });

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  console.log('Launching headless Chrome with CDP on port', PORT);
  const chromeProc = spawn(
    CHROME_PATH,
    [
      '--headless=new',
      '--disable-gpu',
      `--remote-debugging-port=${PORT}`,
      '--remote-allow-origins=*',
      '--window-size=1440,900',
      '--no-first-run',
      '--no-default-browser-check',
      'http://127.0.0.1:3000/mission-control/?view=planner',
    ],
    { stdio: 'ignore' }
  );

  try {
    let connected = false;
    for (let i = 0; i < 20; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${PORT}/json/list`);
        if (res.ok) {
          const list = await res.json();
          if (list && list.length > 0 && list[0].webSocketDebuggerUrl) {
            connected = true;
            break;
          }
        }
      } catch (e) {
        await sleep(500);
      }
    }
    if (!connected) throw new Error('Chrome remote debugging did not respond');

    const listRes = await fetch(`http://127.0.0.1:${PORT}/json/list`);
    const tabs = await listRes.json();
    const target = tabs.find((t) => t.type === 'page') || tabs[0];
    const ws = new WebSocket(target.webSocketDebuggerUrl);

    let idCounter = 1;
    const callbacks = new Map();

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id && callbacks.has(data.id)) {
        const { resolve, reject } = callbacks.get(data.id);
        callbacks.delete(data.id);
        if (data.error) reject(new Error(data.error.message));
        else resolve(data.result);
      }
    };

    await new Promise((resolve) => (ws.onopen = resolve));

    function sendCommand(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = idCounter++;
        callbacks.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    async function evaluate(expression) {
      const res = await sendCommand('Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true,
      });
      return res.result?.value;
    }

    async function captureScreenshot(filename) {
      console.log(`Capturing screenshot: ${filename}...`);
      const { data } = await sendCommand('Page.captureScreenshot', { format: 'png' });
      const buffer = Buffer.from(data, 'base64');
      const artifactPath = path.join(ARTIFACTS_DIR, filename);
      const localPath = path.join(LOCAL_SCREENSHOTS_DIR, filename);
      fs.writeFileSync(artifactPath, buffer);
      fs.writeFileSync(localPath, buffer);
      console.log(`Saved to ${artifactPath} (${buffer.length} bytes)`);
    }

    await sendCommand('Page.enable');
    await sendCommand('Runtime.enable');
    await sendCommand('Network.enable');

    console.log('Waiting 5 seconds for page load and initial WMTS tiles...');
    await sleep(5000);

    // Step 1: Select Preset 1 (Jezero Delta Fan) and compute route
    console.log('Step 1: Selecting preset and computing Martian route...');
    await evaluate(`(() => {
      const presetBtn = document.querySelector('.preset-chip') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Delta'));
      if (presetBtn) presetBtn.click();
    })()`);
    await sleep(1000);

    await evaluate(`(() => {
      const planBtn = document.querySelector('.plan-button') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Generate route'));
      if (planBtn) planBtn.click();
    })()`);
    console.log('Waiting 4 seconds for route calculation and candidate rendering...');
    await sleep(4500);

    // 1. Primary Map HUD Route Candidates
    console.log('Capturing: p1_01_primary_map_hud_route_candidates.png');
    await captureScreenshot('p1_01_primary_map_hud_route_candidates.png');

    // 2. Select Alternative Corridor 1 on HUD
    console.log('Step 2: Selecting Alternative Corridor on Map HUD...');
    await evaluate(`(() => {
      const altCard = document.querySelectorAll('.hud-candidate-card')[1];
      if (altCard) altCard.click();
    })()`);
    await sleep(1500);
    console.log('Capturing: p1_02_alternative_corridor_selected.png');
    await captureScreenshot('p1_02_alternative_corridor_selected.png');

    // 3. Right Analysis Drawer: Mission Resources & Temporal Budget
    console.log('Step 3: Ensuring Right Analysis Drawer is expanded...');
    await evaluate(`(() => {
      const rightDrawer = document.querySelector('.floating-analysis');
      if (rightDrawer && !rightDrawer.classList.contains('expanded')) {
        const toggle = document.querySelector('.analysis-toggle');
        if (toggle) toggle.click();
      }
      const ovTab = Array.from(document.querySelectorAll('.tab-button')).find(b => b.textContent.includes('Overview'));
      if (ovTab) ovTab.click();
      const resCard = document.querySelector('.mission-resources-card');
      if (resCard) resCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    })()`);
    await sleep(1500);
    console.log('Capturing: p1_03_mission_resources_temporal_budget.png');
    await captureScreenshot('p1_03_mission_resources_temporal_budget.png');

    // 4. Cost Breakdown & Educational Energy Model Notice
    console.log('Step 4: Scrolling to Cost Breakdown and Educational Energy Notice...');
    await evaluate(`(() => {
      const detailsEl = document.querySelector('.analysis-details');
      if (detailsEl) {
        detailsEl.open = true;
        detailsEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    })()`);
    await sleep(1500);
    console.log('Capturing: p1_04_cost_breakdown_and_energy_notice.png');
    await captureScreenshot('p1_04_cost_breakdown_and_energy_notice.png');

    // 5. Mission Intelligence Quick Navigation Bar
    console.log('Step 5: Testing Quick Navigation Bar (Switching to Robustness)...');
    await evaluate(`(() => {
      const robustPill = Array.from(document.querySelectorAll('.quick-intel-pill')).find(b => b.textContent.includes('Robustness'));
      if (robustPill) robustPill.click();
    })()`);
    await sleep(2000);
    console.log('Capturing: p1_05_mission_intelligence_quick_navigation.png');
    await captureScreenshot('p1_05_mission_intelligence_quick_navigation.png');

    // 6. Return-to-Base 2D Isochrone Map Legend
    console.log('Step 6: Capturing 2D Return Isochrone Map Legend...');
    await evaluate(`(() => {
      const ovBtn = Array.from(document.querySelectorAll('.tab-button')).find(b => b.textContent.includes('Overview'));
      if (ovBtn) ovBtn.click();
    })()`);
    await sleep(1500);
    console.log('Capturing: p1_06_return_zone_isochrone_legend.png');
    await captureScreenshot('p1_06_return_zone_isochrone_legend.png');

    ws.close();
    console.log('All 6 P1 remediation verification screenshots captured successfully!');
  } finally {
    chromeProc.kill();
  }
}

main().catch((err) => {
  console.error('Error in capture script:', err);
  process.exit(1);
});
