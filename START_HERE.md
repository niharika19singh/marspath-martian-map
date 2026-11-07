# MarsPath source export

## Open in Antigravity
1. Extract this ZIP. Open the extracted MarsPath folder in Antigravity.
2. The editable landing page, catalogue and assets are in dist/. The editable React Mission Control dashboard is in mission-ui/src/.
3. From the MarsPath folder run:

```cmd
python -m http.server 8000 --directory dist
```

Open http://localhost:8000. Mission Control is at http://localhost:8000/mission-control/.
Use an HTTP server; opening index.html directly will not load modules and terrain data correctly.

## Rebuild Mission Control after editing
Install Node.js 22.12+ and npm, then run:

```cmd
cd mission-ui
npm ci
npm run build
cd ..
python -m http.server 8000 --directory dist
```

The build writes to dist/mission-control/. The included build is already ready to serve.

## Integrate with your existing repository
This export contains the website frontend, browser routing engine, images and terrain/traverse data. It does not contain your original Python backend. Preserve the backend already in your repository. The Python API connector requires your own backend URL and compatible API/CORS configuration.

First check your repository and switch to your branch:

```cmd
cd C:\Projects\marspath-martian-map
git status
git switch kunal
```

If kunal does not exist, create it with git switch -c kunal. Preserve any uncommitted work before switching. Inspect existing frontend files before copying: merge changes where names overlap. Copy dist/ and mission-ui/ into the repository root, and this START_HERE.md if desired. The dist directory is required: it contains editable landing source, assets and datasets, as well as the dashboard build.

After copying and checking the site locally:

```cmd
git status
git diff --stat
git add dist mission-ui START_HERE.md
git diff --cached --stat
git commit -m "Import MarsPath website"
git push -u origin kunal
```

Stage START_HERE.md only if you copied it. Do not commit credentials, node_modules or backend environment files. Do not push or merge main.

## Prompt for Antigravity
Read START_HERE.md and both existing READMEs. Work only on branch kunal. Inspect the existing repository, then integrate the exported MarsPath frontend while preserving the Python backend and other contributors' work. Keep mission imagery, terrain data, data provenance, navigation and rover history. Verify the dashboard build and local site before committing. Do not push or merge main.

## Included
- Mars landing, Explore catalogue, Mars field guide and mission briefing.
- React/OpenLayers Mission Control source and prebuilt output.
- Browser A* / Dijkstra routing, alternative routes, terrain analysis and export.
- Mars textures, mission images, Jezero DEM/imagery and recorded Perseverance traverse data.
- Existing READMEs with implementation details and data provenance.

Source snapshot: b56fe5216edd9fe1b9a46e4c815c496c664970aa.
Git history, platform hosting configuration and dependencies are excluded. The hosted website is unchanged by this export.
