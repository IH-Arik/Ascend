# Wellness & Performance Tracking API

Production-oriented FastAPI scaffold for a wellness and performance tracking backend using MongoDB, Beanie, JWT auth, Resend, Anthropic, and AWS S3.

## Stack

- FastAPI
- MongoDB + Beanie ODM
- Pydantic v2 + pydantic-settings
- JWT auth with python-jose and passlib
- Resend for transactional email
- Anthropic Claude API for AI insights
- AWS S3 via boto3

## Structure

The project is organized by core backend layers:

- `app/core` for configuration and security
- `app/db` for MongoDB setup and repositories
- `app/models` for Beanie documents
- `app/schemas` for request and response contracts
- `app/api/v1` for versioned routes
- `app/services` for business service stubs
- `app/utils` for constants and helpers
- `app/tests` for test placeholders

## Run locally

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Notes

- Business logic is intentionally left unimplemented.
- Route handlers currently expose typed stubs only.
- Configure environment values by copying `.env.example` into `.env`.
