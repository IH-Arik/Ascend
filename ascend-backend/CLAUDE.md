# Claude Working Memory

## Last Updated

- 2026-08-04

## Reviewed Sources

- `1. Final Ascend App Requirements (AC).docx`
- Ascend project Markdown docs under `docs/`
- `UPDATE.MD`
- `TASKS.MD`
- `wellness-backend` reference structure
- onboarding screenshots shared in chat
- source question file: `C:\Users\ittes\Downloads\questions.json`

## What Has Been Implemented

- FastAPI backend scaffold for Ascend
- auth foundation with:
  - register
  - login
  - refresh token
  - email verification code
  - resend verification code
  - forgot password
  - verify reset code
  - reset password
  - set new password
  - current user lookup
- auth screen config endpoint for:
  - remember me
  - help/support text
  - terms/privacy/OPSEC notice metadata
- role and permission foundation
- MongoDB + Beanie setup foundation
- optional database startup mode via `DB_REQUIRED=false`
- fixed local run target to `127.0.0.1:8010`
- Swagger available at `http://127.0.0.1:8010/docs`

## Onboarding Backend Implemented

- first-use status endpoint
- onboarding intro endpoint
- consent submit endpoint
- step-progress save endpoint
- onboarding question-bank endpoint
- onboarding answer save endpoint
- baseline preview endpoint
- baseline complete endpoint

## Onboarding Design Now In Backend

- normalized 20-question onboarding bank based on screenshots + `questions.json`
- separated question types into:
  - scoreable baseline questions
  - context-only questions
  - provider-flag questions
  - follow-up questions
- follow-up modal definitions included for:
  - severity sheet
  - toggle sheet
  - role sheet
  - text sheet

## OPS Scoring Logic Implemented

- scoreable baseline questions convert ordered answers into:
  - `1 / 2 / 3 / 4`
  - then `25 / 50 / 75 / 100`
- component averages are calculated for:
  - Physical Readiness
  - Sleep Readiness
  - Mental Readiness
  - Nutritional Readiness
  - Spiritual Readiness
- weighted OPS formula implemented:
  - `Physical x 0.25`
  - `Sleep x 0.20`
  - `Mental x 0.20`
  - `Nutritional x 0.20`
  - `Spiritual x 0.15`
- baseline band mapping implemented
- confidence label mapping implemented

## AI Payload Shape Implemented

- onboarding completion now builds a structured AI-ready payload containing:
  - trace id
  - user id
  - flow name
  - component scores
  - baseline OPS score
  - confidence
  - normalized answers
  - provider flags
  - follow-up answers

## Important Behavior

- onboarding generates `baseline OPS`
- current OPS is not produced yet from onboarding alone
- docs-aligned behavior: same-day daily check-in is still needed for `current OPS`
- pain/injury and medical-condition style answers are stored as flag/context, not baseline OPS score
- support pathways, top goal, upload preference, and cadence preference are stored for routing/personalization context

## Current Backend Files Touched For This Work

- `app/core/config.py`
- `app/core/database.py`
- `app/core/question_bank.py`
- `app/core/scoring.py`
- `app/core/roles.py`
- `app/models/__init__.py`
- `app/models/onboarding_answer.py`
- `app/models/user.py`
- `app/api/deps.py`
- `app/modules/auth/routes.py`
- `app/modules/onboarding/routes.py`
- `app/modules/roles/routes.py`
- `app/modules/admin/routes.py`
- `app/schemas/onboarding.py`
- `app/services/auth_service.py`
- `app/services/onboarding_service.py`
- `.env`
- `.env.example`
- `run.py`
- `README.md`
- `docs/ENVIRONMENT.md`

## Confirmed Working

- backend compiles with `python -m compileall -q app run.py`
- backend is running on port `8010`
- Swagger shows onboarding routes including:
  - `/api/v1/onboarding/questions`
  - `/api/v1/onboarding/answer`
  - `/api/v1/onboarding/baseline/preview`
  - `/api/v1/onboarding/baseline/complete`

## Known Gaps To Finish Later

- screenshot flow still needs final pass and exact sequencing polish
- follow-up validation can be stricter per question
- provider task/work-item generation not implemented yet
- actual AI call is not implemented yet, only AI-ready payload generation exists
- day-0 daily check-in and current OPS flow still pending
- document upload storage flow still pending
- stronger role-safe onboarding messaging can be added later with dashboard/admin provisioning logic

## Recommended Next Move

- update backend flow to exactly match the final screenshot sequence first
- then close remaining gaps in:
  - follow-up enforcement
  - provider routing tasks
  - AI summary generation
  - daily/current OPS flow
