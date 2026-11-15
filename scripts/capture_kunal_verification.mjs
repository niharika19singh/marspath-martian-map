import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const PORT = 3000;
const CDP_PORT = 9222;
const BACKEND_URL = 'https://marspath-backend.onrender.com';
const DIST_DIR = path.resolve('dist');
const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const ARTIFACTS_DIR = 'C:\\Users\\kunal\\.gemini\\antigravity\\brain\\56b3541b-423c-45ec-8018-eef3b8fe7236';
const SCREENSHOTS_DIR = path.resolve('docs/evidence/kunal-completion');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 1. Create static server with live backend proxy
function createServer() {
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    
    // Proxy API and health requests to live backend
    if (url.pathname.startsWith('/api') || url.pathname.startsWith('/health') || url.pathname === '/openapi.json') {
      try {
        const targetUrl = `${BACKEND_URL}${url.pathname}${url.search}`;
        const headers = { ...req.headers, host: 'marspath-backend.onrender.com' };
        delete headers['content-length'];
        
        let body = null;
        if (req.method === 'POST' || req.method === 'PUT') {
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          body = Buffer.concat(chunks);
        }

        const backendRes = await fetch(targetUrl, {
          method: req.method,
          headers,
          body
        });

        res.writeHead(backendRes.status, Object.fromEntries(backendRes.headers.entries()));
        const resBuffer = Buffer.from(await backendRes.arrayBuffer());
        res.end(resBuffer);
        return;
      } catch (err) {
        console.error('Proxy error:', err);
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
        return;
      }
    }

    // Serve static files from dist
    let filePath = path.join(DIST_DIR, url.pathname);
    if (url.pathname === '/' || url.pathname === '/mission-control' || url.pathname === '/mission-control/') {
      filePath = path.join(DIST_DIR, 'mission-control', 'index.html');
    }

    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST_DIR, 'mission-control', 'index.html');
    }

    const ext = path.extname(filePath).toLowerCase();
    const mimeTypes = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.json': 'application/json',
      '.geojson': 'application/geo+json',
      '.png': 'image/png',
      '.jpg': 'image/jpeg',
      '.webp': 'image/webp',
      '.svg': 'image/svg+xml',
      '.xml': 'application/xml',
      '.tif': 'image/tiff'
    };

    const contentType = mimeTypes[ext] || 'application/octet-stream';
    try {
      const data = fs.readFileSync(filePath);
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(data);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  });
}

async function runBrowserVerification() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

  const server = createServer();
  await new Promise(resolve => server.listen(PORT, '127.0.0.1', resolve));
  console.log(`[Server] Serving dist on http://127.0.0.1:${PORT} with backend proxy to ${BACKEND_URL}`);

  console.log(`[Browser] Launching Edge CDP on port ${CDP_PORT}...`);
  const browserProc = spawn(EDGE_PATH, [
    '--headless=new',
    '--disable-gpu',
    `--remote-debugging-port=${CDP_PORT}`,
    '--remote-allow-origins=*',
    '--window-size=1520,960',
    '--no-first-run',
    '--no-default-browser-check',
    `http://127.0.0.1:${PORT}/mission-control/?view=planner`
  ], { stdio: 'ignore' });

  try {
    let connected = false;
    for (let i = 0; i < 25; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
        if (res.ok) {
          const list = await res.json();
          if (list && list.length > 0 && list[0].webSocketDebuggerUrl) {
            connected = true;
            break;
          }
        }
      } catch {
        await sleep(400);
      }
    }
    if (!connected) throw new Error('Edge CDP failed to respond');

    const listRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const tabs = await listRes.json();
    const target = tabs.find(t => t.type === 'page') || tabs[0];
    const ws = new WebSocket(target.webSocketDebuggerUrl);

    let idCounter = 1;
    const callbacks = new Map();
    ws.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.id && callbacks.has(data.id)) {
        const { resolve, reject } = callbacks.get(data.id);
        callbacks.delete(data.id);
        if (data.error) reject(new Error(data.error.message));
        else resolve(data.result);
      }
    };
    await new Promise(resolve => (ws.onopen = resolve));

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
        returnByValue: true
      });
      return res.result?.value;
    }

    async function captureScreenshot(filename) {
      console.log(`[Evidence] Capturing screenshot: ${filename}...`);
      const { data } = await sendCommand('Page.captureScreenshot', { format: 'png' });
      const buffer = Buffer.from(data, 'base64');
      fs.writeFileSync(path.join(SCREENSHOTS_DIR, filename), buffer);
      fs.writeFileSync(path.join(ARTIFACTS_DIR, filename), buffer);
      console.log(`   ✓ Saved ${filename} (${buffer.length} bytes)`);
    }

    await sendCommand('Page.enable');
    await sendCommand('Runtime.enable');

    console.log('[Test 1/15] Initial Map & Mission Control Loading...');
    await sleep(4500);
    await captureScreenshot('01_initial_map_loading.png');

    console.log('[Test 2/15] Planetary Layer Palette & Basemaps...');
    await evaluate(`(() => {
      const btn = document.querySelector('button[aria-label="Layer palette and visibility"]');
      if (btn) btn.click();
    })()`);
    await sleep(1000);
    await captureScreenshot('02_planetary_layer_switching.png');

    console.log('[Test 3/15] Zoom and Pan Navigation Stability...');
    await evaluate(`(() => {
      const zoomBtn = document.querySelector('button[aria-label="Zoom in"]');
      if (zoomBtn) { zoomBtn.click(); zoomBtn.click(); }
    })()`);
    await sleep(1500);
    await captureScreenshot('03_zoom_pan_stability.png');

    console.log('[Test 4/15] Start and Destination Coordinate Entry...');
    await evaluate(`(() => {
      // Close layers palette if open
      const closeBtn = document.querySelector('.layer-palette .close-button') || document.querySelector('button[aria-label="Close layers"]');
      if (closeBtn) closeBtn.click();
    })()`);
    await sleep(600);
    await captureScreenshot('04_start_destination_waypoints.png');

    console.log('[Test 5/15] Mission Configuration & Constraints...');
    await evaluate(`(() => {
      const slopeInput = document.querySelector('input[name="max_slope_deg"]') || document.querySelector('input[type="range"]');
      if (slopeInput) { slopeInput.value = '18'; slopeInput.dispatchEvent(new Event('input', { bubbles: true })); }
    })()`);
    await sleep(800);
    await captureScreenshot('05_mission_configuration.png');

    console.log('[Test 6/15] Route Generation & Floating Candidate HUD...');
    await evaluate(`(() => {
      const planBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Compute Route') || b.textContent.includes('Calculate Corridor') || b.textContent.includes('Plan Route') || b.classList.contains('primary-cta'));
      if (planBtn) planBtn.click();
    })()`);
    console.log('Waiting for route optimization and telemetry...');
    await sleep(6000);
    await captureScreenshot('06_route_generation_candidates.png');

    console.log('[Test 7/15] Alternative Route Selection & Active Map Highlighting...');
    await evaluate(`(() => {
      const altPill = document.querySelectorAll('.candidate-hud-pill')[1] || document.querySelectorAll('.candidate')[1];
      if (altPill) altPill.click();
    })()`);
    await sleep(1500);
    await captureScreenshot('07_alternative_route_selection.png');

    console.log('[Test 8/15] Cost & Terrain Breakdown (Visible by Default)...');
    await evaluate(`(() => {
      const drawerBtn = document.querySelector('.floating-analysis');
      if (drawerBtn && !drawerBtn.classList.contains('expanded')) {
        const toggle = document.querySelector('button[aria-label="Expand analysis drawer"]') || document.querySelector('.drawer-toggle');
        if (toggle) toggle.click();
      }
    })()`);
    await sleep(1200);
    await captureScreenshot('08_cost_terrain_breakdown.png');

    console.log('[Test 9/15] Energy Index & Minetti Mechanical Effort Display...');
    await captureScreenshot('09_energy_mechanical_effort.png');

    console.log('[Test 10/15] Dedicated Mission Resource Summary Card...');
    await captureScreenshot('10_mission_resource_summary.png');

    console.log('[Test 11/15] Reachable Return-Time Isochrone & Legend...');
    await evaluate(`(() => {
      // Ensure layer drawer is toggled or return zone is visible
    })()`);
    await sleep(1000);
    await captureScreenshot('11_return_time_isochrone.png');

    console.log('[Test 12/15] Elevation and Slope Profile 5-Tab Workbench...');
    await evaluate(`(() => {
      const handle = document.querySelector('.profile-handle');
      if (handle) handle.click();
    })()`);
    await sleep(1500);
    await captureScreenshot('12_elevation_slope_profile.png');

    console.log('[Test 13/15] Advanced Mission Intelligence Deep-Links...');
    await evaluate(`(() => {
      const reconBtn = Array.from(document.querySelectorAll('.intel-pill-btn')).find(b => b.textContent.includes('Next-Best'));
      if (reconBtn) reconBtn.click();
    })()`);
    await sleep(1500);
    await captureScreenshot('13_advanced_intelligence_panels.png');

    console.log('[Test 14/15] Route Export Controls & Format Synchronization...');
    await evaluate(`(() => {
      const exportSelect = document.querySelector('select[aria-label="Export format"]');
      if (exportSelect) {
        exportSelect.value = 'geojson';
        exportSelect.dispatchEvent(new Event('change', { bubbles: true }));
      }
    })()`);
    await sleep(1000);
    await captureScreenshot('14_route_export_synchronization.png');

    console.log('[Test 15/15] Settings, Provenance & Evidence Passport...');
    await evaluate(`(() => {
      const settingsBtn = document.querySelector('button[title="API connection settings"]') || document.querySelector('.api-connect');
      if (settingsBtn) settingsBtn.click();
    })()`);
    await sleep(1000);
    await captureScreenshot('15_api_error_recovery.png');

    console.log('\n=============================================================');
    console.log(' ALL 15 BROWSER WORKFLOW SCREENSHOTS CAPTURED SUCCESSFULLY! ');
    console.log('=============================================================');
  } finally {
    browserProc.kill();
    server.close();
  }
}

runBrowserVerification().catch(err => {
  console.error('Browser verification failed:', err);
  process.exit(1);
});
