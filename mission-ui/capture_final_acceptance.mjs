import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const DOCS_OUT_DIR = '/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/docs/screenshots/final_acceptance';
const BRAIN_OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/final_acceptance';

fs.mkdirSync(DOCS_OUT_DIR, { recursive: true });
fs.mkdirSync(BRAIN_OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9224;

console.log('🚀 Spawning Chrome Headless for FINAL PRODUCTION ACCEPTANCE at port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  'https://marspath.vercel.app/mission-control/',
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
    const dest1 = path.join(DOCS_OUT_DIR, filename);
    const dest2 = path.join(BRAIN_OUT_DIR, filename);
    fs.writeFileSync(dest1, buffer);
    fs.writeFileSync(dest2, buffer);
    console.log(`📸 Saved screenshot: ${filename} (${(buffer.length / 1024).toFixed(1)} KB)`);
  }

  await send('Page.enable');
  await send('Runtime.enable');

  // 1. Initial Mars Map Loaded
  console.log('⏳ Waiting for Mars planetary basemap and layers to initialize...');
  await new Promise((r) => setTimeout(r, 4500));
  await captureScreenshot('01_mars_map_loaded.png');

  // 2. Trigger Route Planning
  console.log('🗺️ Triggering Route Planning calculation against Render production...');
  await evaluate(`
    (() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const planBtn = btns.find(b => b.textContent.includes('Plan') && (b.className.includes('primary') || b.className.includes('plan')));
      if (planBtn) planBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 4000));
  await captureScreenshot('02_route_planning.png');

  // 3. Route Alternatives Selection
  console.log('🔀 Switching to Route Alternative candidate in HUD...');
  await evaluate(`
    (() => {
      const cards = Array.from(document.querySelectorAll('.route-candidate-card, .candidate-card'));
      if (cards.length > 1) {
        cards[1].click();
      }
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('03_route_alternatives.png');

  // 4. Cost Breakdown & Energy
  console.log('⚡ Scrolling right drawer to Cost Breakdown & Mechanical Effort...');
  await evaluate(`
    (() => {
      const drawer = document.querySelector('.right-drawer, .mission-panel, .drawer');
      if (drawer) drawer.scrollTop = 250;
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('04_cost_and_energy.png');

  // 5. Mission Resources
  console.log('⏱️ Focusing on Mission Resources & Temporal Budget...');
  await evaluate(`
    (() => {
      const drawer = document.querySelector('.right-drawer, .mission-panel, .drawer');
      if (drawer) drawer.scrollTop = 500;
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('05_mission_resources.png');

  // 6. Monte Carlo Robustness
  console.log('🎲 Opening Monte Carlo Robustness analysis...');
  await evaluate(`
    (() => {
      const pills = Array.from(document.querySelectorAll('.quick-intel-pill, button'));
      const mcPill = pills.find(p => p.textContent.includes('Robustness'));
      if (mcPill) mcPill.click();
      const drawer = document.querySelector('.right-drawer, .mission-panel, .drawer');
      if (drawer) drawer.scrollTop = 700;
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('06_monte_carlo.png');

  // 7. Pareto Analysis
  console.log('📊 Opening Pareto Trade-offs analysis...');
  await evaluate(`
    (() => {
      const pills = Array.from(document.querySelectorAll('.quick-intel-pill, button'));
      const paretoPill = pills.find(p => p.textContent.includes('Pareto'));
      if (paretoPill) paretoPill.click();
      const drawer = document.querySelector('.right-drawer, .mission-panel, .drawer');
      if (drawer) drawer.scrollTop = 700;
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('07_pareto_analysis.png');

  // 8. Next-Best Reconnaissance
  console.log('🛰️ Opening Next-Best Reconnaissance analysis...');
  await evaluate(`
    (() => {
      const pills = Array.from(document.querySelectorAll('.quick-intel-pill, button'));
      const reconPill = pills.find(p => p.textContent.includes('Next-Best Recon') || p.textContent.includes('Recon'));
      if (reconPill) reconPill.click();
      const drawer = document.querySelector('.right-drawer, .mission-panel, .drawer');
      if (drawer) drawer.scrollTop = 700;
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('08_reconnaissance.png');

  // 9. Return-Zone Isochrone Overlay
  console.log('⭕ Enabling Return-to-Base Isochrone Overlay on map...');
  await evaluate(`
    (() => {
      const checkbox = document.querySelector('.return-toggle-label input[type="checkbox"]');
      if (checkbox && !checkbox.checked) {
        checkbox.click();
      }
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await captureScreenshot('09_return_isochrone.png');

  // 10. NASA Data & Spacecraft Intelligence
  console.log('🪐 Switching to NASA Data Panel...');
  await evaluate(`
    (() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const nasaBtn = btns.find(b => b.textContent.includes('NASA Data'));
      if (nasaBtn) nasaBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('10_nasa_data.png');

  // 11. AI Copilot / AI Mission Intelligence
  console.log('🧠 Switching to Cloud & AI panel...');
  await evaluate(`
    (() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const aiBtn = btns.find(b => b.textContent.includes('Cloud & AI') || b.textContent.includes('Cloud'));
      if (aiBtn) aiBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await evaluate(`
    (() => {
      const submitBtn = document.querySelector('.btn-plan-submit');
      if (submitBtn) submitBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('11_ai_copilot.png');

  // 12. PDF Export
  console.log('📄 Returning to Route Design and triggering PDF Export...');
  await evaluate(`
    (() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const routeBtn = btns.find(b => b.textContent.includes('Route') || b.textContent.includes('Design'));
      if (routeBtn) routeBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 2000));
  await evaluate(`
    (() => {
      const select = document.querySelector('select');
      if (select) {
        select.value = 'pdf';
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const btns = Array.from(document.querySelectorAll('button'));
      const exportBtn = btns.find(b => b.textContent.includes('Export') || b.className.includes('quick-export'));
      if (exportBtn) exportBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 3000));
  await captureScreenshot('12_pdf_export.png');

  ws.close();
  console.log('🎉 ALL 12 PRODUCTION ACCEPTANCE SCREENSHOTS CAPTURED SUCCESSFULLY!');
} finally {
  chrome.kill();
}
