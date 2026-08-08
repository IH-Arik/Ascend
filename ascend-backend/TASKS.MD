# Tasks

## Current Phase

Onboarding flow completion and screenshot parity alignment.

## Active Tasks

- [x] create base folder structure
- [x] create core planning docs
- [x] create governance and workflow docs
- [x] create FastAPI bootstrap files
- [x] create shared config and router setup
- [x] choose database strategy
- [x] add MongoDB + Beanie foundation setup
- [x] implement auth foundation
- [x] implement roles and permission foundation
- [x] add login-screen auth support endpoints and config
- [x] implement first-use onboarding intro and consent APIs
- [x] scaffold phase-1 modules
- [x] review DOCX against Figma screen-by-screen
- [x] update Markdown docs from Figma findings
- [x] implement backend from approved screen mapping

## Phase-1 Module Targets

- [x] auth (email/password only, no CAC/PKI - real login audit trail via `AuditLog` on every attempt, `activation_date`/`deactivation_date` per DOCX's User Profile data dictionary)
- [x] users (sign-in history + admin-led deactivation-request queue - see `admin` line)
- [x] roles
- [x] onboarding
- [x] checkins (daily/Day 0, weekly W1-W10, monthly M1-M10 all built - the daily/weekly/monthly OPS staleness cascade is implemented)
- [x] ops_scoring (`ScoringConfig` versioned/effective-dated admin config, wired into all 4 real OPS-computation call sites; live-verified a real weight change produces the exact manually-calculated OPS score end-to-end)
- [x] dashboards (Home, Trends, Driver Detail, Monthly Review, personal Wellness Report, k-anonymity unit report for end users - SCS/PT/IM/Specialist/Leadership/Admin dashboards from DOCX section 11 not started)
- [x] recommendations (rule-based engine per DOCX section 4 + provider-assigned "Assigned Action" with steps; admin-configurable thresholds not started)
- [x] support_requests (pathway listing + request submission open to all 5 pathways + Level 5 safety-boundary priority flag + provider-side assigned-requests view/status update + My Support Team assignment/toggle/follow-up-status/assigned-action)
- [x] notifications (event-driven in-app only, triggered by check-ins/recommendations/support requests/messages; no scheduler exists yet so cadence-due reminders from `docs/NOTIFICATION_RULES.md` are not generated)
- [x] oft (SCS/Admin scheduling + result recording + user status view + `next_scheduled_relative`; monthly leadership metrics report not started)
- [x] assessments (SCS/Admin scheduling + completion + user status view for DOCX section 8.1; cohort-level 50%/90% compliance rollup and PRS evidence export not started)
- [x] profile (`GET /users/profile` + `PATCH /users/profile/settings` - identity is admin/provisioning-set (no CAC in this project) + user-editable rank_grade/theme/notifications, assigned SCS/PT-IM, communications preference)
- [x] workouts (DOCX section 9 - RPE 1-5 intensity, custom_title for "other", limitation-keyword flag notifying assigned SCS, real adherence/streak; logging + summary only, no plan/program builder per DOCX's own instruction)
- [x] records (NEW module: Records home aggregator, Data-use summary, Reconditioning Plan (PT/IM+SCS-authored), Fly Away Kit (admin-set emergency contacts, never fabricated), Medical Records upload/list/detail/download/review with local-disk Fernet-encrypted storage, malware-scan stub explicitly not a real AV, SCS excluded from raw record access per DOCX)
- [x] messaging (DOCX section 10 - direct messages, OPSEC-scanned + scan-preview, thread pathway context, per-message audit trace + L0-L5 routing-level catalog, encrypted file attachments (PDF/JPG/PNG/HEIC, 20MB, reuses the medical-records storage service under a separate namespace) live-verified; role-based thread visibility needs a provider-assignment/roster system beyond what exists; real-time transport/push notifications/typing indicators/group threads/retention window remain open product decisions, not built)
- [x] audit_logs (append-only `AuditLog` model + service; wired to support-pathway toggles, message sends, safety-boundary flags, and login success/failure - not yet every DOCX-listed auditable event)
- [x] admin (overview placeholder + deactivation-request queue + emergency-contacts config + user role/unit/provider assignment (closes DOCX's "assign roles, coaches, specialists, teams, units" line, role-change/unit-assign/provider-override all live-verified audit logged) + provider credential tracker + Equipment/Supply Gap Tracker (8.7) + Utilization Event tracking + coverage-hours log + 4 quarterly reports (Injury, Assessment Completion, Utilization, PRS/QCP), all live-verified + CSV export with `ReportExport` audit log (DOCX section 12; PDF export not implemented - no PDF library added, documented as a scope decision, not half-built))
- [x] scheduler (`app/core/scheduler.py`, in-process APScheduler daily job proactively firing check-in/OFT/assessment/credential-expiring reminders that previously only fired when a user's own request happened to trigger them; manually run live end-to-end against all real users, credential-expiring notification independently confirmed in the database; single-instance only, not a distributed queue)

## Open Decisions

- [x] PostgreSQL vs MongoDB
- [x] SQLAlchemy vs Beanie
- [x] background job approach (in-process APScheduler, single-instance - would need Celery/RQ + a broker for multi-instance deployment)
- [x] storage provider for documents (local disk, encrypted at rest - dev/prototype choice; migrate to S3/GCS/Azure Blob before production, only `app/services/file_storage_service.py` needs to change)

## Notes

Onboarding baseline now includes question bank, answer persistence, score calculation, provider flags, and AI-ready payload generation.

**2026-08-07: Atlas connectivity restored, full live pass complete.** The scheduler/scoring-config/admin-management/reports batch above is now fully live-verified. One more real bug was caught in the process: 2 pre-existing `WorkoutLog` documents still had old string-based `intensity`/`activity_type` values from before an earlier schema change, crashing on read - fixed with a one-time data migration on just those 2 documents. Full regression: 33 endpoints, all 200.
