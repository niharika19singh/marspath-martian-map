import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const PORT = 9222;
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ARTIFACTS_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331';
const LOCAL_SCREENSHOTS_DIR = path.resolve('docs/screenshots');

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  if (!fs.existsSync(LOCAL_SCREENSHOTS_DIR)) {
    fs.mkdirSync(LOCAL_SCREENSHOTS_DIR, { recursive: true });
  }

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

    // 1. Global View (Viking 232m global mosaic)
    console.log('Step 1: Navigating to Global Mars Bookmark...');
    await evaluate(`(() => {
      const btns = Array.from(document.querySelectorAll('.planetary-bookmark-bar button'));
      const globalBtn = btns.find(b => b.textContent.includes('Global Mars')) || btns[0];
      if (globalBtn) globalBtn.click();
    })()`);
    await sleep(4000);
    await captureScreenshot('mars_map_01_global_viking.png');

    // 2. Regional View (Jezero Crater CTX mosaic)
    console.log('Step 2: Navigating to Jezero Regional Bookmark...');
    await evaluate(`(() => {
      const btns = Array.from(document.querySelectorAll('.planetary-bookmark-bar button'));
      const jezBtn = btns.find(b => b.textContent.includes('Jezero Crater')) || btns[1];
      if (jezBtn) jezBtn.click();
    })()`);
    await sleep(4000);
    await captureScreenshot('mars_map_02_jezero_ctx.png');

    // 3. High-res View (Octavia E. Butler Landing HiRISE 25cm)
    console.log('Step 3: Navigating to Octavia E. Butler Landing (HiRISE 25cm)...');
    await evaluate(`(() => {
      const btns = Array.from(document.querySelectorAll('.planetary-bookmark-bar button'));
      const octBtn = btns.find(b => b.textContent.includes('Octavia') || b.textContent.includes('Landing')) || btns[2];
      if (octBtn) octBtn.click();
    })()`);
    await sleep(4000);
    await captureScreenshot('mars_map_03_hirise_closeup.png');

    // 4. Interactive Inspection (Click terrain to inspect)
    console.log('Step 4: Clicking terrain to trigger Click-to-Inspect popup...');
    // Click at screen coordinates (750, 420)
    await sendCommand('Input.dispatchMouseEvent', {
      type: 'mousePressed',
      x: 750,
      y: 420,
      button: 'left',
      clickCount: 1,
    });
    await sendCommand('Input.dispatchMouseEvent', {
      type: 'mouseReleased',
      x: 750,
      y: 420,
      button: 'left',
      clickCount: 1,
    });
    await sleep(1500);
    await captureScreenshot('mars_map_04_click_inspect.png');

    // 5. Route with animated rover (Play route playback)
    console.log('Step 5: Starting Route Playback animation...');
    await evaluate(`(() => {
      const playBtn = document.querySelector('.route-playback-deck button[aria-label*="Play"]') || document.querySelector('.route-playback-deck button');
      if (playBtn) playBtn.click();
    })()`);
    await sleep(3500); // Let rover travel along route
    await captureScreenshot('mars_map_05_route_animated_rover.png');

    // 6. Playback controls with scrubber & speed multiplier
    console.log('Step 6: Setting playback scrubber to 55% and 5x speed...');
    await evaluate(`(() => {
      const slider = document.querySelector('.route-playback-deck input[type="range"]');
      if (slider) {
        slider.value = 55;
        slider.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const speedBtns = Array.from(document.querySelectorAll('.route-playback-deck button'));
      const speed5x = speedBtns.find(b => b.textContent === '5x');
      if (speed5x) speed5x.click();
    })()`);
    await sleep(2000);
    await captureScreenshot('mars_map_06_playback_deck_controls.png');

    // 7. Quick-jump navigation (Delta Front & Fan bookmark)
    console.log('Step 7: Quick-jump to Delta Front & Fan bookmark...');
    await evaluate(`(() => {
      const btns = Array.from(document.querySelectorAll('.planetary-bookmark-bar button'));
      const deltaBtn = btns.find(b => b.textContent.includes('Delta Front')) || btns[4];
      if (deltaBtn) deltaBtn.click();
    })()`);
    await sleep(3500);
    await captureScreenshot('mars_map_07_quickjump_navigation.png');

    console.log('\nAll 7 verification screenshots captured successfully!');
    ws.close();
  } finally {
    chromeProc.kill();
  }
}

main().catch(console.error);
