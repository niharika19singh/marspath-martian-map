import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const OUT_DIR = '/Users/user/.gemini/antigravity/brain/f9025004-a488-449d-947c-219230fab331/ai_intel_verification';
fs.mkdirSync(OUT_DIR, { recursive: true });

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9222;

console.log('🚀 Spawning Chrome Headless on port', PORT);
const chrome = spawn(CHROME_PATH, [
  '--headless',
  '--disable-gpu',
  `--remote-debugging-port=${PORT}`,
  '--window-size=1600,1050',
  'http://127.0.0.1:3000/mission-control/',
], { stdio: 'ignore' });

// Wait for Chrome to initialize
await new Promise((r) => setTimeout(r, 2000));

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
    const dest = path.join(OUT_DIR, filename);
    fs.writeFileSync(dest, buffer);
    console.log(`📸 Saved screenshot: ${dest} (${(buffer.length / 1024).toFixed(1)} KB)`);
  }

  await send('Page.enable');
  await send('Runtime.enable');

  // Wait for initial render
  await new Promise((r) => setTimeout(r, 2500));
  await captureScreenshot('ai_01_mission_control_initial.png');

  // Click Cloud & AI mode button
  console.log('🖱️ Clicking Cloud & AI tab button...');
  await evaluate(`
    (() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const aiBtn = btns.find(b => b.textContent.includes('Cloud & AI') || b.textContent.includes('Cloud'));
      if (aiBtn) aiBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('ai_02_ai_mission_intelligence_tab_loaded.png');

  // Trigger Natural Language Planner
  console.log('🧠 Clicking Translate Mission Prompt...');
  await evaluate(`
    (() => {
      const submitBtn = document.querySelector('.btn-plan-submit');
      if (submitBtn) submitBtn.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('ai_03_mission_intent_extracted.png');

  // Switch to Candidate Route Comparison subtab
  console.log('🔄 Switching to Candidate Route Comparison subtab...');
  await evaluate(`
    (() => {
      const tabs = Array.from(document.querySelectorAll('.subtab-pill'));
      const compTab = tabs.find(t => t.textContent.includes('Candidate Route Comparison'));
      if (compTab) compTab.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('ai_04_candidate_route_comparison.png');

  // Switch to Scientific Terrain Interpreter subtab
  console.log('🔬 Switching to Scientific Terrain Interpreter subtab...');
  await evaluate(`
    (() => {
      const tabs = Array.from(document.querySelectorAll('.subtab-pill'));
      const terrTab = tabs.find(t => t.textContent.includes('Scientific Terrain'));
      if (terrTab) terrTab.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('ai_05_scientific_terrain_interpreter.png');

  // Switch to Executive Mission Risk Briefing subtab
  console.log('🛡️ Switching to Executive Risk Briefing subtab...');
  await evaluate(`
    (() => {
      const tabs = Array.from(document.querySelectorAll('.subtab-pill'));
      const riskTab = tabs.find(t => t.textContent.includes('Executive Risk Briefing'));
      if (riskTab) riskTab.click();
    })()
  `);
  await new Promise((r) => setTimeout(r, 1500));
  await captureScreenshot('ai_06_executive_risk_briefing.png');

  ws.close();
  console.log('🎉 All automated UI screenshots captured successfully!');
} finally {
  chrome.kill();
}
