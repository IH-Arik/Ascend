# Ascend Backend

FastAPI-based, module-oriented backend scaffold for the Ascend platform.

## Purpose

This repository is intended to support:

- military-oriented readiness workflows
- role-based access for Airman, SCS, PT/IM, Leadership, IDMT, and Admin
- onboarding and check-in flows
- OPS scoring and provider routing
- reporting, auditability, and compliance-sensitive operations

## Current Status

This is an initial architecture scaffold. The folder structure and planning docs are in place so implementation can begin in a controlled way.

## Proposed Stack

- FastAPI
- Pydantic v2
- MongoDB or PostgreSQL
- SQLAlchemy or Beanie depending on final data decision
- JWT auth
- object storage for documents
- background jobs for notifications and exports

## Initial Structure

```text
app/
  api/
  core/
  common/
  modules/
docs/
tests/
scripts/
```

## Bootstrap Status

The repository now includes:

- a FastAPI entrypoint in `app/main.py`
- versioned API router registration
- basic settings loading from `.env`
- standard response envelope helpers
- starter routes for health, auth, users, and admin

## Run Locally

Use the saved Ascend runner so the API starts on `127.0.0.1:8010` by default:

```bash
.venv\Scripts\python.exe run.py
```

Swagger will be available at `http://127.0.0.1:8010/docs`.

## MongoDB Setup Note

Ascend is already wired for MongoDB through `MONGODB_URL` and `MONGODB_DB_NAME`.

- for local MongoDB, keep `MONGODB_URL=mongodb://localhost:27017`
- for MongoDB Atlas, replace `MONGODB_URL` with the full `mongodb+srv://...` connection string
- keep `DB_REQUIRED=false` while credentials are not ready so Swagger and non-database startup can still work
- when MongoDB is ready for full use, set `DB_REQUIRED=true`

## Next Step

Read the files under `docs/` before implementing modules.
