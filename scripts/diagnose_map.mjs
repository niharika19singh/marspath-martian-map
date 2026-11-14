import { spawn } from 'node:child_process';

const PORT = 9222;
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  console.log('Launching Chrome for diagnosis...');
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
      'http://127.0.0.1:3000/mission-control/',
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
    const wsUrl = target.webSocketDebuggerUrl;

    const ws = new WebSocket(wsUrl);
    let idCounter = 1;
    const callbacks = new Map();

    const consoleLogs = [];
    const networkRequests = [];
    const networkFailures = [];

    const responseErrors = [];

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.method === 'Runtime.consoleAPICalled') {
        const text = data.params.args.map((a) => a.value || a.description || JSON.stringify(a)).join(' ');
        consoleLogs.push(`[CONSOLE ${data.params.type}] ${text}`);
      } else if (data.method === 'Runtime.exceptionThrown') {
        const desc = data.params.exceptionDetails?.exception?.description || data.params.exceptionDetails?.text;
        consoleLogs.push(`[EXCEPTION] ${desc}`);
      } else if (data.method === 'Log.entryAdded') {
        consoleLogs.push(`[LOG ${data.params.entry.level}] ${data.params.entry.text}`);
      } else if (data.method === 'Network.requestWillBeSent') {
        networkRequests.push({ url: data.params.request.url, id: data.params.requestId });
      } else if (data.method === 'Network.responseReceived') {
        if (data.params.response.status >= 400) {
          responseErrors.push({
            url: data.params.response.url,
            status: data.params.response.status,
            statusText: data.params.response.statusText
          });
        }
      } else if (data.method === 'Network.loadingFailed') {
        networkFailures.push({ id: data.params.requestId, errorText: data.params.errorText });
      } else if (data.id && callbacks.has(data.id)) {
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

    await sendCommand('Page.enable');
    await sendCommand('Runtime.enable');
    await sendCommand('Network.enable');
    await sendCommand('Log.enable');

    console.log('Waiting 6 seconds for page lifecycle & map initialization...');
    await sleep(6000);

    console.log('\n=== BROWSER CONSOLE LOGS ===');
    consoleLogs.forEach((l) => console.log(l));

    console.log('\n=== NETWORK REQUESTS FOR TILES OR XML ===');
    const trekRequests = networkRequests.filter((r) => r.url.includes('trek.nasa.gov') || r.url.includes('wmts') || r.url.includes('.xml') || r.url.includes('.jpg') || r.url.includes('.png'));
    console.log(`Found ${trekRequests.length} mapping network requests:`);
    trekRequests.slice(0, 20).forEach((r) => console.log('  ->', r.url));
    if (trekRequests.length > 20) console.log(`  ... and ${trekRequests.length - 20} more`);

    console.log('\n=== HTTP >= 400 ERRORS ===');
    console.log(responseErrors);

    console.log('\n=== NETWORK FAILURES ===');
    console.log(networkFailures);

    console.log('\n=== DOM & OPENLAYERS DIAGNOSTICS ===');
    const domDiag = await evaluate(`(() => {
      const mapEl = document.querySelector('.ol-viewport') || document.querySelector('[class*="map"]') || document.querySelector('canvas');
      const container = document.querySelector('.map-container') || document.querySelector('.map-panel') || (mapEl ? mapEl.parentElement : null);
      const canvases = Array.from(document.querySelectorAll('canvas')).map(c => ({
        width: c.width,
        height: c.height,
        styleWidth: c.style.width,
        styleHeight: c.style.height,
        className: c.className
      }));
      
      const overlays = Array.from(document.querySelectorAll('.glass, .panel, .drawer, .conditions-panel')).map(el => {
        const rect = el.getBoundingClientRect();
        return {
          tag: el.tagName,
          className: el.className,
          rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
          zIndex: window.getComputedStyle(el).zIndex
        };
      });

      // Check OpenLayers global / window map or canvas pixel data
      let samplePixels = null;
      const primaryCanvas = document.querySelector('canvas');
      if (primaryCanvas && primaryCanvas.width > 0 && primaryCanvas.height > 0) {
        try {
          const ctx = primaryCanvas.getContext('2d');
          if (ctx) {
            const imgData = ctx.getImageData(0, 0, Math.min(primaryCanvas.width, 100), Math.min(primaryCanvas.height, 100));
            let nonZero = 0;
            for (let i = 0; i < imgData.data.length; i += 4) {
              if (imgData.data[i] !== 0 || imgData.data[i+1] !== 0 || imgData.data[i+2] !== 0) nonZero++;
            }
            samplePixels = { totalSampled: imgData.data.length / 4, nonZeroPixels: nonZero };
          }
        } catch(e) {
          samplePixels = { error: e.message };
        }
      }

      return {
        containerRect: container ? container.getBoundingClientRect() : null,
        canvases,
        overlays,
        samplePixels
      };
    })()`);

    console.log(JSON.stringify(domDiag, null, 2));

    ws.close();
  } finally {
    chromeProc.kill();
  }
}

main().catch(console.error);
