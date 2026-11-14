# Cloud Cost Controls, Quotas & Security Guardrails

## 1. Zero-Cost Billing Protection Architecture

To ensure zero financial risk during local evaluation, testing, and continuous integration, MARSPath implements a hard **Zero-Cost Billing Protection** system:

```text
+-----------------------------------------------------------+
|              MARSPath Zero-Cost Sandbox Mode              |
|                                                           |
| • GCS Enabled: FALSE -> Uses LocalStorageAdapter          |
| • Cloud Jobs: Local In-Memory Process Dispatcher          |
| • Gemini / Azure: Grounded Fallback Engine Active         |
| • Estimated Daily Spend: $0.00                            |
| • Estimated Monthly Spend: $0.00                          |
+-----------------------------------------------------------+
```

When live GCP credentials are not present or `MARSPATH_GCS_ENABLED=false`, all storage is directed to `backend/app/data/storage/marspath-data/`. No billable cloud requests are ever sent.

---

## 2. Resource Quotas & Budget Guardrails

When deployed to Google Cloud, the `CloudCostManager` enforces strict resource caps:

| Parameter | Sandbox / Guardrail Limit | Enforcement Action |
| :--- | :--- | :--- |
| **Monthly Budget** | $50.00 USD | Alert notifications at 50% ($25) and 80% ($40); execution clamp at 100% |
| **Storage Quota** | 10,240 MB (10 GB) | Uploads rejected if cumulative stored bytes exceed quota |
| **AI Daily Token Cap** | 100,000 tokens / day | AI queries throttled if daily consumption exceeds budget |
| **Cloud Run Memory** | 1024 - 2048 MB / task | Hard memory ceiling prevents run-away allocations |
| **Cloud Run Timeout** | 300 - 900 seconds | Job killed automatically if execution hangs |

---

## 3. Storage Lifecycle Management (Auto-Tiering)

All assets committed to Google Cloud Storage follow declarative lifecycle management rules to minimize storage costs:

1. **Standard Storage (0 - 30 days):** Hot access tier for active mission planning and newly ingested observations.
2. **Nearline Storage (30 - 90 days):** Automatically transitioned after 30 days of inactivity ($0.01 / GB-month).
3. **Coldline Storage (90 - 365 days):** Transitioned after 90 days ($0.004 / GB-month).
4. **Archive Storage (> 365 days):** Long-term planetary archive preservation ($0.0012 / GB-month).

---

## 4. Security & IAM Least Privilege

1. **Service Accounts:**
   - `marspath-scheduler-invoker@PROJECT_ID.iam.gserviceaccount.com`: Role restricted strictly to `roles/run.invoker`.
   - `marspath-batch-runner@PROJECT_ID.iam.gserviceaccount.com`: Role restricted strictly to `roles/storage.objectAdmin` on `gs://marspath-data`.

2. **Credential Safety:**
   - Service account keys and API keys (`GEMINI_API_KEY`, `AZURE_AI_FOUNDRY_API_KEY`) are passed strictly via environment variables.
   - Secret tokens are excluded from version control via `.gitignore`.
