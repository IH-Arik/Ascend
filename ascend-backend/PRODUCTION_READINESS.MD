# Production Readiness

## Purpose

Track what must be true before Ascend backend is considered ready for production deployment.

## Application Readiness

- FastAPI app boots reliably
- environment-based configuration is implemented
- structured logging is enabled
- health and readiness checks exist
- background jobs are operational if required

## Security Readiness

- auth and authorization are enforced server-side
- secrets are externalized
- password and token policies are implemented
- upload restrictions are enforced
- sensitive actions are audited

## Data Readiness

- database migrations are repeatable
- seed strategy exists for question banks and required defaults
- backup and restore expectations are defined
- retention-sensitive data handling is documented

## Product Readiness

- onboarding flow works
- Day 0 daily check-in flow works
- OPS scoring is tested
- role-based dashboards are functional
- permission boundaries are verified

## Operational Readiness

- error monitoring is configured
- deployment process is documented
- rollback path is understood
- admin support workflow is documented
- export generation behavior is tested

## Compliance-Sensitive Readiness

- audit log coverage is verified
- medical record governance rules are enforced if that module is active
- export sensitivity rules are implemented
- role-based access reviews are completed

## Release Gate

No production release should happen until high-risk modules have test coverage and major open decisions are resolved.
