# Google Gemini Mars Science Copilot Specification

## 1. Overview

**Google Gemini** serves as the primary planetary science copilot for MARSPath. Powered by `gemini-2.5-flash`, the copilot translates complex multi-instrument NASA planetary observations into actionable geological interpretations and explains deterministic rover routing trade-offs to human mission operators.

---

## 2. Core Capabilities

1. **Multimodal Orbital & Surface Understanding:**
   - Interprets HiRISE (0.25 m/px) and CTX (6 m/px) morphological features (paleochannels, inverted delta terraces, aeolian bedforms).
   - Ingests CRISM hyperspectral band ratios (2.30 µm and 2.51 µm carbonate absorptions, 2.29 µm Fe/Mg smectite signatures).
   - Evaluates THEMIS 100m thermal inertia ($I$) to quantify soil bulk density and wheel sinkage hazards.
   - Summarizes Mars 2020 Perseverance MEDA in-situ atmospheric sensor telemetry (pressure, air temperature, ground temperature, dust optical depth $\tau$).

2. **Deterministic Route Explanation & Safety Trade-offs:**
   - Synthesizes why specific traverse corridors were selected by A* or Dijkstra algorithms over alternative corridors.
   - Breaks down cost penalties: base distance cost versus cumulative slope penalties.
   - Explains how strict safety limits (e.g., maximum slope $\le 14^\circ$, avoiding low thermal inertia sinkage hazards) were enforced.

3. **Grounded RAG Architecture:**
   - Prompts are augmented with genuine NASA PDS records retrieved via `ContextBuilder`.
   - Never hallucinates data or references non-existent observations.

4. **Structured Scientific Citation Enforcement:**
   - Every copilot response includes structured citations (`CitationResolver`) linking directly to authentic NASA archives:
     - HiRISE products (`https://hirise.lpl.arizona.edu/...`)
     - PDS Geosciences ODE (`https://ode.rsl.wustl.edu/mars/...`)
     - PDS Atmospheres MEDA repository (`https://pds-atmospheres.nmsu.edu/...`)
     - THEMIS Data Viewer (`https://themis.asu.edu/...`)

5. **Mandatory Scientific Uncertainty Notice:**
   - Every generated interpretation is stamped with the required scientific caveat:
     > *"AI scientific interpretation represents an explanatory hypothesis based on available orbital and in-situ data; not a definitive mineralogical composition or physical discovery."*

---

## 3. API Endpoints

- `POST /api/v1/ai/mars-science/chat`: Natural language questions about Martian geology, atmosphere, or observations.
- `POST /api/v1/ai/route/explain`: Explains cost breakdowns and terrain safety margins for calculated routes.
- `POST /api/v1/ai/imagery/interpret`: Geological visual interpretation of catalog imagery.
