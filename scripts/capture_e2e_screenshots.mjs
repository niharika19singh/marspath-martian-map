import fs from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';

const ARTIFACT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331';
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9222;

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  console.log('Launching headless Chrome with remote debugging on port', PORT);
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
      'http://localhost:3000/mission-control/',
    ],
    { stdio: 'ignore' }
  );

  try {
    // Wait for Chrome to listen
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

    console.log('Chrome listening. Connecting to page target...');
    const listRes = await fetch(`http://127.0.0.1:${PORT}/json/list`);
    const tabs = await listRes.json();
    const target = tabs.find((t) => t.type === 'page') || tabs[0];
    const wsUrl = target.webSocketDebuggerUrl;

    const ws = new WebSocket(wsUrl);
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

    async function takeScreenshot(filename) {
      const { data } = await sendCommand('Page.captureScreenshot', { format: 'png' });
      const outPath = path.join(ARTIFACT_DIR, filename);
      fs.writeFileSync(outPath, Buffer.from(data, 'base64'));
      console.log(`Saved screenshot: ${outPath} (${data.length} b64 chars)`);
    }

    await sendCommand('Page.enable');
    await sendCommand('Runtime.enable');

    // Wait for the app to load
    console.log('Waiting for Mission Control page load...');
    await sleep(4000);

    // 1. Live mode screenshot
    console.log('Capturing: mars_now_01_live_mode.png');
    // Ensure "Mars Now" mode is active (click the Mars Now mode button if needed)
    await evaluate(`
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Mars Now'));
      if (btn) btn.click();
    `);
    await sleep(2000);
    await takeScreenshot('mars_now_01_live_mode.png');

    // 2. Time Scrubber mode -> Sol 500
    console.log('Setting Time Scrubber mode and Sol 500...');
    await evaluate(`
      const freezeBtn = document.querySelector('button.time-mode-btn:nth-child(2)') ||
                        Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Time Scrubber'));
      if (freezeBtn) freezeBtn.click();
      const slider = document.querySelector('input[type="range"]');
      if (slider) {
        slider.value = 500;
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        slider.dispatchEvent(new Event('change', { bubbles: true }));
      }
    `);
    await sleep(2500);
    console.log('Capturing: mars_now_02_time_scrubber_sol500.png');
    await takeScreenshot('mars_now_02_time_scrubber_sol500.png');

    // 3. Time Scrubber mode -> Sol 2030 (past archive cutoff Sol 2022)
    console.log('Setting Sol 2030 (past archive cutoff)...');
    await evaluate(`
      const slider = document.querySelector('input[type="range"]');
      if (slider) {
        slider.value = 2030;
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        slider.dispatchEvent(new Event('change', { bubbles: true }));
      }
    `);
    await sleep(2500);
    console.log('Capturing: mars_now_03_archive_cutoff_sol2022.png');
    await takeScreenshot('mars_now_03_archive_cutoff_sol2022.png');

    // 4. Map inspection inside HiRISE 1m DTM bounds
    console.log('Inspecting coordinates inside HiRISE 1m DTM bounds (18.39°N, 77.40°E)...');
    await evaluate(`
      const inputs = Array.from(document.querySelectorAll('.coord-input-row input'));
      if (inputs.length >= 2) {
        inputs[0].value = 18.3900;
        inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
        inputs[1].value = 77.4000;
        inputs[1].dispatchEvent(new Event('change', { bubbles: true }));
      }
      const fetchBtn = document.querySelector('.fetch-conditions-btn');
      if (fetchBtn) fetchBtn.click();
    `);
    await sleep(3000);
    console.log('Capturing: mars_now_04_map_inspection_hirise.png');
    await takeScreenshot('mars_now_04_map_inspection_hirise.png');

    // 5. Switch to Route Planner mode
    console.log('Switching to Route Planner mode...');
    await evaluate(`
      const routeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Route planner'));
      if (routeBtn) routeBtn.click();
      const planBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Plan Route') || b.textContent.includes('Calculate'));
      if (planBtn) planBtn.click();
    `);
    await sleep(3500);
    console.log('Capturing: mars_now_05_route_planner_mint.png');
    await takeScreenshot('mars_now_05_route_planner_mint.png');

    ws.close();
    console.log('All 5 screenshots captured successfully!');
  } finally {
    chromeProc.kill();
  }
}

main().catch((err) => {
  console.error('Error in capture script:', err);
  process.exit(1);
});
