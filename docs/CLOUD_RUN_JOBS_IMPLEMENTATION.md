# Cloud Run Batch Jobs Implementation Guide

## 1. Overview

MARSPath implements **8 specialized containerized batch processing engines** designed for Google Cloud Run Jobs. Cloud Run Jobs are optimized for tasks that run to completion and exit, incurring zero cost between runs.

---

## 2. The 8 Cloud Run Batch Engines

| Job Name | Module | Timeout | RAM / CPU | Primary Scientific Task |
| :--- | :--- | :--- | :--- | :--- |
| **1. `nasa_catalog_sync`** | `nasa_catalog_sync.py` | 600s | 1024MB / 1.0 | Polls NASA PDS catalogues, identifies new/updated products, and updates catalog records. |
| **2. `planetary_imagery_processor`** | `planetary_imagery_processor.py` | 900s | 2048MB / 2.0 | Converts raw CTX and HiRISE imagery into Cloud-Optimized GeoTIFFs (COG) with internal multiresolution overviews. |
| **3. `dem_processor`** | `dem_processor.py` | 600s | 2048MB / 2.0 | Derives continuous slope, roughness, and multidirectional hillshade rasters while preserving NoData masks. |
| **4. `meda_processor`** | `meda_processor.py` | 300s | 1024MB / 1.0 | Ingests Perseverance in-situ atmospheric telemetry, normalizes physical units, and strictly preserves `-9999.0` missing-value flags as `null`. |
| **5. `themis_processor`** | `themis_processor.py` | 300s | 1024MB / 1.0 | Derives surface thermal inertia ($I = \sqrt{k \rho c}$) from 100m infrared observations and tags wheel-sinkage hazards. |
| **6. `crism_processor`** | `crism_processor.py` | 600s | 2048MB / 2.0 | Indexes CRISM hyperspectral targeted cubes for hydrated mineral absorption features (carbonates, Fe/Mg-smectite clays). |
| **7. `provenance_validator`** | `provenance_validator.py` | 300s | 1024MB / 1.0 | Validates SHA-256 cryptographic checksums and persistent DOIs against upstream NASA registries. |
| **8. `imagery_tile_generator`** | `imagery_tile_generator.py` | 900s | 2048MB / 2.0 | Slices high-resolution orbital mosaics into XYZ Slippy Map tile hierarchies for interactive browser rendering. |

---

## 3. Base Job Architecture (`base_job.py`)

All 8 jobs inherit from `BaseCloudRunJob` which enforces:
- **Execution Telemetry:** Records `job_name`, `execution_id`, `started_at`, `completed_at`, `duration_seconds`, and resource usage.
- **Structured Error Trapping:** Prevents silent failures by capturing tracebacks and outputting structured error status (`SUCCESS`, `FAILED`, `TIMED_OUT`).
- **Timeout Protection:** Applies `asyncio.wait_for` against individual job timeout limits.
- **Artifact Commitment:** Guarantees that generated outputs are registered with the active `BaseStorageAdapter`.

---

## 4. Cloud Run Job Template (`infra/cloud_run/job_template.yaml`)

Deployment to Cloud Run Jobs uses standard Google Cloud YAML definitions:

```yaml
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: marspath-batch-processor
  namespace: marspath-production-441200
spec:
  template:
    spec:
      taskCount: 1
      template:
        spec:
          containers:
          - image: gcr.io/marspath-production-441200/marspath-batch-processor:latest
            resources:
              limits:
                memory: 2048Mi
                cpu: "2000m"
            env:
            - name: GCS_BUCKET
              value: "marspath-data"
            - name: GOOGLE_CLOUD_PROJECT
              value: "marspath-production-441200"
          maxRetries: 2
          timeoutSeconds: 900
```
