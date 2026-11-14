# Cloud Scheduler & NASA Data Automation Architecture

## 1. Overview

MARSPath relies on **Google Cloud Scheduler** to run recurrent planetary synchronization jobs without requiring long-lived daemon processes on Render or Vercel.

---

## 2. Declarative Schedules (`infra/cloud_scheduler/schedules.yaml`)

| Schedule Name | Cron Expression | Interval | Target Endpoint | Target Cloud Run Job | Auth Type |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`marspath-daily-catalog-sync`** | `0 4 * * *` | Daily at 04:00 UTC | `/api/v1/cloud/jobs/run/nasa_catalog_sync` | `nasa_catalog_sync` | OIDC Service Account |
| **`marspath-meda-telemetry-ingestion`** | `0 6 * * *` | Daily at 06:00 UTC | `/api/v1/cloud/jobs/run/meda_processor` | `meda_processor` | OIDC Service Account |
| **`marspath-provenance-audit-weekly`** | `0 3 * * 0` | Every Sunday 03:00 UTC | `/api/v1/cloud/jobs/run/provenance_validator` | `provenance_validator` | OIDC Service Account |
| **`marspath-pds-release-monitor`** | `0 2 1 * *` | Monthly 1st 02:00 UTC | `/api/v1/cloud/jobs/run/nasa_catalog_sync` | `nasa_catalog_sync` | OIDC Service Account |

---

## 3. OIDC Service Account Authentication

All requests invoked by Cloud Scheduler include an OpenID Connect (OIDC) identity token issued to a dedicated service account:

```text
marspath-scheduler-invoker@PROJECT_ID.iam.gserviceaccount.com
```

The receiving backend verifies:
1. Issuer (`iss` = `https://accounts.google.com`)
2. Audience (`aud` matching the backend domain)
3. Expiration (`exp` within valid window)
4. Role permissions (`roles/run.invoker`)

---

## 4. Idempotency & Retry Policies

- Every schedule is configured with exponential backoff retries (`retry_count = 2` to `3`, `min_backoff = 5s`, `max_backoff = 60s`).
- Batch jobs use content-addressed hashes (SHA-256) and timestamped sync keys (`sync_report_YYYYMMDD_HHMMSS.json`) to prevent duplicate records or race conditions.
