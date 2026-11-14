# Google Cloud Platform Deployment Guide

## 1. Prerequisites

Before enabling live Google Cloud services, ensure you have:
1. A Google Cloud project with billing enabled (e.g. `marspath-production-441200`).
2. Google Cloud SDK (`gcloud`) installed and authenticated.
3. Enabled the required GCP APIs:
   ```bash
   gcloud services enable storage.googleapis.com run.googleapis.com cloudscheduler.googleapis.com
   ```

---

## 2. Step 1: Create the Google Cloud Storage Bucket

Create the canonical planetary data bucket with uniform bucket-level access:

```bash
# Set project and region
gcloud config set project marspath-production-441200
REGION="us-central1"
BUCKET_NAME="marspath-data"

# Create bucket
gcloud storage buckets create gs://${BUCKET_NAME} \
    --location=${REGION} \
    --uniform-bucket-level-access

# Apply lifecycle rules
gcloud storage buckets lifecycle set infra/cloud_storage/lifecycle.json gs://${BUCKET_NAME}
```

---

## 3. Step 2: Configure Service Accounts and Permissions

Create dedicated least-privilege service accounts:

```bash
# 1. Cloud Run batch runner service account
gcloud iam service-accounts create marspath-batch-runner \
    --display-name="MARSPath Cloud Run Batch Runner"

# Grant storage access to the bucket
gcloud storage buckets add-iam-policy-binding gs://${BUCKET_NAME} \
    --member="serviceAccount:marspath-batch-runner@marspath-production-441200.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"

# 2. Cloud Scheduler invoker service account
gcloud iam service-accounts create marspath-scheduler-invoker \
    --display-name="MARSPath Cloud Scheduler Invoker"
```

---

## 4. Step 3: Deploy Cloud Run Batch Processing Jobs

Build the container image and deploy the Cloud Run Jobs:

```bash
# Build batch container using Google Cloud Build
gcloud builds submit --tag gcr.io/marspath-production-441200/marspath-batch-processor:latest .

# Deploy job definition
gcloud run jobs create marspath-batch-processor \
    --image gcr.io/marspath-production-441200/marspath-batch-processor:latest \
    --region us-central1 \
    --service-account marspath-batch-runner@marspath-production-441200.iam.gserviceaccount.com \
    --memory 2048Mi \
    --cpu 2 \
    --set-env-vars GCS_BUCKET=marspath-data,GOOGLE_CLOUD_PROJECT=marspath-production-441200
```

---

## 5. Step 4: Configure Cloud Scheduler Jobs

Deploy automated telemetry synchronization schedules:

```bash
# Daily catalog sync schedule
gcloud scheduler jobs create http marspath-daily-catalog-sync \
    --location=us-central1 \
    --schedule="0 4 * * *" \
    --uri="https://marspath-backend.onrender.com/api/v1/cloud/jobs/run/nasa_catalog_sync" \
    --http-method=POST \
    --oidc-service-account-email=marspath-scheduler-invoker@marspath-production-441200.iam.gserviceaccount.com

# Daily MEDA in-situ telemetry schedule
gcloud scheduler jobs create http marspath-meda-telemetry-ingestion \
    --location=us-central1 \
    --schedule="0 6 * * *" \
    --uri="https://marspath-backend.onrender.com/api/v1/cloud/jobs/run/meda_processor" \
    --http-method=POST \
    --oidc-service-account-email=marspath-scheduler-invoker@marspath-production-441200.iam.gserviceaccount.com
```

---

## 6. Step 5: Update Render Backend Environment Variables

In the Render Dashboard for `marspath-backend`:
1. Navigate to **Environment Variables**.
2. Add:
   - `GOOGLE_CLOUD_PROJECT=marspath-production-441200`
   - `GOOGLE_CLOUD_LOCATION=us-central1`
   - `GCS_BUCKET=marspath-data`
   - `MARSPATH_GCS_ENABLED=true`
   - `MARSPATH_CLOUD_JOBS_ENABLED=true`
   - `GEMINI_API_KEY=<your-key>`
   - `MARSPATH_GEMINI_ENABLED=true`
   - `AZURE_AI_FOUNDRY_ENDPOINT=<your-endpoint>`
   - `AZURE_AI_FOUNDRY_API_KEY=<your-key>`
   - `MARSPATH_AZURE_AI_ENABLED=true`
3. Trigger a deploy to activate live GCP connectivity.
