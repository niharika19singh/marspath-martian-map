# Microsoft Azure AI Foundry Integration & Comparative Evaluation

## 1. Overview

MARSPath integrates **Microsoft Azure AI Foundry** as a secondary AI provider in an **evaluation and comparison role**. This allows planetary scientists and mission planners to:
- Benchmark Google Gemini against an independent AI provider (`gpt-4o-mini`).
- Test citation alignment across different foundation models.
- Cross-validate hazard interpretations and scientific reasoning.

---

## 2. Technical Integration

The Azure AI Foundry client connects to the official Azure AI Model Inference REST API:

- **Endpoint Format:** `https://<RESOURCE_NAME>.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview`
- **Authentication:** `api-key: <AZURE_AI_FOUNDRY_API_KEY>`
- **Model Used:** `gpt-4o-mini`

---

## 3. Side-by-Side Model Comparison API (`POST /api/v1/ai/models/compare`)

The comparison engine (`MarsScienceAssistantService.compare_models`) dispatches identical prompts concurrently to both providers and computes:
1. **Latency Delta:** Execution duration difference between Gemini and Azure Foundry in milliseconds.
2. **Citation Alignment Score:** Quantitative ratio ($0.0 - 1.0$) measuring overlap between scientific datasets referenced by both models.
3. **Comparative Analysis Summary:** Textual synthesis of points of agreement (e.g. both identifying unconsolidated sand as a high slip risk) and divergence.

---

## 4. UI Evaluation Workbench

The Mission Control UI features a dedicated **Dual-Model Evaluation (Gemini vs Azure)** subtab:
- Side-by-side comparative split view.
- Real-time token estimates and inference latency meters.
- Clickable citation cards linking to upstream NASA and PDS records.
